# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from io import BytesIO
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")

mongo = PyMongo(app)
db = mongo.db
expenses = db.expenses
users = db.users

# ------------------------
# Auth Helpers
# ------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Login required", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------
# Routes
# ------------------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("login"))
    return redirect(url_for("login.html"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        if users.find_one({"username": username}):
            flash("Username already exists", "danger")
            return redirect(url_for("register"))
        hashed = generate_password_hash(password)
        users.insert_one({"username": username, "password": hashed, "role": "user"})
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        user = users.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            session["role"] = user.get("role", "user")
            flash("Logged in successfully", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("login"))

# ------------------------
# User Dashboard
# ------------------------
@app.route("/dashboard")
@login_required
def index():
    all_expenses = list(expenses.find({"user_id": session["user_id"]}).sort("date", -1))
    total = sum(e.get("amount", 0) for e in all_expenses)
    pipeline = [
        {"$match": {"user_id": session["user_id"]}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}}
    ]
    category_agg = list(expenses.aggregate(pipeline))
    categories = [c["_id"] for c in category_agg]
    totals = [c["total"] for c in category_agg]

    for e in all_expenses:
        e["_id"] = str(e["_id"])
        d = e.get("date")
        e["date_str"] = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)

    return render_template("index.html", expenses=all_expenses, total=total,
                           categories=categories, totals=totals)

# ------------------------
# Expense CRUD
# ------------------------
@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        category = request.form.get("category", "Uncategorized").strip()
        amount = request.form.get("amount", "0").strip()
        date_str = request.form.get("date", "").strip()
        try:
            amount = float(amount)
        except:
            flash("Amount must be a number", "danger")
            return redirect(url_for("index"))
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            date_obj = datetime.utcnow()
        expenses.insert_one({"user_id": session["user_id"], "category": category,
                             "amount": amount, "date": date_obj})
        flash("Expense added", "success")
        return redirect(url_for("index"))
    return render_template("add.html")

@app.route("/edit/<id>", methods=["GET", "POST"])
@login_required
def edit(id):
    try:
        obj_id = ObjectId(id)
    except:
        flash("Invalid id", "danger")
        return redirect(url_for("index"))
    exp = expenses.find_one({"_id": obj_id, "user_id": session["user_id"]})
    if not exp:
        flash("Expense not found", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        category = request.form.get("category", exp.get("category", "Uncategorized")).strip()
        amount = request.form.get("amount", str(exp.get("amount", 0))).strip()
        date_str = request.form.get("date", "")
        try:
            amount = float(amount)
        except:
            flash("Amount must be a number", "danger")
            return redirect(url_for("edit", id=id))
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            date_obj = exp.get("date", datetime.utcnow())
        expenses.update_one({"_id": obj_id}, {"$set": {"category": category,
                                                       "amount": amount,
                                                       "date": date_obj}})
        flash("Expense updated", "success")
        return redirect(url_for("index"))
    exp["_id"] = str(exp["_id"])
    d = exp.get("date")
    exp["date_str"] = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
    return render_template("edit.html", expense=exp)

@app.route("/delete/<id>", methods=["POST"])
@login_required
def delete(id):
    try:
        obj_id = ObjectId(id)
        expenses.delete_one({"_id": obj_id, "user_id": session["user_id"]})
        flash("Expense deleted", "success")
    except:
        flash("Could not delete item", "danger")
    return redirect(url_for("index"))

# ------------------------
# Admin Routes
# ------------------------
@app.route("/admin/expenses")
@admin_required
def admin_expenses():
    all_expenses = list(expenses.find())
    for e in all_expenses:
        e["_id"] = str(e["_id"])
        d = e.get("date")
        e["date_str"] = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
    return render_template("admin_expenses.html", expenses=all_expenses)

@app.route("/admin/users")
@admin_required
def admin_users():
    all_users = list(users.find())
    for u in all_users:
        u["_id"] = str(u["_id"])
    return render_template("admin_users.html", users=all_users)

@app.route("/admin/export/<string:type>")
@admin_required
def admin_export(type):
    if type == "expenses":
        data = list(expenses.find())
    elif type == "users":
        data = list(users.find())
    else:
        flash("Invalid export type", "danger")
        return redirect(url_for("admin_expenses"))

    for d in data:
        d["_id"] = str(d["_id"])
        if "date" in d and isinstance(d["date"], datetime):
            d["date"] = d["date"].strftime("%Y-%m-%d")

    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)

    return send_file(output, download_name=f"{type}.xlsx", as_attachment=True)

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
