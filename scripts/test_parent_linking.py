import requests

BASE = "http://127.0.0.1:8000"

print("--- Testing Parent Child Linking Workflow ---")
# 1. School Search
r = requests.get(f"{BASE}/schools/all")
assert r.status_code == 200
schools = r.json()
print(f"1. Total active schools: {len(schools)}")
school = schools[0]
school_id = school["id"]
print(f"   Selected school: {school['name']} ({school_id})")

# 2. School Classes
r = requests.get(f"{BASE}/parent/school-classes/{school_id}")
assert r.status_code == 200
classes_data = r.json()
classes = classes_data.get("classes", [])
print(f"2. Classes found: {len(classes)}")
for c in classes:
    print(f"   - Class {c['grade']}, Sections: {c['sections']}")

# 3. Class Students
grade = classes[0]["grade"]
section = classes[0]["sections"][0]
r = requests.get(f"{BASE}/parent/class-students?school_id={school_id}&grade={grade}&section={section}")
assert r.status_code == 200
students = r.json()
print(f"3. Students in Class {grade}-{section}: {len(students)}")
first_student = students[0]
print(f"   First student: {first_student['name']} (ID: {first_student['student_id']}, Roll: {first_student['roll_no']}, Adm: {first_student['admission_no']})")

# 4. Link Child by student_id
# Find parent user
r_parent = requests.get(f"{BASE}/admin/users?school_id={school_id}", headers={"Authorization": ""})
# Test linking payload
link_payload = {
    "parent_user_id": "c0000000-0000-0000-0000-000000000001",
    "school_id": school_id,
    "student_id": first_student["student_id"],
    "relation": "Father"
}
r_link = requests.post(f"{BASE}/parent/link-child", json=link_payload)
print(f"4. Link Child Response: {r_link.status_code} -> {r_link.json()}")
assert r_link.status_code in [200, 201]

# 5. Timetable verification
r_tt = requests.get(f"{BASE}/timetable/class?school_id={school_id}&grade={grade}&section={section}")
assert r_tt.status_code == 200
tt_data = r_tt.json()
days = list(tt_data.get("schedule", {}).keys())
print(f"5. Weekly timetable loaded across {len(days)} days: {days}")
assert len(days) >= 5

r_today = requests.get(f"{BASE}/timetable/today?school_id={school_id}&grade={grade}&section={section}")
assert r_today.status_code == 200
today_data = r_today.json()
print(f"   Today ({today_data.get('day')}): {len(today_data.get('periods', []))} periods scheduled")

print("\nSUCCESS: All new endpoints verified and working with live database!")
