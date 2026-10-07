"""
Customer Loyalty & Rewards Program - Web Dashboard

Run:
  set LOYALTY_USE_SQLITE=1   (Windows: set, macOS/Linux: export)
  python app.py

Then open http://127.0.0.1:5000
"""

import os

os.environ.setdefault("LOYALTY_USE_SQLITE", "1")  # default to SQLite for easy local dev

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta

import customer as customer_mod
import product as product_mod
import purchase as purchase_mod
import rewards as rewards_mod
from config import CURRENCY_SYMBOL, REDEMPTION_RATE

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
app.jinja_env.globals["currency"] = CURRENCY_SYMBOL


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@app.route("/")
def dashboard():
    customers = customer_mod.list_customers()
    all_purchases = purchase_mod.get_purchase_history()
    all_redemptions = rewards_mod.get_redemption_history()

    total_customers = len(customers)
    total_purchases = len(all_purchases)
    total_points_earned = sum(p["points_earned"] for p in all_purchases)
    total_points_redeemed = sum(r["points_redeemed"] for r in all_redemptions)

    recent_purchases = all_purchases[:5]

    # Build a simple last-30-days purchase-amount series for the chart
    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    totals_by_day = {d.isoformat(): 0.0 for d in days}
    for p in all_purchases:
        pdate = str(p["purchase_date"])[:10]
        if pdate in totals_by_day:
            totals_by_day[pdate] += float(p["purchase_amount"])
    chart_labels = [d.strftime("%d %b") for d in days]
    chart_values = [round(totals_by_day[d.isoformat()], 2) for d in days]

    return render_template(
        "dashboard.html",
        active="dashboard",
        total_customers=total_customers,
        total_purchases=total_purchases,
        total_points_earned=total_points_earned,
        total_points_redeemed=total_points_redeemed,
        recent_purchases=recent_purchases,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


# ---------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------
@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip() or None
        address = request.form.get("address", "").strip() or None
        try:
            if not first or not email:
                raise ValueError("Name and email are required.")
            customer_mod.register_customer(first, last, email, phone, address)
            flash("Customer registered.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("customers"))

    rows = customer_mod.list_customers()
    balances = {c["customer_id"]: rewards_mod.get_points_balance(c["customer_id"]) for c in rows}
    return render_template("customers.html", active="customers", customers=rows, balances=balances)


@app.route("/customers/<int:customer_id>/deactivate", methods=["POST"])
def deactivate_customer(customer_id):
    customer_mod.deactivate_customer(customer_id)
    flash("Customer deactivated.", "success")
    return redirect(url_for("customers"))


# ---------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------
@app.route("/products", methods=["GET", "POST"])
def products():
    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        price = request.form.get("price", "").strip()
        try:
            if not name or not price:
                raise ValueError("Product name and price are required.")
            product_mod.add_product(name, float(price))
            flash("Product added.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("products"))

    rows = product_mod.list_products()
    return render_template("products.html", active="products", products=rows)


@app.route("/products/<int:product_id>/edit", methods=["POST"])
def edit_product(product_id):
    name = request.form.get("product_name", "").strip()
    price = request.form.get("price", "").strip()
    try:
        fields = {}
        if name:
            fields["product_name"] = name
        if price:
            fields["price"] = float(price)
        product_mod.update_product(product_id, **fields)
        flash("Product updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("products"))


@app.route("/products/<int:product_id>/delete", methods=["POST"])
def delete_product(product_id):
    product_mod.delete_product(product_id)
    flash("Product removed.", "success")
    return redirect(url_for("products"))


# ---------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------
@app.route("/purchases", methods=["GET", "POST"])
def purchases():
    if request.method == "POST":
        try:
            cid = int(request.form.get("customer_id"))
            pid = int(request.form.get("product_id"))
            qty = int(request.form.get("quantity", 1))
            purchase_mod.add_purchase_for_product(cid, pid, qty)
            flash("Purchase recorded.", "success")
        except (ValueError, TypeError) as e:
            flash(str(e) or "Please select a customer and product.", "error")
        return redirect(url_for("purchases"))

    customers_list = customer_mod.list_customers()
    products_list = product_mod.list_products()
    recent = purchase_mod.get_purchase_history(limit=15)
    return render_template(
        "purchases.html",
        active="purchases",
        customers=customers_list,
        products=products_list,
        recent_purchases=recent,
    )


# ---------------------------------------------------------------------
# Rewards / redemption
# ---------------------------------------------------------------------
@app.route("/rewards", methods=["GET", "POST"])
def rewards():
    selected_customer = None
    balance = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")
        cid = request.form.get("customer_id")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            flash("Choose a customer first.", "error")
            return redirect(url_for("rewards"))

        if action == "lookup":
            pass  # fall through to render with this customer selected
        elif action == "redeem":
            points = request.form.get("points", "0")
            try:
                redemption_id, value = rewards_mod.redeem_points_amount(cid, int(points))
                flash(f"Redeemed {points} points for {CURRENCY_SYMBOL}{value:.2f}.", "success")
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("rewards", customer_id=cid))

        selected_customer = customer_mod.get_customer(cid)

    else:
        cid = request.args.get("customer_id")
        if cid:
            selected_customer = customer_mod.get_customer(int(cid))

    if selected_customer:
        balance = rewards_mod.get_points_balance(selected_customer["customer_id"])

    customers_list = customer_mod.list_customers()
    catalog = rewards_mod.list_rewards_catalog()
    return render_template(
        "rewards.html",
        active="rewards",
        customers=customers_list,
        selected_customer=selected_customer,
        balance=balance,
        redemption_rate=REDEMPTION_RATE,
        catalog=catalog,
    )


@app.route("/api/points-balance/<int:customer_id>")
def api_points_balance(customer_id):
    return jsonify({"balance": rewards_mod.get_points_balance(customer_id)})


# ---------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------
@app.route("/reports")
def reports():
    view = request.args.get("view", "purchases")
    cid = request.args.get("customer_id")
    cid = int(cid) if cid else None

    customers_list = customer_mod.list_customers()
    purchase_rows = purchase_mod.get_purchase_history(customer_id=cid)
    redemption_rows = rewards_mod.get_redemption_history(customer_id=cid)

    return render_template(
        "reports.html",
        active="reports",
        view=view,
        customers=customers_list,
        selected_customer_id=cid,
        purchase_rows=purchase_rows,
        redemption_rows=redemption_rows,
    )


# ---------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------
@app.route("/maintenance/expire-points", methods=["POST"])
def run_expire_points():
    count = rewards_mod.expire_points()
    flash(f"Expired points on {count} ledger row(s).", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/logout")
def logout():
    # No auth system is wired up; this simply returns to the dashboard.
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
