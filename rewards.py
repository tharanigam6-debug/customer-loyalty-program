"""
Reward points balance, redemption, and expiration management.

Redemption uses FIFO consumption: oldest (soonest to expire) EARN
ledger rows are drawn down first, so customers never lose points
unnecessarily to expiration ahead of a redemption.

Date comparisons are done in Python (rather than relying on MySQL's
NOW()/DATE_ADD or SQLite's datetime()) so the same code works
unchanged against either backend.
"""

from datetime import datetime, timedelta
from database import run_query, get_connection, USE_SQLITE
from customer import get_customer
from config import REDEMPTION_RATE

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _now_str():
    return datetime.now().strftime(DATE_FMT)


def _exec(cursor, query, params=()):
    """Execute a query on a raw cursor, converting %s -> ? for SQLite."""
    if USE_SQLITE:
        query = query.replace("%s", "?")
    cursor.execute(query, params)
    return cursor


def get_points_balance(customer_id):
    """Return the customer's current available (non-expired, unredeemed) points."""
    row = run_query(
        "SELECT available_points FROM customer_points_balance WHERE customer_id = %s",
        (customer_id,),
        fetch=True,
        many=True,
    )
    return row["available_points"] if row else 0


def list_rewards_catalog(active_only=True):
    query = "SELECT * FROM rewards_catalog"
    if active_only:
        query += " WHERE is_active = 1"
    return run_query(query, fetch=True)


def _fifo_deduct(cursor, customer_id, points_required):
    """Deduct points_required from the customer's oldest non-expired EARN
    ledger rows. Raises ValueError if the balance is insufficient.
    Returns nothing; mutates points_ledger rows via the given cursor."""
    now = _now_str()
    _exec(cursor, 
        """SELECT ledger_id, remaining_points FROM points_ledger
           WHERE customer_id = %s AND transaction_type = 'EARN'
             AND remaining_points > 0
             AND (expiry_date IS NULL OR expiry_date > %s)
           ORDER BY earned_date ASC""",
        (customer_id, now),
    )
    earn_rows = cursor.fetchall()

    remaining_to_deduct = points_required
    for row in earn_rows:
        if remaining_to_deduct <= 0:
            break
        row_remaining = row["remaining_points"]
        deduct = min(row_remaining, remaining_to_deduct)
        _exec(cursor, 
            "UPDATE points_ledger SET remaining_points = remaining_points - %s WHERE ledger_id = %s",
            (deduct, row["ledger_id"]),
        )
        remaining_to_deduct -= deduct

    if remaining_to_deduct > 0:
        raise ValueError("Insufficient points to complete this redemption.")


def redeem_points(customer_id, reward_id):
    """Redeem a fixed reward from the catalog for a customer."""
    customer = get_customer(customer_id)
    if not customer:
        raise ValueError(f"No customer with id {customer_id}")

    reward = run_query(
        "SELECT * FROM rewards_catalog WHERE reward_id = %s AND is_active = 1",
        (reward_id,),
        fetch=True,
        many=True,
    )
    if not reward:
        raise ValueError(f"Reward #{reward_id} not found or inactive.")

    points_required = reward["points_required"]
    balance = get_points_balance(customer_id)
    if balance < points_required:
        raise ValueError(
            f"Insufficient points: customer #{customer_id} has {balance}, needs {points_required}."
        )

    reward_value = round(points_required / REDEMPTION_RATE, 2)

    conn = get_connection()
    cursor = _dict_cursor(conn)
    try:
        _fifo_deduct(cursor, customer_id, points_required)

        _exec(cursor, 
            """INSERT INTO redemptions (customer_id, reward_id, points_redeemed, reward_value)
               VALUES (%s, %s, %s, %s)""",
            (customer_id, reward_id, points_required, reward_value),
        )
        redemption_id = cursor.lastrowid

        _exec(cursor, 
            """INSERT INTO points_ledger
                   (customer_id, points, transaction_type, reference_type, reference_id, remaining_points)
               VALUES (%s, %s, 'REDEEM', 'REDEMPTION', %s, 0)""",
            (customer_id, -points_required, redemption_id),
        )

        conn.commit()
        print(
            f"Redemption #{redemption_id}: customer #{customer_id} redeemed "
            f"'{reward['reward_name']}' for {points_required} points."
        )
        return redemption_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def redeem_points_amount(customer_id, points_to_redeem):
    """Freeform redemption: redeem an arbitrary number of points for
    store credit, valued at config.REDEMPTION_RATE points per currency
    unit. Used by the 'Customer Rewards' panel in the web dashboard."""
    points_to_redeem = int(points_to_redeem)
    if points_to_redeem <= 0:
        raise ValueError("Enter a positive number of points to redeem.")

    customer = get_customer(customer_id)
    if not customer:
        raise ValueError(f"No customer with id {customer_id}")

    balance = get_points_balance(customer_id)
    if balance < points_to_redeem:
        raise ValueError(
            f"Insufficient points: available {balance}, requested {points_to_redeem}."
        )

    reward_value = round(points_to_redeem / REDEMPTION_RATE, 2)

    conn = get_connection()
    cursor = _dict_cursor(conn)
    try:
        _fifo_deduct(cursor, customer_id, points_to_redeem)

        _exec(cursor, 
            """INSERT INTO redemptions (customer_id, reward_id, points_redeemed, reward_value)
               VALUES (%s, NULL, %s, %s)""",
            (customer_id, points_to_redeem, reward_value),
        )
        redemption_id = cursor.lastrowid

        _exec(cursor, 
            """INSERT INTO points_ledger
                   (customer_id, points, transaction_type, reference_type, reference_id, remaining_points)
               VALUES (%s, %s, 'REDEEM', 'REDEMPTION', %s, 0)""",
            (customer_id, -points_to_redeem, redemption_id),
        )

        conn.commit()
        return redemption_id, reward_value
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def expire_points():
    """Expire all EARN ledger rows whose expiry_date has passed."""
    now = _now_str()
    conn = get_connection()
    cursor = _dict_cursor(conn)
    try:
        _exec(cursor, 
            """SELECT ledger_id, customer_id, remaining_points FROM points_ledger
               WHERE transaction_type = 'EARN' AND remaining_points > 0
                 AND expiry_date IS NOT NULL AND expiry_date <= %s""",
            (now,),
        )
        expiring = cursor.fetchall()

        for row in expiring:
            _exec(cursor, 
                """INSERT INTO points_ledger
                       (customer_id, points, transaction_type, reference_type, reference_id, remaining_points)
                   VALUES (%s, %s, 'EXPIRE', 'SYSTEM', %s, 0)""",
                (row["customer_id"], -row["remaining_points"], row["ledger_id"]),
            )
            _exec(cursor, 
                "UPDATE points_ledger SET remaining_points = 0 WHERE ledger_id = %s",
                (row["ledger_id"],),
            )

        conn.commit()
        print(f"Expired points for {len(expiring)} ledger row(s).")
        return len(expiring)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_points_expiring_soon(customer_id, within_days=30):
    """Points that will expire within the given window (useful for reminders)."""
    now = _now_str()
    cutoff = (datetime.now() + timedelta(days=within_days)).strftime(DATE_FMT)
    return run_query(
        """SELECT ledger_id, remaining_points, expiry_date
           FROM points_ledger
           WHERE customer_id = %s AND transaction_type = 'EARN'
             AND remaining_points > 0
             AND expiry_date IS NOT NULL
             AND expiry_date BETWEEN %s AND %s
           ORDER BY expiry_date ASC""",
        (customer_id, now, cutoff),
        fetch=True,
    )


def get_ledger_history(customer_id=None, limit=None):
    query = "SELECT * FROM points_ledger"
    params = ()
    if customer_id:
        query += " WHERE customer_id = %s"
        params = (customer_id,)
    query += " ORDER BY created_at DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return run_query(query, params, fetch=True)


def get_redemption_history(customer_id=None, limit=None):
    query = """SELECT r.*, c.first_name, c.last_name, rc.reward_name
               FROM redemptions r
               JOIN customers c ON c.customer_id = r.customer_id
               LEFT JOIN rewards_catalog rc ON rc.reward_id = r.reward_id"""
    params = ()
    if customer_id:
        query += " WHERE r.customer_id = %s"
        params = (customer_id,)
    query += " ORDER BY r.redemption_date DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return run_query(query, params, fetch=True)


def _dict_cursor(conn):
    """Return a dict-yielding cursor for either MySQL or SQLite connections."""
    try:
        return conn.cursor(dictionary=True)  # mysql-connector
    except TypeError:
        return conn.cursor()  # sqlite3.Row-based connection already dict-like
