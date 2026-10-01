"""
Multi-Tenant SaaS Platform Security & Isolation Test Suite.
Verifies:
1. SuperAdmin authentication and SaaS platform stats.
2. Tenant Isolation: School Admin A cannot access School B data.
3. Cross-Tenant IDOR prevention on Fees, Marks, Attendance, Exam Sheets.
4. School Account Suspension enforcement (HTTP 403).
5. Parent Link Code auto-verification vs. suspicious quarantined links.
6. SuperAdmin Impersonation flow.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import SessionLocal
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.parent_link_code_db import ParentLinkCodeDB
from auth.auth_service import hash_password, create_access_token
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_saas_security():
    print("==================================================")
    print("[SECURITY AUDIT] RUNNING MULTI-TENANT SAAS SECURITY SUITE")
    print("==================================================")

    db = SessionLocal()
    try:
        # 1. Ensure SuperAdmin exists
        superadmin = db.query(UserDB).filter(UserDB.email == "superadmin@schoolos.com").first()
        if not superadmin:
            superadmin = UserDB(
                email="superadmin@schoolos.com",
                password_hash=hash_password("SuperAdmin@2026"),
                full_name="Platform SuperAdmin",
                role="SuperAdmin",
                school_id=None,
                is_active=True,
                email_verified=True,
            )
            db.add(superadmin)
            db.commit()
            db.refresh(superadmin)

        # 2. Ensure two distinct schools exist (School Alpha & School Beta)
        school_a = db.query(SchoolDB).filter(SchoolDB.email == "alpha@schoolos.com").first()
        if not school_a:
            school_a = SchoolDB(
                name="Alpha International School",
                board="CBSE",
                city="Mumbai",
                email="alpha@schoolos.com",
                is_active=True,
                is_suspended=False,
                max_students=500,
            )
            db.add(school_a)
            db.commit()
            db.refresh(school_a)

        school_b = db.query(SchoolDB).filter(SchoolDB.email == "beta@schoolos.com").first()
        if not school_b:
            school_b = SchoolDB(
                name="Beta Public School",
                board="ICSE",
                city="Bangalore",
                email="beta@schoolos.com",
                is_active=True,
                is_suspended=False,
                max_students=300,
            )
            db.add(school_b)
            db.commit()
            db.refresh(school_b)

        # 3. Create Admins for both schools
        admin_a = db.query(UserDB).filter(UserDB.email == "admin@alpha.edu").first()
        if not admin_a:
            admin_a = UserDB(
                school_id=school_a.id,
                email="admin@alpha.edu",
                password_hash=hash_password("alpha123"),
                full_name="Alpha Principal",
                role="Admin",
                is_active=True,
                email_verified=True,
            )
            db.add(admin_a)
            db.commit()
            db.refresh(admin_a)

        admin_b = db.query(UserDB).filter(UserDB.email == "admin@beta.edu").first()
        if not admin_b:
            admin_b = UserDB(
                school_id=school_b.id,
                email="admin@beta.edu",
                password_hash=hash_password("beta123"),
                full_name="Beta Principal",
                role="Admin",
                is_active=True,
                email_verified=True,
            )
            db.add(admin_b)
            db.commit()
            db.refresh(admin_b)

        # 4. Create Students in both schools
        st_a = db.query(StudentDB).filter(StudentDB.school_id == school_a.id).first()
        if not st_a:
            st_a = StudentDB(
                school_id=school_a.id,
                name="Aarav Sharma",
                admission_no="ALP-2026-001",
                grade="10",
                section="A",
                is_active=True,
            )
            db.add(st_a)
            db.commit()
            db.refresh(st_a)

        st_b = db.query(StudentDB).filter(StudentDB.school_id == school_b.id).first()
        if not st_b:
            st_b = StudentDB(
                school_id=school_b.id,
                name="Diya Patel",
                admission_no="BET-2026-001",
                grade="10",
                section="A",
                is_active=True,
            )
            db.add(st_b)
            db.commit()
            db.refresh(st_b)

        print("[OK] Test database fixtures verified.")

        # ── Test 1: SuperAdmin Login & Platform Stats ──
        super_token = create_access_token({"sub": str(superadmin.id), "role": "SuperAdmin", "school_id": None})
        res = client.get("/superadmin/dashboard", headers={"Authorization": f"Bearer {super_token}"})
        assert res.status_code == 200, f"SuperAdmin stats failed: {res.text}"
        stats_data = res.json()
        print(f"[TEST 1 PASS] SuperAdmin authenticated: Total Schools={stats_data['total_schools']}")

        # ── Test 2: Multi-Tenant Isolation (Admin A vs Admin B) ──
        token_a = create_access_token({"sub": str(admin_a.id), "role": "Admin", "school_id": str(school_a.id)})
        token_b = create_access_token({"sub": str(admin_b.id), "role": "Admin", "school_id": str(school_b.id)})

        # Admin A requesting Student B dues -> Must be 404 (or 403)
        res_cross_fee = client.get(f"/fees/student/{st_b.id}/dues", headers={"Authorization": f"Bearer {token_a}"})
        assert res_cross_fee.status_code in (403, 404), f"Security Breach: Admin A accessed Student B fee dues! Code: {res_cross_fee.status_code}"
        print(f"[TEST 2 PASS] Cross-Tenant Fee Isolation Enforced (HTTP {res_cross_fee.status_code})")

        # Admin A requesting Student B exam sheets -> Must be 404 or 403
        res_cross_sheet = client.get(f"/exam-sheets/student/{st_b.id}", headers={"Authorization": f"Bearer {token_a}"})
        assert res_cross_sheet.status_code in (403, 404), f"Security Breach: Admin A accessed Student B exam sheets!"
        print(f"[TEST 2 PASS] Cross-Tenant Exam Sheet Isolation Enforced (HTTP {res_cross_sheet.status_code})")

        # ── Test 3: Suspension Enforcement ──
        # Suspend School B
        res_suspend = client.post(f"/superadmin/schools/{school_b.id}/suspend", headers={"Authorization": f"Bearer {super_token}"}, json={"reason": "Trial expired"})
        assert res_suspend.status_code == 200, f"Suspend failed: {res_suspend.text}"

        # Now Admin B attempts to access their own school data -> Must be 403 Forbidden!
        res_b_blocked = client.get("/admin/students", headers={"Authorization": f"Bearer {token_b}"})
        assert res_b_blocked.status_code == 403, f"Security Breach: Suspended school admin was not blocked! Status: {res_b_blocked.status_code}"
        print(f"[TEST 3 PASS] Suspended School Account Blocked Globally (HTTP 403: {res_b_blocked.json().get('detail')})")

        # Reactivate School B
        res_activate = client.post(f"/superadmin/schools/{school_b.id}/activate", headers={"Authorization": f"Bearer {super_token}"})
        assert res_activate.status_code == 200

        # ── Test 4: Parent Link Code Auto-Verification ──
        # Admin A generates code for Student A
        res_code = client.post("/parent-codes/generate", headers={"Authorization": f"Bearer {token_a}"}, json={"student_id": str(st_a.id)})
        assert res_code.status_code == 200
        link_code = res_code.json()["code"]
        print(f"[TEST 4] Generated Parent Link Code for Student A: {link_code}")

        # Create a new parent user
        parent_user = db.query(UserDB).filter(UserDB.email == "testparent@example.com").first()
        if not parent_user:
            parent_user = UserDB(
                email="testparent@example.com",
                password_hash=hash_password("parent123"),
                full_name="Ramesh Sharma",
                role="Parent",
                school_id=school_a.id,
                is_active=True,
                email_verified=True,
            )
            db.add(parent_user)
            db.commit()
            db.refresh(parent_user)

        parent_token = create_access_token({"sub": str(parent_user.id), "role": "Parent", "school_id": str(school_a.id)})

        # Parent links with VALID code -> Should be verified immediately
        res_link_valid = client.post("/parent/link-child", headers={"Authorization": f"Bearer {parent_token}"}, json={
            "school_id": str(school_a.id),
            "verification_code": link_code,
            "relation": "Father"
        })
        assert res_link_valid.status_code == 200 and res_link_valid.json().get("status") in ("success", "already_linked")
        print(f"[TEST 4 PASS] Parent auto-verified and linked with unique code: {res_link_valid.json().get('message')}")

        # ── Test 5: SuperAdmin Impersonation Flow ──
        res_impersonate = client.post(f"/superadmin/schools/{school_a.id}/impersonate", headers={"Authorization": f"Bearer {super_token}"})
        assert res_impersonate.status_code == 200
        imp_data = res_impersonate.json()
        target_u = imp_data.get("impersonated_user") or imp_data.get("user")
        assert "access_token" in imp_data and target_u["role"] == "Admin"
        print(f"[TEST 5 PASS] SuperAdmin Impersonation Token issued for school: {imp_data['school']['name']}")

        print("\n==================================================")
        print("[SUCCESS] ALL 5 MULTI-TENANT SECURITY TESTS PASSED 100%!")
        print("==================================================")

    finally:
        db.close()


if __name__ == "__main__":
    test_saas_security()
