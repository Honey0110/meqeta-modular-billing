from shared import *
import pyautogui

# Time to switch focus from the billing app to another application.
FOCUS_SWITCH_DELAY_MS = 5000
TYPE_INTERVAL_SECONDS = 0.12


class AutomationMixin:
    def fill_to_pms(self):
        """Fetch bill by KOT, load bill header AND its items, then fill PMS."""
        if self.automation_running:
            return

        kot = simpledialog.askstring(
            "Fill to PMS", "Enter KOT Number:",
            initialvalue=self.v["kot"].get().strip(), parent=self.root
        )
        if kot is None:
            return
        kot = kot.strip()
        if not kot:
            messagebox.showwarning("KOT Required", "Enter a KOT number.")
            return

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, bill_no FROM bills WHERE kot_no = %s ORDER BY id DESC",
                (kot,)
            )
            matches = cursor.fetchall()
            if not matches:
                messagebox.showwarning("KOT Not Found", f"No bill found for KOT {kot}.")
                return
            if len(matches) != 1:
                messagebox.showwarning(
                    "Ambiguous KOT",
                    f"KOT {kot} belongs to {len(matches)} bills. "
                    "Please find the correct bill by bill number first."
                )
                return
            bill_no = str(matches[0]["bill_no"])
        except (Error, RuntimeError) as error:
            messagebox.showerror("Database Error", str(error))
            return
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

        try:
            data = self.get_bill_from_database(bill_no)
            if data is None:
                messagebox.showwarning("Not Found", f"Bill {bill_no} not found.")
                return
            automation_data = {
                key: str(data.get(key) or "").strip() for key in PMS_FIELDS
            }
            missing = [key for key, value in automation_data.items() if not value]
            if missing:
                messagebox.showwarning("Missing PMS Data", ", ".join(missing))
                return
            automation_data["date"] = normalize_date(automation_data["date"])

            # load_data() clears old rows and populates Code/Item/Qty/Rate.
            # calculate() derives Amount and all totals from those values.
            self.load_data(data)
            self.pending_bill_data = data
            self.automation_data = automation_data
            self.calculate()
            self.status.set(
                f"Loaded bill {bill_no}, KOT {kot}, "
                f"{len(data.get('items', []))} item(s) from MariaDB."
            )
        except (Error, RuntimeError, ValueError) as error:
            messagebox.showerror("Database Error", str(error))
            return

        self.automation_running = True
        self.external_cancel.clear()
        self.automation_token += 1
        token = self.automation_token
        self.set_controls(False)
        self.automation_job = self.root.after(
            FOCUS_SWITCH_DELAY_MS, lambda: self.detect_target(token)
        )


    def detect_target(self, token):
        if token != self.automation_token:
            return

        if not self.automation_running:
            return

        self.automation_job = None

        active_handle = active_window_handle()

        try:
            own_handle = self.root.winfo_id()

            own_root = root_window_handle(
                own_handle
            )

            active_root = root_window_handle(
                active_handle
            )

            is_internal = (
                active_root == own_root
                and active_root is not None
            )

        except tk.TclError:
            is_internal = False

        if is_internal or sys.platform != "win32":
            self.start_internal_automation(token)
        else:
            self.start_external_automation(token)


    def start_internal_automation(self, token):
        self.automation_index = 0

        for key in DROPDOWN_FIELDS:
            widget = self.fields[key]
            options = list(widget["values"])
            value = self.automation_data[key]

            match = next(
                (
                    option for option in options
                    if str(option).casefold()
                    == str(value).casefold()
                ),
                None
            )

            if match is None:
                options.append(value)
                widget["values"] = options
            else:
                self.automation_data[key] = match

        self.status.set(
            "Internal automation started..."
        )

        self.fill_internal_field(token)


    def fill_internal_field(self, token):
        if token != self.automation_token:
            return

        if not self.automation_running:
            return

        self.automation_job = None

        if self.automation_index >= len(PMS_FIELDS):
            self.finish_automation(
                "Internal automation completed."
            )
            return

        key = PMS_FIELDS[self.automation_index]
        value = self.automation_data[key]

        widget = self.fields[key]
        widget.focus_set()

        if key in DROPDOWN_FIELDS:
            self.select_internal_dropdown(
                key, value, token
            )
            return

        # Show each character instead of instantly assigning the value.
        self.type_internal_text(key, value, token)


    def type_internal_text(self, key, value, token):
        """Animate a header field without blocking the Tkinter event loop."""
        self.v[key].set("")
        value = str(value)

        def write_next(index=0):
            if token != self.automation_token or not self.automation_running:
                return
            if index >= len(value):
                self.status.set(f"Typed {key.upper()}: {value}")
                self.next_internal_field(token)
                return
            self.v[key].set(value[:index + 1])
            self.automation_job = self.root.after(
                120, lambda: write_next(index + 1)
            )

        write_next()


    def select_internal_dropdown(
        self, key, value, token
    ):
        widget = self.fields[key]
        options = list(widget["values"])

        index = next(
            (
                i for i, option in enumerate(options)
                if str(option).casefold()
                == str(value).casefold()
            ),
            None
        )

        if index is None:
            options.append(value)
            widget["values"] = options
            index = len(options) - 1

        try:
            widget.event_generate("<Alt-Down>")
        except tk.TclError:
            pass

        def choose_option():
            if token != self.automation_token:
                return

            if not self.automation_running:
                return

            self.automation_job = None

            widget.current(index)

            try:
                widget.event_generate("<Escape>")
            except tk.TclError:
                pass

            self.status.set(
                f"Selected {key.upper()}: {value}"
            )

            self.next_internal_field(token)

        self.automation_job = self.root.after(
            INTERNAL_DROPDOWN_HOLD_MS,
            choose_option
        )


    def next_internal_field(self, token):
        self.automation_index += 1

        if self.automation_index >= len(PMS_FIELDS):
            self.fields["kot"].focus_set()

            self.finish_automation(
                "Internal automation completed."
            )
            return

        self.automation_job = self.root.after(
            INTERNAL_FIELD_DELAY_MS,
            lambda: self.fill_internal_field(token)
        )


    def start_external_automation(self, token):
        self.status.set(
            "External PMS automation started..."
        )

        data = dict(self.automation_data)
        # Take a snapshot of item data before the worker thread starts.
        data["_items"] = list(self.pending_bill_data.get("items", []))

        self.external_thread = threading.Thread(
            target=self.external_worker,
            args=(data, token),
            daemon=True
        )

        self.external_thread.start()


    def external_worker(self, data, token):
        """Type into the external window that had focus after the switch delay.

        Enter navigation depends on the target application's keyboard behavior.
        The worker never manipulates Tkinter widgets directly.
        """
        try:
            sequence = [(key, data[key]) for key in PMS_FIELDS]
            items = data.get("_items", [])
            # Header fields: Bill, Date, Waiter, Service, KOT.
            for key, value in sequence:
                if self.external_cancel.is_set():
                    return
                if key in DROPDOWN_FIELDS:
                    if not self.fill_external_dropdown(value):
                        return
                else:
                    self.fill_external_text(value)
                if self.external_cancel.wait(EXTERNAL_FIELD_DELAY):
                    return
                pyautogui.press(EXTERNAL_NEXT_KEY)

            # Item rows: Code, Item, Qty, Rate, Amount.
            # Assumes each Enter moves to the next cell, including the next row.
            for item in items:
                if self.external_cancel.is_set():
                    return
                if not isinstance(item, dict):
                    raise ValueError("Item row is not a dictionary; check database item format")
                code = item.get("code", "")
                name = item.get("item", item.get("name", ""))
                qty = item.get("qty", item.get("quantity", ""))
                rate = item.get("rate", "")
                amount = item.get("amount")
                if amount is None or amount == "":
                    try:
                        amount = f"{float(qty) * float(rate):.2f}"
                    except (TypeError, ValueError):
                        amount = ""
                for value in (code, name, qty, rate, amount):
                    if self.external_cancel.is_set():
                        return
                    self.fill_external_text(value)
                    if self.external_cancel.wait(EXTERNAL_FIELD_DELAY):
                        return
                    pyautogui.press(EXTERNAL_NEXT_KEY)

            if not self.external_cancel.is_set():
                self.external_results.put((token, True, "External PMS automation completed."))
        except Exception as error:
            if not self.external_cancel.is_set():
                self.external_results.put((token, False, str(error)))

    def fill_external_text(self, value):
        """Type rather than paste into the currently focused external field."""
        pyautogui.write(str(value), interval=TYPE_INTERVAL_SECONDS)

    def fill_external_dropdown(self, value):
        """Open a dropdown and type its value (target-specific behavior)."""
        pyautogui.hotkey("alt", "down")
        if self.external_cancel.wait(EXTERNAL_DROPDOWN_DELAY):
            return False
        pyautogui.write(str(value), interval=TYPE_INTERVAL_SECONDS)
        # Do not press Enter here: external_worker handles navigation.
        return True


    def poll_external_results(self):
        if self.closing:
            return

        try:
            while True:
                token, success, message = (
                    self.external_results.get_nowait()
                )

                if token == self.automation_token:
                    self.finish_automation(
                        message, success
                    )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self.poll_external_results
        )


    def set_controls(self, enabled):
        state = (
            "normal" if enabled else "disabled"
        )

        self.pms_button.config(
            state=state,
            text=(
                "Fill to PMS"
                if enabled
                else "Filling..."
            )
        )

        for button in self.action_buttons:
            button.config(state=state)


    def finish_automation(
        self, message, success=True
    ):
        if self.closing:
            return

        self.automation_running = False
        self.automation_job = None

        self.set_controls(True)
        self.status.set(message)

        if not success:
            messagebox.showerror(
                "Automation Error",
                message
            )


    def cancel_automation(self):
        self.automation_token += 1
        self.external_cancel.set()

        if self.automation_job is not None:
            try:
                self.root.after_cancel(
                    self.automation_job
                )
            except tk.TclError:
                pass

        self.automation_job = None
        self.automation_running = False

