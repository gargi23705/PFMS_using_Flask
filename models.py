from app import db
import mysql.connector

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="expense_tracker"
)
cur = db.cursor(dictionary=True)
