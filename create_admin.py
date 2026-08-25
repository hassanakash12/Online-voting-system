"""
Run this once to create your first admin account.
Usage: python create_admin.py
"""

import MySQLdb
from werkzeug.security import generate_password_hash
import config

ADMIN_NAME = "System Admin"
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "123456"   # change this before running, or edit after via /edit_voter

conn = MySQLdb.connect(
    host=config.MYSQL_HOST,
    user=config.MYSQL_USER,
    passwd=config.MYSQL_PASSWORD,
    db=config.MYSQL_DB
)

cursor = conn.cursor()

hashed_password = generate_password_hash(ADMIN_PASSWORD)

cursor.execute(
    """INSERT INTO users (full_name, email, password, role, status)
       VALUES (%s, %s, %s, %s, %s)""",
    (ADMIN_NAME, ADMIN_EMAIL, hashed_password, "admin", "Approved")
)

conn.commit()
cursor.close()
conn.close()

print(f"Admin created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
print("Please log in and change this password.")
