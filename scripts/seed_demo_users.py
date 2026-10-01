from __future__ import annotations

import sys
from getpass import getpass

from db.session import SessionLocal
from models.user_db import UserDB
from auth.auth_service import hash_password


def main():
    print("\n=== Seeding Demo Users (Admin, Teacher, Parent) ===\n")

    demo_users = [
        {"email": "admin@example.com", "name": "Admin User", "role": "Admin", "password": "password123"},
        {"email": "teacher@example.com", "name": "Teacher User", "role": "Teacher", "password": "password123"},
        {"email": "parent@example.com", "name": "Parent User", "role": "Parent", "password": "password123"},
    ]

    db = SessionLocal()
    try:
        for u in demo_users:
            email = u["email"]
            pwd = u["password"]
            
            user = db.query(UserDB).filter(UserDB.email == email).first()

            if user:
                user.full_name = u["name"]
                user.password_hash = hash_password(pwd)
                user.role = u["role"]
                print(f"✅ Updated existing user: {email} (Role: {u['role']})")
            else:
                user = UserDB(
                    full_name=u["name"],
                    email=email,
                    password_hash=hash_password(pwd),
                    role=u["role"],
                )
                db.add(user)
                print(f"✅ Created new user: {email} (Role: {u['role']})")

        db.commit()
        print("\n✅ All demo users have been successfully seeded!")
        print("You can now log in with the following credentials:")
        print("-------------------------------------------------")
        for u in demo_users:
            print(f"  Email    : {u['email']}")
            print(f"  Password : {u['password']}")
            print("-------------------------------------------------")
        print("\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
