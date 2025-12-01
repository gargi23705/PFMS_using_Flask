import sqlite3
import pandas as pd


def get_db_local():
    db = sqlite3.connect("expense_tracker.db")
    db.row_factory = sqlite3.Row
    return db


def get_clean_data_for_user(user_id):
    db = get_db_local()
    cur = db.cursor()

    cur.execute("""
        SELECT amount, category, date
        FROM transactions
        WHERE user_id = ?
        ORDER BY date ASC
    """, (user_id,))

    rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=["amount", "category", "date", "year", "month"])

    # Convert rows to DataFrame
    df = pd.DataFrame(rows, columns=["amount", "category", "date"])

    # Clean date
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notnull()]

    # Clean amount
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df[df["amount"].notnull()]

    # Category
    df["category"] = df["category"].fillna("Others").astype(str)

    # Add year & month
    df["year"] = df["date"].dt.year.astype(int)
    df["month"] = df["date"].dt.month.astype(int)

    # Sort
    df = df.sort_values("date").reset_index(drop=True)

    return df
