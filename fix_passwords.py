"""
Fixes existing plaintext passwords in the `users` table by hashing them.
Safe to run multiple times — already-hashed passwords are detected and skipped.

Usage: python fix_passwords.py
"""

import MySQLdb
import MySQLdb.cursors
from werkzeug.security import generate_password_hash
import config

conn = MySQLdb.connect(
    host=config.MYSQL_HOST,
    user=config.MYSQL_USER,
    passwd=config.MYSQL_PASSWORD,
    db=config.MYSQL_DB
)

cursor = conn.cursor(MySQLdb.cursors.DictCursor)
cursor.execute("SELECT id, email, password FROM users")
users = cursor.fetchall()

fixed = 0

for u in users:
    pwd = u["password"] or ""

    # werkzeug hashes always start with one of these prefixes
    already_hashed = pwd.startswith("scrypt:") or pwd.startswith("pbkdf2:")

    if not already_hashed:
        new_hash = generate_password_hash(pwd)
        update_cursor = conn.cursor()
        update_cursor.execute(
            "UPDATE users SET password=%s WHERE id=%s",
            (new_hash, u["id"])
        )
        update_cursor.close()
        fixed += 1
        print(f"Fixed: {u['email']}  (was plaintext '{pwd}')")

conn.commit()
cursor.close()
conn.close()

print(f"\nDone. {fixed} password(s) hashed.")
print("Note: their login password stays the same as before (e.g. '123456') — only the stored format changed.")
