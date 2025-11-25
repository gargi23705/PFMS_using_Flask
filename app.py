from data_cleaning import get_clean_data_for_user
from flask import Flask, render_template, request, flash, redirect, url_for, session, logging, jsonify, Response
from wtforms import Form, StringField, PasswordField, TextAreaField, validators, SubmitField,DecimalField, SelectField
from wtforms.validators import DataRequired, Length
from passlib.hash import sha256_crypt
from functools import wraps
import timeago
import datetime
from wtforms import StringField
from wtforms.validators import Email
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
import plotly.graph_objects as go
import mysql.connector
import pandas as pd

# import _mysql_connector 

app = Flask(__name__, static_url_path='/static')

app.secret_key = 'supersecretgargi'

# app.config.from_pyfile('config.py')
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''   # EMPTY PASSWORD for XAMPP
app.config['MYSQL_DB'] = 'expense_tracker'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'


# FLASK-MYSQLDB (only if your project uses MySQL queries)


mail = Mail(app)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')



class SignUpForm(Form):
    first_name = StringField('First Name', [validators.Length(min=1, max=100)])
    last_name = StringField('Last Name', [validators.Length(min=1, max=100)])
    email = StringField('Email address', [
                       validators.DataRequired(), validators.Email()])
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'logged_in' in session and session['logged_in'] == True:
        flash('You are already logged in', 'info')
        return redirect(url_for('addTransactions'))

    form = SignUpForm(request.form)

    if request.method == 'POST' and form.validate():

        first_name = form.first_name.data
        last_name  = form.last_name.data
        email      = form.email.data
        username   = form.username.data
        password   = sha256_crypt.encrypt(str(form.password.data))

        db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker")
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", [email])
        user = cur.fetchone()

        if user and sha256_crypt.verify(password, user['password']):
          session['logged_in'] = True
          session['username']  = user['username']
          session['role']      = user['role']   # IMPORTANT

        # Check email already exists
        result = cur.execute("SELECT * FROM users WHERE email=%s", [email])

        if result > 0:
            flash('Email already exists. Try another one.', 'info')
            return redirect(url_for('signup'))
        else:
            cur.execute("""
                INSERT INTO users(first_name, last_name, email, username, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (first_name, last_name, email, username, password))

            db.commit()
            cur.close()

            flash('You are now registered and can log in', 'success')
            return redirect(url_for('login'))

    return render_template('signUp.html', form=form)



class LoginForm(Form):
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [
        validators.DataRequired(),
    ])

class TransactionForm(FlaskForm):
    amount = DecimalField('Amount', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    category = SelectField('Category', choices=[
        ('Food', 'Food'),
        ('Transportation', 'Transportation'),
        ('Clothing', 'Clothing'),
        ('Bills and Taxes', 'Bills and Taxes'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    submit = SubmitField('Submit')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session and session['logged_in'] == True:
        flash('You are already logged in', 'info')
        return redirect(url_for('addTransactions'))
    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        username = form.username.data
        password_input = form.password.data

        db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="expense_tracker"
    )
        cur = db.cursor(dictionary=True)
        result = cur.execute(
            "SELECT * FROM users WHERE username = %s", [username])
        data = cur.fetchone()

        if data :
            userID = data['id']
            password = data['password']
            role = data['role']

            if sha256_crypt.verify(password_input, password):
                session['logged_in'] = True
                session['username'] = username
                session['role'] = role
                session['userID'] = userID
                flash('You are now logged in', 'success')
                return redirect(url_for('addTransactions'))
            else:
                error = 'Invalid Password'
                return render_template('login.html', form=form, error=error)
            
            cur.close()

        else:
            error = 'Username not found'
            return render_template('login.html', form=form, error=error)

    return render_template('login.html', form=form)


def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Please login', 'info')
            return redirect(url_for('login'))
    return wrap


# salary
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))

@app.route('/addSalary', methods=['GET', 'POST'])
@is_logged_in
def addSalary():
    if request.method == 'POST':
        salary_amount = request.form['salary_amount']
        month = datetime.datetime.now().strftime("%m")
        year = datetime.datetime.now().strftime("%Y")

        db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
        cur = db.cursor(dictionary=True)

        cur.execute(
            "INSERT INTO salary(user_id, salary_amount, month, year) VALUES (%s, %s, %s, %s)",
            (session['userID'], salary_amount, month, year)
        )
        db.commit()
        cur.close()

        flash("Salary Added Successfully", "success")
        return redirect(url_for('addTransactions'))

    return render_template("addSalary.html")


@app.route('/addTransactions', methods=['GET', 'POST'])
@is_logged_in
def addTransactions():
    # ---------- POST: Add a new transaction ----------
    if request.method == 'POST':
        amount = request.form['amount']
        description = request.form['description']
        category = request.form['category']
        date = request.form.get('date')

        if date:
            date = date.replace('T', ' ')
        else:
            date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="expense_tracker"
        )
        cur = db.cursor(dictionary=True)

        cur.execute(
            "INSERT INTO transactions (user_id, amount, description, category, date) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session['userID'], amount, description, category, date)
        )
        db.commit()
        cur.close()
        db.close()

        flash('Transaction Successfully Recorded', 'success')
        return redirect(url_for('addTransactions'))


    # ---------- GET: Load page with salary, expenses, categories ----------
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="expense_tracker"
    )
    cur = db.cursor(dictionary=True)

    # Total monthly expenses
    cur.execute(
        "SELECT SUM(amount) AS total FROM transactions "
        "WHERE MONTH(date)=MONTH(CURRENT_DATE()) "
        "AND YEAR(date)=YEAR(CURRENT_DATE()) "
        "AND user_id=%s",
        (session['userID'],)     # ✔ FIXED
    )
    totalExpenses = cur.fetchone()['total'] or 0

    # Salary fetch
    cur.execute(
        "SELECT salary_amount FROM salary "
        "WHERE user_id=%s "
        "AND month=MONTH(CURRENT_DATE()) "
        "AND year=YEAR(CURRENT_DATE()) "
        "ORDER BY id DESC LIMIT 1",
        (session['userID'],)     # ✔ FIXED
    )
    salary_data = cur.fetchone()
    monthly_salary = salary_data['salary_amount'] if salary_data else 0

    remaining_balance = monthly_salary - totalExpenses

    # Fetch transactions
    cur.execute(
        "SELECT * FROM transactions "
        "WHERE MONTH(date)=MONTH(CURRENT_DATE()) "
        "AND YEAR(date)=YEAR(CURRENT_DATE()) "
        "AND user_id=%s ORDER BY date DESC",
        (session['userID'],)     # ✔ FIXED
    )
    transactions = cur.fetchall()

    # ⭐ FETCH USER CATEGORIES (FIXED)
    cur.execute(
        "SELECT * FROM categories WHERE user_id=%s",
        (session['userID'],)     # ✔✔ MOST IMPORTANT FIX
    )
    user_categories = cur.fetchall()

    # Format transaction dates
    for t in transactions:
        if isinstance(t['date'], datetime.datetime):
            if datetime.datetime.now() - t['date'] < datetime.timedelta(days=0.5):
                t['date'] = timeago.format(t['date'], datetime.datetime.now())
            else:
                t['date'] = t['date'].strftime('%d %B, %Y')

    cur.close()
    db.close()

    return render_template(
        "addTransactions.html",
        totalExpenses=totalExpenses,
        transactions=transactions,
        monthly_salary=monthly_salary,
        remaining_balance=remaining_balance,
        user_categories=user_categories   # ✔ dropdown will now show new categories
    )



@app.route('/transactionHistory', methods=['GET', 'POST'])
@is_logged_in
def transactionHistory():

    month = None
    year = None

    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)


    # ========== POST (when filter used) ==========
    if request.method == "POST":
        month = request.form['month']
        year = request.form['year']

        if month == "00":
            cur.execute(
                "SELECT SUM(amount) AS total FROM transactions WHERE YEAR(date)=%s AND user_id=%s",
                (year, session['userID'])
            )
        else:
            cur.execute(
                "SELECT SUM(amount) AS total FROM transactions WHERE MONTH(date)=%s AND YEAR(date)=%s AND user_id=%s",
                (month, year, session['userID'])
            )

        totalExpenses = cur.fetchone()['total'] or 0

        cur.execute(
            "SELECT salary_amount FROM salary WHERE user_id=%s AND month=%s AND year=%s ORDER BY id DESC LIMIT 1",
            (session['userID'], month, year)
        )
        s = cur.fetchone()
        monthly_salary = s['salary_amount'] if s else 0
        saved_salary = monthly_salary - totalExpenses

        if month == "00":
            cur.execute(
                "SELECT * FROM transactions WHERE YEAR(date)=%s AND user_id=%s ORDER BY date DESC",
                (year, session['userID'])
            )
        else:
            cur.execute(
                "SELECT * FROM transactions WHERE MONTH(date)=%s AND YEAR(date)=%s AND user_id=%s ORDER BY date DESC",
                (month, year, session['userID'])
            )

        transactions = cur.fetchall()
        cur.close()

        return render_template(
            'transactionHistory.html',
            transactions=transactions,
            totalExpenses=totalExpenses,
            monthly_salary=monthly_salary,
            saved_salary=saved_salary
        )

    # ---------------- GET DEFAULT (CURRENT MONTH) --------------------
    cur.execute(
        "SELECT SUM(amount) AS total FROM transactions WHERE MONTH(date)=MONTH(CURRENT_DATE()) AND YEAR(date)=YEAR(CURRENT_DATE()) AND user_id=%s",
        [session['userID']]
    )
    totalExpenses = cur.fetchone()['total'] or 0

    cur.execute(
        "SELECT salary_amount FROM salary WHERE user_id=%s AND month=MONTH(CURRENT_DATE()) AND year=YEAR(CURRENT_DATE()) ORDER BY id DESC LIMIT 1",
        [session['userID']]
    )
    s = cur.fetchone()
    monthly_salary = s['salary_amount'] if s else 0
    saved_salary = monthly_salary - totalExpenses

    cur.execute(
        "SELECT * FROM transactions WHERE MONTH(date)=MONTH(CURRENT_DATE()) AND YEAR(date)=YEAR(CURRENT_DATE()) AND user_id=%s ORDER BY date DESC",
        [session['userID']]
    )
    transactions = cur.fetchall()
    cur.close()

    return render_template(
        'transactionHistory.html',
        transactions=transactions,
        totalExpenses=totalExpenses,
        monthly_salary=monthly_salary,
        saved_salary=saved_salary
    )
  

@app.route('/editCurrentMonthTransaction/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def editCurrentMonthTransaction(id):
    # Create cursor
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)


    # Get transaction by id
    cur.execute("SELECT * FROM transactions WHERE id = %s", [id])

    transaction = cur.fetchone()
    cur.close()
    # Get form
    form = TransactionForm(request.form)

    # Populate transaction form fields
    form.amount.data = transaction['amount']
    form.description.data = transaction['description']

    if request.method == 'POST' and form.validate():
        amount = request.form['amount']
        description = request.form['description']

        # Create Cursor
        db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
        cur = db.cursor(dictionary=True)

        # Execute
        cur.execute("UPDATE transactions SET amount=%s, description=%s WHERE id = %s",
                    (amount, description, id))
        # Commit to DB
        db.commit() 

        # Close connection
        cur.close()

        flash('Transaction Updated', 'success')

        return redirect(url_for('addTransactions'))

    return render_template('editTransaction.html', form=form)


# Delete transaction
@app.route('/deleteCurrentMonthTransaction/<string:id>', methods=['POST'])
@is_logged_in
def deleteCurrentMonthTransaction(id):
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)    
    cur.execute("DELETE FROM transactions WHERE id=%s AND user_id=%s", (id, session['userID']))
    db.commit()
    cur.close()
    flash("Transaction Deleted Successfully", "success")
    return redirect(url_for('addTransactions'))


class RequestResetForm(Form):
    email = StringField('Email address', [
                       validators.DataRequired(), validators.Email()])


@app.route("/reset_request", methods=['GET', 'POST'])
def reset_request():
    if 'logged_in' in session and session['logged_in'] == True:
        flash('You are already logged in', 'info')
        return redirect(url_for('index'))
    form = RequestResetForm(request.form)
    if request.method == 'POST' and form.validate():
        email = form.email.data
        cur = mysql.connection.cursor()
        result = cur.execute(
            "SELECT id,username,email FROM users WHERE email = %s", [email])
        if result == 0:
            flash(
                'There is no account with that email. You must register first.', 'warning')
            return redirect(url_for('signup'))
        else:
            data = cur.fetchone()
            user_id = data['id']
            user_email = data['email']
            cur.close()
            s = Serializer(app.config['SECRET_KEY'])
            token = s.dumps({'user_id': user_id})
            msg = Message('Password Reset Request',
                          sender='noreply@demo.com', recipients=[user_email])
            msg.body = f'''To reset your password, visit the following link:
            {url_for('reset_token', token=token, _external=True)}
            If you did not make password reset request then simply ignore this email and no changes will be made.
            Note:This link is valid only for 30 mins from the time you requested a password change request.
                                                   '''
            mail.send(msg)
            flash(
                'An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('login'))
    return render_template('reset_request.html', form=form)


class ResetPasswordForm(Form):
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if 'logged_in' in session and session['logged_in'] == True:
        flash('You are already logged in', 'info')
        return redirect(url_for('index'))
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=1800)
            user_id = data['user_id']
        except:
            flash("Token is invalid or expired", "warning")
            return redirect(url_for("reset_request"))
    cur.execute("SELECT id FROM users WHERE id = %s", [user_id])
    data = cur.fetchone()
    cur.close()
    user_id = data['id']
    form = ResetPasswordForm(request.form)
    if request.method == 'POST' and form.validate():
        password = sha256_crypt.encrypt(str(form.password.data))
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE users SET password = %s WHERE id = %s", (password, user_id))
        db.commit()
        cur.close()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)

# Category Wise Pie Chart For Current Year As Percentage #
@app.route('/category-data')
def category_data():
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)


    query = """
        SELECT SUM(amount) AS amount, category
        FROM transactions
        WHERE YEAR(date) = YEAR(CURRENT_DATE())
          AND user_id = %s
        GROUP BY category
        ORDER BY category
    """
    
    cur.execute(query, (session['userID'],))
    rows = cur.fetchall()

    amounts = [float(row['amount']) for row in rows]
    categories = [row['category'] for row in rows]

    return jsonify({
        'amount': amounts,
        'category': categories
    })

# ... other imports above ...

# Replace your existing /dashboard route with this:
@app.route('/dashboard')
@is_logged_in
def dashboard():
    # require userID
    user_id = session.get('userID')
    if not user_id:
        flash("Please log in to view the dashboard", "info")
        return redirect(url_for('login'))

    # get cleaned data for this user
    df = get_clean_data_for_user(user_id)

    # ---- Prepare Monthly Trend (last 12 months) ----
    df['month'] = df['date'].dt.to_period('M').dt.to_timestamp()
    monthly_sum = (df.groupby('month')['amount'].sum()
                     .reset_index().sort_values('month'))

    # if empty, create placeholder
    if monthly_sum.empty:
        monthly_sum = pd.DataFrame({'month': [], 'amount': []})

    fig_month = go.Figure()
    fig_month.add_trace(go.Scatter(
        x=monthly_sum['month'].dt.strftime('%Y-%m'),
        y=monthly_sum['amount'],
        mode='lines+markers',
        name='Monthly'
    ))
    fig_month.update_layout(
        title='Monthly Spending (Last 12 months)',
        template='plotly_dark',
        margin=dict(t=40, b=30)
    )
    monthly_graph = fig_month.to_html(full_html=False)

    # ---- Yearly Trend ----
    df['year'] = df['date'].dt.year
    yearly_sum = df.groupby('year')['amount'].sum().reset_index().sort_values('year')
    fig_year = go.Figure()
    fig_year.add_trace(go.Bar(x=yearly_sum['year'].astype(str), y=yearly_sum['amount']))
    fig_year.update_layout(title='Yearly Spending', template='plotly_dark', margin=dict(t=40, b=30))
    yearly_graph = fig_year.to_html(full_html=False)

    # ---- Category Pie ----
    category_sum = df.groupby('category')['amount'].sum().reset_index().sort_values('amount', ascending=False)
    fig_pie = go.Figure(data=[go.Pie(labels=category_sum['category'], values=category_sum['amount'], hole=0.35)])
    fig_pie.update_layout(title='Category-wise Spending', template='plotly_dark', margin=dict(t=40, b=30))
    pie_graph = fig_pie.to_html(full_html=False)

    # ---- Daily Trend (last 30 days) ----
    cutoff = pd.Timestamp.today() - pd.Timedelta(days=30)
    last30 = df[df['date'] >= cutoff]
    daily = last30.groupby(last30['date'].dt.date)['amount'].sum().reset_index()
    fig_day = go.Figure()
    fig_day.add_trace(go.Scatter(x=daily['date'].astype(str), y=daily['amount'], mode='lines+markers'))
    fig_day.update_layout(title='Daily (Last 30 days)', template='plotly_dark', margin=dict(t=40, b=30))
    daily_graph = fig_day.to_html(full_html=False)

    # ---- Summary Metrics ----
    total_spent = float(df['amount'].sum()) if not df.empty else 0.0
    avg_spent = float(df['amount'].mean()) if not df.empty else 0.0
    max_spent = float(df['amount'].max()) if not df.empty else 0.0
    min_spent = float(df['amount'].min()) if not df.empty else 0.0
    top_categories = category_sum.head(5).to_dict(orient='records')

    # ----yearly metrics-----

    # ---- Yearly Saved Salary Calculation ----
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)

    cur.execute("""
    SELECT year, SUM(salary_amount) AS yearly_salary
    FROM salary
    WHERE user_id=%s
    GROUP BY year
    ORDER BY year
    """, [session['userID']])
    salary_year_data = cur.fetchall()
    cur.close()

    salary_df = pd.DataFrame(salary_year_data)

# Convert to integer
    salary_df['year'] = salary_df['year'].astype(int)

# Expense grouped by year
    df['year'] = df['date'].dt.year.astype(int)
    expense_yearly = df.groupby('year')['amount'].sum().reset_index()

# Merge salary & expense
    yearly_saved = pd.merge(salary_df, expense_yearly, on="year", how="left").fillna(0)

# ---- CALCULATE SAVINGS ----
    yearly_saved['saved'] = yearly_saved['yearly_salary'].astype(float) - yearly_saved['amount'].astype(float)


# Convert for charts
    yearly_labels = yearly_saved['year'].astype(str).tolist()
    yearly_saved_values = yearly_saved['saved'].tolist()

    return render_template(
     'dashboard.html',
     yearly_labels=yearly_labels,
    yearly_saved_values=yearly_saved_values,
    monthly_graph=monthly_graph,
    yearly_graph=yearly_graph,
    pie_graph=pie_graph,
    daily_graph=daily_graph,
    total_spent=total_spent,
    avg_spent=avg_spent,
    max_spent=max_spent,
    min_spent=min_spent,
    top_categories=top_categories
)


@app.route('/addCategory', methods=['GET','POST'])
@is_logged_in
def addCategory():
    print("🔥 ROUTE REACHED. METHOD =", request.method)   # DEBUG

    if request.method == 'POST':
        print("📩 FORM RECEIVED =", request.form)         # DEBUG

        category_name = request.form.get('category_name')
        print("📌 CATEGORY =", category_name)              # DEBUG

        if not category_name:
            print("❌ CATEGORY EMPTY")
            flash("Category name empty", "danger")
            return redirect(url_for('manageCategories'))

        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="expense_tracker"
        )
        cur = db.cursor(dictionary=True)

        cur.execute(
            "INSERT INTO categories (user_id, category_name) VALUES (%s, %s)",
            (session['userID'], category_name)
        )
        db.commit()
        cur.close()
        db.close()

        print("✅ INSERTED SUCCESSFULLY")
        return redirect(url_for('manageCategories'))

    return redirect(url_for('manageCategories'))


@app.route('/categories')
@is_logged_in
def manageCategories():
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM categories WHERE user_id=%s", (session['userID'],))
    categories = cur.fetchall()
    cur.close()
    db.close()
    return render_template('categories.html', categories=categories)

@app.route('/editCategory/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def editCategory(id):
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="expense_tracker"
    )
    cur = db.cursor(dictionary=True)

    # --- Fetch category ---
    cur.execute("SELECT * FROM categories WHERE id=%s AND user_id=%s", (id, session['userID']))
    category = cur.fetchone()

    if not category:
        flash("Category not found!", "danger")
        return redirect(url_for('manageCategories'))

    # --- POST = update ---
    if request.method == "POST":
        new_name = request.form['category_name']
        cur.execute("UPDATE categories SET category_name=%s WHERE id=%s AND user_id=%s",
                    (new_name, id, session['userID']))
        db.commit()
        cur.close()
        db.close()

        flash("Category Updated Successfully", "success")
        return redirect(url_for('manageCategories'))

    cur.close()
    db.close()

    return render_template('editCategory.html', category=category)

@app.route('/deleteCategory/<string:id>', methods=['POST'])
@is_logged_in
def deleteCategory(id):
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="expense_tracker"
    )
    cur = db.cursor(dictionary=True)

    cur.execute("DELETE FROM categories WHERE id=%s AND user_id=%s", (id, session['userID']))
    db.commit()

    cur.close()
    db.close()

    flash("Category Deleted Successfully", "success")
    return redirect(url_for('manageCategories'))


@app.route('/deleteTransaction/<string:id>', methods=['POST'])
@is_logged_in
def deleteTransaction(id):
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
    cur = db.cursor(dictionary=True)

    cur.execute("DELETE FROM transactions WHERE id=%s AND user_id=%s", (id, session['userID']))
    db.commit()
    cur.close()

    flash("Transaction Deleted Successfully", "success")
    return redirect(url_for('transactionHistory'))
    

if __name__ == '__main__':
    app.run(debug=True)

