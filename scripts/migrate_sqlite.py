import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "academics_insights.db")
print(f"Connecting to database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Inspect schools table
cursor.execute("PRAGMA table_info(schools)")
cols = [r[1] for r in cursor.fetchall()]
print(f"Current columns in schools: {cols}")

needed_cols = [
    ("code", "VARCHAR(50)"),
    ("is_active", "BOOLEAN DEFAULT 1"),
    ("is_suspended", "BOOLEAN DEFAULT 0"),
    ("max_students", "INTEGER DEFAULT 500"),
    ("max_teachers", "INTEGER DEFAULT 50"),
    ("trial_ends_at", "DATETIME"),
    ("subscription_plan", "VARCHAR(30) DEFAULT 'starter'"),
    ("brand_color", "VARCHAR(30) DEFAULT '#635bff'"),
    ("powered_by_text", "VARCHAR(100) DEFAULT 'Powered by Technula'"),
    ("parent_profile_approval_required", "BOOLEAN DEFAULT 0"),
    ("birthday_template", "TEXT")
]

for col_name, col_type in needed_cols:
    if col_name not in cols:
        print(f"Adding column '{col_name}'...")
        try:
            cursor.execute(f"ALTER TABLE schools ADD COLUMN {col_name} {col_type}")
            print(f"Added '{col_name}' successfully.")
        except Exception as e:
            print(f"Could not add '{col_name}': {e}")

conn.commit()

# Ensure at least one school has an active code (e.g. AGPK01 or TECH01)
cursor.execute("SELECT id, name, code FROM schools")
schools = cursor.fetchall()
print(f"\nExisting Schools ({len(schools)}):")
for s in schools:
    print(s)

if schools:
    for s_id, s_name, s_code in schools:
        if not s_code:
            # Set code
            new_code = "AGPK01" if "agpk" in s_name.lower() else "TECH01"
            print(f"Assigning code '{new_code}' to school '{s_name}'...")
            cursor.execute("UPDATE schools SET code = ?, is_active = 1 WHERE id = ?", (new_code, s_id))
    conn.commit()
else:
    # Insert default school
    import uuid
    school_id = str(uuid.uuid4())
    print("Creating default school AGPK Academy with code AGPK01...")
    cursor.execute("""
        INSERT INTO schools (id, name, code, is_active, subscription_plan)
        VALUES (?, 'AGPK Academy', 'AGPK01', 1, 'growth')
    """, (school_id,))
    conn.commit()

# Check students
cursor.execute("PRAGMA table_info(students)")
st_cols = [r[1] for r in cursor.fetchall()]
print(f"\nStudent columns: {st_cols}")

cursor.execute("SELECT id, name, grade, section, admission_no, father_phone, mother_phone, school_id FROM students")
students = cursor.fetchall()
print(f"\nStudents found: {len(students)}")
for st in students[:5]:
    print(st)

conn.close()
print("\nMigration completed successfully!")
