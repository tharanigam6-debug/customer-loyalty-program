"""
Database configuration for the Loyalty & Rewards Program.
Update these values to match your MySQL server.
"""

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_password",   # <-- change me
    "database": "loyalty_program",
}

# Business rules
POINTS_PER_DOLLAR = 1          # base points earned per $10 spent
DOLLARS_PER_POINT_UNIT = 10    # $10 spent = POINTS_PER_DOLLAR points (before tier multiplier)
POINTS_EXPIRY_MONTHS = 12      # points expire N months after being earned

# Display / redemption
CURRENCY_SYMBOL = "\u20b9"     # symbol shown in the web UI (Rupee by default)
REDEMPTION_RATE = 10           # points per 1 currency unit when redeeming (10 pts = ₹1)
