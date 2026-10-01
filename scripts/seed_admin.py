from __future__ import annotations

import sys
from getpass import getpass

from db.session import SessionLocal
from models.user_db import UserDB
from auth.auth_service import hash_password


def main():
    print("\n=== Seed Admin User ===")

    email = input("Admin email: ").strip().lower()
    if not email:
        print("❌ Email is required.")
        sys.exit(1)

    name = input("Admin full name (optional): ").strip()

    # Use hidden password input
    pwd1 = getpass("Admin password: ")
    pwd2 = getpass("Confirm password: ")
    if not pwd1 or pwd1 != pwd2:
        print("❌ Passwords do not match / empty.")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(UserDB.email == email).first()

        if user:
            user.full_name = name or user.full_name
            user.password_hash = hash_password(pwd1)
            user.role = "Admin"
            db.add(user)
            db.commit()
            print(f"✅ Updated existing user as Admin: {email}")
        else:
            user = UserDB(
                full_name=name or None,
                email=email,
                password_hash=hash_password(pwd1),
                role="Admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Created Admin user: {email} (id={user.id})")

        print("✅ Done.\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
