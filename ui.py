from shared import *

class UiMixin:
    def __init__(self, root):
        self.root = root

        self.root.title(
            "Food & Beverages Billing Entry"
        )

        self.root.geometry("1180x780")
        self.root.minsize(1050, 680)

        self.bg = "#e8e8e8"
        self.blue = "#253e70"

        self.root.configure(bg=self.bg)

        names = [
            "bill",
            "date",
            "time",
            "waiter",
            "service",
            "room",
            "reg",
            "kot",
            "guest",
            "company",
            "arrival",
            "arrival_time",
            "departure",
            "departure_time",
            "stay",
            "detail"
        ]

        self.v = {
            key: tk.StringVar()
            for key in names
        }

        self.mode = tk.StringVar(value="Current")
        self.paid = tk.BooleanVar(value=False)

        self.charges = {
            key: tk.StringVar(value="0")
            for key in (
                "discount",
                "service_charge",
                "cgst",
                "sgst",
                "cess"
            )
        }

        self.totals = {
            key: tk.StringVar(value="0.00")
            for key in (
                "qty",
                "total",
                "cgst_amount",
                "sgst_amount",
                "cess_amount",
                "round_off",
                "net"
            )
        }

        self.fields = {}
        self.rows = []
        self.cells = []
        self.row_frames = []
        self.action_buttons = []

        self.table_keys = (
            "code",
            "item",
            "qty",
            "rate"
        )

        self.status = tk.StringVar(value="Ready")

        # Automation state.
        self.automation_running = False
        self.automation_job = None
        self.automation_token = 0
        self.automation_index = 0
        self.automation_data = {}

        self.external_cancel = threading.Event()
        self.external_thread = None
        self.external_results = queue.Queue()

        self.closing = False

        # Extra fields retained in memory because the
        # existing SQL schema does not contain them.
        self.extra_data = {}

        # Build original interface.
        self.build_ui()
        self.bind_navigation()
        # Enter in the KOT field fetches its saved item rows.
        self.fields["kot"].bind("<Return>", self.load_items_by_kot)

        for variable in self.charges.values():
            variable.trace_add(
                "write",
                lambda *_: self.calculate()
            )

        self.calculate()
        self.clock()
        self.poll_external_results()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close_app
        )

        self.root.after(
            300,
            self.check_database_on_start
        )


    def check_database_on_start(self):
        if test_database_connection():
            self.status.set(
                "MariaDB connected - meqeta_billing"
            )
        else:
            self.status.set(
                "Database connection unavailable"
            )


    def label(self, parent, text, x, y, width=90):
        tk.Label(
            parent,
            text=text,
            bg=self.bg,
            fg=self.blue,
            anchor="e",
            font=("Arial", 9, "bold")
        ).place(
            x=x,
            y=y,
            width=width,
            height=24
        )


    def entry(self, parent, key, x, y, width):
        widget = tk.Entry(
            parent,
            textvariable=self.v[key],
            font=("Arial", 10)
        )

        widget.place(
            x=x,
            y=y,
            width=width,
            height=24
        )

        self.fields[key] = widget
        return widget


    def combo(
        self,
        parent,
        key,
        values,
        x,
        y,
        width,
        readonly=False
    ):
        widget = ttk.Combobox(
            parent,
            textvariable=self.v[key],
            values=values,
            state=(
                "readonly"
                if readonly
                else "normal"
            ),
            font=("Arial", 10)
        )

        widget.place(
            x=x,
            y=y,
            width=width,
            height=24
        )

        self.fields[key] = widget
        return widget


    def build_ui(self):
        top = tk.Frame(
            self.root,
            bg=self.bg,
            height=215
        )

        top.pack(
            side="top",
            fill="x",
            padx=12,
            pady=(8, 0)
        )

        top.pack_propagate(False)

        self.pms_button = tk.Button(
            top,
            text="Fill to PMS",
            command=self.fill_to_pms,
            bg="#a9d2f0",
            fg="#17365d",
            font=("Arial", 10, "bold"),
            cursor="hand2"
        )

        self.pms_button.place(
            relx=1,
            x=-160,
            y=8,
            width=150,
            height=35
        )

        tk.Label(
            top,
            textvariable=self.status,
            bg=self.bg,
            fg="#247044",
            anchor="e",
            font=("Arial", 9)
        ).place(
            relx=1,
            x=-380,
            y=48,
            width=370,
            height=22
        )

        # Bill number.
        self.label(top, "Bill No :", 0, 10)
        self.entry(top, "bill", 95, 10, 110)

        tk.Button(
            top,
            text="Adding",
            command=self.summary,
            bg="#e9b5bb"
        ).place(
            x=215,
            y=8,
            width=85,
            height=29
        )

        tk.Radiobutton(
            top,
            text="Current",
            variable=self.mode,
            value="Current",
            bg=self.bg
        ).place(x=310, y=10)

        tk.Radiobutton(
            top,
            text="Previous",
            variable=self.mode,
            value="Previous",
            bg=self.bg
        ).place(x=390, y=10)

        # Date dropdown.
        self.label(top, "Date :", 0, 47)

        self.combo(
            top,
            "date",
            generate_date_options(),
            95, 47, 135,
            readonly=True
        )

        tk.Label(
            top,
            textvariable=self.v["time"],
            bg="white",
            relief="sunken"
        ).place(
            x=240,
            y=47,
            width=100,
            height=24
        )

        # Waiter dropdown.
        self.label(top, "Waiter :", 0, 84)

        self.combo(
            top,
            "waiter",
            ["AKASH", "RAHUL", "AMIT", "JOHN"],
            95, 84, 195,
            readonly=True
        )

        self.label(top, "Room No :", 300, 84, 90)

        self.combo(
            top,
            "room",
            ["101", "102", "201", "202"],
            395, 84, 100
        )

        # Service type.
        self.label(top, "Ser. Type :", 0, 121)

        self.combo(
            top,
            "service",
            [
                "FOOD & BEVERAGES",
                "ROOM SERVICE",
                "RESTAURANT",
                "TAKE AWAY"
            ],
            95, 121, 195,
            readonly=True
        )

        self.label(top, "Reg No :", 300, 121, 90)
        self.entry(top, "reg", 395, 121, 100)

        # KOT.
        self.label(top, "KOT No :", 0, 158)
        self.entry(top, "kot", 95, 158, 125)

        # Guest details.
        ttk.Separator(
            top,
            orient="vertical"
        ).place(
            x=510,
            y=5,
            height=195
        )

        self.label(top, "Guest :", 520, 10)
        self.entry(top, "guest", 615, 10, 350)

        self.label(top, "Company :", 520, 47)
        self.entry(top, "company", 615, 47, 350)

        self.label(top, "Arr. Date :", 520, 84)
        self.entry(top, "arrival", 615, 84, 125)
        self.entry(
            top,
            "arrival_time",
            748, 84, 85
        )

        self.label(top, "Dep. Date :", 520, 121)
        self.entry(
            top,
            "departure",
            615, 121, 125
        )
        self.entry(
            top,
            "departure_time",
            748, 121, 85
        )

        self.label(top, "Stay Plan :", 520, 158)

        self.combo(
            top,
            "stay",
            ["MAP", "AP", "CP", "EP"],
            615, 158, 150
        )

        bottom = tk.Frame(
            self.root,
            bg=self.bg,
            height=215
        )

        bottom.pack(
            side="bottom",
            fill="x",
            padx=12,
            pady=6
        )

        bottom.pack_propagate(False)

        self.create_bottom(bottom)
        self.create_table()


    def create_bottom(self, parent):
        self.label(
            parent, "Detail :", 0, 8, 75
        )

        self.combo(
            parent,
            "detail",
            [
                "Cash",
                "Card",
                "UPI",
                "Room Charge",
                "Credit",
                "Other"
            ],
            80, 8, 330
        )

        tk.Checkbutton(
            parent,
            text="Bill Paid",
            variable=self.paid,
            bg=self.bg
        ).place(x=80, y=45)

        buttons = [
            ("Save", self.save_bill),
            ("Delete", self.delete_bill),
            ("Clear", self.clear_form),
            ("Find", self.find_bill),
            ("Print", self.print_bill),
            ("Exit", self.close_app)
        ]

        for index, (name, command) in enumerate(
            buttons
        ):
            button = tk.Button(
                parent,
                text=name,
                command=command,
                bg="#dce3e9",
                font=("Arial", 9, "bold")
            )

            button.place(
                x=3 + index * 80,
                y=105,
                width=75,
                height=42
            )

            if name != "Exit":
                self.action_buttons.append(button)

        clone = tk.Button(
            parent,
            text="Clone Bill",
            command=self.clone_bill,
            bg="#d6e9d2",
            font=("Arial", 9, "bold")
        )

        clone.place(
            x=3,
            y=158,
            width=115,
            height=35
        )

        self.action_buttons.append(clone)

        calculation = tk.LabelFrame(
            parent,
            text="Bill Calculation",
            bg=self.bg,
            fg=self.blue
        )

        calculation.place(
            relx=1,
            x=-460,
            y=0,
            width=460,
            height=205
        )

        fields = [
            ("QTY", "qty", "output"),
            ("Total", "total", "output"),
            ("Discount", "discount", "input"),
            ("Service Charge", "service_charge", "input"),
            ("+ CGST (%)", "cgst", "tax"),
            ("+ SGST (%)", "sgst", "tax"),
            ("+ CESS (%)", "cess", "tax"),
            ("ROUND OFF", "round_off", "output"),
            ("Net Amount", "net", "output")
        ]

        for index, (title, key, kind) in enumerate(
            fields
        ):
            y = 6 + index * 20

            tk.Label(
                calculation,
                text=title,
                bg=self.bg,
                fg=self.blue,
                anchor="w"
            ).place(
                x=10,
                y=y,
                width=140,
                height=19
            )

            if kind == "tax":
                tk.Entry(
                    calculation,
                    textvariable=self.charges[key],
                    justify="right"
                ).place(
                    x=155,
                    y=y,
                    width=90,
                    height=19
                )

                tk.Label(
                    calculation,
                    textvariable=self.totals[
                        key + "_amount"
                    ],
                    bg="white",
                    relief="sunken",
                    anchor="e"
                ).place(
                    x=260,
                    y=y,
                    width=175,
                    height=19
                )

            elif kind == "input":
                tk.Entry(
                    calculation,
                    textvariable=self.charges[key],
                    justify="right"
                ).place(
                    x=260,
                    y=y,
                    width=175,
                    height=19
                )

            else:
                tk.Label(
                    calculation,
                    textvariable=self.totals[key],
                    bg="white",
                    relief="sunken",
                    anchor="e"
                ).place(
                    x=260,
                    y=y,
                    width=175,
                    height=19
                )


    def bind_navigation(self):
        order = [
            "bill",
            "date",
            "waiter",
            "service",
            "kot",
            "room",
            "reg",
            "guest",
            "company",
            "arrival",
            "arrival_time",
            "departure",
            "departure_time",
            "stay",
            "detail"
        ]

        self.form_order = [
            self.fields[key]
            for key in order
        ]

        for widget in self.form_order:
            for event in ("<Return>", "<Tab>"):
                widget.bind(
                    event,
                    lambda e: self.move_form(e, 1)
                )

            widget.bind(
                "<Shift-Tab>",
                lambda e: self.move_form(e, -1)
            )

            if not isinstance(widget, ttk.Combobox):
                widget.bind(
                    "<Down>",
                    lambda e: self.move_form(e, 1)
                )

                widget.bind(
                    "<Up>",
                    lambda e: self.move_form(e, -1)
                )


    def move_form(self, event, direction):
        if self.automation_running:
            return "break"

        index = (
            self.form_order.index(event.widget)
            + direction
        )

        if index >= len(self.form_order):
            self.focus_cell(0, 0)

        elif index >= 0:
            widget = self.form_order[index]
            widget.focus_set()

            try:
                widget.selection_range(0, "end")
            except tk.TclError:
                pass

        return "break"


    def clock(self):
        if self.closing:
            return

        self.v["time"].set(
            datetime.now().strftime("%H:%M:%S")
        )

        self.root.after(
            1000,
            self.clock
        )


    def close_app(self):
        self.closing = True
        self.cancel_automation()
        self.root.destroy()

