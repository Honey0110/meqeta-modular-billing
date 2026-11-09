# MEQETA Billing - modular project

This project was extracted from the **last** `BillingApp` definition in the supplied 6,655-line `main2.py`. The uploaded file contained two separate versions, so the older version was not merged into the new one.

## Files
- `main.py`: entry point and BillingApp composition
- `shared.py`: imports, settings, helper functions, MySQL connection
- `ui.py`: interface, navigation and clock
- `table.py`: item table and keyboard navigation
- `automation.py`: internal/external PMS automation
- `billing.py`: calculations, form data, printing
- `database.py`: save, find, clone, delete, MySQL queries

## Install and run
From the folder containing `main.py`:

```powershell
python -m pip install mysql-connector-python pyautogui pyperclip
$env:MEQETA_DB_PASSWORD = "YOUR_PASSWORD"
python main.py
```

Keep your existing `ink.txt` in this folder if you use it. Do not delete your original `main2.py` or database files. This is a structural refactor, not a tested live MySQL/PMS integration.
