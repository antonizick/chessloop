#!/usr/bin/env python3
"""
Clean slate: Delete all test accounts and their associated data.
Only keeps: nick, admin
"""

import sqlite3
import sys

db_path = "/home/nick/dev/lucent/idea/ChessLoop/chessloop/backend/chessloop.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 120)
print("TEST ACCOUNT CLEANUP — CLEAN SLATE")
print("=" * 120)

# Find all test accounts (everything except nick and admin)
cursor.execute("""
SELECT id, username, email
FROM user
WHERE username NOT IN ('nick', 'admin')
ORDER BY created_at DESC;
""")

test_accounts = cursor.fetchall()

if not test_accounts:
    print("\n✓ No test accounts found. Database is clean.")
    conn.close()
    sys.exit(0)

print(f"\nFound {len(test_accounts)} test account(s) to delete:\n")
print(f"{'Username':<25} {'Email':<40}")
print("-" * 120)
for acc in test_accounts:
    print(f"{acc['username']:<25} {acc['email']:<40}")

# Collect account IDs for deletion
test_user_ids = [acc['id'] for acc in test_accounts]

# Show what will be deleted
print("\n" + "=" * 120)
print("DATA TO BE DELETED")
print("=" * 120)

placeholders = ','.join(['?' for _ in test_user_ids])

cursor.execute(f"""
SELECT COUNT(*) as count FROM library WHERE owner_user_id IN ({placeholders});
""", test_user_ids)
lib_count = cursor.fetchone()['count']

cursor.execute(f"""
SELECT COUNT(*) as count FROM practicesession WHERE user_id IN ({placeholders});
""", test_user_ids)
session_count = cursor.fetchone()['count']

cursor.execute(f"""
SELECT COUNT(*) as count FROM reviewlog WHERE user_id IN ({placeholders});
""", test_user_ids)
review_count = cursor.fetchone()['count']

cursor.execute(f"""
SELECT COUNT(*) as count FROM practiceposition WHERE user_id IN ({placeholders});
""", test_user_ids)
position_count = cursor.fetchone()['count']

cursor.execute(f"""
SELECT COUNT(*) as count FROM publicsignal WHERE user_id IN ({placeholders});
""", test_user_ids)
signal_count = cursor.fetchone()['count']

print(f"\nLibraries: {lib_count}")
print(f"Practice Sessions: {session_count}")
print(f"Review Logs: {review_count}")
print(f"Practice Positions: {position_count}")
print(f"Public Signals (stars/comments): {signal_count}")
print(f"Test Accounts: {len(test_accounts)}")

total_to_delete = lib_count + session_count + review_count + position_count + signal_count + len(test_accounts)
print(f"\nTotal records to delete: {total_to_delete}")

# Confirm
print("\n" + "=" * 120)
response = input("Delete all test accounts and their data? Type 'yes' to confirm: ")

if response.lower() != 'yes':
    print("\n✗ Cancelled. No changes made.")
    conn.close()
    sys.exit(0)

print("\nDeleting in cascade order...")

# Deletion cascade (correct order for foreign keys):
# 1. ReviewLog entries (references PracticePosition and User)
# 2. PracticePosition entries (references Line and User)
# 3. Line entries (references Library)
# 4. PublicSignal entries (references Library and User)
# 5. Library entries (references User)
# 6. PracticeSession entries (references User)
# 7. User entries

print("\n1. Deleting ReviewLog entries...", end='', flush=True)
cursor.execute(f"""
DELETE FROM reviewlog
WHERE user_id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("2. Deleting PracticePosition entries...", end='', flush=True)
cursor.execute(f"""
DELETE FROM practiceposition
WHERE user_id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("3. Deleting Line entries (from libraries owned by test accounts)...", end='', flush=True)
cursor.execute(f"""
DELETE FROM line
WHERE library_id IN (
    SELECT id FROM library WHERE owner_user_id IN ({placeholders})
);
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("4. Deleting PublicSignal entries...", end='', flush=True)
cursor.execute(f"""
DELETE FROM publicsignal
WHERE user_id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("5. Deleting Library entries...", end='', flush=True)
cursor.execute(f"""
DELETE FROM library
WHERE owner_user_id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("6. Deleting PracticeSession entries...", end='', flush=True)
cursor.execute(f"""
DELETE FROM practicesession
WHERE user_id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

print("7. Deleting User accounts...", end='', flush=True)
cursor.execute(f"""
DELETE FROM user
WHERE id IN ({placeholders});
""", test_user_ids)
print(f" ✓ ({cursor.rowcount} records)")

conn.commit()

print("\n" + "=" * 120)
print("✓ CLEANUP COMPLETE")
print("=" * 120)

# Verify
cursor.execute("SELECT COUNT(*) as count FROM user WHERE username NOT IN ('nick', 'admin');")
remaining = cursor.fetchone()['count']

cursor.execute("SELECT COUNT(*) as count FROM user;")
total_users = cursor.fetchone()['count']

print(f"\nRemaining users: {total_users}")
print(f"  - nick")
print(f"  - admin")
print(f"Test accounts remaining: {remaining}")

if remaining == 0:
    print("\n✓ All test accounts successfully deleted.")
else:
    print(f"\n✗ Warning: {remaining} test accounts still remain.")

conn.close()
