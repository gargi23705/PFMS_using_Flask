import mysql.connector
import pandas as pd

def get_clean_data_for_user(user_id):
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="expense_tracker"
    )

    cur = db.cursor(dictionary=True)

    query = """
        SELECT date, amount, category
        FROM transactions
        WHERE user_id = %s
    """
    cur.execute(query, (user_id,))
    rows = cur.fetchall()

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(columns=['date', 'amount', 'category'])

    df['date'] = pd.to_datetime(df['date'])
    df['amount'] = pd.to_numeric(df['amount'])
    df['category'] = df['category'].astype(str)

    return df
