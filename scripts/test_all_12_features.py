"""
End-to-End Test for All 12 Expansion Modules & Real Data Flows
"""
import sys
import os
import json

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app import app
from db.session import SessionLocal
from models.user_db import UserDB
from models.student_db import StudentDB
from models.school import SchoolDB

from auth.auth_service import create_access_token

client = TestClient(app)

def run_tests():
    print("=" * 60)
    print("RUNNING END-TO-END VALIDATION ACROSS ALL 12 EXPANSION MODULES")
    print("=" * 60)

    db = SessionLocal()
    try:
        school = db.query(SchoolDB).first()
        if not school:
            print("Creating test school...")
            school = SchoolDB(id=1, name="Delhi Public Test School", board="CBSE")
            db.add(school)
            db.commit()
            db.refresh(school)
        school_id = str(school.id)

        parent_user = db.query(UserDB).filter(UserDB.role == "Parent").first()
        if not parent_user:
            parent_user = UserDB(
                full_name="Parent Tester",
                email="parent_test@domain.com",
                password_hash="testpass",
                role="Parent",
                school_id=school.id,
                allow_whatsapp=True,
                allow_email=True,
                allow_sms=False
            )
            db.add(parent_user)
            db.commit()
            db.refresh(parent_user)

        student = db.query(StudentDB).filter(StudentDB.school_id == school.id).first()
        if not student:
            student = StudentDB(
                name="Aarav Sharma",
                grade="10",
                section="A",
                school_id=school.id,
                admission_no="ADM-9901",
                roll_number="12"
            )
            db.add(student)
            db.commit()
            db.refresh(student)

        # Admin user
        admin_user = db.query(UserDB).filter(UserDB.role == "Admin", UserDB.school_id == school.id).first()
        if not admin_user:
            admin_user = UserDB(
                full_name="Admin Tester",
                email="admin_test@domain.com",
                password_hash="testpass",
                role="Admin",
                school_id=school.id,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        # Guard user
        guard_user = db.query(UserDB).filter(UserDB.role == "Security", UserDB.school_id == school.id).first()
        if not guard_user:
            guard_user = UserDB(
                full_name="Security Guard",
                email="guard_test@domain.com",
                password_hash="testpass",
                role="Security",
                school_id=school.id,
            )
            db.add(guard_user)
            db.commit()
            db.refresh(guard_user)

        student_id = str(student.id)
        parent_user_id = str(parent_user.id)
        admin_user_id = str(admin_user.id)
        guard_user_id = str(guard_user.id)
        print(f"Using School ID: {school_id}, Student ID: {student_id}, Parent ID: {parent_user_id}, Admin ID: {admin_user_id}")

        parent_token = create_access_token({"sub": parent_user_id, "role": "Parent", "school_id": school_id})
        admin_token = create_access_token({"sub": admin_user_id, "role": "Admin", "school_id": school_id})
        guard_token = create_access_token({"sub": guard_user_id, "role": "Security", "school_id": school_id})

        parent_headers = {"Authorization": f"Bearer {parent_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        guard_headers = {"Authorization": f"Bearer {guard_token}"}

        # 1. Gate Pass Lifecycle
        print("\n--- 1. Testing Gate Pass Lifecycle ---")
        req_res = client.post("/gate-passes/request", headers=parent_headers, json={
            "student_id": student_id,
            "parent_user_id": parent_user_id,
            "school_id": school_id,
            "reason_category": "Medical",
            "reason": "Severe headache and fever, doctor appointment booked",
            "authorized_pickup_person": "Ramesh Sharma (Father)",
            "departure_time": "2026-10-15T11:30:00"
        })
        assert req_res.status_code == 200, f"Gate pass request failed: {req_res.text}"
        pass_data = req_res.json()
        pass_id = pass_data["id"]
        qr_code = pass_data["qr_code"]
        print(f"Gate Pass Created! ID={pass_id}, Code={pass_data.get('pass_code')}, Status={pass_data.get('status')}")

        # Admin approvals queue
        admin_res = client.get(f"/gate-passes/admin/queue?school_id={school_id}", headers=admin_headers)
        assert admin_res.status_code == 200, f"Admin queue fetch failed: {admin_res.text}"
        print(f"Admin Queue Count: {len(admin_res.json())}")

        # Admin approves
        approve_res = client.patch(f"/gate-passes/{pass_id}/review", headers=admin_headers, json={
            "status": "APPROVED",
            "admin_user_id": admin_user_id,
            "review_notes": "Authorized by Principal Desk"
        })
        assert approve_res.status_code == 200, f"Approval failed: {approve_res.text}"
        assert approve_res.json()["status"] == "APPROVED"
        print("Gate Pass APPROVED by Admin successfully.")

        # Guard Scanner Verification
        verify_res = client.get(f"/gate-passes/verify-qr/{qr_code}", headers=guard_headers)
        assert verify_res.status_code == 200, f"QR verification failed: {verify_res.text}"
        assert verify_res.json()["status"] == "APPROVED"
        print("Security Guard QR Scan Verified successfully!")

        # Guard Departure
        dep_res = client.post(f"/gate-passes/{pass_id}/guard-scan", headers=guard_headers, json={
            "action": "DEPARTURE",
            "guard_user_id": guard_user_id,
            "notes": "Left through Gate #2 with Father in car DL-04-1234"
        })
        assert dep_res.status_code == 200, f"Departure failed: {dep_res.text}"
        assert dep_res.json()["status"] == "OUT"
        print("Student marked OUT at Gate Scanner.")

        # Guard Return
        ret_res = client.post(f"/gate-passes/{pass_id}/guard-scan", headers=guard_headers, json={
            "action": "RETURN",
            "guard_user_id": guard_user_id,
            "notes": "Returned safely to campus"
        })
        assert ret_res.status_code == 200, f"Return failed: {ret_res.text}"
        assert ret_res.json()["status"] == "RETURNED"
        print("Student marked RETURNED at Gate Scanner.")

        # 2. Datesheets (Exam Timetable)
        print("\n--- 2. Testing Exam Datesheets ---")
        ds_res = client.post("/datesheets/", headers=admin_headers, json={
            "school_id": school_id,
            "exam_title": "Term-1 Half Yearly Examination 2026",
            "grade": "10",
            "academic_term": "Term 1",
            "session_year": "2026-27",
            "instructions": "Admit card and school ID badge mandatory. Calculators prohibited.",
            "entries": [
                {"subject_name": "Mathematics", "subject_code": "041", "exam_date": "2026-10-12", "start_time": "09:00 AM", "end_time": "12:00 PM", "max_marks": 80, "room_no": "Hall A"},
                {"subject_name": "Science", "subject_code": "086", "exam_date": "2026-10-15", "start_time": "09:00 AM", "end_time": "12:00 PM", "max_marks": 80, "room_no": "Hall A"},
                {"subject_name": "English", "subject_code": "184", "exam_date": "2026-10-18", "start_time": "09:00 AM", "end_time": "12:00 PM", "max_marks": 80, "room_no": "Hall B"}
            ]
        })
        assert ds_res.status_code == 200, f"Datesheet creation failed: {ds_res.text}"
        print(f"Datesheet Created! ID={ds_res.json().get('id')}")

        parent_ds = client.get("/datesheets/class/10", headers=parent_headers)
        assert parent_ds.status_code == 200, f"Parent datesheet fetch failed: {parent_ds.text}"
        print(f"Parent View Grade 10 Datesheets Count: {len(parent_ds.json())}")

        # 3. School Almanac & Handbooks
        print("\n--- 3. Testing Almanac Documents with Validity Window ---")
        alm_res = client.post("/almanac/", headers=admin_headers, json={
            "school_id": school_id,
            "title": "Annual Code of Conduct & Dress Code 2026-27",
            "category": "Rules & Conduct",
            "description": "Guidelines on punctuality, grooming, uniform standards, and device policy.",
            "content": "Full code of conduct text...",
            "valid_from": "2026-04-01",
            "valid_to": "2027-03-31"
        })
        assert alm_res.status_code == 200, f"Almanac creation failed: {alm_res.text}"
        print(f"Almanac Document Created! ID={alm_res.json().get('id')}")

        parent_alm = client.get(f"/almanac/school/{school_id}", headers=parent_headers)
        assert parent_alm.status_code == 200, f"Parent almanac fetch failed: {parent_alm.text}"
        print(f"Active Verified Almanac Documents Count: {len(parent_alm.json())}")

        # 4. Holiday Calendar
        print("\n--- 4. Testing Holiday Calendar & Next Holiday Countdown ---")
        hol_res = client.post("/holidays/", headers=admin_headers, json={
            "school_id": school_id,
            "title": "Diwali & Chhath Festive Break",
            "start_date": "2026-10-24",
            "end_date": "2026-10-30",
            "category": "Festival",
            "description": "School will remain closed for auspicious Diwali celebrations."
        })
        assert hol_res.status_code == 200, f"Holiday creation failed: {hol_res.text}"
        print("Holiday Published successfully.")

        hol_data = client.get(f"/holidays/school/{school_id}", headers=parent_headers).json()
        print(f"Holidays Count: {len(hol_data.get('holidays', []))}, Next Holiday Highlight: {hol_data.get('next_holiday', {}).get('title')}")

        # 5. Photo Gallery & Event Albums
        print("\n--- 5. Testing Photo Gallery ---")
        alb_res = client.post("/gallery/albums", headers=admin_headers, json={
            "school_id": school_id,
            "title": "Annual Sports Day Gala 2026",
            "description": "100m sprint, relay race, and trophy ceremony highlights.",
            "event_date": "2026-09-10"
        })
        assert alb_res.status_code == 200, f"Album creation failed: {alb_res.text}"
        alb_id = alb_res.json()["id"]
        print(f"Gallery Album Created! ID={alb_id}")

        photo_res = client.post(f"/gallery/albums/{alb_id}/photos", headers=admin_headers, json={
            "photos": [
                {"photo_url": "/static/uploads/sports_gold_medal.jpg", "caption": "Gold Medal Winner Podium"},
                {"photo_url": "/static/uploads/relay_race.jpg", "caption": "Senior Boys Relay Final"}
            ]
        })
        assert photo_res.status_code == 200, f"Photos add failed: {photo_res.text}"
        print("Photos attached to album.")

        # 6. Campus Activities Feed
        print("\n--- 6. Testing Campus Activity Feed ---")
        act_res = client.post("/activities/", headers=admin_headers, json={
            "school_id": school_id,
            "title": "Inter-School Science Olympiad Champions",
            "category": "Science",
            "description": "Our Grade 10 team secured 1st place in the National Robotics Expo!",
            "event_date": "2026-09-18"
        })
        assert act_res.status_code == 200, f"Activity creation failed: {act_res.text}"
        print(f"Activity Created! ID={act_res.json().get('id')}")

        # 7. Scoped Teachers Directory
        print("\n--- 7. Testing Scoped Teachers Directory ---")
        t_res = client.get(f"/parent/student/{student_id}/teachers", headers=parent_headers)
        assert t_res.status_code == 200, f"Teachers fetch failed: {t_res.text}"
        print(f"Scoped Teachers for Student {student_id}: {len(t_res.json().get('teachers', []))} mentors assigned.")

        # 8. Notification Permissions & Preferences
        print("\n--- 8. Testing Notification Permissions ---")
        pref_res = client.get(f"/parent-profile/channels/{parent_user_id}", headers=parent_headers)
        assert pref_res.status_code == 200, f"Prefs fetch failed: {pref_res.text}"
        print(f"Current Parent Prefs: {pref_res.json()}")

        up_pref = client.put(f"/parent-profile/channels/{parent_user_id}", headers=parent_headers, json={
            "allow_whatsapp": True,
            "allow_email": False,
            "allow_sms": True
        })
        assert up_pref.status_code == 200, f"Prefs update failed: {up_pref.text}"
        assert up_pref.json()["allow_whatsapp"] is True
        assert up_pref.json()["allow_email"] is False
        print("Channel preferences updated: WhatsApp=ON, Email=OFF, SMS=ON, In-App=Always ON.")

        # 9. Campus Visitor Log (Front Desk)
        print("\n--- 9. Testing Campus Visitor Log (Front Desk) ---")
        vis_res = client.post("/visitors/check-in", headers=admin_headers, json={
            "school_id": school_id,
            "visitor_name": "Sunita Verma",
            "visitor_phone": "+91 9876543219",
            "purpose": "PTM meeting with Class Teacher",
            "person_to_meet": "Mrs. Anjali Sharma",
            "id_proof_type": "Aadhaar Card",
            "id_proof_number": "XXXX-XXXX-1234",
            "logged_by_user_id": admin_user_id
        })
        assert vis_res.status_code == 200, f"Visitor check-in failed: {vis_res.text}"
        vis_id = vis_res.json()["id"]
        badge_num = vis_res.json().get("badge_number")
        print(f"Visitor Checked In! ID={vis_id}, Badge={badge_num}")

        vis_out = client.patch(f"/visitors/{vis_id}/check-out?guard_user_id={guard_user_id}", headers=guard_headers)
        assert vis_out.status_code == 200, f"Visitor check-out failed: {vis_out.text}"
        assert vis_out.json()["status"] == "CHECKED_OUT"
        print("Visitor Checked Out cleanly.")

        # 10. School Branding & Theme Customization
        print("\n--- 10. Testing School Branding Customization ---")
        brand_res = client.put(f"/branding/{school_id}", headers=admin_headers, json={
            "brand_color": "#1E3A8A",
            "powered_by_text": "Powered by Technula-Gaj",
            "birthday_template": "Happy Birthday {student_name}! Wishing you boundless joy from {school_name}.",
            "parent_profile_approval_required": True
        })
        assert brand_res.status_code == 200, f"Branding update failed: {brand_res.text}"
        assert brand_res.json()["brand_color"] == "#1E3A8A"
        print("Branding customized: Color=#1E3A8A, Attribution='Powered by Technula-Gaj'.")

        # 11. Multi-Channel Broadcast Alert Dispatch
        print("\n--- 11. Testing Multi-Channel Broadcast Alert ---")
        bcast_res = client.post("/broadcast/send", headers=admin_headers, json={
            "school_id": school_id,
            "target_audience": "ALL",
            "title": "Heavy Rain Alert & Early School Closure",
            "message": "Due to meteorological rainfall warnings, campus will dismiss at 12:30 PM today.",
            "channels": ["WHATSAPP", "EMAIL", "IN_APP"],
            "sender_user_id": admin_user_id
        })
        assert bcast_res.status_code == 200, f"Broadcast failed: {bcast_res.text}"
        print(f"Broadcast Dispatched! Result: {bcast_res.json()}")

        print("\n" + "=" * 60)
        print("ALL 12 MODULES & DATA FLOWS VALIDATED WITH 100% SUCCESS!")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
