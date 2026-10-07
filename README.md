# Customer Loyalty & Rewards System

A full Python + MySQL (with a SQLite dev fallback) loyalty program: a
web dashboard (Flask) plus a command-line interface, both backed by
the same data layer.

## Features
- **Customer registration** — name, phone, email, address; list, deactivate
- **Product catalog** — add / edit / remove products with prices
- **Purchase tracking** — pick a customer + product + quantity, see the total and reward points calculate live, and record the sale
- **Reward points calculation** — points scale with the customer's membership tier (Bronze → Platinum), with automatic tier upgrades as they earn more
- **Redemption** — redeem any number of points for store credit (FIFO: oldest, soonest-to-expire points are used first), plus a reference rewards catalog
- **Expiration management** — points expire 12 months after being earned, via a one-click maintenance action, the CLI, or a MySQL scheduled `EVENT`
- **Dashboard & reports** — KPI cards, a 30-day purchase chart, recent purchases, and filterable purchase/reward history

## Project structure
```
loyalty_program/
├── schema.sql            # MySQL schema (tables, view, stored procedure, event) + demo data
├── config.py              # DB connection settings & business rule constants
├── database.py            # Connection helper — MySQL by default, SQLite fallback for local dev
├── customer.py            # Customer registration & management
├── product.py              # Product catalog management
├── purchase.py             # Purchase tracking & points calculation
├── rewards.py              # Balance, redemption (FIFO), and expiration logic
├── main.py                 # Command-line interface
├── app.py                  # Flask web dashboard
├── create_db.py            # Applies schema.sql to a MySQL server
├── create_sqlite_db.py     # Creates/seeds the local loyalty.db SQLite file
├── loyalty.db              # Pre-seeded SQLite database (demo data included)
├── templates/               # Dashboard HTML (Jinja2)
├── static/css/style.css      # Dashboard styling
└── requirements.txt
```

## Quick start (VS Code, no MySQL required)

This project defaults to SQLite so you can run it immediately without
installing or configuring MySQL.

1. Open this folder in VS Code.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. (Optional — a seeded `loyalty.db` is already included.) To regenerate it:
   ```bash
   python create_sqlite_db.py --reset
   ```
4. Run the web dashboard:
   ```bash
   python app.py
   ```
   Open **http://127.0.0.1:5000** in your browser.

   Or run the command-line version instead:
   ```bash
   python main.py
   ```

## Switching to MySQL

The app defaults to SQLite (`LOYALTY_USE_SQLITE=1`, set automatically
at the top of `app.py`). To use MySQL instead:

1. Edit `config.py` with your MySQL host/user/password.
2. Apply the schema:
   ```bash
   python create_db.py
   ```
   (or run `mysql -u root -p < schema.sql` directly)
3. Unset the SQLite flag and run:
   ```bash
   # macOS/Linux
   unset LOYALTY_USE_SQLITE
   python app.py

   # Windows (cmd)
   set LOYALTY_USE_SQLITE=
   python app.py
   ```
   `database.py` checks this environment variable at import time — as
   long as it isn't `"1"`, every module talks to MySQL via
   `mysql-connector-python`.

To enable automatic daily point expiration in MySQL (optional — you
can also just click "Run Points Expiration" on the Reports page):
```sql
SET GLOBAL event_scheduler = ON;
```

## How points work
- Base rate: 1 point per ₹10 spent (`POINTS_PER_DOLLAR` / `DOLLARS_PER_POINT_UNIT` in `config.py` — rename/adjust as needed)
- Tier multipliers (`reward_tiers` table): Bronze 1.00x (0+ lifetime points), Silver 1.25x (500+), Gold 1.50x (1,500+), Platinum 2.00x (3,000+)
- Points expire **12 months** after being earned (`POINTS_EXPIRY_MONTHS`)
- Redemption rate: 10 points = ₹1 (`REDEMPTION_RATE` in `config.py`)
- Redemption draws down the **oldest** unexpired points first (FIFO)

Every points event (earn, redeem, expire) is written to `points_ledger`,
giving a full, auditable history per customer — visible on the Reports
page or via `main.py`'s ledger history option.

## Currency
The dashboard displays amounts in ₹ (Indian Rupees) by default. Change
`CURRENCY_SYMBOL` in `config.py` to switch currencies.

## Extending it
- Add authentication (the sidebar "Logout" link and "Welcome, Admin" are currently placeholders with no real auth behind them)
- Add a `notify_expiring_points()` job (see `rewards.get_points_expiring_soon`) to email/SMS customers before points lapse
- Add unit tests around `purchase.calculate_points` and `rewards.redeem_points_amount`
- Deploy with a production WSGI server (gunicorn/waitress) instead of Flask's dev server
