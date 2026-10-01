"""
SaaS Platform SuperAdmin Seeder.
Creates the master SuperAdmin account (`superadmin@schoolos.com`)
to manage multi-school SaaS tenants, metrics, audit logs, and school accounts.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import SessionLocal
from models.user_db import UserDB
from auth.auth_service import hash_password
from db.init_db import init_db


import secrets
from core.config import settings


def seed_superadmin():
    init_db()
    db = SessionLocal()
    try:
        phones = settings.authorized_superadmin_phones
        if not phones:
            print("[Seed] No authorized SuperAdmin phones configured in settings/env.")
            return

        for phone in sorted(phones):
            clean_phone = phone[-10:]
            email = f"superadmin.{clean_phone}@eduflow.technula.com"
            existing = db.query(UserDB).filter(
                (UserDB.phone.ilike(f"%{clean_phone}%")) | (UserDB.email == email)
            ).first()

            if existing:
                existing.role = "SuperAdmin"
                existing.phone = f"+91{clean_phone}"
                existing.is_active = True
                existing.email_verified = True
                db.commit()
                print(f"[OK] Verified SuperAdmin account from env: {existing.email} / +91{clean_phone}")
            else:
                superadmin = UserDB(
                    email=email,
                    phone=f"+91{clean_phone}",
                    password_hash=hash_password(secrets.token_urlsafe(16)),
                    full_name=f"Platform SuperAdmin ({clean_phone[-4:]})",
                    role="SuperAdmin",
                    school_id=None,
                    is_active=True,
                    email_verified=True,
                )
                db.add(superadmin)
                db.commit()
                print(f"[OK] Created SuperAdmin account from env: {email} / +91{clean_phone}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_superadmin()
