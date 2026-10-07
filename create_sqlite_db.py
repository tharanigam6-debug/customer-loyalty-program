"""
Create (or upgrade) the SQLite version of the loyalty program schema,
and seed it with a small demo dataset so the web dashboard has data to
show immediately.

Usage:
  set LOYALTY_USE_SQLITE=1
  python create_sqlite_db.py [--reset]

--reset drops and recreates every table (useful while developing).
This will create/update `loyalty.db` next to this script.
"""
import os
import sys
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "loyalty.db")

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS reward_tiers (
    tier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier_name TEXT NOT NULL UNIQUE,
    min_lifetime_points INTEGER NOT NULL DEFAULT 0,
    points_multiplier REAL NOT NULL DEFAULT 1.0
);

INSERT OR IGNORE INTO reward_tiers (tier_name, min_lifetime_points, points_multiplier) VALUES
    ('Bronze', 0, 1.0),
    ('Silver', 500, 1.25),
    ('Gold', 1500, 1.5),
    ('Platinum', 3000, 2.0);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    address TEXT,
    registration_date DATETIME DEFAULT (datetime('now')),
    lifetime_points INTEGER NOT NULL DEFAULT 0,
    membership_tier TEXT NOT NULL DEFAULT 'Bronze',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    price REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER,
    quantity INTEGER NOT NULL DEFAULT 1,
    purchase_amount REAL NOT NULL,
    purchase_date DATETIME DEFAULT (datetime('now')),
    store_location TEXT,
    points_earned INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS points_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    points INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    earned_date DATETIME DEFAULT (datetime('now')),
    expiry_date DATETIME,
    remaining_points INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rewards_catalog (
    reward_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reward_name TEXT NOT NULL,
    description TEXT,
    points_required INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO rewards_catalog (reward_name, description, points_required) VALUES
    ('₹5 Store Credit', 'Redeem for ₹5 off your next purchase', 50),
    ('₹10 Store Credit', 'Redeem for ₹10 off your next purchase', 100),
    ('Free Shipping', 'One free shipping voucher', 25),
    ('₹25 Gift Card', 'Redeem for a ₹25 gift card', 250);

CREATE TABLE IF NOT EXISTS redemptions (
    redemption_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    reward_id INTEGER,
    points_redeemed INTEGER NOT NULL,
    reward_value REAL,
    redemption_date DATETIME DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'COMPLETED',
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (reward_id) REFERENCES rewards_catalog(reward_id)
);

CREATE VIEW IF NOT EXISTS customer_points_balance AS
SELECT
    c.customer_id as customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.membership_tier AS membership_tier,
    c.lifetime_points AS lifetime_points,
    COALESCE(SUM(CASE WHEN pl.transaction_type = 'EARN' AND (pl.expiry_date IS NULL OR pl.expiry_date > datetime('now')) THEN pl.remaining_points ELSE 0 END), 0) AS available_points
FROM customers c
LEFT JOIN points_ledger pl ON pl.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.membership_tier, c.lifetime_points;
"""


def seed_demo_data(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM customers")
    if cur.fetchone()[0] > 0:
        return  # already has data, don't reseed

    demo_customers = [
        ("Tharaniga", "R", "tharaniga@example.com", "9876500001", "Chennai"),
        ("Karthik", "S", "karthik@example.com", "9876500002", "Coimbatore"),
        ("Priya", "M", "priya@example.com", "9876500003", "Madurai"),
        ("Anitha", "K", "anitha@example.com", "9876500004", "Trichy"),
        ("Hari", "V", "hari@example.com", "9876500005", "Salem"),
    ]
    for first, last, email, phone, address in demo_customers:
        cur.execute(
            "INSERT INTO customers (first_name, last_name, email, phone, address) VALUES (?,?,?,?,?)",
            (first, last, email, phone, address),
        )

    demo_products = [
        ("Wireless Headphone", 1500.00),
        ("Smart Watch", 2500.00),
        ("Bluetooth Speaker", 1200.00),
        ("Power Bank", 800.00),
        ("Laptop Bag", 700.00),
    ]
    for name, price in demo_products:
        cur.execute("INSERT INTO products (product_name, price) VALUES (?,?)", (name, price))

    conn.commit()

    # A few sample purchases so the dashboard chart/table aren't empty
    import random
    today = datetime.now()
    for i in range(8):
        cid = random.randint(1, len(demo_customers))
        pid = random.randint(1, len(demo_products))
        qty = random.randint(1, 3)
        cur.execute("SELECT price FROM products WHERE product_id=?", (pid,))
        price = cur.fetchone()[0]
        amount = round(price * qty, 2)
        points = int(amount // 10)
        pdate = today - timedelta(days=random.randint(0, 27))
        cur.execute(
            """INSERT INTO purchases (customer_id, product_id, quantity, purchase_amount,
                                       purchase_date, points_earned)
               VALUES (?,?,?,?,?,?)""",
            (cid, pid, qty, amount, pdate.strftime("%Y-%m-%d %H:%M:%S"), points),
        )
        purchase_id = cur.lastrowid
        expiry = pdate + timedelta(days=365)
        cur.execute(
            """INSERT INTO points_ledger (customer_id, points, transaction_type, reference_type,
                                           reference_id, earned_date, expiry_date, remaining_points, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (cid, points, "EARN", "PURCHASE", purchase_id,
             pdate.strftime("%Y-%m-%d %H:%M:%S"), expiry.strftime("%Y-%m-%d %H:%M:%S"),
             points, pdate.strftime("%Y-%m-%d %H:%M:%S")),
        )
        cur.execute(
            "UPDATE customers SET lifetime_points = lifetime_points + ? WHERE customer_id=?",
            (points, cid),
        )
    conn.commit()


def main():
    reset = "--reset" in sys.argv
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Existing database removed (--reset).")

    print(f"Using SQLite DB at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SCHEMA)
        conn.commit()
        print("Schema created/updated.")
        seed_demo_data(conn)
        print("Demo data seeded (skipped if data already existed).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
