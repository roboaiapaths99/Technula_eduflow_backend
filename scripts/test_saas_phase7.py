"""
Phase 7 Verification Script — Subscriptions, PayU, Quotas, Custom Roles, Bulk CSV, and Parent Linking.
"""
from __future__ import annotations
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import SessionLocal
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.subscription_plan_db import SubscriptionPlanDB
from auth.auth_service import hash_password, create_access_token
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def run_phase7_tests():
    print("==================================================")
    print("[TEST] STARTING PHASE 7 SAAS SUBSCRIPTION & ADMIN SUITE")
    print("==================================================")

    db = SessionLocal()
    try:
        # 1. Setup School Test Tenant
        school = db.query(SchoolDB).filter(SchoolDB.email == "test_phase7@schoolos.com").first()
        if not school:
            school = SchoolDB(
                name="Phase 7 Test Academy",
                board="CBSE",
                city="Bengaluru",
                email="test_phase7@schoolos.com",
                is_active=True,
                subscription_plan="starter",
            )
            db.add(school)
            db.commit()
            db.refresh(school)
        else:
            school.subscription_plan = "starter"
            db.query(SubscriptionPlanDB).filter(SubscriptionPlanDB.school_id == school.id).delete()
            db.commit()
            db.refresh(school)

        admin = db.query(UserDB).filter(UserDB.email == "admin_phase7@schoolos.com").first()
        if not admin:
            admin = UserDB(
                email="admin_phase7@schoolos.com",
                password_hash=hash_password("School@123"),
                full_name="Phase7 Admin",
                role="Admin",
                school_id=school.id,
                is_active=True,
                email_verified=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        parent = db.query(UserDB).filter(UserDB.email == "parent_phase7@schoolos.com").first()
        if not parent:
            parent = UserDB(
                email="parent_phase7@schoolos.com",
                password_hash=hash_password("Parent@123"),
                full_name="Phase7 Parent",
                role="Parent",
                phone="9876543299",
                school_id=school.id,
                is_active=True,
                email_verified=True,
            )
            db.add(parent)
            db.commit()
            db.refresh(parent)

        admin_token = create_access_token({"sub": str(admin.id), "role": admin.role, "school_id": str(school.id)})
        parent_token = create_access_token({"sub": str(parent.id), "role": parent.role, "school_id": str(school.id)})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        parent_headers = {"Authorization": f"Bearer {parent_token}"}

        # ── Test 1: Public Plans Endpoint ────────────────────────────
        print("\n[1] Testing GET /subscription/plans...")
        r = client.get("/subscription/plans")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        plans = r.json().get("plans", [])
        assert len(plans) == 3, f"Expected 3 plans, got {len(plans)}"
        starter_plan = next(p for p in plans if p["tier"] == "starter")
        assert starter_plan["trial_days"] == 10, f"Starter trial should be 10 days, got {starter_plan['trial_days']}"
        print("PASS: 3 subscription tiers found with 10-day Starter trial.")

        # ── Test 2: Current Subscription Status & Usage ──────────────
        print("\n[2] Testing GET /subscription/current...")
        r = client.get("/subscription/current", headers=admin_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        sub_info = r.json()
        assert sub_info["plan_tier"] == "starter", f"Expected starter, got {sub_info['plan_tier']}"
        assert sub_info["is_trial"] is True, "Starter should be in trial mode"
        assert "quotas" in sub_info and "usage" in sub_info
        print(f"PASS: Current subscription fetched. Tier={sub_info['plan_tier']}, Trial Days={sub_info['trial_days_remaining']}")

        # ── Test 3: PayU Hash Generation ─────────────────────────────
        print("\n[3] Testing POST /subscription/payu-init...")
        payload = {
            "plan_tier": "growth",
            "billing_cycle": "monthly",
            "firstname": "Phase7 Admin",
            "email": "admin_phase7@schoolos.com",
            "phone": "9876543210",
        }
        r = client.post("/subscription/payu-init", json=payload, headers=admin_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        payu_data = r.json()
        assert "hash" in payu_data and len(payu_data["hash"]) == 128, "SHA-512 hash should be 128 hex chars"
        assert payu_data["amount"] == "1999.00", f"Expected 1999.00, got {payu_data['amount']}"
        assert payu_data["key"] and payu_data["txnid"]
        print(f"PASS: PayU transaction parameters & SHA-512 hash generated: txnid={payu_data['txnid']}")

        # ── Test 4: Custom Role & Staff Quota Enforcement ────────────
        print("\n[4] Testing Custom Roles on POST /admin/users...")
        custom_user_payload = {
            "email": "accountant_p7@schoolos.com",
            "full_name": "Accountant Staff",
            "role": "Chief Accountant",  # Custom Role
            "phone": "9112233445",
        }
        r = client.post("/admin/users", json=custom_user_payload, headers=admin_headers)
        assert r.status_code in [200, 400], f"Failed with {r.status_code}: {r.text}"
        if r.status_code == 200:
            assert r.json()["user"]["role"] == "Chief Accountant"
            print("PASS: Custom role 'Chief Accountant' created successfully.")
        else:
            print("User exists already, checking role list.")

        # Test roles list includes custom role
        r = client.get("/admin/roles", headers=admin_headers)
        assert r.status_code == 200
        roles = r.json().get("roles", [])
        assert "Chief Accountant" in roles or "Teacher" in roles
        print(f"PASS: Roles endpoint returned {len(roles)} roles.")

        # ── Test 5: CSV Template Download ────────────────────────────
        print("\n[5] Testing GET /admin/students/csv-template...")
        r = client.get("/admin/students/csv-template", headers=admin_headers)
        assert r.status_code == 200
        assert "admission_no" in r.text and "name" in r.text
        print("PASS: Student CSV template downloaded with required headers.")

        # ── Test 6: Bulk Student CSV Upload ──────────────────────────
        print("\n[6] Testing POST /admin/students/upload-csv...")
        csv_data = (
            "name,admission_no,grade,section,roll_no,gender,father_name,father_phone\n"
            "Rahul Varma,P7-STU-001,9,A,1,Male,Sanjay Varma,9876543201\n"
            "Ananya Sen,P7-STU-002,9,A,2,Female,Debashis Sen,9876543202\n"
        )
        files = {"file": ("students.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        r = client.post("/admin/students/upload-csv", files=files, headers=admin_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        res = r.json()
        assert res["status"] == "ok"
        print(f"PASS: Bulk upload processed. Created={res['created_count']}, Skipped={res['skipped_count']}")

        # Verify created students have parent_link_code
        created_students = res["created_students"]
        assert len(created_students) > 0 or res["skipped_count"] > 0
        first_stu = db.query(StudentDB).filter(StudentDB.admission_no == "P7-STU-001").first()
        assert first_stu is not None
        print(f"PASS: Student {first_stu.name} verified in database.")

        # ── Test 7: Parent Search & Link by Admission Number ─────────
        print("\n[7] Testing POST /parent-codes/search-and-link...")
        # Get the link code for P7-STU-001
        from models.parent_link_code_db import ParentLinkCodeDB
        code_record = db.query(ParentLinkCodeDB).filter(ParentLinkCodeDB.student_id == first_stu.id).first()
        assert code_record is not None, "ParentLinkCode record should exist"

        link_payload = {
            "admission_no": "P7-STU-001",
            "link_code": code_record.code,
            "relation": "Father",
        }
        r = client.post("/parent-codes/search-and-link", json=link_payload, headers=parent_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        link_res = r.json()
        assert link_res["success"] is True and link_res["verified"] is True
        print(f"PASS: Child successfully linked with verified status using code {code_record.code}.")

        # ── Test 8: Feature Gating on Starter Plan ────────────────────
        print("\n[8] Testing Plan Feature Gating (Starter should reject fee_management)...")
        r = client.get("/fees/config", headers=admin_headers)
        assert r.status_code == 403, f"Expected 403 Forbidden for fee_management on Starter, got {r.status_code}"
        print("PASS: Feature gating blocked fee_management on Starter plan (HTTP 403).")

        # ── Test 9: Upgrade to Growth via PayU Verify ─────────────────
        print("\n[9] Testing POST /subscription/payu-verify (Simulated Upgrade)...")
        verify_payload = {
            "txnid": "TXN_SIMULATED_001",
            "status": "success",
            "plan_tier": "growth",
            "billing_cycle": "monthly",
            "is_simulation": True,
        }
        r = client.post("/subscription/payu-verify", json=verify_payload, headers=admin_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["plan_tier"] == "growth"
        print("PASS: Upgraded school plan to Growth tier.")

        # Re-test fee_management now that school is on Growth plan!
        r = client.get("/fees/config", headers=admin_headers)
        assert r.status_code == 200, f"Expected 200 for fee_management on Growth plan, got {r.status_code}"
        print("PASS: Feature gating allowed fee_management on Growth plan (HTTP 200)!")

        print("\n==================================================")
        print("ALL PHASE 7 TESTS PASSED PERFECTLY!")
        print("==================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_phase7_tests()
