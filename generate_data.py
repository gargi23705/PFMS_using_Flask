from faker import Faker
import random
import mysql.connector
from datetime import datetime, timedelta

fake = Faker()

# Connect to your MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"  # ← change to your DB name
)

cursor = db.cursor()

# Generate 400 rows
for _ in range(400):
    category = random.choice(["Food", "Travel", "Shopping", "Bills", "Entertainment", "Recharge", "Grocery"])
    amount = round(random.uniform(50, 3000), 2)
    date = fake.date_between(start_date='-6M', end_date='today')
    description = fake.sentence()

    cursor.execute("""
        INSERT INTO transactions (user_id, category, amount, date, description)
        VALUES (%s, %s, %s, %s, %s)
    """, (1, category, amount, date, description))

db.commit()
cursor.close()
db.close()

print("Data generated successfully!")
