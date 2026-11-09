"""MEQETA billing application - entry point."""
import tkinter as tk
from ui import UiMixin
from table import TableMixin
from automation import AutomationMixin
from billing import BillingMixin
from database import DatabaseMixin

class BillingApp(UiMixin, TableMixin, AutomationMixin, BillingMixin, DatabaseMixin):
    pass

if __name__ == "__main__":
    root = tk.Tk()
    app = BillingApp(root)
    root.mainloop()
