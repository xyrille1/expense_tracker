# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")

mongo = PyMongo(app)
db = mongo.db
expenses = db.expenses

@app.route("/")
def index():
    all_expenses = list(expenses.find().sort("date", -1))
    total = sum(e.get("amount", 0) for e in all_expenses)

    # category breakdown via aggregation
    pipeline = [
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}}
    ]
    category_agg = list(expenses.aggregate(pipeline))
    categories = [c["_id"] for c in category_agg]
    totals = [c["total"] for c in category_agg]

    # prepare for template (convert ObjectId, format date)
    for e in all_expenses:
        e["_id"] = str(e["_id"])
        d = e.get("date")
        e["date_str"] = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)

    return render_template("index.html",
                           expenses=all_expenses,
                           total=total,
                           categories=categories,
                           totals=totals)

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        category = request.form.get("category", "Uncategorized").strip()
        amount = request.form.get("amount", "0").strip()
        date_str = request.form.get("date", "").strip()
        try:
            amount = float(amount)
        except Exception:
            flash("Amount must be a number", "danger")
            return redirect(url_for("index"))

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            date_obj = datetime.utcnow()

        expenses.insert_one({
            "category": category,
            "amount": amount,
            "date": date_obj
        })
        flash("Expense added", "success")
        return redirect(url_for("index"))
    return render_template("add.html")

@app.route("/edit/<id>", methods=["GET", "POST"])
def edit(id):
    try:
        obj_id = ObjectId(id)
    except Exception:
        flash("Invalid id", "danger")
        return redirect(url_for("index"))

    exp = expenses.find_one({"_id": obj_id})
    if not exp:
        flash("Expense not found", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        category = request.form.get("category", exp.get("category", "Uncategorized")).strip()
        amount = request.form.get("amount", str(exp.get("amount", 0))).strip()
        date_str = request.form.get("date", "")
        try:
            amount = float(amount)
        except Exception:
            flash("Amount must be a number", "danger")
            return redirect(url_for("edit", id=id))

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            date_obj = exp.get("date", datetime.utcnow())

        expenses.update_one({"_id": obj_id}, {"$set": {
            "category": category,
            "amount": amount,
            "date": date_obj
        }})
        flash("Expense updated", "success")
        return redirect(url_for("index"))

    # prepare for template
    exp["_id"] = str(exp["_id"])
    d = exp.get("date")
    exp["date_str"] = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
    return render_template("edit.html", expense=exp)

@app.route("/delete/<id>", methods=["POST"])
def delete(id):
    try:
        obj_id = ObjectId(id)
        expenses.delete_one({"_id": obj_id})
        flash("Expense deleted", "success")
    except Exception:
        flash("Could not delete item", "danger")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
