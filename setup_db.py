import sqlite3

# Create SQLite database file
db = sqlite3.connect("expense_tracker.db")
cur = db.cursor()

# USERS TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT DEFAULT 'user'
);
""")

# TRANSACTIONS TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    category TEXT,
    description TEXT,
    date TEXT,   -- will store ISO datetime string: YYYY-MM-DD HH:MM:SS
    FOREIGN KEY(user_id) REFERENCES users(id)
);
""")

# SALARY TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS salary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    salary_amount REAL NOT NULL,
    month TEXT NOT NULL,
    year TEXT NOT NULL,
    created_at TEXT, -- will store ISO timestamp
    FOREIGN KEY(user_id) REFERENCES users(id)
);
""")

# CATEGORIES TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category_name TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
""")

db.commit()
db.close()

print("SQLite database and tables created successfully!")
