"""
Product catalog management (used by purchase tracking to look up price).
"""

from database import run_query


def add_product(product_name, price):
    product_id = run_query(
        "INSERT INTO products (product_name, price) VALUES (%s, %s)",
        (product_name, price),
        commit=True,
    )
    print(f"Product #{product_id} added: {product_name} (₹{price})")
    return product_id


def list_products(active_only=True):
    query = "SELECT * FROM products"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY product_id"
    return run_query(query, fetch=True)


def get_product(product_id):
    return run_query(
        "SELECT * FROM products WHERE product_id = %s", (product_id,), fetch=True, many=True
    )


def update_product(product_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    params = list(fields.values()) + [product_id]
    run_query(f"UPDATE products SET {set_clause} WHERE product_id = %s", params, commit=True)
    print(f"Product #{product_id} updated.")


def delete_product(product_id):
    """Soft-delete: keep historical purchase records intact."""
    run_query(
        "UPDATE products SET is_active = 0 WHERE product_id = %s", (product_id,), commit=True
    )
    print(f"Product #{product_id} deactivated.")
