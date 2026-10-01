"""
Create all database tables.
"""
from db.base import Base
from db.session import engine

from sqlalchemy import text, inspect

# Import all models so SQLAlchemy registers them
import models  # noqa: F401


def run_migrations():
    """Ensure newly added columns exist in existing tables without dropping data."""
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            table_names = inspector.get_table_names()

            # Check schools table
            if "schools" in table_names:
                school_cols = {c["name"] for c in inspector.get_columns("schools")}
                new_school_cols = [
                    ("affiliation_no", "VARCHAR(100)"),
                    ("principal_name", "VARCHAR(150)"),
                    ("website", "VARCHAR(255)"),
                    ("academic_year", "VARCHAR(20) DEFAULT '2025-26'"),
                    ("stamp_url", "VARCHAR(500)"),
                    ("signature_url", "VARCHAR(500)"),
                    # SaaS multi-tenant fields
                    ("code", "VARCHAR(50)"),
                    ("is_suspended", "BOOLEAN DEFAULT 0"),
                    ("max_students", "INTEGER DEFAULT 500"),
                    ("max_teachers", "INTEGER DEFAULT 50"),
                    ("trial_ends_at", "DATETIME"),
                    ("subscription_plan", "VARCHAR(30) DEFAULT 'starter'"),
                    ("brand_color", "VARCHAR(30) DEFAULT '#635bff'"),
                    ("powered_by_text", "VARCHAR(100) DEFAULT 'Powered by Technula-Gaj'"),
                    ("parent_profile_approval_required", "BOOLEAN DEFAULT 0"),
                    ("birthday_template", "TEXT"),
                ]

                for col_name, col_type in new_school_cols:
                    if col_name not in school_cols:
                        conn.execute(text(f"ALTER TABLE schools ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to schools table.")

                # Backfill schools that have NULL code
                rows = conn.execute(text("SELECT id, name FROM schools WHERE code IS NULL")).fetchall()
                for row in rows:
                    s_id, s_name = row[0], row[1] or "SCH"
                    # Generate 6-character code, e.g. TECH01 or DPS001
                    clean_name = "".join(c for c in s_name.upper() if c.isalnum())
                    prefix = clean_name[:4] if len(clean_name) >= 4 else clean_name.ljust(4, "X")
                    code_cand = f"{prefix}01"
                    conn.execute(text("UPDATE schools SET code = :code WHERE id = :id"), {"code": code_cand, "id": s_id})
                    print(f"[DB Migration] Generated school code {code_cand} for {s_name}")

            # Check users table
            if "users" in table_names:
                user_cols = {c["name"] for c in inspector.get_columns("users")}
                new_user_cols = [
                    ("allow_whatsapp", "BOOLEAN DEFAULT 1"),
                    ("allow_email", "BOOLEAN DEFAULT 1"),
                    ("allow_sms", "BOOLEAN DEFAULT 0"),
                    ("must_reset_password", "BOOLEAN DEFAULT 0"),
                    ("permissions_json", "TEXT"),
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                    ("deleted_at", "DATETIME"),
                ]
                for col_name, col_type in new_user_cols:
                    if col_name not in user_cols:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to users table.")

            # Check students table
            if "students" in table_names:
                student_cols = {c["name"] for c in inspector.get_columns("students")}
                new_student_cols = [
                    ("dob", "DATE"),
                    ("photo_url", "VARCHAR(500)"),
                    ("blood_group", "VARCHAR(10)"),
                    ("father_name", "VARCHAR(100)"),
                    ("father_phone", "VARCHAR(20)"),
                    ("mother_name", "VARCHAR(100)"),
                    ("mother_phone", "VARCHAR(20)"),
                    ("emergency_contact_name", "VARCHAR(100)"),
                    ("emergency_contact_phone", "VARCHAR(20)"),
                    ("address", "VARCHAR(500)"),
                    ("medical_notes", "VARCHAR(500)"),
                    ("previous_school", "VARCHAR(255)"),
                    ("is_active", "BOOLEAN DEFAULT 1"),
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                    ("deleted_at", "DATETIME"),
                ]
                for col_name, col_type in new_student_cols:
                    if col_name not in student_cols:
                        conn.execute(text(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to students table.")

            # Check attendance table
            if "attendance" in table_names:
                att_cols = {c["name"] for c in inspector.get_columns("attendance")}
                new_att_cols = [
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                ]
                for col_name, col_type in new_att_cols:
                    if col_name not in att_cols:
                        conn.execute(text(f"ALTER TABLE attendance ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to attendance table.")

            # Check fee_payments table
            if "fee_payments" in table_names:
                fee_cols = {c["name"] for c in inspector.get_columns("fee_payments")}
                new_fee_cols = [
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                ]
                for col_name, col_type in new_fee_cols:
                    if col_name not in fee_cols:
                        conn.execute(text(f"ALTER TABLE fee_payments ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to fee_payments table.")

            # Check homework table
            if "homework" in table_names:
                hw_cols = {c["name"] for c in inspector.get_columns("homework")}
                new_hw_cols = [
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                ]
                for col_name, col_type in new_hw_cols:
                    if col_name not in hw_cols:
                        conn.execute(text(f"ALTER TABLE homework ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to homework table.")

            # Check timetable_slots table
            if "timetable_slots" in table_names:
                tt_cols = {c["name"] for c in inspector.get_columns("timetable_slots")}
                new_tt_cols = [
                    ("updated_at", "DATETIME"),
                    ("updated_by", "CHAR(36)"),
                ]
                for col_name, col_type in new_tt_cols:
                    if col_name not in tt_cols:
                        conn.execute(text(f"ALTER TABLE timetable_slots ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to timetable_slots table.")

            # Check school_payment_configs table
            if "school_payment_configs" in table_names:
                cfg_cols = {c["name"] for c in inspector.get_columns("school_payment_configs")}
                new_cfg_cols = [
                    ("bank_name", "VARCHAR(150)"),
                    ("bank_account_no", "VARCHAR(50)"),
                    ("bank_ifsc", "VARCHAR(20)"),
                    ("bank_account_holder", "VARCHAR(150)"),
                    ("qr_code_url", "TEXT"),
                    ("payment_instructions", "TEXT"),
                ]
                for col_name, col_type in new_cfg_cols:
                    if col_name not in cfg_cols:
                        conn.execute(text(f"ALTER TABLE school_payment_configs ADD COLUMN {col_name} {col_type}"))
                        print(f"[DB Migration] Added {col_name} to school_payment_configs table.")

            # Create high-performance compound indexes if not exist
            indexes_to_create = [
                ("ix_attendance_school_date_status", "CREATE INDEX IF NOT EXISTS ix_attendance_school_date_status ON attendance (school_id, date, status)"),
                ("ix_students_school_grade_sec", "CREATE INDEX IF NOT EXISTS ix_students_school_grade_sec ON students (school_id, grade, section)"),
                ("ix_fee_payments_school_date", "CREATE INDEX IF NOT EXISTS ix_fee_payments_school_date ON fee_payments (school_id, payment_date)"),
            ]
            for idx_name, idx_sql in indexes_to_create:
                try:
                    conn.execute(text(idx_sql))
                    print(f"[DB Index] Verified index {idx_name}.")
                except Exception as ex:
                    print(f"[DB Index] Notice for {idx_name}: {ex}")

            conn.commit()
    except Exception as e:
        print(f"[DB Migration] Notice: {e}")


def init_db():
    """Create all tables if they don't exist and run incremental column migrations."""
    Base.metadata.create_all(bind=engine)
    run_migrations()
    print("[DB] All tables created/verified.")

