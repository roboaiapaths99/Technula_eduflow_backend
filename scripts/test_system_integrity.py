import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app import app
from db.session import SessionLocal
from models.student_db import StudentDB
from models.school import SchoolDB
from models.user_db import UserDB

client = TestClient(app)

from auth.auth_service import create_access_token

def test_system_integrity():
    db = SessionLocal()
    try:
        student = db.query(StudentDB).first()
        school = db.query(SchoolDB).first()
        assert student is not None, "At least one student must exist in database"
        assert school is not None, "At least one school must exist in database"

        # Generate valid staff token for tests
        admin = db.query(UserDB).filter(UserDB.school_id == student.school_id, UserDB.role == "Admin").first()
        if not admin:
            admin = db.query(UserDB).filter(UserDB.role == "Admin").first()
        assert admin is not None, "At least one Admin user must exist"
        token = create_access_token({
            "sub": str(admin.id),
            "school_id": str(student.school_id),
            "role": "Admin",
            "email": admin.email,
        })
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Test GET /parent/student-overview/{student_id}
        print(f"\n[TEST 1] Testing /parent/student-overview/{student.id}...")
        res = client.get(f"/parent/student-overview/{student.id}", headers=headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "subjects" in data, "Response must include top-level 'subjects'"
        assert "overall_percentage" in data, "Response must include top-level 'overall_percentage'"
        assert isinstance(data["subjects"], list), "'subjects' must be a list"
        print(f"  -> Success! Found {len(data['subjects'])} subjects, overall score: {data['overall_percentage']}%")
        if data["subjects"]:
            print(f"  -> Sample subject: {data['subjects'][0]['name']} ({data['subjects'][0]['percentage']}%)")

        # 2. Test GET /chat/contacts with unlinked parent
        print("\n[TEST 2] Testing /chat/contacts with unlinked parent...")
        parent = db.query(UserDB).filter(UserDB.role == "Parent").first()
        if parent:
            p_token = create_access_token({"sub": str(parent.id), "school_id": str(school.id), "role": "Parent"})
            res = client.get("/chat/contacts", headers={"Authorization": f"Bearer {p_token}"})
            assert res.status_code == 200
            contacts = res.json()
            print(f"  -> Parent {parent.full_name} has {len(contacts)} contacts")
        else:
            res = client.get("/chat/contacts", headers=headers)
            assert res.status_code == 200
            contacts = res.json()
            print(f"  -> Admin has {len(contacts)} contacts")

        # 3. Test PTC Events & Slots
        print(f"\n[TEST 3] Testing /ptc/events for school {school.id}...")
        res = client.get(f"/ptc/events?school_id={school.id}", headers=headers)
        assert res.status_code == 200
        events = res.json()
        print(f"  -> Found {len(events)} PTC events")
        if events:
            ev_id = events[0]["id"]
            slots_res = client.get(f"/ptc/slots?event_id={ev_id}", headers=headers)
            assert slots_res.status_code == 200
            slots = slots_res.json()
            print(f"  -> Event '{events[0]['title']}' has {len(slots)} slots")

        # 4. Test Student Certificates
        print(f"\n[TEST 4] Testing /certificates/student/{student.id}...")
        res = client.get(f"/certificates/student/{student.id}", headers=headers)
        assert res.status_code == 200
        certs = res.json()
        print(f"  -> Found {len(certs)} certificate records for student")

        # 5. Test Student Diary
        print(f"\n[TEST 5] Testing /diary/student/{student.id}...")
        res = client.get(f"/diary/student/{student.id}", headers=headers)
        assert res.status_code == 200
        diary = res.json()
        entries = diary if isinstance(diary, list) else diary.get("entries", [])
        print(f"  -> Found {len(entries)} diary remarks for student")

        # 6. Test School Search
        print("\n[TEST 6] Testing /schools/search...")
        res = client.get("/schools/search?query=Public")
        assert res.status_code == 200
        schools = res.json()
        print(f"  -> Search returned {len(schools)} matching schools")

        print("\n==========================================")
        print("ALL SYSTEM INTEGRITY TESTS PASSED (100% OK)")
        print("==========================================")

    finally:
        db.close()

if __name__ == "__main__":
    test_system_integrity()
