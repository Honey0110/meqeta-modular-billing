
# PMS automation for the MEQETA billing application.
# This file keeps the original logic intact; only explanatory comments were added.
# Dependencies, constants, and helper functions are imported from shared.py.
# External automation uses the currently focused window: verify focus before running.

from shared import *

class AutomationMixin:
    # ==================================================================
    # MAIN ENTRY POINT: LOAD BILL BY KOT
    # Ask for a KOT, locate its unique bill, load bill/items, validate PMS fields and schedule automation.
    # ==================================================================
    def fill_to_pms(self):
        """Fetch bill by KOT, load bill header AND its items, then fill PMS."""
        if self.automation_running:
            return

        # Ask for the KOT number; cancelling leaves the current bill untouched.
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
            # Open a database connection and look up bills matching this KOT.
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
            # A KOT matching multiple bills is ambiguous: do not choose silently.
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
            # Retrieve the full bill, including its item rows.
            data = self.get_bill_from_database(bill_no)
            if data is None:
                messagebox.showwarning("Not Found", f"Bill {bill_no} not found.")
                return
            automation_data = {
                key: str(data.get(key) or "").strip() for key in PMS_FIELDS
            }
            # All required PMS fields must be present before automation starts.
            missing = [key for key, value in automation_data.items() if not value]
            if missing:
                messagebox.showwarning("Missing PMS Data", ", ".join(missing))
                return
            automation_data["date"] = normalize_date(automation_data["date"])

           # Load the bill header and item rows from the database.
            self.load_data(data)

# Keep the data available for PMS automation.
            self.pending_bill_data = data
            self.automation_data = automation_data

# Update totals.
            self.calculate()

          # Bill fields and item rows will be filled
          # progressively by the automation functions.
            self.status.set(
                f"Loaded bill {bill_no}, KOT {kot}, "
                f"{len(data.get('items', []))} item(s) from MariaDB."
            )
        except (Error, RuntimeError, ValueError) as error:
            messagebox.showerror("Database Error", str(error))
            return

        # Mark automation active and delay target detection to allow focus changes.
        self.automation_running = True
        self.external_cancel.clear()
        # Increment the token so callbacks from older runs cannot continue.
        self.automation_token += 1
        token = self.automation_token
        self.finish_automation("Internal automation completed."
            )
        return

        # Follow the configured PMS_FIELDS order rather than widget layout order.
        key = PMS_FIELDS[self.automation_index]
        value = self.automation_data[key]

        widget = self.fields[key]
        widget.focus_set()

        if key in DROPDOWN_FIELDS:
            self.select_internal_dropdown(
                key, value, token
            )
            return

        # Type the field value character by character.
            self.type_internal_text(
                key,
                value,
                token,
            self.next_internal_field)
        return

        try:
            widget.icursor("end")
        except tk.TclError:
            pass

        self.status.set(
            f"Filled {key.upper()}: {value}"
        )

        self.next_internal_field(token)


    # ==================================================================
    # VISIBLE DROPDOWN SELECTION
    # Open the dropdown briefly, select the matching option, then proceed to the next field.
    # ==================================================================
    
    def type_internal_text(self, key, value, token, on_complete):
        """
        Visibly type Bill No and KOT No.
        Each character appears after 120 milliseconds.
        """

        # Get the correct input field.
        widget = self.fields[key]
        widget.focus_set()

        # Clear the existing field.
        self.v[key].set("")
        value = str(value)

        def type_character(index=0):
            """Type one character at a time."""

            # Stop if the automation was cancelled.
            if token != self.automation_token:
                return

            if not self.automation_running:
                return

            # Move to the next field when typing finishes.
            if index >= len(value):
                on_complete(token)
                return

            # Display the next character.
            self.v[key].set(value[:index + 1])

            # Wait 120 ms before typing again.
            self.automation_job = self.root.after(
                120,
                lambda: type_character(index + 1)
            )

        # Start the typing animation.
        type_character()

    
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
            # Attempt to show the dropdown before selecting its value.
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

        self.external_thread.start()


    # ==================================================================
    # EXTERNAL FIELD SEQUENCE
    # Send bill, date, waiter, service and KOT, advancing with the configured key.
    # ==================================================================
    def external_worker(self, data, token):
        """
        External PMS sequence:

        Bill -> Enter -> Date -> Enter ->
        Waiter -> Enter -> Service -> Enter -> KOT

        IMPORTANT:
        The external PMS Bill No field must have
        keyboard focus when automation starts.
        """

        try:
            # External target must start with keyboard focus on its Bill field.
            sequence = [
                ("bill", data["bill"]),
                ("date", data["date"]),
                ("waiter", data["waiter"]),
                ("service", data["service"]),
                ("kot", data["kot"])
            ]

            for index, (key, value) in enumerate(sequence):
                if self.external_cancel.is_set():
                    return

                if key in DROPDOWN_FIELDS:
                    self.fill_external_dropdown(value)
                else:
                    self.fill_external_text(value)

                if index < len(sequence) - 1:
                    if self.external_cancel.wait(
                        EXTERNAL_FIELD_DELAY
                    ):
                        return

                    pyautogui.press(EXTERNAL_NEXT_KEY)

            if not self.external_cancel.is_set():
                self.external_results.put(
                    (
                        token,
                        True,
                        "External PMS automation completed."
                    )
                )

        except Exception as error:
            if not self.external_cancel.is_set():
                self.external_results.put(
                    (token, False, str(error))
                )


    # ==================================================================
    # EXTERNAL TEXT INPUT
    # Replace the currently focused field using clipboard paste (Ctrl+A then Ctrl+V).
    # ==================================================================
    def fill_external_text(self, value):
        # Current implementation pastes text; it does not simulate character typing.
        pyperclip.copy(str(value))
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "v")


    # ==================================================================
    # EXTERNAL DROPDOWN INPUT
    # Open the active dropdown, wait briefly, and type its value.
    # ==================================================================
    def fill_external_dropdown(self, value):
        # Request the target application to open its dropdown.
        pyautogui.hotkey("alt", "down")

        if self.external_cancel.wait(
            EXTERNAL_DROPDOWN_DELAY
        ):
            return

        pyautogui.write(
            str(value),
            interval=0.04
        )
# ==================================================================
    # THREAD RESULT POLLING
    # Read background-worker results safely on the Tkinter UI thread.
    # ==================================================================
    def poll_external_results(self):
        if self.closing:
            return

        try:
            # Drain all available completion/error messages without blocking.
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


    # ==================================================================
    # ENABLE OR DISABLE UI CONTROLS
    # Prevent competing actions while automation is running.
    # ==================================================================
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


    # ==================================================================
    # AUTOMATION COMPLETION
    # Reset running state, restore buttons, update status and report errors.
    # ==================================================================
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


    # ==================================================================
    # CANCEL AUTOMATION
    # Invalidate scheduled callbacks, signal the worker and cancel pending Tkinter jobs.
    # ==================================================================
    def cancel_automation(self):
        # Increment the token so callbacks from older runs cannot continue.
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

