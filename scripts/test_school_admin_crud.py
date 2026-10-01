"""
Automated Test Suite for Real-World School & Student Management.
Tests:
1. GET /schools/all & GET /schools/{school_id}
2. PUT /schools/{school_id} (School settings & institutional profile update)
3. GET & POST /fees/config (Payment Gateway & UPI Direct Collection)
4. POST /admin/students (Full real-world enrollment with DOB, Mother details, Medical notes, Emergency contact)
5. Automatic Parent Account Provisioning & Linking
6. GET /admin/students (List with all extended fields)
7. GET /admin/students/{student_id} (Student Dossier inspection)
8. PUT /admin/students/{student_id} (Update student record)
9. Cleanup test records
"""
import os
import sys
from datetime import date
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app import app
from db.session import SessionLocal
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.school_payment_config_db import SchoolPaymentConfigDB
from auth.auth_service import create_access_token

client = TestClient(app)

def test_school_and_student_management():
    print("=" * 70)
    print("  TESTING REAL-WORLD SCHOOL & STUDENT LIFECYCLE MANAGEMENT")
    print("=" * 70)

    db = SessionLocal()
    created_student_id = None
    created_parent_id = None

    try:
        # 1. Fetch existing school and admin user
        school = db.query(SchoolDB).first()
        assert school is not None, "At least one SchoolDB record must exist in the database."
        school_id = str(school.id)

        admin_user = db.query(UserDB).filter(UserDB.school_id == school.id, UserDB.role == "Admin").first()
        if not admin_user:
            from auth.auth_service import hash_password
            admin_user = UserDB(
                school_id=school.id,
                email=f"admin_test_{school.id}@test.school",
                full_name="System Test Admin",
                password_hash=hash_password("Admin@123"),
                role="Admin",
                is_active=True,
                email_verified=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        admin_token = create_access_token({
            "sub": str(admin_user.id),
            "role": "Admin",
            "school_id": school_id,
        })
        auth_headers = {"Authorization": f"Bearer {admin_token}"}
        print(f"[*] Authenticated as Admin: '{admin_user.full_name}' for school '{school.name}' ({school_id})")

        # ── Test 1: GET /schools/all ──────────────────────────────────────────
        print("\n[+] Test 1: GET /schools/all")
        res = client.get("/schools/all")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        schools = res.json()
        assert isinstance(schools, list) and len(schools) > 0, "Expected non-empty list of schools."
        curr = next((s for s in schools if s["id"] == school_id), None)
        assert curr is not None, "Current school must be present in /schools/all"
        assert "academic_year" in curr, "Response must include academic_year"
        print(f"    -> Found {len(schools)} registered schools. Target school: {curr['name']} ({curr.get('academic_year')})")

        # ── Test 2: GET /schools/{school_id} ──────────────────────────────────
        print(f"\n[+] Test 2: GET /schools/{school_id}")
        res = client.get(f"/schools/{school_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        sch_data = res.json()
        assert sch_data["id"] == school_id
        assert "affiliation_no" in sch_data
        assert "principal_name" in sch_data
        assert "website" in sch_data
        assert "academic_year" in sch_data
        print(f"    -> Institutional Metadata: Board={sch_data.get('board')}, Term={sch_data.get('academic_year')}, Affiliation={sch_data.get('affiliation_no')}")

        # ── Test 3: PUT /schools/{school_id} ──────────────────────────────────
        print(f"\n[+] Test 3: PUT /schools/{school_id} (Update institutional profile)")
        orig_name = sch_data["name"]
        update_payload = {
            "name": f"{orig_name}",
            "board": "CBSE",
            "affiliation_no": "CBSE/AFF/2130999",
            "principal_name": "Dr. Sunita Mehra, Ph.D.",
            "website": "https://www.dps-international.edu.in",
            "academic_year": "2025-26",
            "address": "Campus Block 4, Knowledge City",
            "city": "New Delhi",
            "state": "Delhi",
            "phone": "+91 11 2789 0001",
        }
        res = client.put(f"/schools/{school_id}", json=update_payload, headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        updated = res.json()["school"]
        assert updated["affiliation_no"] == "CBSE/AFF/2130999"
        assert updated["principal_name"] == "Dr. Sunita Mehra, Ph.D."
        assert updated["website"] == "https://www.dps-international.edu.in"
        assert updated["academic_year"] == "2025-26"
        print(f"    -> Successfully updated school: Principal={updated['principal_name']}, Affiliation={updated['affiliation_no']}")

        # ── Test 4: Payment Gateway & UPI Settings ────────────────────────────
        print(f"\n[+] Test 4: GET & POST /fees/config (Gateway & UPI settings)")
        pay_res = client.get(f"/fees/config?school_id={school_id}", headers=auth_headers)
        assert pay_res.status_code == 200, f"Expected 200, got {pay_res.status_code}: {pay_res.text}"

        save_pay_payload = {
            "school_id": school_id,
            "gateway_provider": "RAZORPAY",
            "merchant_key": "rzp_live_testkey_9988",
            "upi_vpa": "delhipublic@hdfcbank",
            "upi_account_name": "DPS International Society",
            "receipt_prefix": "DPS-RCP",
            "is_active": True,
        }
        res = client.post("/fees/config", json=save_pay_payload, headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        verify_pay = client.get(f"/fees/config?school_id={school_id}", headers=auth_headers).json()
        assert verify_pay["gateway_provider"] == "RAZORPAY"
        assert verify_pay["upi_vpa"] == "delhipublic@hdfcbank"
        assert verify_pay["receipt_prefix"] == "DPS-RCP"
        print(f"    -> Saved payment config: Provider={verify_pay['gateway_provider']}, UPI VPA={verify_pay['upi_vpa']}, Prefix={verify_pay['receipt_prefix']}")

        # ── Test 5: POST /admin/students (Full Real-World Enrollment) ──────────
        print(f"\n[+] Test 5: POST /admin/students (Enroll with all real-world fields)")
        import random
        random_suffix = random.randint(1000, 9999)
        test_adm_no = f"ADM-TEST-{random_suffix}"
        test_father_phone = f"98765{random.randint(10000, 99999)}"

        student_payload = {
            "name": "Kavya Sharma",
            "admission_no": test_adm_no,
            "roll_no": "42",
            "grade": "10",
            "section": "A",
            "gender": "Female",
            "dob": "2010-08-15",
            "photo_url": "/static/uploads/sample_kavya.png",
            "blood_group": "B+",
            "father_name": "Ramesh Sharma",
            "father_phone": test_father_phone,
            "mother_name": "Geeta Sharma",
            "mother_phone": "9811122334",
            "emergency_contact_name": "Dr. Ananya Sharma",
            "emergency_contact_phone": "+919876543210",
            "address": "Flat 304, Green Heights, Vasant Kunj, New Delhi",
            "medical_notes": "Mild asthma; carries inhaler in backpack",
            "previous_school": "St. Xavier's Convent (TC No. 8812)",
            "is_active": True,
        }

        res = client.post("/admin/students", json=student_payload, headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        st_data = res.json()["student"]
        created_student_id = st_data["id"]
        assert st_data["admission_no"] == test_adm_no
        assert st_data["dob"] == "2010-08-15"
        assert st_data["mother_name"] == "Geeta Sharma"
        assert st_data["blood_group"] == "B+"
        assert st_data["medical_notes"] == "Mild asthma; carries inhaler in backpack"
        assert st_data["previous_school"] == "St. Xavier's Convent (TC No. 8812)"
        print(f"    -> Enrolled student: '{st_data['name']}' (ID: {created_student_id}, DOB: {st_data['dob']}, Blood: {st_data['blood_group']})")

        # ── Test 6: Verify Auto-Provisioned Parent Account & Link ─────────────
        print(f"\n[+] Test 6: Verify Auto-Provisioned Parent Account")
        parent_user = db.query(UserDB).filter(UserDB.phone == test_father_phone).first()
        assert parent_user is not None, f"Parent account with phone {test_father_phone} should have been auto-provisioned."
        created_parent_id = str(parent_user.id)
        assert parent_user.role == "Parent"

        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == parent_user.id,
            ParentStudentDB.student_id == created_student_id
        ).first()
        assert link is not None, "ParentStudentDB link should have been created."
        print(f"    -> Verified parent account auto-created: {parent_user.email} (Phone: {parent_user.phone}, Relation: {link.relation})")

        # ── Test 7: GET /admin/students (List with all fields) ─────────────────
        print(f"\n[+] Test 7: GET /admin/students (Verify all extended fields in response)")
        res = client.get("/admin/students", headers=auth_headers)
        assert res.status_code == 200
        all_st = res.json()
        found_st = next((s for s in all_st if s["id"] == created_student_id), None)
        assert found_st is not None, "Created student should be in list"
        assert found_st["dob"] == "2010-08-15"
        assert found_st["mother_name"] == "Geeta Sharma"
        assert found_st["medical_notes"] == "Mild asthma; carries inhaler in backpack"
        assert found_st["previous_school"] == "St. Xavier's Convent (TC No. 8812)"
        assert found_st["is_active"] is True
        print(f"    -> Verified {len(all_st)} students listed. Created student contains all extended fields.")

        # ── Test 8: GET /admin/students/{student_id} (Dossier API) ─────────────
        print(f"\n[+] Test 8: GET /admin/students/{created_student_id} (Student Dossier)")
        res = client.get(f"/admin/students/{created_student_id}", headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        dossier = res.json()
        assert dossier["id"] == created_student_id
        assert dossier["name"] == "Kavya Sharma"
        assert dossier["dob"] == "2010-08-15"
        assert dossier["emergency_contact_name"] == "Dr. Ananya Sharma"
        assert dossier["address"] == "Flat 304, Green Heights, Vasant Kunj, New Delhi"
        print(f"    -> Student Dossier retrieved: Name={dossier['name']}, Emergency Contact={dossier['emergency_contact_name']} ({dossier['emergency_contact_phone']})")

        # ── Test 9: PUT /admin/students/{student_id} (Update student) ─────────
        print(f"\n[+] Test 9: PUT /admin/students/{created_student_id} (Update record)")
        update_st_payload = {
            "name": "Kavya R. Sharma",
            "roll_no": "43",
            "dob": "2010-08-16",
            "medical_notes": "Asthma resolved; allergy to pollen only",
            "address": "Villa 12, Palm Meadows, Gurgaon",
        }
        res = client.put(f"/admin/students/{created_student_id}", json=update_st_payload, headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        up_st = res.json()["student"]
        assert up_st["name"] == "Kavya R. Sharma"
        assert up_st["roll_no"] == "43"
        assert up_st["dob"] == "2010-08-16"
        assert up_st["medical_notes"] == "Asthma resolved; allergy to pollen only"
        assert up_st["address"] == "Villa 12, Palm Meadows, Gurgaon"
        print(f"    -> Updated student record: Name={up_st['name']}, DOB={up_st['dob']}, Notes={up_st['medical_notes']}")

        print("\n" + "=" * 70)
        print("  ALL REAL-WORLD SCHOOL & STUDENT CRUD TESTS PASSED WITH 100% SUCCESS!")
        print("=" * 70)

    finally:
        # Cleanup test student and parent
        if created_student_id:
            try:
                st = db.query(StudentDB).filter(StudentDB.id == created_student_id).first()
                if st:
                    db.delete(st)
                    db.commit()
            except Exception:
                pass
        if created_parent_id:
            try:
                p = db.query(UserDB).filter(UserDB.id == created_parent_id).first()
                if p:
                    db.delete(p)
                    db.commit()
            except Exception:
                pass
        db.close()

if __name__ == "__main__":
    test_school_and_student_management()
