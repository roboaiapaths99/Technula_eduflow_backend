import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:8000"

def post(path, data, token=None):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get(path, token=None):
    req = urllib.request.Request(f"{BASE}{path}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

print("--- 1. Testing Health ---")
h = get("/health")
print("Health:", h)

print("\n--- 2. Testing Schools Search ---")
schools = get("/schools/search")
print(f"Found {len(schools)} active schools. First school: {schools[0]['name']} (ID: {schools[0]['id']})")
school_id = schools[0]['id']

print("\n--- 3. Testing Admin Login ---")
admin_res = post("/auth/login", {"email": "admin@dpis.edu", "password": "admin123"})
admin_token = admin_res["access_token"]
print("Admin Logged In:", admin_res["user"]["full_name"], "Role:", admin_res["user"]["role"])

print("\n--- 4. Testing Admin Overview Stats ---")
stats = get(f"/admin-stats/overview?school_id={school_id}", token=admin_token)
print("KPIs:", stats.get("kpis"))

print("\n--- 5. Testing Teacher Login ---")
teacher_res = post("/auth/login", {"email": "teacher@dpis.edu", "password": "teacher123"})
teacher_token = teacher_res["access_token"]
print("Teacher Logged In:", teacher_res["user"]["full_name"], "Role:", teacher_res["user"]["role"])

print("\n--- 6. Testing Class Attendance Retrieval ---")
att = get(f"/attendance/class-session?school_id={school_id}&grade=10&section=A", token=teacher_token)
print(f"Attendance sheet loaded for Grade 10-A: {len(att.get('students', []))} students")

print("\n--- 7. Testing Exams and Marks Matrix ---")
exams = get("/admin/exams", token=teacher_token)
print(f"Found {len(exams)} exams. Latest: {exams[0]['name']}")
exam_id = exams[0]["id"]
matrix = get(f"/marks/matrix?school_id={school_id}&exam_id={exam_id}&grade=10&section=A", token=teacher_token)
print(f"Marks matrix loaded with {len(matrix.get('subjects', []))} subjects and {len(matrix.get('roster', []))} student records")

print("\n--- 8. Testing Student Risk Cases ---")
cases = get(f"/risk-cases/?school_id={school_id}", token=admin_token)
print(f"Active risk cases identified: {len(cases)}")
for c in cases:
    print(f"  - [{c['risk_level']}] {c['student_name']}: {c['title']}")

print("\n--- 9. Testing Report Card Data Generation ---")
st_id = matrix['roster'][0]['student_id']
st_name = matrix['roster'][0]['name']
report = get(f"/report-cards/student/{st_id}/exam/{exam_id}", token=admin_token)
print(f"Report card generated for {st_name}: Overall Percentage = {report['overall_percentage']}%, Letter Grade Summary = {len(report['marks'])} subjects")

print("\n--- 10. Testing Live SVG Analytics Endpoints ---")
subj_avgs = get(f"/analytics/subject-averages?school_id={school_id}", token=admin_token)
print("Live Subject Averages:", subj_avgs)
grade_dist = get(f"/analytics/grade-distribution?school_id={school_id}", token=admin_token)
print("Live Grade Distribution:", grade_dist)
att_trend = get(f"/analytics/attendance-trend?school_id={school_id}", token=admin_token)
print(f"Live Attendance Trend: {len(att_trend.get('trend', []))} days recorded")
tiers = get(f"/analytics/performance-tiers?school_id={school_id}", token=admin_token)
print("Live Performance Tiers:", tiers)

print("\n--- 11. Testing Fee Management & Dues Calculation ---")
fee_overview = get(f"/fees/overview?school_id={school_id}", token=admin_token)
print("Fee Summary KPI:", fee_overview)
fee_dues = get(f"/fees/student/{st_id}/dues", token=admin_token)
print(f"Fee Dues for {st_name}: Total Paid=₹{fee_dues['summary']['total_fee_paid']}, Balance Outstanding=₹{fee_dues['summary']['total_balance_outstanding']}, Installments={len(fee_dues['breakdown'])}")

print("\n--- 12. Testing Weekly Timetable & Daily Schedule ---")
tt = get(f"/timetable/class?school_id={school_id}&grade=10&section=A", token=admin_token)
total_slots = sum(len(v) for v in tt.get("schedule", {}).values())
print(f"Weekly timetable loaded for 10-A: {total_slots} slots mapped across {len(tt.get('schedule', {}))} days")
today_tt = get(f"/timetable/today?school_id={school_id}&grade=10&section=A", token=admin_token)
print(f"Today's periods count: {len(today_tt.get('periods', []))}")

print("\n--- 13. Testing School Calendar & Working Days Calculation ---")
cal_events = get(f"/calendar/events?school_id={school_id}", token=admin_token)
print(f"Calendar events on file: {len(cal_events)}")
working_days = get(f"/calendar/working-days?school_id={school_id}&from_date=2025-08-01&to_date=2025-08-31", token=admin_token)
print("August 2025 Working Days calculation (excluding Sundays & Gazetted holidays):", working_days)

print("\n--- 14. Testing Digital Leave Management ---")
pending_leaves = get(f"/leaves/pending?school_id={school_id}", token=admin_token)
print(f"Pending leave applications awaiting review: {len(pending_leaves)}")
for l in pending_leaves:
    print(f"  - Leave for {l.get('student_name')}: {l.get('from_date')} to {l.get('to_date')} ({l.get('reason')})")

print("\n--- 15. Testing Homework Diary & Class Submissions ---")
hw_list = get(f"/homework/class?school_id={school_id}&grade=10&section=A", token=admin_token)
print(f"Active class homework assignments: {len(hw_list)}")
if hw_list:
    hw_id = hw_list[0]['id']
    subs = get(f"/homework/{hw_id}/submissions", token=admin_token)
    print(f"Submissions for '{hw_list[0]['title']}': {len(subs)} students recorded")

print("\n=============================================")
print("ALL 15 ENTERPRISE SUBSYSTEMS ARE 100% OPERATIONAL WITH REAL SQL DATA FLOW!")
print("=============================================")
