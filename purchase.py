"""
Purchase tracking: recording a purchase automatically calculates and
credits reward points (applying the customer's tier multiplier),
and logs the earn event in the points_ledger with an expiry date.
"""

from datetime import datetime, timedelta
from database import run_query
from customer import get_customer, _refresh_tier
from config import POINTS_PER_DOLLAR, DOLLARS_PER_POINT_UNIT, POINTS_EXPIRY_MONTHS


def calculate_points(purchase_amount, tier_multiplier):
    """Base points = floor(amount / DOLLARS_PER_POINT_UNIT) * POINTS_PER_DOLLAR,
    then scaled by the customer's tier multiplier."""
    base_points = int(purchase_amount // DOLLARS_PER_POINT_UNIT) * POINTS_PER_DOLLAR
    return int(base_points * float(tier_multiplier))


def _get_tier_multiplier(customer):
    tier = run_query(
        "SELECT points_multiplier FROM reward_tiers WHERE tier_name = %s",
        (customer["membership_tier"],),
        fetch=True,
        many=True,
    )
    return tier["points_multiplier"] if tier else 1.0


def add_purchase(customer_id, purchase_amount, store_location=None, product_id=None, quantity=1):
    """Record a purchase, award points, and log the ledger entry.
    Works either as a plain amount (product_id=None) or tied to a
    product + quantity from the catalog (amount is still stored for
    reporting, computed by the caller or by add_purchase_for_product)."""
    customer = get_customer(customer_id)
    if not customer:
        raise ValueError(f"No customer with id {customer_id}")
    if not customer["is_active"]:
        raise ValueError(f"Customer #{customer_id} is not active.")

    multiplier = _get_tier_multiplier(customer)
    points_earned = calculate_points(purchase_amount, multiplier)

    purchase_id = run_query(
        """INSERT INTO purchases (customer_id, product_id, quantity, purchase_amount, store_location, points_earned)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (customer_id, product_id, quantity, purchase_amount, store_location, points_earned),
        commit=True,
    )

    if points_earned > 0:
        expiry_date = datetime.now() + timedelta(days=30 * POINTS_EXPIRY_MONTHS)
        run_query(
            """INSERT INTO points_ledger
                   (customer_id, points, transaction_type, reference_type,
                    reference_id, expiry_date, remaining_points)
               VALUES (%s, %s, 'EARN', 'PURCHASE', %s, %s, %s)""",
            (customer_id, points_earned, purchase_id, expiry_date, points_earned),
            commit=True,
        )
        run_query(
            "UPDATE customers SET lifetime_points = lifetime_points + %s WHERE customer_id = %s",
            (points_earned, customer_id),
            commit=True,
        )
        _refresh_tier(customer_id)

    print(
        f"Purchase #{purchase_id} recorded: ${purchase_amount:.2f} "
        f"-> {points_earned} points earned (customer #{customer_id})"
    )
    return purchase_id, points_earned


def add_purchase_for_product(customer_id, product_id, quantity, store_location=None):
    """Convenience wrapper used by the web UI: look up the product's
    price, compute the total, and record the purchase."""
    from product import get_product

    product = get_product(product_id)
    if not product:
        raise ValueError(f"No product with id {product_id}")
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    amount = round(float(product["price"]) * quantity, 2)
    return add_purchase(customer_id, amount, store_location, product_id=product_id, quantity=quantity)


def get_purchase_history(customer_id=None, limit=None):
    query = """SELECT p.*, c.first_name, c.last_name, pr.product_name
               FROM purchases p
               JOIN customers c ON c.customer_id = p.customer_id
               LEFT JOIN products pr ON pr.product_id = p.product_id"""
    params = ()
    if customer_id:
        query += " WHERE p.customer_id = %s"
        params = (customer_id,)
    query += " ORDER BY p.purchase_date DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return run_query(query, params, fetch=True)
