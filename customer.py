"""
Customer registration and lookup.
"""

from database import run_query


def register_customer(first_name, last_name, email, phone=None, address=None):
    """Register a new customer. Returns the new customer_id."""
    existing = run_query(
        "SELECT customer_id FROM customers WHERE email = %s", (email,), fetch=True, many=True
    )
    if existing:
        raise ValueError(f"A customer with email '{email}' already exists.")

    customer_id = run_query(
        """INSERT INTO customers (first_name, last_name, email, phone, address)
           VALUES (%s, %s, %s, %s, %s)""",
        (first_name, last_name, email, phone, address),
        commit=True,
    )
    print(f"Registered customer #{customer_id}: {first_name} {last_name}")
    return customer_id


def get_customer(customer_id):
    return run_query(
        "SELECT * FROM customers WHERE customer_id = %s", (customer_id,), fetch=True, many=True
    )


def get_customer_by_email(email):
    return run_query(
        "SELECT * FROM customers WHERE email = %s", (email,), fetch=True, many=True
    )


def list_customers(active_only=True):
    query = "SELECT * FROM customers"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY customer_id"
    return run_query(query, fetch=True)


def update_customer(customer_id, **fields):
    """Update arbitrary customer fields, e.g. update_customer(1, phone='555-1234')."""
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    params = list(fields.values()) + [customer_id]
    run_query(
        f"UPDATE customers SET {set_clause} WHERE customer_id = %s", params, commit=True
    )
    print(f"Customer #{customer_id} updated.")


def deactivate_customer(customer_id):
    run_query(
        "UPDATE customers SET is_active = 0 WHERE customer_id = %s",
        (customer_id,),
        commit=True,
    )
    print(f"Customer #{customer_id} deactivated.")


def _refresh_tier(customer_id):
    """Recalculate and update a customer's membership tier based on lifetime points."""
    customer = get_customer(customer_id)
    if not customer:
        return
    lifetime_points = customer["lifetime_points"]

    tier = run_query(
        """SELECT tier_name FROM reward_tiers
           WHERE min_lifetime_points <= %s
           ORDER BY min_lifetime_points DESC LIMIT 1""",
        (lifetime_points,),
        fetch=True,
        many=True,
    )
    if tier and tier["tier_name"] != customer["membership_tier"]:
        run_query(
            "UPDATE customers SET membership_tier = %s WHERE customer_id = %s",
            (tier["tier_name"], customer_id),
            commit=True,
        )
        print(f"Customer #{customer_id} upgraded to tier: {tier['tier_name']}")
