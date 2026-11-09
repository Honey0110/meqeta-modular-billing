from shared import *

class DatabaseMixin:
    def get_bill_from_database(self, bill_no):
        """
        Fetch the main bill and all its items.

        Returns a dictionary compatible with load_data().
        """

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            if bill_no is None:
                # Highest auto-increment ID = latest inserted bill.
                cursor.execute(
                    "SELECT * FROM bills ORDER BY id DESC LIMIT 1"
                )
            else:
                cursor.execute(
                    "SELECT * FROM bills WHERE bill_no = %s",
                    (bill_no,)
                )

            bill = cursor.fetchone()

            if bill is None:
                return None

            cursor.execute(
                """
                SELECT
                    item_code,
                    item_name,
                    quantity,
                    rate,
                    amount
                FROM bill_items
                WHERE bill_id = %s
                ORDER BY id
                """,
                (bill["id"],)
            )

            items = cursor.fetchall()

            data = {
                "bill": bill["bill_no"],
                "date": sql_date_to_text(
                    bill["bill_date"]
                ),
                "waiter": bill["waiter"] or "",
                "service": bill["service_type"] or "",
                "kot": bill["kot_no"] or "",
                "room": bill["room_no"] or "",
                "reg": bill["reg_no"] or "",
                "guest": bill["guest_name"] or "",
                "company": bill["company"] or "",
                "detail": bill["payment_method"] or "",
                "paid": bool(bill["paid"]),
                "mode": "Current",

                "charges": {
                    "discount": str(
                        bill["discount"] or 0
                    ),
                    "service_charge": str(
                        bill["service_charge"] or 0
                    ),
                    "cgst": str(
                        bill["cgst_rate"] or 0
                    ),
                    "sgst": str(
                        bill["sgst_rate"] or 0
                    ),
                    "cess": str(
                        bill["cess_rate"] or 0
                    )
                },

                "items": []
            }

            for item in items:
                data["items"].append({
                    "code": item["item_code"] or "",
                    "item": item["item_name"] or "",
                    "qty": str(
                        item["quantity"] or 0
                    ),
                    "rate": str(
                        item["rate"] or 0
                    ),
                    "amount": str(
                        item["amount"] or 0
                    )
                })

            return data

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()


    def load_items_by_kot(self, event=None):
        """Fetch the most recently inserted bill matching the entered KOT.

        This updates item rows only; existing bill/header fields stay intact.
        Press Enter in the KOT field to run it.
        """
        if self.automation_running:
            return "break"

        kot = self.v["kot"].get().strip()
        if not kot:
            messagebox.showwarning("KOT Required", "Enter a KOT number first.")
            return "break"

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM bills WHERE kot_no = %s "
                "ORDER BY id DESC LIMIT 1",
                (kot,)
            )
            bill = cursor.fetchone()
            if bill is None:
                messagebox.showinfo("KOT Not Found", f"No saved bill for KOT {kot}.")
                return "break"

            cursor.execute(
                "SELECT item_code, item_name, quantity, rate, amount "
                "FROM bill_items WHERE bill_id = %s ORDER BY id",
                (bill["id"],)
            )
            items = cursor.fetchall()
            if not items:
                messagebox.showinfo("No Items", f"KOT {kot} has no saved items.")
                return "break"

            # Fetch first; only change the form after a successful query.
            while len(self.rows) < len(items):
                self.add_row()
            for row in self.rows:
                for key in self.table_keys:
                    row[key].set("")

            for index, item in enumerate(items):
                row = self.rows[index]
                row["code"].set(str(item["item_code"] or ""))
                row["item"].set(str(item["item_name"] or ""))
                row["qty"].set(str(item["quantity"] if item["quantity"] is not None else ""))
                row["rate"].set(str(item["rate"] if item["rate"] is not None else ""))
                # Amount is recalculated by calculate() from Qty * Rate.

            self.calculate()
            self.status.set(f"Loaded {len(items)} item(s) for KOT {kot}.")
            return "break"

        except (Error, RuntimeError, ValueError) as error:
            messagebox.showerror("KOT Database Error", str(error))
            return "break"
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()


    def get_latest_bill_from_database(self):
        """Return the newest inserted bill and its associated items."""
        return self.get_bill_from_database(None)


    def bill_exists(self, bill_no):
        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                "SELECT id FROM bills WHERE bill_no = %s",
                (bill_no,)
            )

            return cursor.fetchone() is not None

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()


    def save_bill(self):
        if self.automation_running:
            return

        data = self.collect_data()
        bill_no = data["bill"].strip()

        if not bill_no:
            messagebox.showwarning(
                "Save",
                "Bill No is required."
            )
            return

        connection = None
        cursor = None

        try:
            bill_date = optional_sql_date(
                data["date"]
            )

            # Validate item values before writing.
            for index, item in enumerate(
                data["items"], start=1
            ):
                for key in ("qty", "rate"):
                    raw = item[key].strip()

                    if raw:
                        try:
                            value = Decimal(raw)

                            if (
                                not value.is_finite()
                                or value < 0
                            ):
                                raise ValueError

                        except (
                            InvalidOperation,
                            ValueError
                        ):
                            raise ValueError(
                                f"Invalid {key} in "
                                f"item row {index}."
                            )

            connection = get_db_connection()
            connection.start_transaction()

            cursor = connection.cursor()

            # Lock an existing bill during update.
            cursor.execute(
                """
                SELECT id
                FROM bills
                WHERE bill_no = %s
                FOR UPDATE
                """,
                (bill_no,)
            )

            existing = cursor.fetchone()

            values = (
                bill_date,
                data["waiter"],
                data["service"],
                data["kot"],
                data["room"],
                data["reg"],
                data["guest"],
                data["company"],
                data["detail"],
                int(data["paid"]),
                num(data["totals"]["total"]),
                num(data["charges"]["discount"]),
                num(data["charges"]["service_charge"]),
                num(data["charges"]["cgst"]),
                num(data["charges"]["sgst"]),
                num(data["charges"]["cess"]),
                num(data["totals"]["net"])
            )

            if existing:
                bill_id = existing[0]

                if not messagebox.askyesno(
                    "Overwrite",
                    f"Bill {bill_no} already exists.\n"
                    "Overwrite it?"
                ):
                    connection.rollback()
                    return

                cursor.execute(
                    """
                    UPDATE bills
                    SET
                        bill_date = %s,
                        waiter = %s,
                        service_type = %s,
                        kot_no = %s,
                        room_no = %s,
                        reg_no = %s,
                        guest_name = %s,
                        company = %s,
                        payment_method = %s,
                        paid = %s,
                        subtotal = %s,
                        discount = %s,
                        service_charge = %s,
                        cgst_rate = %s,
                        sgst_rate = %s,
                        cess_rate = %s,
                        net_amount = %s
                    WHERE id = %s
                    """,
                    values + (bill_id,)
                )

                cursor.execute(
                    """
                    DELETE FROM bill_items
                    WHERE bill_id = %s
                    """,
                    (bill_id,)
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO bills (
                        bill_no,
                        bill_date,
                        waiter,
                        service_type,
                        kot_no,
                        room_no,
                        reg_no,
                        guest_name,
                        company,
                        payment_method,
                        paid,
                        subtotal,
                        discount,
                        service_charge,
                        cgst_rate,
                        sgst_rate,
                        cess_rate,
                        net_amount
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (bill_no,) + values
                )

                bill_id = cursor.lastrowid

            for item in data["items"]:
                qty = num(item["qty"])
                rate = num(item["rate"])

                amount = (
                    qty * rate
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )

                cursor.execute(
                    """
                    INSERT INTO bill_items (
                        bill_id,
                        item_code,
                        item_name,
                        quantity,
                        rate,
                        amount
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        bill_id,
                        item["code"],
                        item["item"],
                        qty,
                        rate,
                        amount
                    )
                )

            connection.commit()

            self.status.set(
                f"Bill {bill_no} saved to MariaDB."
            )

            messagebox.showinfo(
                "Saved",
                f"Bill {bill_no} saved successfully."
            )

        except (Error, RuntimeError, ValueError) as error:
            if connection is not None:
                connection.rollback()

            messagebox.showerror(
                "Database Error",
                str(error)
            )

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()


    def find_bill(self):
        if self.automation_running:
            return

        bill_no = simpledialog.askstring(
            "Find Bill",
            "Enter Bill No:",
            parent=self.root
        )

        if not bill_no:
            return

        bill_no = bill_no.strip()

        try:
            data = self.get_bill_from_database(
                bill_no
            )

            if data is None:
                messagebox.showinfo(
                    "Find",
                    "Bill not found in MariaDB."
                )
                return

            self.load_data(data)

            self.status.set(
                f"Loaded bill {bill_no} from MariaDB."
            )

        except (Error, RuntimeError, ValueError) as error:
            messagebox.showerror(
                "Database Error",
                str(error)
            )


    def clone_bill(self):
        if self.automation_running:
            return

        old_bill = self.v["bill"].get().strip()

        if not old_bill:
            messagebox.showwarning(
                "Clone",
                "Enter the original Bill No first."
            )
            return

        try:
            original = self.get_bill_from_database(
                old_bill
            )

            if original is None:
                messagebox.showwarning(
                    "Clone",
                    "Original bill not found in MariaDB."
                )
                return

            new_bill = simpledialog.askstring(
                "Clone Bill",
                "Enter new Bill No:",
                parent=self.root
            )

            if not new_bill:
                return

            new_bill = new_bill.strip()

            if not new_bill:
                messagebox.showwarning(
                    "Clone",
                    "New Bill No cannot be empty."
                )
                return

            if self.bill_exists(new_bill):
                messagebox.showwarning(
                    "Clone",
                    "New Bill No already exists."
                )
                return

            cloned = copy.deepcopy(original)
            cloned["bill"] = new_bill

            self.load_data(cloned)

            self.status.set(
                f"Cloned {old_bill} to {new_bill}. "
                "Click Save."
            )

            messagebox.showinfo(
                "Clone",
                "Bill cloned.\nClick Save to store it."
            )

        except (Error, RuntimeError, ValueError) as error:
            messagebox.showerror(
                "Database Error",
                str(error)
            )


    def delete_bill(self):
        if self.automation_running:
            return

        bill_no = self.v["bill"].get().strip()

        if not bill_no:
            messagebox.showwarning(
                "Delete",
                "Enter the Bill No."
            )
            return

        if not messagebox.askyesno(
            "Delete",
            f"Delete bill {bill_no} permanently?"
        ):
            return

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            connection.start_transaction()

            cursor = connection.cursor()

            cursor.execute(
                """
                DELETE FROM bills
                WHERE bill_no = %s
                """,
                (bill_no,)
            )

            deleted = cursor.rowcount

            connection.commit()

            if deleted == 0:
                messagebox.showinfo(
                    "Delete",
                    "Bill not found."
                )
                return

            # bill_items are deleted automatically
            # through the ON DELETE CASCADE relation.
            self.clear_form()

            self.status.set(
                f"Bill {bill_no} deleted from MariaDB."
            )

            messagebox.showinfo(
                "Deleted",
                f"Bill {bill_no} deleted successfully."
            )

        except (Error, RuntimeError) as error:
            if connection is not None:
                connection.rollback()

            messagebox.showerror(
                "Database Error",
                str(error)
            )

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

