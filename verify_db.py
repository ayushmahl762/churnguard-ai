import sqlite3
import os

db_path = os.path.join("database", "churnguard.db")
conn = sqlite3.connect(db_path)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables found:", tables)
import sqlite3

conn = sqlite3.connect('database/churnguard.db')
cursor = conn.cursor()

# Get column names
cursor.execute("PRAGMA table_info(churn_predictions)")
columns = [info[1] for info in cursor.fetchall()]

print("Available columns in 'churn_predictions':")
print(columns)

conn.close()