from shared import *

class BillingMixin:
    def calculate(self):
        qty_total = Decimal("0")
        subtotal = Decimal("0")

        for row in self.rows:
            qty = num(row["qty"].get())
            rate = num(row["rate"].get())

            if row["qty"].get().strip():
                qty_total += qty

            if (
                row["qty"].get().strip()
                and row["rate"].get().strip()
            ):
                amount = qty * rate
                row["amount"].set(money(amount))
                subtotal += amount

            else:
                row["amount"].set("")

        discount = num(
            self.charges["discount"].get()
        )

        service = num(
            self.charges["service_charge"].get()
        )

        taxable = max(
            Decimal("0"),
            subtotal - discount + service
        )

        taxes = {}

        for key in ("cgst", "sgst", "cess"):
            taxes[key] = (
                taxable
                * num(self.charges[key].get())
                / Decimal("100")
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

            self.totals[
                key + "_amount"
            ].set(money(taxes[key]))

        gross = taxable + sum(
            taxes.values(),
            Decimal("0")
        )

        net = gross.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )

        self.totals["qty"].set(str(qty_total))
        self.totals["total"].set(money(subtotal))

        self.totals["round_off"].set(
            money(net - gross)
        )

        self.totals["net"].set(money(net))


    def collect_data(self):
        data = {
            key: variable.get()
            for key, variable in self.v.items()
        }

        data["mode"] = self.mode.get()
        data["paid"] = self.paid.get()

        data["charges"] = {
            key: variable.get()
            for key, variable in self.charges.items()
        }

        data["totals"] = {
            key: variable.get()
            for key, variable in self.totals.items()
        }

        data["items"] = []

        for row in self.rows:
            item = {
                key: variable.get()
                for key, variable in row.items()
            }

            if any(
                item[key].strip()
                for key in self.table_keys
            ):
                data["items"].append(item)

        return data


    def load_data(self, data):
        self.clear_form()

        for key in self.v:
            if key in data and key != "time":
                self.v[key].set(data[key])

        for key in DROPDOWN_FIELDS:
            value = self.v[key].get()

            if value:
                widget = self.fields[key]
                options = list(widget["values"])

                if value not in options:
                    options.append(value)
                    widget["values"] = options

        self.mode.set(
            data.get("mode", "Current")
        )

        self.paid.set(
            bool(data.get("paid", False))
        )

        for key, value in data.get(
            "charges", {}
        ).items():
            if key in self.charges:
                self.charges[key].set(str(value))

        items = data.get("items", [])

        while len(self.rows) < len(items):
            self.add_row()

        for index, item in enumerate(items):
            for key in self.table_keys:
                self.rows[index][key].set(
                    str(item.get(key, ""))
                )

        self.calculate()


    def clear_form(self):
        if self.automation_running:
            return

        for key, variable in self.v.items():
            if key != "time":
                variable.set("")

        self.mode.set("Current")
        self.paid.set(False)

        for variable in self.charges.values():
            variable.set("0")

        for row in self.rows:
            for variable in row.values():
                variable.set("")

        self.calculate()
        self.status.set("Ready")


    def summary(self):
        data = self.collect_data()

        window = tk.Toplevel(self.root)
        window.title("Bill Summary")
        window.geometry("650x500")

        text = tk.Text(
            window,
            font=("Consolas", 10),
            wrap="word"
        )

        text.pack(
            fill="both",
            expand=True
        )

        text.insert(
            "end",
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )
        )

        text.config(state="disabled")


    def print_bill(self):
        data = self.collect_data()

        window = tk.Toplevel(self.root)
        window.title("Print Preview")
        window.geometry("650x550")

        text = tk.Text(
            window,
            font=("Consolas", 10)
        )

        text.pack(
            fill="both",
            expand=True
        )

        text.insert(
            "end",
            "FOOD & BEVERAGES BILL\n"
            "============================\n\n"
        )

        for key in (
            "bill",
            "date",
            "waiter",
            "service",
            "room",
            "reg",
            "kot",
            "guest"
        ):
            text.insert(
                "end",
                f"{key.upper()}: "
                f"{data.get(key, '')}\n"
            )

        text.insert(
            "end",
            "\nITEMS\n"
            "----------------------------\n"
        )

        for item in data["items"]:
            text.insert(
                "end",
                f"{item['item']} "
                f"{item['qty']} x "
                f"{item['rate']} "
                f"= {item['amount']}\n"
            )

        text.insert(
            "end",
            "\nNET AMOUNT: "
            + data["totals"]["net"]
        )

