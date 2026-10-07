"""
Customer Loyalty & Rewards Program - CLI

Run:
  set LOYALTY_USE_SQLITE=1   (optional, defaults to MySQL otherwise)
  python main.py

For the web dashboard instead, run app.py.
"""

import customer
import product
import purchase
import rewards
from config import CURRENCY_SYMBOL


def prompt(msg):
    return input(msg).strip()


def menu_register_customer():
    print("\n-- Register Customer --")
    first = prompt("First name: ")
    last = prompt("Last name: ")
    email = prompt("Email: ")
    phone = prompt("Phone (optional): ") or None
    address = prompt("Address (optional): ") or None
    try:
        customer.register_customer(first, last, email, phone, address)
    except ValueError as e:
        print(f"Error: {e}")


def menu_list_customers():
    print("\n-- All Customers --")
    for c in customer.list_customers():
        print(f"  #{c['customer_id']} {c['first_name']} {c['last_name']} "
              f"<{c['email']}> [{c['membership_tier']}] lifetime={c['lifetime_points']}")


def menu_add_product():
    print("\n-- Add Product --")
    name = prompt("Product name: ")
    try:
        price = float(prompt(f"Price ({CURRENCY_SYMBOL}): "))
        product.add_product(name, price)
    except ValueError as e:
        print(f"Error: {e}")


def menu_list_products():
    print("\n-- All Products --")
    for p in product.list_products():
        print(f"  #{p['product_id']} {p['product_name']} - {CURRENCY_SYMBOL}{p['price']:.2f}")


def menu_record_purchase():
    print("\n-- Record Purchase --")
    menu_list_products()
    try:
        cid = int(prompt("Customer ID: "))
        pid = int(prompt("Product ID: "))
        qty = int(prompt("Quantity: ") or "1")
        purchase.add_purchase_for_product(cid, pid, qty)
    except (ValueError, Exception) as e:
        print(f"Error: {e}")


def menu_view_balance():
    print("\n-- View Points Balance --")
    try:
        cid = int(prompt("Customer ID: "))
        c = customer.get_customer(cid)
        if not c:
            print("Customer not found.")
            return
        balance = rewards.get_points_balance(cid)
        print(f"{c['first_name']} {c['last_name']} ({c['membership_tier']}) "
              f"-> Available points: {balance} | Lifetime points: {c['lifetime_points']}")
        soon = rewards.get_points_expiring_soon(cid)
        if soon:
            print("Points expiring within 30 days:")
            for row in soon:
                print(f"  {row['remaining_points']} pts expiring on {row['expiry_date']}")
    except ValueError as e:
        print(f"Error: {e}")


def menu_redeem():
    print("\n-- Redeem Points --")
    print("  [C] Redeem from catalog   [F] Freeform points redemption")
    mode = prompt("Choose mode (C/F): ").strip().upper()
    try:
        cid = int(prompt("Customer ID: "))
        if mode == "C":
            catalog = rewards.list_rewards_catalog()
            for r in catalog:
                print(f"  [{r['reward_id']}] {r['reward_name']} - {r['points_required']} pts")
            rid = int(prompt("Reward ID: "))
            rewards.redeem_points(cid, rid)
        else:
            points = int(prompt("Points to redeem: "))
            redemption_id, value = rewards.redeem_points_amount(cid, points)
            print(f"Redemption #{redemption_id}: {points} points -> {CURRENCY_SYMBOL}{value:.2f}")
    except (ValueError, Exception) as e:
        print(f"Error: {e}")


def menu_expire():
    print("\n-- Run Points Expiration --")
    rewards.expire_points()


def menu_purchase_history():
    print("\n-- Purchase History --")
    try:
        cid = int(prompt("Customer ID: "))
        history = purchase.get_purchase_history(cid)
        if not history:
            print("No purchases found.")
        for p in history:
            print(f"  #{p['purchase_id']} {p.get('product_name') or 'n/a'} x{p['quantity']} "
                  f"{CURRENCY_SYMBOL}{p['purchase_amount']} on {p['purchase_date']} "
                  f"-> {p['points_earned']} pts")
    except ValueError as e:
        print(f"Error: {e}")


def menu_ledger_history():
    print("\n-- Points Ledger History --")
    try:
        cid = int(prompt("Customer ID: "))
        ledger = rewards.get_ledger_history(cid)
        for row in ledger:
            print(f"  [{row['transaction_type']}] {row['points']:+} pts "
                  f"(ref: {row['reference_type']}#{row['reference_id']}) "
                  f"on {row['created_at']}")
    except ValueError as e:
        print(f"Error: {e}")


MENU = """
=========================================
 Customer Loyalty & Rewards Program
=========================================
 1. Register new customer
 2. List customers
 3. Add product
 4. List products
 5. Record a purchase
 6. View points balance
 7. Redeem points
 8. View purchase history
 9. View points ledger history
10. Run points expiration (maintenance)
 0. Exit
-----------------------------------------
"""


def main():
    actions = {
        "1": menu_register_customer,
        "2": menu_list_customers,
        "3": menu_add_product,
        "4": menu_list_products,
        "5": menu_record_purchase,
        "6": menu_view_balance,
        "7": menu_redeem,
        "8": menu_purchase_history,
        "9": menu_ledger_history,
        "10": menu_expire,
    }
    while True:
        print(MENU)
        choice = prompt("Choose an option: ")
        if choice == "0":
            print("Goodbye!")
            break
        action = actions.get(choice)
        if action:
            action()
        else:
            print("Invalid option, try again.")


if __name__ == "__main__":
    main()
