import sqlite3

con = sqlite3.connect('academics_insights.db')
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
for t in tables:
    count = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f'{t}: {count}')

print("\n--- SCHOOLS ---")
for row in con.execute("SELECT id, code, name, created_at FROM schools").fetchall():
    print(row)

print("\n--- USERS ---")
for row in con.execute("SELECT id, school_id, email, phone, full_name, role FROM users").fetchall():
    print(row)
