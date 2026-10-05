"""
Database Seeder for Google Play Store Reviewer Demo Account.
Safely populates real PostgreSQL / SQLite database with verified parent-student records:
- Parent: Arun Patel (Phone: 9811223344, Role: Parent)
- Student: Aarav Patel (Class 10-A, Roll 12, Admission: ADM-2026-1001)
- Verified Parent-Student Link
- Real 30-day Attendance records
- Real Mid-Term & Unit Test Exam Marks
- Real Fee Payments and Verified Receipts
- Real Class Timetable Slots
- Real School Announcements

Usage on VPS:
    docker exec -it eduflow_backend python scripts/seed_reviewer_account.py
"""
import sys
import os
from datetime import date, timedelta, datetime, timezone
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.session import SessionLocal
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.subject import Subject
from models.exam import Exam
from models.marks import Mark
from models.attendance_db import AttendanceDB
from models.parent_student_db import ParentStudentDB
from models.fee_structure_db import FeeStructureDB
from models.fee_payment_db import FeePaymentDB
from models.timetable_db import TimetableSlotDB
from models.announcement_db import AnnouncementDB
from auth.auth_service import hash_password

def seed_reviewer():
    db = SessionLocal()
    try:
        schools = db.query(SchoolDB).filter(SchoolDB.is_active == True).all()
        if not schools:
            print("[Reviewer Seed] No active school found. Creating default school...")
            school = SchoolDB(
                name="Delhi Public International School",
                board="CBSE",
                address="Sector 24, Rohini, New Delhi, Delhi 110085",
                city="New Delhi",
                state="Delhi",
                phone="9811223344",
                email="sales@technula.com",
                is_active=True,
            )
            db.add(school)
            db.commit()
            db.refresh(school)
            schools = [school]

        for school in schools:
            print(f"\n==================================================")
            print(f"[*] Seeding Reviewer Account for School: {school.name} ({school.id})")
            print(f"==================================================")

            # 1. Create or update Parent User (Arun Patel)
            parent = db.query(UserDB).filter(
                UserDB.school_id == school.id,
                UserDB.phone == "9811223344",
                UserDB.role == "Parent"
            ).first()

            if not parent:
                parent = UserDB(
                    school_id=school.id,
                    email=f"reviewer.{school.code or 'parent'}@technula.com".lower(),
                    phone="9811223344",
                    full_name="Arun Patel",
                    password_hash=hash_password("reviewer123"),
                    role="Parent",
                    email_verified=True,
                )
                db.add(parent)
                db.commit()
                db.refresh(parent)
                print(f"[+] Created Parent User: {parent.full_name} | Phone: {parent.phone} | ID: {parent.id}")
            else:
                print(f"[=] Parent User already exists: {parent.full_name} | ID: {parent.id}")

            # 2. Create or update Student (Aarav Patel)
            student = db.query(StudentDB).filter(
                StudentDB.school_id == school.id,
                (StudentDB.father_phone == "9811223344") | (StudentDB.admission_no == "ADM-2026-1001")
            ).first()

            if not student:
                student = StudentDB(
                    school_id=school.id,
                    name="Aarav Patel",
                    admission_no="ADM-2026-1001",
                    roll_no="12",
                    grade="10",
                    section="A",
                    gender="Male",
                    dob=date(2011, 5, 14),
                    blood_group="O+",
                    father_name="Arun Patel",
                    father_phone="9811223344",
                    mother_name="Pooja Patel",
                    mother_phone="9811223345",
                    emergency_contact_name="Arun Patel",
                    emergency_contact_phone="9811223344",
                    address="Flat 402, Royal Palms, Sector 15",
                    is_active=True,
                )
                db.add(student)
                db.commit()
                db.refresh(student)
                print(f"[+] Created Student: {student.name} | Class: {student.grade}-{student.section} | ID: {student.id}")
            else:
                # Ensure phone is updated
                student.father_phone = "9811223344"
                db.commit()
                print(f"[=] Student already exists: {student.name} | ID: {student.id}")

            # 3. Create or verify Parent-Student Link
            link = db.query(ParentStudentDB).filter(
                ParentStudentDB.parent_user_id == parent.id,
                ParentStudentDB.student_id == student.id
            ).first()

            if not link:
                link = ParentStudentDB(
                    parent_user_id=parent.id,
                    student_id=student.id,
                    relation="Father",
                    is_primary=True,
                    is_verified=True,
                )
                db.add(link)
                db.commit()
                print(f"[+] Linked Parent ({parent.full_name}) <--> Student ({student.name})")
            else:
                link.is_verified = True
                link.is_primary = True
                db.commit()
                print(f"[=] Parent-Student Link verified and active.")

            # 4. Subjects
            subjects_data = [
                ("Mathematics", "MATH10", 1),
                ("Science & Physics", "SCI10", 2),
                ("English Core", "ENG10", 3),
                ("Social Studies", "SST10", 4),
                ("Computer Science", "CS10", 5),
            ]
            sub_objs = {}
            for name, code, order in subjects_data:
                s = db.query(Subject).filter(Subject.school_id == school.id, Subject.name == name).first()
                if not s:
                    s = Subject(school_id=school.id, name=name, code=code, sort_order=order)
                    db.add(s)
                    db.commit()
                    db.refresh(s)
                sub_objs[name] = s
            print(f"[+] Verified {len(sub_objs)} Academic Subjects")

            # 5. Exam & Marks
            exam = db.query(Exam).filter(Exam.school_id == school.id, Exam.name == "Mid-Term Assessment 2026").first()
            if not exam:
                exam = Exam(
                    school_id=school.id,
                    name="Mid-Term Assessment 2026",
                    exam_type="Term Exam",
                    term="Term 1",
                    grade="10",
                    date=date.today() - timedelta(days=20),
                    total_marks=100.0,
                    is_published=True,
                )
                db.add(exam)
                db.commit()
                db.refresh(exam)
                print(f"[+] Created Exam: {exam.name}")

            # Marks for Aarav Patel
            marks_map = {
                "Mathematics": (94.0, "A+"),
                "Science & Physics": (91.0, "A+"),
                "English Core": (86.0, "A"),
                "Social Studies": (88.0, "A"),
                "Computer Science": (96.0, "A+"),
            }
            for sub_name, (score, gr) in marks_map.items():
                sub = sub_objs[sub_name]
                m = db.query(Mark).filter(
                    Mark.school_id == school.id,
                    Mark.student_id == student.id,
                    Mark.exam_id == exam.id,
                    Mark.subject_id == sub.id
                ).first()
                if not m:
                    m = Mark(
                        school_id=school.id,
                        student_id=student.id,
                        exam_id=exam.id,
                        subject_id=sub.id,
                        marks_obtained=score,
                        max_marks=100.0,
                        grade_letter=gr,
                    )
                    db.add(m)
            db.commit()
            print(f"[+] Seeded Verified Marks for {student.name}")

            # 6. 30 Days of Real Attendance
            today = date.today()
            existing_att = db.query(AttendanceDB).filter(
                AttendanceDB.student_id == student.id
            ).count()

            if existing_att < 15:
                for day_offset in range(35, 0, -1):
                    att_date = today - timedelta(days=day_offset)
                    # Skip Sunday
                    if att_date.weekday() == 6:
                        continue

                    status = "Present"
                    remarks = "On time"
                    if day_offset == 15:
                        status = "Holiday"
                        remarks = "School Holiday"
                    elif day_offset == 7:
                        status = "Leave"
                        remarks = "Approved Sick Leave"

                    rec = db.query(AttendanceDB).filter(
                        AttendanceDB.student_id == student.id,
                        AttendanceDB.date == att_date
                    ).first()
                    if not rec:
                        db.add(AttendanceDB(
                            school_id=school.id,
                            student_id=student.id,
                            date=att_date,
                            status=status,
                            reason=remarks,
                        ))
                db.commit()
                print(f"[+] Seeded 30 Days of Real Daily Attendance for {student.name}")

            # 7. Real Fee Structure & Payment History
            fee_struct = db.query(FeeStructureDB).filter(
                FeeStructureDB.school_id == school.id,
                FeeStructureDB.grade == "10",
                FeeStructureDB.academic_year == "2026-27"
            ).first()
            if not fee_struct:
                fee_struct = FeeStructureDB(
                    school_id=school.id,
                    academic_year="2026-27",
                    grade="10",
                    fee_head="Tuition & Annual Composite Fee",
                    total_amount=37500.0,
                    installment_name="Annual",
                    due_date=date.today() + timedelta(days=60),
                    grace_period_days=10,
                    late_fine_per_day=50.0,
                    is_optional=False,
                    is_active=True
                )
                db.add(fee_struct)
                db.commit()
                db.refresh(fee_struct)

            # Verified Payments
            payments = db.query(FeePaymentDB).filter(FeePaymentDB.student_id == student.id).all()
            if not payments:
                p1 = FeePaymentDB(
                    school_id=school.id,
                    student_id=student.id,
                    fee_structure_id=fee_struct.id,
                    receipt_no="RCP-2026-0412",
                    base_amount_paid=12500.0,
                    fine_amount_paid=0.0,
                    discount_waiver=0.0,
                    total_paid=12500.0,
                    payment_mode="UPI_ONLINE",
                    transaction_ref="UPI/120938472910",
                    gateway_status="COMPLETED",
                    payment_date=date.today() - timedelta(days=120),
                    remarks="Term 1 Fee Payment - Verified"
                )
                p2 = FeePaymentDB(
                    school_id=school.id,
                    student_id=student.id,
                    fee_structure_id=fee_struct.id,
                    receipt_no="RCP-2026-0891",
                    base_amount_paid=12500.0,
                    fine_amount_paid=0.0,
                    discount_waiver=0.0,
                    total_paid=12500.0,
                    payment_mode="UPI_ONLINE",
                    transaction_ref="UPI/839201928374",
                    gateway_status="COMPLETED",
                    payment_date=date.today() - timedelta(days=50),
                    remarks="Term 2 Fee Payment - Verified"
                )
                db.add_all([p1, p2])
                db.commit()
                print(f"[+] Seeded Verified Fee Payment Receipts (RCP-2026-0412, RCP-2026-0891)")

            # 8. Timetable
            existing_slots = db.query(TimetableSlotDB).filter(
                TimetableSlotDB.school_id == school.id,
                TimetableSlotDB.grade == "10",
                TimetableSlotDB.section == "A"
            ).count()

            if existing_slots == 0:
                for day_idx in range(5):
                    periods = [
                        (1, "08:30", "09:15", "Mathematics", "Room 101"),
                        (2, "09:20", "10:05", "Science & Physics", "Lab 2"),
                        (3, "10:10", "10:55", "English Core", "Room 101"),
                        (4, "11:30", "12:15", "Social Studies", "Room 101"),
                        (5, "12:20", "13:05", "Computer Science", "Comp Lab 1"),
                    ]
                    for p_num, start_t, end_t, sub_name, room in periods:
                        sub = db.query(Subject).filter(Subject.school_id == school.id, Subject.name == sub_name).first()
                        db.add(TimetableSlotDB(
                            school_id=school.id,
                            academic_year="2026-27",
                            grade="10",
                            section="A",
                            day_of_week=day_idx,
                            period_number=p_num,
                            start_time=start_t,
                            end_time=end_t,
                            subject_id=sub.id if sub else None,
                            room_number=room,
                            slot_type="CLASS"
                        ))
                db.commit()
                print(f"[+] Seeded Class 10-A Timetable Schedule")

            # 9. Circulars & Announcements
            existing_ann = db.query(AnnouncementDB).filter(AnnouncementDB.school_id == school.id).count()
            if existing_ann == 0:
                ann1 = AnnouncementDB(
                    school_id=school.id,
                    title="Annual Sports Meet 2026",
                    content="We are pleased to announce our Annual Sports Meet scheduled for next month. All students must wear house uniforms.",
                    target_role="ALL",
                    is_pinned=True,
                    created_at=datetime.now(timezone.utc) - timedelta(days=2),
                )
                ann2 = AnnouncementDB(
                    school_id=school.id,
                    title="Parent-Teacher Meeting (PTM) Schedule",
                    content="Mid-term PTM will be held this Saturday between 9:00 AM and 1:00 PM. Parents can discuss term exam performance.",
                    target_role="PARENTS",
                    is_pinned=False,
                    created_at=datetime.now(timezone.utc) - timedelta(days=5),
                )
                db.add_all([ann1, ann2])
                db.commit()
                print(f"[+] Seeded Real School Announcements")

        print(f"\n[SUCCESS] Reviewer data feed completed! Ready for 100% real data flow.\n")

    finally:
        db.close()

if __name__ == "__main__":
    seed_reviewer()
