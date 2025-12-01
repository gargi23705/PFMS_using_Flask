import os
import sqlite3
import datetime
import timeago
import pandas as pd
from functools import wraps
import pickle

from data_cleaning import get_clean_data_for_user
from flask import Flask, render_template, request, flash, redirect, url_for, session, jsonify
from passlib.hash import sha256_crypt
from wtforms import Form, StringField, PasswordField, validators
from wtforms import SubmitField, DecimalField, SelectField
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask_wtf import FlaskForm
import plotly.graph_objects as go


def get_db():
    db = sqlite3.connect("expense_tracker.db")
    db.row_factory = sqlite3.Row
    return db


app = Flask(__name__, static_url_path="/static")
app.secret_key = "supersecretgargi"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
MODEL_PATH = "model.pkl"


# ----------------- SIGNUP FORM -----------------
class SignUpForm(Form):
    first_name = StringField('First Name', [validators.Length(min=1, max=100)])
    last_name = StringField('Last Name', [validators.Length(min=1, max=100)])
    email = StringField('Email', [validators.DataRequired(), validators.Email()])
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


# ----------------- SIGNUP ROUTE -----------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'logged_in' in session:
        return redirect(url_for('addTransactions'))

    form = SignUpForm(request.form)

    if request.method == 'POST' and form.validate():
        db = get_db()
        cur = db.cursor()

        email = form.email.data
        username = form.username.data

        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            flash("Email already exists", "warning")
            return redirect(url_for('signup'))

        hashed_pw = sha256_crypt.hash(str(form.password.data))

        cur.execute("""
            INSERT INTO users (first_name, last_name, email, username, password)
            VALUES (?, ?, ?, ?, ?)
        """, (form.first_name.data, form.last_name.data, email, username, hashed_pw))

        db.commit()
        flash("Account created. Please login.", "success")
        return redirect(url_for('login'))

    return render_template("signUp.html", form=form)


# ----------------- LOGIN FORM -----------------
class LoginForm(Form):
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [validators.DataRequired()])


# ----------------- LOGIN ROUTE -----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm(request.form)

    if request.method == "POST" and form.validate():
        db = get_db()
        cur = db.cursor()

        cur.execute("SELECT * FROM users WHERE username = ?", (form.username.data,))
        user = cur.fetchone()

        if user and sha256_crypt.verify(form.password.data, user["password"]):
            session['logged_in'] = True
            session['username'] = user["username"]
            session['userID'] = user["id"]
            session['role'] = user["role"]
            flash("Logged in successfully", "success")
            return redirect(url_for("addTransactions"))

        flash("Invalid username or password", "danger")

    return render_template("login.html", form=form)


# ----------------- LOGIN CHECK DECORATOR -----------------
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "logged_in" in session:
            return f(*args, **kwargs)
        flash("Please login first", "warning")
        return redirect(url_for('login'))
    return wrap


# ----------------- LOGOUT -----------------
@app.route('/logout')
def logout():
    session.clear()
    flash("You are logged out", "success")
    return redirect(url_for("login"))

# ----------------- ADD SALARY -----------------
@app.route('/addSalary', methods=['GET', 'POST'])
@is_logged_in
def addSalary():
    if request.method == "POST":
        salary_amount = request.form['salary_amount']
        month = datetime.datetime.now().strftime("%m")
        year = datetime.datetime.now().strftime("%Y")
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO salary (user_id, salary_amount, month, year, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session['userID'], salary_amount, month, year, created_at))

        db.commit()

        flash("Salary added successfully!", "success")
        return redirect(url_for('addTransactions'))

    return render_template("addSalary.html")


# ----------------- ADD TRANSACTIONS -----------------
@app.route('/addTransactions', methods=['GET', 'POST'])
@is_logged_in
def addTransactions():
    db = get_db()
    cur = db.cursor()

    # ---------- SAVE NEW TRANSACTION ----------
    if request.method == 'POST':
        amount = request.form['amount']
        description = request.form['description']
        category = request.form['category']

        date = request.form.get('date')
        if date:
            date = date.replace("T", " ")  # convert HTML datetime-local format
        else:
            date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO transactions (user_id, amount, description, category, date)
            VALUES (?, ?, ?, ?, ?)
        """, (session['userID'], amount, description, category, date))

        db.commit()
        flash("Transaction added successfully!", "success")
        return redirect(url_for("addTransactions"))

    # ---------- SUMMARY FOR CURRENT MONTH ----------
    cur.execute("""
        SELECT SUM(amount) AS total
        FROM transactions
        WHERE user_id = ?
        AND strftime('%m', date) = strftime('%m', 'now')
        AND strftime('%Y', date) = strftime('%Y', 'now')
    """, (session['userID'],))
    totalExpenses = cur.fetchone()['total'] or 0

    # ---------- MONTHLY SALARY ----------
    cur.execute("""
        SELECT salary_amount FROM salary
        WHERE user_id = ?
        AND month = strftime('%m', 'now')
        AND year = strftime('%Y', 'now')
        ORDER BY id DESC LIMIT 1
    """, (session['userID'],))
    salary_data = cur.fetchone()
    monthly_salary = salary_data['salary_amount'] if salary_data else 0

    remaining_balance = monthly_salary - totalExpenses

    # ---------- FETCH CURRENT MONTH TRANSACTIONS ----------
    cur.execute("""
        SELECT * FROM transactions
        WHERE user_id = ?
        AND strftime('%m', date) = strftime('%m', 'now')
        AND strftime('%Y', date) = strftime('%Y', 'now')
        ORDER BY date DESC
    """, (session['userID'],))
    rows = cur.fetchall()

    transactions = []
    for t in rows:
        original = t['date']
        try:
            dt = datetime.datetime.strptime(original, "%Y-%m-%d %H:%M:%S")
        except:
            try:
                dt = datetime.datetime.strptime(original, "%Y-%m-%d %H:%M")
            except:
                dt = None

        if dt:
            if datetime.datetime.now() - dt < datetime.timedelta(hours=12):
                formatted = timeago.format(dt, datetime.datetime.now())
            else:
                formatted = dt.strftime("%d %B, %Y")
        else:
            formatted = original

        item = dict(t)
        item["date"] = formatted
        transactions.append(item)

    # ---------- LOAD USER CATEGORIES ----------
    cur.execute("SELECT * FROM categories WHERE user_id = ?", (session['userID'],))
    user_categories = cur.fetchall()

    # ==========================================================
    # 🚀 CATEGORY-WISE EXPENSE BAR GRAPH (THIS MONTH ONLY)
    # ==========================================================
    cur.execute("""
        SELECT category, SUM(amount) AS total_amount
        FROM transactions
        WHERE user_id = ?
        AND strftime('%m', date) = strftime('%m', 'now')
        AND strftime('%Y', date) = strftime('%Y', 'now')
        GROUP BY category
    """, (session['userID'],))

    cat_rows = cur.fetchall()

    if cat_rows:
        cat_df = pd.DataFrame(cat_rows, columns=["category", "total_amount"])
    else:
        cat_df = pd.DataFrame(columns=["category", "total_amount"])

    fig_cat = go.Figure()
    fig_cat.add_trace(go.Bar(
        x=cat_df["category"],
        y=cat_df["total_amount"],
        text=cat_df["total_amount"],
        textposition="outside"
    ))

    fig_cat.update_layout(
        title="Category-wise Expenses (This Month)",
        xaxis_title="Category",
        yaxis_title="Amount (₹)",
        bargap=0.3
    )

    category_bar_graph = fig_cat.to_html(full_html=False)

    # ---------- FINAL PAGE RETURN ----------
    return render_template(
        "addTransactions.html",
        totalExpenses=totalExpenses,
        transactions=transactions,
        monthly_salary=monthly_salary,
        remaining_balance=remaining_balance,
        user_categories=user_categories,
        category_bar_graph=category_bar_graph
    )


# ----------------- TRANSACTION HISTORY -----------------
@app.route('/transactionHistory', methods=['GET', 'POST'])
@is_logged_in
def transactionHistory():
    db = get_db()
    cur = db.cursor()

    # --------------------- POST FILTER ---------------------
    if request.method == "POST":
        month = request.form['month']
        year = request.form['year']

        # TOTAL EXPENSE
        if month == "00":
            cur.execute("""
                SELECT SUM(amount) AS total FROM transactions
                WHERE strftime('%Y', date) = ?
                AND user_id = ?
            """, (year, session['userID']))
        else:
            cur.execute("""
                SELECT SUM(amount) AS total FROM transactions
                WHERE strftime('%m', date) = ?
                AND strftime('%Y', date) = ?
                AND user_id = ?
            """, (month, year, session['userID']))

        totalExpenses = cur.fetchone()['total'] or 0

        # SALARY
        cur.execute("""
            SELECT salary_amount FROM salary
            WHERE user_id = ? AND month = ? AND year = ?
            ORDER BY id DESC LIMIT 1
        """, (session['userID'], month, year))
        s = cur.fetchone()

        monthly_salary = s['salary_amount'] if s else 0
        saved_salary = monthly_salary - totalExpenses

        # FETCH TRANSACTIONS
        if month == "00":
            cur.execute("""
                SELECT * FROM transactions
                WHERE strftime('%Y', date) = ?
                AND user_id = ?
                ORDER BY date DESC
            """, (year, session['userID']))
        else:
            cur.execute("""
                SELECT * FROM transactions
                WHERE strftime('%m', date) = ?
                AND strftime('%Y', date) = ?
                AND user_id = ?
                ORDER BY date DESC
            """, (month, year, session['userID']))

        rows = cur.fetchall()

    # --------------------- DEFAULT GET: CURRENT MONTH ---------------------
    else:
        cur.execute("""
            SELECT SUM(amount) AS total FROM transactions
            WHERE strftime('%m', date) = strftime('%m', 'now')
            AND strftime('%Y', date) = strftime('%Y', 'now')
            AND user_id = ?
        """, (session['userID'],))
        totalExpenses = cur.fetchone()['total'] or 0

        # Salary for current month
        cur.execute("""
            SELECT salary_amount FROM salary
            WHERE user_id = ?
            AND month = strftime('%m', 'now')
            AND year = strftime('%Y', 'now')
            ORDER BY id DESC LIMIT 1
        """, (session['userID'],))
        s = cur.fetchone()

        monthly_salary = s['salary_amount'] if s else 0
        saved_salary = monthly_salary - totalExpenses

        # Fetch current month transactions
        cur.execute("""
            SELECT * FROM transactions
            WHERE strftime('%m', date) = strftime('%m', 'now')
            AND strftime('%Y', date) = strftime('%Y', 'now')
            AND user_id = ?
            ORDER BY date DESC
        """, (session['userID'],))
        rows = cur.fetchall()

    # --------------------- FORMAT DATES SAFELY ---------------------
    transactions = []
    for t in rows:
        original_date = t['date']
        dt = None

        # Try parsing date
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.datetime.strptime(original_date, fmt)
                break
            except:
                continue

        if dt:
            try:
                formatted = dt.strftime("%d %B %Y, %I:%M %p")
            except:
                formatted = original_date
        else:
            formatted = original_date

        # Convert row into dict
        record = dict(t)
        record['date'] = formatted
        transactions.append(record)

    return render_template(
        "transactionHistory.html",
        transactions=transactions,
        totalExpenses=totalExpenses,
        monthly_salary=monthly_salary,
        saved_salary=saved_salary
    )


# ----------------- EDIT TRANSACTION -----------------
@app.route('/editCurrentMonthTransaction/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def editCurrentMonthTransaction(id):
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (id, session['userID']))
    trans = cur.fetchone()

    if not trans:
        flash("Transaction not found", "danger")
        return redirect(url_for('addTransactions'))

    if request.method == "POST":
        amount = request.form['amount']
        description = request.form['description']

        cur.execute("""
            UPDATE transactions
            SET amount = ?, description = ?
            WHERE id = ? AND user_id = ?
        """, (amount, description, id, session['userID']))

        db.commit()
        flash("Transaction updated!", "success")
        return redirect(url_for('addTransactions'))

    return render_template("editTransaction.html", transaction=trans)


# ----------------- DELETE TRANSACTION -----------------
@app.route('/deleteCurrentMonthTransaction/<string:id>', methods=['POST'])
@is_logged_in
def deleteCurrentMonthTransaction(id):
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (id, session['userID']))
    db.commit()

    flash("Transaction deleted!", "success")
    return redirect(url_for('addTransactions'))


# ----------------- CATEGORIES -----------------
@app.route('/categories')
@is_logged_in
def manageCategories():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM categories WHERE user_id = ?", (session['userID'],))
    categories = cur.fetchall()

    return render_template("categories.html", categories=categories)


@app.route('/addCategory', methods=['POST'])
@is_logged_in
def addCategory():
    name = request.form.get("category_name")

    if not name:
        flash("Category cannot be empty", "danger")
        return redirect(url_for('manageCategories'))

    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO categories (user_id, category_name) VALUES (?, ?)",
                (session['userID'], name))
    db.commit()

    flash("Category added!", "success")
    return redirect(url_for('manageCategories'))


@app.route('/editCategory/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def editCategory(id):
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM categories WHERE id = ? AND user_id = ?", (id, session['userID']))
    category = cur.fetchone()

    if not category:
        flash("Category not found!", "danger")
        return redirect(url_for('manageCategories'))

    if request.method == "POST":
        new_name = request.form['category_name']

        cur.execute("""
            UPDATE categories SET category_name = ?
            WHERE id = ? AND user_id = ?
        """, (new_name, id, session['userID']))

        db.commit()
        flash("Category updated!", "success")
        return redirect(url_for('manageCategories'))

    return render_template("editCategory.html", category=category)


@app.route('/deleteCategory/<string:id>', methods=['POST'])
@is_logged_in
def deleteCategory(id):
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (id, session['userID']))
    db.commit()

    flash("Category deleted!", "success")
    return redirect(url_for('manageCategories'))

# ----------------- CATEGORY DATA API (Pie Chart) -----------------
@app.route('/category-data')
@is_logged_in
def category_data():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT category, SUM(amount) AS amount
        FROM transactions
        WHERE user_id = ?
          AND strftime('%Y', date) = strftime('%Y', 'now')
        GROUP BY category
    """, (session['userID'],))

    rows = cur.fetchall()

    amounts = [float(r['amount']) for r in rows]
    categories = [r['category'] for r in rows]

    return jsonify({
        'amount': amounts,
        'category': categories
    })

# ----------------- DASHBOARD -----------------
@app.route('/dashboard')
@is_logged_in
def dashboard():
    user_id = session.get("userID")

    # If no file, return empty dashboard safely
    if not os.path.exists("cleaned_data.csv"):
        return render_template("dashboard.html",
                               prediction=None,
                               monthly_graph="", yearly_graph="", daily_graph="", pie_graph="",
                               total_spent=0, avg_spent=0, max_spent=0, min_spent=0,
                               top_categories=[], yearly_labels=[], yearly_saved_values=[])

    df = pd.read_csv("cleaned_data.csv")

    if df.empty:
        return render_template("dashboard.html",
                               prediction=None,
                               monthly_graph="", yearly_graph="", daily_graph="", pie_graph="",
                               total_spent=0, avg_spent=0, max_spent=0, min_spent=0,
                               top_categories=[], yearly_labels=[], yearly_saved_values=[])

    # ---------------------------
    # FIX DATE COLUMN
    # ---------------------------
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notnull()].reset_index(drop=True)

    df["year"] = df["date"].dt.year.astype(int)
    df["month"] = df["date"].dt.month.astype(int)
    df["category"] = df["category"].fillna("Others")

    # ---------------------------
    # SUMMARY VALUES
    # ---------------------------
    total_spent = float(df["amount"].sum())
    avg_spent = float(df["amount"].mean())
    max_spent = float(df["amount"].max())
    min_spent = float(df["amount"].min())

    # ---------------------------
    # TOP CATEGORIES
    # ---------------------------
    category_sum = df.groupby("category")["amount"].sum().reset_index()
    top_categories = (
        category_sum.sort_values("amount", ascending=False)
                    .head(5)
                    .to_dict(orient="records")
    )

    # ---------------------------
    # MONTHLY TREND
    # ---------------------------
    monthly = df.groupby(df["date"].dt.to_period("M"))["amount"].sum().reset_index()
    monthly["month"] = monthly["date"].astype(str)   # <-- correct

    fig_m = go.Figure()
    fig_m.add_trace(go.Scatter(x=monthly["month"], y=monthly["amount"],
                               mode="lines+markers"))
    fig_m.update_layout(yaxis=dict(tickformat=",d"))
    monthly_graph = fig_m.to_html(full_html=False)

    # ---------------------------
    # DAILY TREND (LAST 30 DAYS)
    # ---------------------------
    last30 = df[df["date"] >= pd.Timestamp.today() - pd.Timedelta(days=30)]
    daily = last30.groupby(last30["date"].dt.date)["amount"].sum().reset_index()

    fig_d = go.Figure()
    if not daily.empty:
        fig_d.add_trace(go.Bar(x=daily["date"].astype(str), y=daily["amount"]))
    daily_graph = fig_d.to_html(full_html=False)

    # ---------------------------
    # YEARLY EXPENSE
    # ---------------------------
    yearly_exp = df.groupby("year")["amount"].sum().reset_index()

    # ---------------------------
    # YEARLY SALARY FROM DB
    # ---------------------------
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT year, SUM(salary_amount)
        FROM salary
        WHERE user_id=?
        GROUP BY year
    """, (user_id,))
    rows = cur.fetchall()
    salary_df = pd.DataFrame(rows, columns=["year", "salary"])
    salary_df["year"] = salary_df["year"].astype(int)

    # ---------------------------
    # MERGE BOTH
    # ---------------------------
    combined = pd.merge(yearly_exp, salary_df, on="year", how="outer").fillna(0)
    combined["saved"] = combined.apply(lambda r: max(r["salary"] - r["amount"], 0), axis=1)


    # YEARLY GRAPH
    fig_y = go.Figure()
    fig_y.add_trace(go.Bar(name="Expense", x=combined["year"], y=combined["amount"]))
    fig_y.add_trace(go.Bar(name="Salary", x=combined["year"], y=combined["salary"]))
    fig_y.add_trace(go.Bar(name="Saved", x=combined["year"], y=combined["saved"]))

    fig_y.update_layout(
        barmode="group",
        yaxis=dict(tickformat=",d")   # <-- removes K or M formatting
    )

    yearly_graph = fig_y.to_html(full_html=False)


    # ---------------------------
    # PIE CHART
    # ---------------------------
    fig_p = go.Figure(data=[go.Pie(labels=category_sum["category"],
                                   values=category_sum["amount"])])
    pie_graph = fig_p.to_html(full_html=False)

    # ---------------------------
    # PREDICTION
    # ---------------------------
    try:
        prediction = predict_next_month()
    except:
        prediction = None

    # ---------------------------
    # RENDER PAGE
    # ---------------------------
    return render_template(
        "dashboard.html",
        prediction=prediction,
        monthly_graph=monthly_graph,
        yearly_graph=yearly_graph,
        pie_graph=pie_graph,
        daily_graph=daily_graph,
        top_categories=top_categories,
        total_spent=total_spent,
        avg_spent=avg_spent,
        max_spent=max_spent,
        min_spent=min_spent,
        yearly_labels=combined["year"].astype(str).tolist(),
        yearly_saved_values=combined["saved"].tolist()
    )



@app.route('/upload_excel', methods=['POST'])
def upload_excel():
    file = request.files.get("excel_file")

    # 1. Check if file exists
    if not file or file.filename.strip() == "":
        flash("Please select a CSV or Excel file.", "danger")
        return redirect(url_for("dashboard"))

    filename = file.filename.lower()

    # 2. Read file safely
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(file, encoding="utf-8")
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(file)
        else:
            flash("Only CSV or Excel files are supported.", "danger")
            return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Error reading file: {str(e)}", "danger")
        return redirect(url_for("dashboard"))

    # 3. Normalize column names
    df.columns = df.columns.str.lower().str.strip()

    # 4. Required columns
    if "date" not in df.columns or "amount" not in df.columns:
        flash("File must contain 'date' and 'amount' columns!", "danger")
        return redirect(url_for("dashboard"))

    # 5. Clean DATE
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notnull()]

    # 6. Clean AMOUNT (no K, no conversion)
    df["amount"] = df["amount"].astype(str)

    # Remove currency symbols and commas only
    df["amount"] = (
        df["amount"]
        .str.replace("₹", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    # Convert to number
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df[df["amount"].notnull()]

    # Remove extreme wrong values above 2 lakh (your limit)
    df = df[df["amount"] <= 200000]

    # 7. Category
    if "category" not in df.columns:
        df["category"] = "Others"
    else:
        df["category"] = df["category"].fillna("Others")

    # 8. Add year & month
    df["year"] = df["date"].dt.year.astype(int)
    df["month"] = df["date"].dt.month.astype(int)

    # 9. Remove duplicates
    df = df.drop_duplicates()

    # 10. Sort
    df = df.sort_values("date").reset_index(drop=True)

    # 11. Save cleaned file
    try:
        df.to_csv("cleaned_data.csv", index=False)
    except Exception as e:
        flash(f"Could not save cleaned data: {e}", "danger")
        return redirect(url_for("dashboard"))

    flash("File cleaned & uploaded successfully!", "success")

    return redirect(url_for("dashboard"))


def train_model():
    if not os.path.exists("cleaned_data.csv"):
        return

    df = pd.read_csv("cleaned_data.csv")

    if df.empty:
        return

    if "year" not in df.columns or "month" not in df.columns:
        # Recreate if missing
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notnull()]
        df["year"] = df["date"].dt.year.astype(int)
        df["month"] = df["date"].dt.month.astype(int)

    monthly = df.groupby(["year", "month"])["amount"].sum().reset_index()

    if monthly.empty or len(monthly) < 2:
        return

    monthly["month_index"] = range(1, len(monthly) + 1)

    X = monthly["month_index"].values
    y = monthly["amount"].values

    if len(X) == 0 or len(y) == 0:
        return

    mean_x = X.mean()
    mean_y = y.mean()

    numerator = ((X - mean_x) * (y - mean_y)).sum()
    denominator = ((X - mean_x) ** 2).sum()

    if denominator == 0:
        return

    m = numerator / denominator
    c = mean_y - (m * mean_x)

    model = {"m": float(m), "c": float(c)}
    pickle.dump(model, open(MODEL_PATH, "wb"))

def predict_next_month():
    if not os.path.exists(MODEL_PATH) or not os.path.exists("cleaned_data.csv"):
        return None

    df = pd.read_csv("cleaned_data.csv")

    if df.empty:
        return None

    if "year" not in df.columns or "month" not in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notnull()]
        df["year"] = df["date"].dt.year.astype(int)
        df["month"] = df["date"].dt.month.astype(int)

    monthly = df.groupby(["year", "month"])["amount"].sum().reset_index()

    if monthly.empty:
        return None

    next_index = len(monthly) + 1

    model = pickle.load(open(MODEL_PATH, "rb"))
    prediction = model["m"] * next_index + model["c"]

    return round(float(prediction), 2)


# ----------------- HOME PAGE -----------------
@app.route('/')
def index():
    return render_template("index.html")


# ----------------- FINAL APP RUN -----------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )
