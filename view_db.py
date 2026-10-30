import sqlite3

conn = sqlite3.connect("research.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM topics ORDER BY id DESC").fetchall()

print("Total rows:", len(rows))
for r in rows:
    print("-" * 60)
    for key in r.keys():
        print(f"{key}: {r[key]}")