"""
Seed comprehensive demo data for Academic Insights AI.
Creates:
- 2 Schools (Delhi Public International School, St. Xavier's)
- Admin, Teachers, Parents
- 8 Students in Grade 10-A
- 6 Subjects (Math, Science, English, SST, Hindi, Computers)
- 4 Exams across the academic year
- Real marks and letter grades
- 30 days of attendance
- Risk engine cases
- School announcements
- Parent support tickets
"""
import sys
import os
from datetime import date, timedelta, datetime, timezone
import random

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.session import SessionLocal, engine
from db.init_db import init_db
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.subject import Subject
from models.exam import Exam
from models.marks import Mark
from models.attendance_db import AttendanceDB
from models.parent_student_db import ParentStudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.teacher_feedback import TeacherFeedback
from models.risk_case_db import RiskCaseDB
from models.announcement_db import AnnouncementDB
from models.ticket_db import TicketDB
from models.notification_db import NotificationDB
from models.school_payment_config_db import SchoolPaymentConfigDB
from models.fee_structure_db import FeeStructureDB
from models.fee_payment_db import FeePaymentDB
from models.timetable_db import TimetableSlotDB
from models.school_calendar_db import SchoolCalendarEventDB
from models.leave_request_db import LeaveRequestDB
from models.homework_db import HomeworkDB, HomeworkSubmissionDB
from auth.auth_service import hash_password


def seed():
    print("[Seed] Initializing clean database schema...")
    from db.base import Base
    Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()

    try:

        print("[Seed] Creating Schools...")
        school1 = SchoolDB(
            name="Delhi Public International School",
            board="CBSE",
            address="Sector 24, Rohini, New Delhi, Delhi 110085",
            city="New Delhi",
            state="Delhi",
            phone="+91-11-27891234",
            email="info@dpis.edu.in",
            logo_url="/static/logo.jpg",
            is_active=True,
        )
        school2 = SchoolDB(
            name="St. Xavier's World Academy",
            board="ICSE",
            address="Fort Campus, Mumbai, Maharashtra 400001",
            city="Mumbai",
            state="Maharashtra",
            phone="+91-22-22620123",
            email="admissions@stxaviers.edu.in",
            is_active=True,
        )
        db.add_all([school1, school2])
        db.commit()
        db.refresh(school1)
        db.refresh(school2)

        s1_id = school1.id

        print("[Seed] Creating Users (Admin, Teachers, Parents)...")
        admin_user = UserDB(
            school_id=s1_id,
            email="admin@dpis.edu",
            phone="+919810011223",
            full_name="Dr. Alok Verma (Principal)",
            password_hash=hash_password("admin123"),
            role="Admin",
            email_verified=True,
        )
        teacher_sunita = UserDB(
            school_id=s1_id,
            email="teacher@dpis.edu",
            phone="+919876543210",
            full_name="Sunita Sharma",
            password_hash=hash_password("teacher123"),
            role="ClassTeacher",
            email_verified=True,
        )
        teacher_rajesh = UserDB(
            school_id=s1_id,
            email="rajesh.math@dpis.edu",
            phone="+919876543211",
            full_name="Rajesh Verma (Math Lead)",
            password_hash=hash_password("teacher123"),
            role="SubjectTeacher",
            email_verified=True,
        )
        parent_arun = UserDB(
            school_id=s1_id,
            email="parent@dpis.edu",
            phone="+919811223344",
            full_name="Arun Patel",
            password_hash=hash_password("parent123"),
            role="Parent",
            email_verified=True,
        )
        parent_priya = UserDB(
            school_id=s1_id,
            email="priya.singh@gmail.com",
            phone="+919822334455",
            full_name="Priya Singh",
            password_hash=hash_password("parent123"),
            role="Parent",
            email_verified=True,
        )
        parent_vikram = UserDB(
            school_id=s1_id,
            email="vikram.mehta@gmail.com",
            phone="+919833445566",
            full_name="Vikram Mehta",
            password_hash=hash_password("parent123"),
            role="Parent",
            email_verified=True,
        )

        db.add_all([admin_user, teacher_sunita, teacher_rajesh, parent_arun, parent_priya, parent_vikram])
        db.commit()
        db.refresh(admin_user)
        db.refresh(teacher_sunita)
        db.refresh(parent_arun)
        db.refresh(parent_priya)
        db.refresh(parent_vikram)

        print("[Seed] Creating Subjects...")
        subjects_data = [
            ("Mathematics", "MATH10", 1),
            ("Science", "SCI10", 2),
            ("English Language & Lit", "ENG10", 3),
            ("Social Science", "SST10", 4),
            ("Hindi Course A", "HIN10", 5),
            ("Information Technology", "IT10", 6),
        ]
        sub_objs = {}
        for name, code, order in subjects_data:
            s = Subject(school_id=s1_id, name=name, code=code, sort_order=order)
            db.add(s)
            db.commit()
            db.refresh(s)
            sub_objs[name] = s

        print("[Seed] Creating Teacher Class Assignments...")
        assign1 = TeacherAssignmentDB(
            school_id=s1_id,
            teacher_user_id=teacher_sunita.id,
            grade="10",
            section="A",
            role_type="ClassTeacher",
            subject_id=sub_objs["Science"].id,
        )
        assign2 = TeacherAssignmentDB(
            school_id=s1_id,
            teacher_user_id=teacher_rajesh.id,
            grade="10",
            section="A",
            role_type="SubjectTeacher",
            subject_id=sub_objs["Mathematics"].id,
        )
        db.add_all([assign1, assign2])
        db.commit()

        print("[Seed] Creating Students in Grade 10-A...")
        students_info = [
            ("Aarav Patel", "ADM-2025-101", "1", "Male", date(2010, 4, 12), "B+", "Arun Patel", "+919811122233", "Meena Patel", "+919811122234", "+919811122233", "Flat 402, Lotus Greens, Sector 24, Rohini, New Delhi", "No known chronic conditions. Carries spectacles."),
            ("Ananya Singh", "ADM-2025-102", "2", "Female", date(2010, 8, 24), "O+", "Rajesh Singh", "+919822233344", "Priya Singh", "+919822233345", "+919822233345", "House 12, Pocket D, Shalimar Bagh, New Delhi", "Allergic to penicillin."),
            ("Rohan Mehta", "ADM-2025-103", "3", "Male", date(2010, 2, 15), "A+", "Vikram Mehta", "+919833344455", "Kavita Mehta", "+919833344456", "+919833344455", "Tower 3, Apt 901, Palm Court, Pitampura, New Delhi", "Mild seasonal asthma. Inhaler kept in medical room."),
            ("Diya Kapoor", "ADM-2025-104", "4", "Female", date(2010, 11, 5), "AB+", "Sanjay Kapoor", "+919844455566", "Neha Kapoor", "+919844455567", "+919844455566", "B-104, Model Town Phase 2, New Delhi", "Normal health profile."),
            ("Kabir Khan", "ADM-2025-105", "5", "Male", date(2009, 12, 19), "O-", "Tariq Khan", "+919855566677", "Shabana Khan", "+919855566678", "+919855566677", "C-45, Ashok Vihar Phase 1, New Delhi", "Requires front-row seating due to mild myopia."),
            ("Ishaan Gupta", "ADM-2025-106", "6", "Male", date(2010, 6, 30), "B-", "Praveen Gupta", "+919866677788", "Ritu Gupta", "+919866677789", "+919866677788", "Pocket 7, Sector 9, Rohini, New Delhi", "Normal health profile."),
            ("Riya Sen", "ADM-2025-107", "7", "Female", date(2010, 9, 14), "A-", "Subhash Sen", "+919877788899", "Moumita Sen", "+919877788800", "+919877788899", "18/2, Civil Lines, North Delhi", "Lactose intolerant."),
            ("Aditya Joshi", "ADM-2025-108", "8", "Male", date(2010, 1, 8), "O+", "Nitin Joshi", "+919888899900", "Anjali Joshi", "+919888899901", "+919888899900", "D-6, Paschim Vihar, New Delhi", "Normal health profile."),
        ]
        student_objs = {}
        for name, adm, roll, gen, dob, bg, f_name, f_phone, m_name, m_phone, emg_phone, addr, med in students_info:
            st = StudentDB(
                school_id=s1_id,
                name=name,
                admission_no=adm,
                roll_no=roll,
                grade="10",
                section="A",
                gender=gen,
                dob=dob,
                blood_group=bg,
                father_name=f_name,
                father_phone=f_phone,
                mother_name=m_name,
                mother_phone=m_phone,
                emergency_contact_phone=emg_phone,
                address=addr,
                medical_notes=med,
                is_active=True,
            )
            db.add(st)
            db.commit()
            db.refresh(st)
            student_objs[name] = st

        print("[Seed] Linking Parents to Students...")
        p_links = [
            ParentStudentDB(parent_user_id=parent_arun.id, student_id=student_objs["Aarav Patel"].id, relation="Father", is_primary=True, is_verified=True),
            ParentStudentDB(parent_user_id=parent_priya.id, student_id=student_objs["Ananya Singh"].id, relation="Mother", is_primary=True, is_verified=True),
            ParentStudentDB(parent_user_id=parent_vikram.id, student_id=student_objs["Rohan Mehta"].id, relation="Father", is_primary=True, is_verified=True),
        ]
        db.add_all(p_links)
        db.commit()

        print("[Seed] Creating Exams...")
        exams_data = [
            ("Unit Test 1", "Unit Test", "Term 1", "10", date(2025, 7, 15), 50.0),
            ("Mid-Term Examination", "Term Exam", "Term 1", "10", date(2025, 9, 25), 100.0),
            ("Unit Test 2", "Unit Test", "Term 2", "10", date(2025, 11, 20), 50.0),
            ("Pre-Board Examination", "Final", "Term 2", "10", date(2026, 1, 15), 100.0),
        ]
        exam_objs = {}
        for name, etype, term, grade, edate, max_m in exams_data:
            ex = Exam(
                school_id=s1_id,
                name=name,
                exam_type=etype,
                term=term,
                grade=grade,
                date=edate,
                total_marks=max_m,
                is_published=True,
            )
            db.add(ex)
            db.commit()
            db.refresh(ex)
            exam_objs[name] = ex

        print("[Seed] Adding Marks for all students...")
        # Distinct realistic performance baselines per student
        perf_profiles = {
            "Aarav Patel": (0.88, 0.94),   # Strong consistently
            "Ananya Singh": (0.92, 0.98),  # Class topper
            "Rohan Mehta": (0.45, 0.55),   # Struggling / dropping
            "Diya Kapoor": (0.65, 0.75),   # Average
            "Kabir Khan": (0.75, 0.85),    # Above average
            "Ishaan Gupta": (0.70, 0.80),  # Good
            "Riya Sen": (0.82, 0.90),      # High achiever
            "Aditya Joshi": (0.58, 0.68),  # Needs support
        }

        for ex_name, ex in exam_objs.items():
            max_marks = ex.total_marks
            for st_name, st in student_objs.items():
                min_p, max_p = perf_profiles[st_name]
                for sub_name, sub in sub_objs.items():
                    # Special cases for realism
                    if st_name == "Rohan Mehta" and sub_name == "Mathematics":
                        pct = 0.36  # Failing in math
                    elif st_name == "Diya Kapoor" and sub_name == "Science":
                        pct = 0.42
                    else:
                        pct = round(random.uniform(min_p, max_p), 2)

                    obtained = round(pct * max_marks, 1)
                    grade_letter = "A+" if pct >= 0.90 else ("A" if pct >= 0.80 else ("B" if pct >= 0.65 else ("C" if pct >= 0.50 else ("D" if pct >= 0.40 else "F"))))

                    mark = Mark(
                        school_id=s1_id,
                        student_id=st.id,
                        exam_id=ex.id,
                        subject_id=sub.id,
                        marks_obtained=obtained,
                        max_marks=max_marks,
                        grade_letter=grade_letter,
                        uploaded_by=teacher_sunita.id,
                    )
                    db.add(mark)
        db.commit()

        print("[Seed] Adding 30 days of Daily Attendance...")
        today = date.today()
        for day_offset in range(30, 0, -1):
            att_date = today - timedelta(days=day_offset)
            # Skip Sundays
            if att_date.weekday() == 6:
                continue

            for st_name, st in student_objs.items():
                # Rohan Mehta has consecutive absences recently
                if st_name == "Rohan Mehta" and day_offset <= 4:
                    status = "Absent"
                    reason = "Unexcused Absence"
                elif st_name == "Rohan Mehta" and random.random() < 0.25:
                    status = "Absent"
                    reason = "Medical Leave"
                elif random.random() < 0.05:
                    status = "Absent"
                    reason = "Family Event"
                else:
                    status = "Present"
                    reason = None

                att = AttendanceDB(
                    school_id=s1_id,
                    student_id=st.id,
                    date=att_date,
                    status=status,
                    reason=reason,
                    marked_by=teacher_sunita.id,
                )
                db.add(att)
        db.commit()

        print("[Seed] Adding Teacher Feedback...")
        fb1 = TeacherFeedback(
            school_id=s1_id,
            student_id=student_objs["Aarav Patel"].id,
            exam_id=exam_objs["Pre-Board Examination"].id,
            teacher_id=teacher_sunita.id,
            feedback="Aarav is an exceptional and inquisitive learner. His analytical ability in Science and Mathematics is outstanding.",
            strengths="Analytical Thinking, Consistent Homework, Active Participation",
            needs_work="Speed in descriptive writing for Social Sciences",
        )
        fb2 = TeacherFeedback(
            school_id=s1_id,
            student_id=student_objs["Rohan Mehta"].id,
            exam_id=exam_objs["Pre-Board Examination"].id,
            teacher_id=teacher_sunita.id,
            feedback="Rohan has great potential but attendance irregularities have affected his understanding of recent complex topics in Mathematics.",
            strengths="Creative Problem Solving when attentive",
            needs_work="Class Attendance, Daily Formula Practice, Homework completion",
        )
        db.add_all([fb1, fb2])
        db.commit()

        print("[Seed] Adding Risk Cases...")
        rc1 = RiskCaseDB(
            school_id=s1_id,
            student_id=student_objs["Rohan Mehta"].id,
            risk_level="HIGH",
            trigger_rule="CONSECUTIVE_ABSENCES_4",
            title="Attendance Alert: 4 Consecutive Days Absent",
            description="Rohan Mehta has missed 4 consecutive days without prior sanctioned leave. Attendance rate dropped to 68%.",
            status="OPEN",
            assigned_to=teacher_sunita.id,
        )
        rc2 = RiskCaseDB(
            school_id=s1_id,
            student_id=student_objs["Rohan Mehta"].id,
            risk_level="HIGH",
            trigger_rule="FAILING_SUBJECTS_1",
            title="Academic Alert: Mathematics Score Under 40%",
            description="Scored 36% in Mathematics Pre-Board Exam. Remedial intervention recommended.",
            status="OPEN",
            assigned_to=teacher_rajesh.id,
        )
        db.add_all([rc1, rc2])
        db.commit()

        print("[Seed] Adding Announcements...")
        announcements = [
            AnnouncementDB(
                school_id=s1_id,
                author_id=admin_user.id,
                title="Annual Sports Meet 2026 Schedule & Guidelines",
                content="The Annual Sports Meet will be held on February 20-21. All students must assemble in proper athletic uniforms by 8:00 AM.",
                target_role="ALL",
                is_pinned=True,
                send_whatsapp=True,
                send_email=True,
            ),
            AnnouncementDB(
                school_id=s1_id,
                author_id=admin_user.id,
                title="Term 2 Parent-Teacher Meeting (PTM)",
                content="The PTM for Grade 10 is scheduled for Saturday, February 14, from 9:00 AM to 1:00 PM. Parents are requested to adhere to their designated time slots.",
                target_role="PARENTS",
                is_pinned=True,
                send_whatsapp=True,
                send_email=True,
            ),
            AnnouncementDB(
                school_id=s1_id,
                author_id=admin_user.id,
                title="CBSE Board Examination Admit Cards & Instructions",
                content="Admit cards for the Class 10 CBSE Board Examinations are available for collection at the administrative office. Kindly verify details carefully.",
                target_role="GRADE_10",
                target_grade="10",
                is_pinned=False,
                send_whatsapp=True,
                send_email=True,
            ),
        ]
        db.add_all(announcements)
        db.commit()

        print("[Seed] Adding Parent Service Tickets...")
        tickets = [
            TicketDB(
                school_id=s1_id,
                parent_user_id=parent_arun.id,
                student_id=student_objs["Aarav Patel"].id,
                category="Academic",
                subject="Request for advanced Olympiad preparation material",
                description="We would appreciate guidance and sample problem sets for Aarav for the upcoming Regional Math Olympiad.",
                priority="MEDIUM",
                status="OPEN",
            ),
            TicketDB(
                school_id=s1_id,
                parent_user_id=parent_vikram.id,
                student_id=student_objs["Rohan Mehta"].id,
                category="Transport",
                subject="Bus Route 14B morning stop change inquiry",
                description="Due to road construction near Gate 2, could the morning bus halt near the community center instead?",
                priority="HIGH",
                status="IN_PROGRESS",
            ),
            TicketDB(
                school_id=s1_id,
                parent_user_id=parent_priya.id,
                student_id=student_objs["Ananya Singh"].id,
                category="Fees",
                subject="Confirmation for Term 2 tuition receipt",
                description="Tuition fee was transferred on 2nd Jan. Requesting copy of official signed receipt for tax filing.",
                priority="LOW",
                status="RESOLVED",
                resolution_notes="Receipt emailed to parent on 4th Jan.",
                resolved_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(tickets)
        db.commit()

        print("[Seed] Creating School Payment Config...")
        pay_cfg = SchoolPaymentConfigDB(
            school_id=s1_id,
            gateway_provider="RAZORPAY",
            merchant_key="rzp_live_dpis_demo99",
            merchant_secret="rzp_sec_dpis_demo99",
            upi_vpa="dpis.school@icici",
            upi_account_name="Delhi Public International School Admin",
            receipt_prefix="DPIS/2025-26/",
            is_active=True,
        )
        db.add(pay_cfg)
        db.commit()

        print("[Seed] Creating Fee Structures...")
        fee_structs = [
            FeeStructureDB(
                school_id=s1_id,
                academic_year="2025-26",
                grade="10",
                fee_head="Tuition Fee (Quarter 1)",
                total_amount=18500.0,
                installment_name="Q1 (Apr - Jun)",
                due_date=date(2025, 7, 15),
                grace_period_days=7,
                late_fine_per_day=50.0,
                is_optional=False,
                is_active=True,
            ),
            FeeStructureDB(
                school_id=s1_id,
                academic_year="2025-26",
                grade="10",
                fee_head="Science & Robotics Lab Fee",
                total_amount=4500.0,
                installment_name="Annual Lab",
                due_date=date(2025, 8, 1),
                grace_period_days=10,
                late_fine_per_day=20.0,
                is_optional=False,
                is_active=True,
            ),
            FeeStructureDB(
                school_id=s1_id,
                academic_year="2025-26",
                grade="10",
                fee_head="Annual Sports & Infrastructure Development",
                total_amount=7000.0,
                installment_name="Annual Development",
                due_date=date(2025, 8, 15),
                grace_period_days=15,
                late_fine_per_day=25.0,
                is_optional=False,
                is_active=True,
            ),
            FeeStructureDB(
                school_id=s1_id,
                academic_year="2025-26",
                grade="10",
                fee_head="Tuition Fee (Quarter 2)",
                total_amount=18500.0,
                installment_name="Q2 (Jul - Sep)",
                due_date=date(2025, 10, 15),
                grace_period_days=7,
                late_fine_per_day=50.0,
                is_optional=False,
                is_active=True,
            ),
        ]
        db.add_all(fee_structs)
        db.commit()
        for f in fee_structs:
            db.refresh(f)

        print("[Seed] Recording Atomic Fee Payments...")
        payments = [
            FeePaymentDB(
                school_id=s1_id,
                student_id=student_objs["Aarav Patel"].id,
                fee_structure_id=fee_structs[0].id,
                receipt_no="DPIS/2025-26/1001",
                base_amount_paid=18500.0,
                fine_amount_paid=0.0,
                discount_waiver=0.0,
                total_paid=18500.0,
                payment_mode="ONLINE_UPI",
                transaction_ref="UPI-UTR-90812344",
                gateway_status="COMPLETED",
                payment_date=date(2025, 7, 10),
                remarks="Online Parent Portal Payment",
            ),
            FeePaymentDB(
                school_id=s1_id,
                student_id=student_objs["Aarav Patel"].id,
                fee_structure_id=fee_structs[1].id,
                receipt_no="DPIS/2025-26/1002",
                base_amount_paid=4500.0,
                fine_amount_paid=0.0,
                discount_waiver=0.0,
                total_paid=4500.0,
                payment_mode="CARD",
                transaction_ref="POS-SWIPE-67890",
                gateway_status="COMPLETED",
                payment_date=date(2025, 7, 28),
                collected_by=admin_user.id,
                remarks="School Accounts Desk Swipe",
            ),
            FeePaymentDB(
                school_id=s1_id,
                student_id=student_objs["Ananya Singh"].id,
                fee_structure_id=fee_structs[0].id,
                receipt_no="DPIS/2025-26/1003",
                base_amount_paid=18500.0,
                fine_amount_paid=0.0,
                discount_waiver=0.0,
                total_paid=18500.0,
                payment_mode="CASH",
                transaction_ref="CASH-COUNTER-01",
                gateway_status="COMPLETED",
                payment_date=date(2025, 7, 12),
                collected_by=admin_user.id,
                remarks="Cashier Counter Official Receipt",
            ),
            FeePaymentDB(
                school_id=s1_id,
                student_id=student_objs["Rohan Mehta"].id,
                fee_structure_id=fee_structs[1].id,
                receipt_no="DPIS/2025-26/1004",
                base_amount_paid=4500.0,
                fine_amount_paid=0.0,
                discount_waiver=0.0,
                total_paid=4500.0,
                payment_mode="UPI_COUNTER",
                transaction_ref="UPI-COUNTER-9921",
                gateway_status="COMPLETED",
                payment_date=date(2025, 8, 2),
                collected_by=admin_user.id,
                remarks="QR Desk Scan Payment",
            ),
        ]
        db.add_all(payments)
        db.commit()

        print("[Seed] Creating Weekly Timetable for Grade 10-A...")
        period_defs = [
            (1, "08:00", "08:45", "Mathematics", teacher_rajesh.id, "Room 204"),
            (2, "08:45", "09:30", "Science", teacher_sunita.id, "Science Lab 1"),
            (3, "09:45", "10:30", "English Language & Lit", teacher_sunita.id, "Room 204"),
            (4, "10:30", "11:15", "Social Science", teacher_rajesh.id, "Room 204"),
            (5, "11:45", "12:30", "Hindi Course A", teacher_sunita.id, "Room 204"),
            (6, "12:30", "01:15", "Information Technology", teacher_rajesh.id, "Computer Lab B"),
            (7, "01:25", "02:05", "Science", teacher_sunita.id, "Science Lab 1"),
            (8, "02:05", "02:45", "Mathematics", teacher_rajesh.id, "Room 204"),
        ]
        # Days: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat
        slots = []
        for day in range(6):
            for p_num, s_time, e_time, sub_name, t_id, r_num in period_defs:
                slot = TimetableSlotDB(
                    school_id=s1_id,
                    academic_year="2025-26",
                    grade="10",
                    section="A",
                    day_of_week=day,
                    period_number=p_num,
                    start_time=s_time,
                    end_time=e_time,
                    subject_id=sub_objs[sub_name].id,
                    teacher_id=t_id,
                    room_number=r_num,
                    slot_type="CLASS",
                )
                slots.append(slot)
        db.add_all(slots)
        db.commit()

        print("[Seed] Creating School Calendar & Events...")
        cal_events = [
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Independence Day & Flag Hoisting",
                start_date=date(2025, 8, 15),
                end_date=date(2025, 8, 15),
                event_type="HOLIDAY",
                is_holiday=True,
                affects_attendance=True,
                target_grades="ALL",
                description="National Holiday - 78th Independence Day Celebrations.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Teachers' Day Special Assembly",
                start_date=date(2025, 9, 5),
                end_date=date(2025, 9, 5),
                event_type="OTHER",
                is_holiday=False,
                affects_attendance=False,
                target_grades="ALL",
                description="Student council-led felicitation of teachers.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Term 1 Mid-Term Examinations",
                start_date=date(2025, 9, 20),
                end_date=date(2025, 9, 30),
                event_type="EXAM",
                is_holiday=False,
                affects_attendance=False,
                target_grades="10",
                description="CBSE Class 10 Mid-Term Assessment Window.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Mahatma Gandhi Jayanti",
                start_date=date(2025, 10, 2),
                end_date=date(2025, 10, 2),
                event_type="HOLIDAY",
                is_holiday=True,
                affects_attendance=True,
                target_grades="ALL",
                description="Gazetted Public Holiday.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Diwali & Autumn Vacation",
                start_date=date(2025, 10, 20),
                end_date=date(2025, 10, 24),
                event_type="VACATION",
                is_holiday=True,
                affects_attendance=True,
                target_grades="ALL",
                description="Festive break for Diwali celebrations.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Children's Day & STEM Fair",
                start_date=date(2025, 11, 14),
                end_date=date(2025, 11, 14),
                event_type="OTHER",
                is_holiday=False,
                affects_attendance=False,
                target_grades="ALL",
                description="Annual Science, Technology and Robotics Exhibition.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Winter Vacation",
                start_date=date(2025, 12, 25),
                end_date=date(2026, 1, 2),
                event_type="VACATION",
                is_holiday=True,
                affects_attendance=True,
                target_grades="ALL",
                description="Scheduled Winter Closure.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Republic Day Celebrations",
                start_date=date(2026, 1, 26),
                end_date=date(2026, 1, 26),
                event_type="HOLIDAY",
                is_holiday=True,
                affects_attendance=True,
                target_grades="ALL",
                description="National Holiday - 77th Republic Day.",
            ),
            SchoolCalendarEventDB(
                school_id=s1_id,
                title="Annual Sports Meet 2026",
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 11),
                event_type="SPORTS",
                is_holiday=False,
                affects_attendance=False,
                target_grades="ALL",
                description="Inter-house track and field athletic championship.",
            ),
        ]
        db.add_all(cal_events)
        db.commit()

        print("[Seed] Creating Homework & Submissions...")
        today = date.today()
        hw1 = HomeworkDB(
            school_id=s1_id,
            grade="10",
            section="A",
            subject_id=sub_objs["Mathematics"].id,
            posted_by=teacher_rajesh.id,
            title="Trigonometric Applications & Heights Problem Set",
            description="Complete NCERT Chapter 9 Exercise 9.1 Questions 1 to 10 in fair notebook.",
            due_date=today + timedelta(days=2),
            priority="HIGH",
        )
        hw2 = HomeworkDB(
            school_id=s1_id,
            grade="10",
            section="A",
            subject_id=sub_objs["Science"].id,
            posted_by=teacher_sunita.id,
            title="Chemical Reactions & Precipitation Observations",
            description="Write step-by-step balanced equations for displacement and double-displacement lab reactions.",
            due_date=today + timedelta(days=3),
            priority="MEDIUM",
        )
        hw3 = HomeworkDB(
            school_id=s1_id,
            grade="10",
            section="A",
            subject_id=sub_objs["Information Technology"].id,
            posted_by=teacher_rajesh.id,
            title="HTML5 Webpage with Structured CSS Layout",
            description="Create a responsive personal portfolio page using semantic tags and flexbox.",
            due_date=today + timedelta(days=4),
            priority="LOW",
        )
        db.add_all([hw1, hw2, hw3])
        db.commit()
        db.refresh(hw1)
        db.refresh(hw2)
        db.refresh(hw3)

        hw_subs = [
            HomeworkSubmissionDB(
                homework_id=hw1.id,
                student_id=student_objs["Aarav Patel"].id,
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc) - timedelta(hours=5),
                remarks="Notebook checked and verified.",
                grade_value="A+",
            ),
            HomeworkSubmissionDB(
                homework_id=hw2.id,
                student_id=student_objs["Aarav Patel"].id,
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc) - timedelta(hours=3),
                remarks="Detailed diagrams included.",
                grade_value="A",
            ),
            HomeworkSubmissionDB(
                homework_id=hw1.id,
                student_id=student_objs["Ananya Singh"].id,
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc) - timedelta(hours=6),
                remarks="Accurate formulas.",
                grade_value="A+",
            ),
            HomeworkSubmissionDB(
                homework_id=hw2.id,
                student_id=student_objs["Rohan Mehta"].id,
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc) - timedelta(hours=2),
                remarks="Good effort.",
                grade_value="B+",
            ),
        ]
        db.add_all(hw_subs)
        db.commit()

        print("[Seed] Creating Digital Leave Requests...")
        leaves = [
            LeaveRequestDB(
                school_id=s1_id,
                student_id=student_objs["Aarav Patel"].id,
                user_id=parent_arun.id,
                from_date=today - timedelta(days=4),
                to_date=today - timedelta(days=3),
                leave_type="SICK",
                reason="Viral fever and throat infection. Doctor advised 2 days of bed rest.",
                attachment_url="/prescriptions/aarav_medical_note.pdf",
                status="APPROVED",
                reviewed_by=teacher_sunita.id,
                admin_remarks="Approved. Medical prescription on record. Rest well.",
                reviewed_at=datetime.now(timezone.utc) - timedelta(days=3),
            ),
            LeaveRequestDB(
                school_id=s1_id,
                student_id=student_objs["Rohan Mehta"].id,
                user_id=parent_vikram.id,
                from_date=today + timedelta(days=1),
                to_date=today + timedelta(days=2),
                leave_type="FAMILY",
                reason="Attending elder cousin's wedding ceremony in Jaipur with family.",
                status="PENDING",
            ),
        ]
        db.add_all(leaves)
        db.commit()

        print("\n" + "="*60)
        print("[SUCCESS] Demo Data Seeding Completed Successfully!")
        print("="*60)
        print("School Name: Delhi Public International School")
        print("School ID  :", s1_id)
        print("\nTest Credentials:")
        print("1. Admin  : admin@dpis.edu   / admin123")
        print("2. Teacher: teacher@dpis.edu / teacher123")
        print("3. Parent : parent@dpis.edu  / parent123 (Child: Aarav Patel, ADM-2025-101)")
        print("="*60)

    except Exception as e:
        db.rollback()
        print(f"[Seed] Error occurred during seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
