from shared import *

class TableMixin:
    def create_table(self):
        holder = tk.Frame(
            self.root,
            relief="sunken",
            bd=1
        )

        holder.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=4
        )

        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            holder,
            bg="white",
            highlightthickness=0
        )

        self.canvas.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        scrollbar_y = ttk.Scrollbar(
            holder,
            orient="vertical",
            command=self.canvas.yview
        )

        scrollbar_y.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        scrollbar_x = ttk.Scrollbar(
            holder,
            orient="horizontal",
            command=self.canvas.xview
        )

        scrollbar_x.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        self.canvas.configure(
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set
        )

        self.inner = tk.Frame(
            self.canvas,
            bg="white"
        )

        self.canvas.create_window(
            (0, 0),
            window=self.inner,
            anchor="nw"
        )

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.columns = [
            ("Sr", 45),
            ("Code", 120),
            ("Item", 430),
            ("Qty", 95),
            ("Rate", 130),
            ("Amount", 150)
        ]

        for column, (name, width) in enumerate(
            self.columns
        ):
            frame = tk.Frame(
                self.inner,
                width=width,
                height=30,
                bg="#d9e1e8",
                relief="solid",
                bd=1
            )

            frame.grid(
                row=0,
                column=column
            )

            frame.grid_propagate(False)

            tk.Label(
                frame,
                text=name,
                bg="#d9e1e8",
                font=("Arial", 10, "bold")
            ).pack(
                fill="both",
                expand=True
            )

        for _ in range(20):
            self.add_row()

        self.canvas.bind(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                -1 if e.delta > 0 else 1,
                "units"
            )
        )


    def add_row(self):
        index = len(self.rows)

        row = {
            key: tk.StringVar()
            for key in (
                "code",
                "item",
                "qty",
                "rate",
                "amount"
            )
        }

        self.rows.append(row)

        widgets = {}
        frames = []

        for column, (name, width) in enumerate(
            self.columns
        ):
            frame = tk.Frame(
                self.inner,
                width=width,
                height=27,
                bg="white",
                relief="solid",
                bd=1
            )

            frame.grid(
                row=index + 1,
                column=column
            )

            frame.grid_propagate(False)
            frames.append(frame)

            if column == 0:
                tk.Label(
                    frame,
                    text=str(index + 1),
                    bg="white"
                ).pack(
                    fill="both",
                    expand=True
                )
                continue

            key = name.lower()

            widget = tk.Entry(
                frame,
                textvariable=row[key],
                bd=0,
                justify=(
                    "right"
                    if key in (
                        "qty",
                        "rate",
                        "amount"
                    )
                    else "left"
                ),
                state=(
                    "readonly"
                    if key == "amount"
                    else "normal"
                )
            )

            widget.pack(
                fill="both",
                expand=True
            )

            widgets[key] = widget

            if key == "amount":
                continue

            widget.bind(
                "<Return>",
                lambda e, r=index, k=key:
                    self.next_cell(r, k)
            )

            widget.bind(
                "<Tab>",
                lambda e, r=index, k=key:
                    self.next_cell(r, k)
            )

            widget.bind(
                "<Shift-Tab>",
                lambda e, r=index, k=key:
                    self.previous_cell(r, k)
            )

            for event, dr, dc in (
                ("<Up>", -1, 0),
                ("<Down>", 1, 0),
                ("<Left>", 0, -1),
                ("<Right>", 0, 1)
            ):
                widget.bind(
                    event,
                    lambda e, r=index, k=key,
                    a=dr, b=dc:
                        self.move_cell(r, k, a, b)
                )

        self.cells.append(widgets)
        self.row_frames.append(frames)

        for key in ("qty", "rate"):
            row[key].trace_add(
                "write",
                lambda *_: self.calculate()
            )


    def focus_cell(self, row, column):
        if row < 0:
            return

        while row >= len(self.rows):
            self.add_row()

        column = max(0, min(3, column))

        self.root.update_idletasks()

        frame = self.row_frames[row][column + 1]

        y = frame.winfo_y()
        x = frame.winfo_x()

        height = self.inner.winfo_reqheight()
        width = self.inner.winfo_reqwidth()

        view_height = self.canvas.winfo_height()
        view_width = self.canvas.winfo_width()

        if height > view_height:
            if y < self.canvas.canvasy(0):
                self.canvas.yview_moveto(y / height)

            elif y + 27 > (
                self.canvas.canvasy(0) + view_height
            ):
                self.canvas.yview_moveto(
                    (y + 27 - view_height) / height
                )

        if width > view_width:
            if x < self.canvas.canvasx(0):
                self.canvas.xview_moveto(x / width)

            elif (
                x + frame.winfo_width()
                > self.canvas.canvasx(0) + view_width
            ):
                self.canvas.xview_moveto(
                    (
                        x + frame.winfo_width() - view_width
                    ) / width
                )

        widget = self.cells[row][
            self.table_keys[column]
        ]

        widget.focus_set()
        widget.select_range(0, "end")


    def next_cell(self, row, key):
        column = self.table_keys.index(key)

        if column == 3:
            self.focus_cell(row + 1, 0)
        else:
            self.focus_cell(row, column + 1)

        return "break"


    def previous_cell(self, row, key):
        column = self.table_keys.index(key)

        if column == 0 and row > 0:
            self.focus_cell(row - 1, 3)
        elif column > 0:
            self.focus_cell(row, column - 1)

        return "break"


    def move_cell(self, row, key, dr, dc):
        column = self.table_keys.index(key)

        new_row = row + dr
        new_column = column + dc

        if new_column > 3:
            new_row += 1
            new_column = 0

        elif new_column < 0:
            new_row -= 1
            new_column = 3

        if new_row >= 0:
            self.focus_cell(
                new_row,
                new_column
            )

        return "break"

