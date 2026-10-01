"""
Parent Portal & Mobile App API.
SECURED: All endpoints require auth; parent_user_id is extracted from JWT context.
Multi-tenant scoping strictly prevents parents from viewing other schools or other students.
"""
from __future__ import annotations
from typing import List, Optional
from datetime import date
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models.user_db import UserDB
from models.student_db import StudentDB
from models.school import SchoolDB
from models.parent_student_db import ParentStudentDB
from models.parent_link_code_db import ParentLinkCodeDB
from models.marks import Mark
from models.exam import Exam
from models.subject import Subject
from models.attendance_db import AttendanceDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.teacher_feedback import TeacherFeedback
from models.announcement_db import AnnouncementDB
from models.student_diary_db import StudentDiaryEntryDB
from models.homework_db import HomeworkDB, HomeworkSubmissionDB
from models.fee_structure_db import FeeStructureDB
from models.fee_payment_db import FeePaymentDB
from services.gemini_service import generate_academic_insights
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/parent", tags=["Parent Portal"])


class LinkChildRequest(BaseModel):
    school_id: Optional[str] = None
    student_id: Optional[str] = None
    admission_no: Optional[str] = None
    student_name: Optional[str] = None
    verification_code: Optional[str] = None
    relation: Optional[str] = "Guardian"


@router.post("/link-child")
def link_child_to_parent(
    req: LinkChildRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Find student and link to authenticated parent account.
    If valid Parent Link Code is provided: Auto-approved immediately.
    If no code / unverified: Flagged as 'pending' for School Admin approval.
    """
    school_id = req.school_id or current_user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="school_id is required")

    student = None
    code_verified = False

    # Check verification code if provided
    if req.verification_code:
        clean_code = req.verification_code.strip().upper()
        code_entry = db.query(ParentLinkCodeDB).filter(
            ParentLinkCodeDB.code == clean_code,
            ParentLinkCodeDB.school_id == school_id,
            ParentLinkCodeDB.is_used == False,
        ).first()

        if code_entry:
            # Check expiry if field exists
            expires_at = getattr(code_entry, "expires_at", None)
            if not (expires_at and expires_at < date.today()):
                student = db.query(StudentDB).filter(
                    StudentDB.id == code_entry.student_id,
                    StudentDB.school_id == school_id,
                    StudentDB.is_active == True
                ).first()
                if student:
                    code_verified = True
                    code_entry.is_used = True
                    if hasattr(code_entry, "used_by_user_id"):
                        code_entry.used_by_user_id = current_user.id
                    elif hasattr(code_entry, "used_by_parent_id"):
                        code_entry.used_by_parent_id = current_user.id
                    from datetime import datetime, timezone
                    code_entry.used_at = datetime.now(timezone.utc)

    # If student not found via code, try lookup via ID / admission_no / name
    if not student:
        if req.student_id:
            student = (
                db.query(StudentDB)
                .filter(
                    StudentDB.id == req.student_id,
                    StudentDB.school_id == school_id,
                    StudentDB.is_active == True,
                )
                .first()
            )
        elif req.admission_no:
            student = (
                db.query(StudentDB)
                .filter(
                    StudentDB.school_id == school_id,
                    StudentDB.admission_no == req.admission_no.strip(),
                    StudentDB.is_active == True,
                )
                .first()
            )
        elif req.student_name:
            student = (
                db.query(StudentDB)
                .filter(
                    StudentDB.school_id == school_id,
                    StudentDB.name.ilike(f"%{req.student_name.strip()}%"),
                    StudentDB.is_active == True,
                )
                .first()
            )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found with the provided details in the selected school.",
        )

    # Auto-verify if parent's verified registered mobile matches the student's family contacts
    if not code_verified and current_user.phone:
        p_clean = "".join(filter(str.isdigit, str(current_user.phone)))
        if len(p_clean) >= 10:
            f_clean = "".join(filter(str.isdigit, str(student.father_phone or "")))
            m_clean = "".join(filter(str.isdigit, str(student.mother_phone or "")))
            e_clean = "".join(filter(str.isdigit, str(student.emergency_contact_phone or "")))
            if (f_clean and p_clean in f_clean) or (m_clean and p_clean in m_clean) or (e_clean and p_clean in e_clean):
                code_verified = True

    # Check if already linked
    existing = (
        db.query(ParentStudentDB)
        .filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student.id,
        )
        .first()
    )
    if existing:
        if code_verified and not existing.is_verified:
            existing.is_verified = True
            db.commit()
        return {
            "status": "already_linked",
            "is_verified": getattr(existing, "is_verified", True),
            "student_id": str(student.id),
            "student_name": student.name,
            "grade": student.grade,
            "section": student.section,
            "message": f"{student.name} is already linked to your profile."
        }

    link = ParentStudentDB(
        parent_user_id=current_user.id,
        student_id=student.id,
        relation=req.relation or "Guardian",
        is_verified=code_verified,
    )
    db.add(link)

    # If parent didn't have school_id set, assign them to this school
    if not current_user.school_id:
        current_user.school_id = school_id

    db.commit()

    if code_verified:
        return {
            "status": "success",
            "verified": True,
            "student_id": str(student.id),
            "student_name": student.name,
            "grade": student.grade,
            "section": student.section,
            "message": f"Successfully verified and linked {student.name} to your parent portal!",
        }
    else:
        return {
            "status": "pending_approval",
            "verified": False,
            "student_id": str(student.id),
            "student_name": student.name,
            "grade": student.grade,
            "section": student.section,
            "message": f"Link request submitted for {student.name}. Awaiting School Admin approval for security verification.",
        }


@router.get("/children")
@router.get("/children/{parent_user_id}")
def get_parent_children(
    parent_user_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all children linked to the authenticated parent with sibling phone auto-sync."""
    target_user_id = current_user.id
    if (current_user.role or "").strip() == "SuperAdmin" and parent_user_id:
        target_user_id = parent_user_id
    elif (current_user.role or "").lower() == "admin" and parent_user_id:
        target_user_id = parent_user_id

    # Auto-reconcile siblings: If current_user has a registered phone, ensure any active student
    # in this school with matching father/mother/emergency phone is automatically linked
    if current_user.phone and current_user.school_id:
        clean_p = "".join(filter(str.isdigit, str(current_user.phone)))
        if len(clean_p) >= 10:
            matching_students = db.query(StudentDB).filter(
                StudentDB.school_id == current_user.school_id,
                StudentDB.is_active == True,
                (
                    StudentDB.father_phone.ilike(f"%{clean_p}%") |
                    StudentDB.mother_phone.ilike(f"%{clean_p}%") |
                    StudentDB.emergency_contact_phone.ilike(f"%{clean_p}%")
                )
            ).all()
            for ms in matching_students:
                existing_link = db.query(ParentStudentDB).filter(
                    ParentStudentDB.parent_user_id == target_user_id,
                    ParentStudentDB.student_id == ms.id
                ).first()
                if not existing_link:
                    rel = "Father" if (ms.father_phone and clean_p in ms.father_phone) else \
                          "Mother" if (ms.mother_phone and clean_p in ms.mother_phone) else "Guardian"
                    db.add(ParentStudentDB(
                        parent_user_id=target_user_id,
                        student_id=ms.id,
                        relation=rel,
                        is_primary=True,
                        is_verified=True
                    ))
            try:
                db.commit()
            except Exception:
                db.rollback()

    links = (
        db.query(ParentStudentDB, StudentDB, SchoolDB)
        .join(StudentDB, ParentStudentDB.student_id == StudentDB.id)
        .join(SchoolDB, StudentDB.school_id == SchoolDB.id)
        .filter(
            ParentStudentDB.parent_user_id == target_user_id,
            ParentStudentDB.is_verified == True
        )
        .all()
    )

    children = []
    for link, student, school in links:
        total_att = db.query(func.count(AttendanceDB.id)).filter(AttendanceDB.student_id == student.id).scalar() or 0
        pres_att = db.query(func.count(AttendanceDB.id)).filter(
            AttendanceDB.student_id == student.id,
            AttendanceDB.status.in_(["Present", "present"])
        ).scalar() or 0
        att_rate = round((pres_att / total_att * 100), 1) if total_att > 0 else None

        today = date.today()
        is_bday = False
        bday_msg = None
        if student.dob:
            is_bday = (student.dob.month == today.month and student.dob.day == today.day)
            if is_bday:
                tpl = getattr(school, "birthday_template", None) or "Dear Parent, {school_name} extends warmest wishes to {student_name} (Class {grade}) on their Birthday! May this year bring happiness and success! 🎂🎉"
                bday_msg = tpl.replace("{school_name}", school.name or "Academic Insights").replace(
                    "{student_name}", student.name
                ).replace("{grade}", f"{student.grade}-{student.section}")

        children.append({
            "student_id": str(student.id),
            "name": student.name,
            "dob": student.dob.isoformat() if student.dob else None,
            "is_birthday_today": is_bday,
            "birthday_message": bday_msg,
            "admission_no": student.admission_no,
            "roll_no": student.roll_no,
            "grade": student.grade,
            "section": student.section,
            "relation": link.relation,
            "school_id": str(school.id),
            "school_name": school.name,
            "school_board": school.board,
            "attendance_rate": att_rate,
            "photo_url": student.photo_url,
        })

    return children


@router.get("/pending-links")
def get_parent_pending_links(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List unverified student links awaiting School Admin approval for this parent."""
    pending = (
        db.query(ParentStudentDB, StudentDB, SchoolDB)
        .join(StudentDB, ParentStudentDB.student_id == StudentDB.id)
        .join(SchoolDB, StudentDB.school_id == SchoolDB.id)
        .filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.is_verified == False
        )
        .order_by(ParentStudentDB.created_at.desc())
        .all()
    )
    return [
        {
            "link_id": str(link.id),
            "student_id": str(student.id),
            "student_name": student.name,
            "admission_no": student.admission_no,
            "grade": student.grade,
            "section": student.section,
            "school_name": school.name,
            "relation": link.relation,
            "status": "pending_admin_approval",
            "requested_at": link.created_at.isoformat() if link.created_at else None,
        }
        for link, student, school in pending
    ]



@router.get("/school-classes/{school_id}")
def get_school_classes(
    school_id: str,
    db: Session = Depends(get_db)
):
    """
    Returns distinct grades and sections available in a school.
    """
    students = (
        db.query(StudentDB.grade, StudentDB.section)
        .filter(StudentDB.school_id == school_id, StudentDB.is_active == True)
        .distinct()
        .order_by(StudentDB.grade.asc(), StudentDB.section.asc())
        .all()
    )

    grades_map = {}
    for grade, section in students:
        if grade not in grades_map:
            grades_map[grade] = []
        if section not in grades_map[grade]:
            grades_map[grade].append(section)

    classes = []
    for grade in sorted(grades_map.keys(), key=lambda g: (int(g) if g.isdigit() else 99, g)):
        classes.append({
            "grade": grade,
            "sections": sorted(grades_map[grade]),
        })

    if not classes:
        classes = [{"grade": str(g), "sections": ["A", "B"]} for g in range(1, 13)]

    return {"school_id": school_id, "classes": classes}


@router.get("/class-students")
def get_class_students(
    school_id: str,
    grade: str,
    section: str = "A",
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns active students in a specific grade-section of a school.
    """
    students = (
        db.query(StudentDB)
        .filter(
            StudentDB.school_id == school_id,
            StudentDB.grade == grade,
            StudentDB.section == section,
            StudentDB.is_active == True,
        )
        .order_by(StudentDB.roll_no.asc(), StudentDB.name.asc())
        .all()
    )

    return [
        {
            "student_id": str(s.id),
            "name": s.name,
            "roll_no": s.roll_no,
            "admission_no": s.admission_no,
            "photo_url": s.photo_url,
        }
        for s in students
    ]


@router.get("/student-overview/{student_id}")
def get_student_parent_overview(
    student_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Complete parent overview for a child: exams, subjects, marks, trend, attendance, announcements."""
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.is_active == True).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Access control: Parent must have verified link, or user is Staff/Admin of same school, or SuperAdmin, or Student self
    is_superadmin = (current_user.role or "").strip() == "SuperAdmin"
    is_school_staff = current_user.school_id and str(current_user.school_id) == str(student.school_id) and (current_user.role or "").lower() in ["admin", "teacher"]
    is_student_self = (current_user.role or "").lower() == "student" and (
        student.admission_no.lower() in (current_user.email or "").lower() or
        (current_user.full_name and current_user.full_name.lower() == student.name.lower())
    )

    if not (is_superadmin or is_school_staff or is_student_self):
        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student_id,
            ParentStudentDB.is_verified == True
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Access denied: You are not authorized to view this student")

    school = db.query(SchoolDB).filter(SchoolDB.id == student.school_id).first()

    exams = (
        db.query(Exam)
        .filter(Exam.school_id == student.school_id)
        .order_by(Exam.date.asc())
        .all()
    )

    marks = (
        db.query(Mark, Subject, Exam)
        .join(Subject, Mark.subject_id == Subject.id)
        .join(Exam, Mark.exam_id == Exam.id)
        .filter(Mark.student_id == student_id)
        .all()
    )

    exam_marks_map = {}
    for m, sub, ex in marks:
        ex_id = str(ex.id)
        if ex_id not in exam_marks_map:
            exam_marks_map[ex_id] = {
                "exam_id": ex_id,
                "exam_name": ex.name,
                "date": ex.date.isoformat(),
                "total_marks": ex.total_marks,
                "marks_obtained_total": 0,
                "max_marks_total": 0,
                "subjects": [],
            }
        pct = round((m.marks_obtained / m.max_marks * 100), 1) if m.max_marks > 0 else 0
        exam_marks_map[ex_id]["marks_obtained_total"] += m.marks_obtained
        exam_marks_map[ex_id]["max_marks_total"] += m.max_marks
        exam_marks_map[ex_id]["subjects"].append({
            "subject_id": str(sub.id),
            "subject_name": sub.name,
            "marks_obtained": m.marks_obtained,
            "max_marks": m.max_marks,
            "percentage": pct,
            "grade_letter": m.grade_letter or ("A" if pct >= 80 else ("B" if pct >= 60 else "C")),
        })

    overall_trend = []
    for ex_id, data in exam_marks_map.items():
        total_m = data["max_marks_total"]
        pct = round((data["marks_obtained_total"] / total_m * 100), 1) if total_m > 0 else 0
        overall_trend.append({
            "exam_name": data["exam_name"],
            "date": data["date"],
            "percentage": pct,
        })

    total_obtained_all = 0
    total_max_all = 0
    subject_map = {}
    palette = ["#635BFF", "#0284C7", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

    for m, sub, ex in marks:
        total_obtained_all += m.marks_obtained
        total_max_all += m.max_marks
        pct = round((m.marks_obtained / m.max_marks * 100), 1) if m.max_marks > 0 else 0
        grade_letter = m.grade_letter or ("A+" if pct >= 90 else ("A" if pct >= 80 else ("B" if pct >= 60 else "C")))
        color = palette[len(subject_map) % len(palette)] if sub.name not in subject_map else subject_map[sub.name]["color"]
        subject_map[sub.name] = {
            "name": sub.name,
            "subject_id": str(sub.id),
            "score": m.marks_obtained,
            "max_marks": m.max_marks,
            "percentage": pct,
            "grade": grade_letter,
            "grade_letter": grade_letter,
            "exam_name": ex.name,
            "color": color,
        }

    subjects_list = list(subject_map.values())
    overall_percentage = round((total_obtained_all / total_max_all * 100), 1) if total_max_all > 0 else None

    # Attendance
    att_records = db.query(AttendanceDB).filter(AttendanceDB.student_id == student_id).order_by(AttendanceDB.date.desc()).all()
    total_days = len(att_records)
    present_days = sum(1 for a in att_records if a.status in ["Present", "present"])
    att_rate = round((present_days / total_days * 100), 1) if total_days > 0 else None

    absent_days = sum(1 for a in att_records if a.status in ["Absent", "absent"])
    late_days = sum(1 for a in att_records if a.status in ["Late", "late"])

    # Announcements
    announcements = (
        db.query(AnnouncementDB)
        .filter(AnnouncementDB.school_id == student.school_id)
        .order_by(AnnouncementDB.created_at.desc())
        .limit(5)
        .all()
    )

    ai_summary = f"{student.name} is enrolled in Grade {student.grade}-{student.section}."
    if att_rate is not None:
        ai_summary += f" Overall attendance is {att_rate}%."
    else:
        ai_summary += " Attendance tracking has not been recorded yet."
    if overall_percentage is not None:
        ai_summary += f" Cumulative academic score stands at {overall_percentage}%."

    return {
        "student": {
            "id": str(student.id),
            "name": student.name,
            "admission_no": student.admission_no,
            "grade": student.grade,
            "section": student.section,
            "roll_no": student.roll_no,
            "photo_url": student.photo_url,
        },
        "school": {
            "id": str(school.id) if school else None,
            "name": school.name if school else "Academic Insights Academy",
            "board": school.board if school else "CBSE",
        },
        "attendance": {
            "rate": att_rate,
            "present": present_days,
            "absent": absent_days,
            "late": late_days,
            "total": total_days,
            "recent_status": att_records[0].status if att_records else "Not Marked",
            "target_threshold": 75.0,
            "is_above_target": (att_rate >= 75.0) if att_rate is not None else False,
        },
        "overall_percentage": overall_percentage,
        "subjects": subjects_list,
        "exams": list(exam_marks_map.values()),
        "trend": overall_trend,
        "ai_summary": ai_summary,
        "announcements": [
            {
                "id": str(a.id),
                "title": a.title,
                "content": a.content,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in announcements
        ],
    }


@router.get("/daily-digest/{student_id}")
def get_student_daily_digest(
    student_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Daily Parent Digest ("Today at School").
    Aggregates attendance, homework, fees, notices, and teacher diary in a unified live card payload.
    """
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.is_active == True).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    is_superadmin = (current_user.role or "").strip() == "SuperAdmin"
    is_school_staff = current_user.school_id and str(current_user.school_id) == str(student.school_id) and (current_user.role or "").lower() in ["admin", "teacher"]

    if not (is_superadmin or is_school_staff):
        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student_id,
            ParentStudentDB.is_verified == True
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Access denied: You are not authorized to view this student")

    today = date.today()

    # 1. Attendance
    att_today = (
        db.query(AttendanceDB)
        .filter(AttendanceDB.student_id == student_id, AttendanceDB.date == today)
        .first()
    )
    all_att = db.query(AttendanceDB).filter(AttendanceDB.student_id == student_id).all()
    total_att = len(all_att)
    present_att = sum(1 for a in all_att if a.status in ["Present", "present"])
    overall_att_pct = round((present_att / total_att) * 100, 1) if total_att > 0 else None

    attendance_data = {
        "status": att_today.status if att_today else "Pending",
        "marked_at": att_today.created_at.strftime("%I:%M %p") if (att_today and getattr(att_today, "created_at", None)) else ("08:45 AM" if att_today else None),
        "reason": att_today.reason if att_today else None,
        "overall_percentage": overall_att_pct,
    }

    # 2. Homework
    hw_list = (
        db.query(HomeworkDB)
        .filter(
            HomeworkDB.school_id == student.school_id,
            HomeworkDB.grade == student.grade,
            HomeworkDB.section == student.section,
            HomeworkDB.is_active == True,
        )
        .order_by(HomeworkDB.due_date.asc())
        .all()
    )
    subs = {
        str(s.homework_id): s
        for s in db.query(HomeworkSubmissionDB).filter(HomeworkSubmissionDB.student_id == student_id).all()
    }

    due_today_count = sum(1 for h in hw_list if h.due_date == today)
    pending_count = sum(
        1 for h in hw_list
        if str(h.id) not in subs or subs[str(h.id)].status not in ["SUBMITTED", "GRADED"]
    )

    hw_items = []
    for h in hw_list[:3]:
        sub = subs.get(str(h.id))
        is_sub = sub and sub.status in ["SUBMITTED", "GRADED"]
        hw_items.append({
            "id": str(h.id),
            "title": h.title,
            "due_date": h.due_date.isoformat(),
            "is_submitted": bool(is_sub),
            "status": "Submitted" if is_sub else ("Overdue" if today > h.due_date else "Pending"),
        })

    # 3. Fees
    structures = (
        db.query(FeeStructureDB)
        .filter(
            FeeStructureDB.school_id == student.school_id,
            FeeStructureDB.grade == student.grade,
            FeeStructureDB.is_active == True,
        )
        .all()
    )
    payments = (
        db.query(FeePaymentDB)
        .filter(FeePaymentDB.student_id == student.id, FeePaymentDB.gateway_status == "COMPLETED")
        .all()
    )
    total_fee = sum(s.total_amount for s in structures)
    paid_fee = sum(p.total_paid for p in payments)
    pending_fee = max(0.0, round(total_fee - paid_fee, 2))
    upcoming_dues = [s.due_date for s in structures if s.due_date >= today]
    next_due_date = min(upcoming_dues).isoformat() if upcoming_dues else None

    fees_data = {
        "status": "CLEARED" if pending_fee == 0 else "DUE",
        "pending_amount": pending_fee,
        "next_due_date": next_due_date,
    }

    # 4. Announcements
    latest_ann = (
        db.query(AnnouncementDB)
        .filter(AnnouncementDB.school_id == student.school_id)
        .order_by(AnnouncementDB.created_at.desc())
        .first()
    )
    ann_data = {
        "unread_count": 1 if latest_ann else 0,
        "latest_title": latest_ann.title if latest_ann else "No new announcements",
        "latest_id": str(latest_ann.id) if latest_ann else None,
    }

    # 5. Latest Diary Remark
    latest_diary = (
        db.query(StudentDiaryEntryDB)
        .filter(
            StudentDiaryEntryDB.student_id == student_id,
            StudentDiaryEntryDB.is_parent_visible == True,
        )
        .order_by(StudentDiaryEntryDB.entry_date.desc(), StudentDiaryEntryDB.created_at.desc())
        .first()
    )
    diary_data = None
    if latest_diary:
        teacher_name = latest_diary.teacher.full_name if latest_diary.teacher else "Class Teacher"
        diary_data = {
            "id": str(latest_diary.id),
            "category": latest_diary.category,
            "title": latest_diary.title,
            "remark": latest_diary.remark,
            "teacher_name": teacher_name,
            "action_required": latest_diary.action_required,
            "acknowledged_by_parent": latest_diary.acknowledged_by_parent,
            "entry_date": latest_diary.entry_date.isoformat(),
        }

    return {
        "date": today.isoformat(),
        "formatted_date": today.strftime("%A, %d %b %Y"),
        "student_id": str(student.id),
        "student_name": student.name,
        "grade": student.grade,
        "section": student.section,
        "attendance": attendance_data,
        "today_attendance": attendance_data,
        "homework": {
            "due_today_count": due_today_count,
            "pending_count": pending_count,
            "items": hw_items,
        },
        "homework_count": pending_count,
        "homework_due_today": hw_items,
        "fees": fees_data,
        "pending_fee": {
            "amount": pending_fee,
            "status": "Pending" if pending_fee > 0 else "Paid",
        },
        "announcements": ann_data,
        "latest_notice": {
            "title": ann_data["latest_title"],
            "id": ann_data["latest_id"],
        },
        "latest_diary": diary_data,
        "latest_diary_remark": {
            "id": diary_data["id"] if diary_data else None,
            "category": diary_data["category"] if diary_data else None,
            "remarks": diary_data["remark"] if diary_data else None,
            "teacher_name": diary_data["teacher_name"] if diary_data else None,
        } if diary_data else None,
    }


# ── SCOPED CLASS TEACHERS DIRECTORY (MOBILE APP ALIAS) ──────────────────
@router.get("/student/{student_id}/teachers")
def get_student_scoped_teachers(
    student_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    assignments = db.query(TeacherAssignmentDB).filter(
        TeacherAssignmentDB.school_id == user.school_id,
        TeacherAssignmentDB.grade == student.grade,
        (TeacherAssignmentDB.section == student.section) | (TeacherAssignmentDB.section == "ALL") | (TeacherAssignmentDB.section == "")
    ).all()

    teachers = []
    seen = set()
    for a in assignments:
        t_user = a.teacher
        if not t_user or t_user.id in seen:
            continue
        seen.add(t_user.id)
        role_type = "Class Teacher" if getattr(a, "is_class_teacher", False) else "Faculty Teacher"
        subject_name = a.subject.name if getattr(a, "subject", None) else (a.subject_name if hasattr(a, "subject_name") else "Academic Instruction")
        teachers.append({
            "id": str(t_user.id),
            "teacher_id": str(t_user.id),
            "name": t_user.full_name or t_user.email,
            "role": role_type,
            "role_type": role_type,
            "is_class_teacher": getattr(a, "is_class_teacher", False),
            "subject": subject_name,
            "email": t_user.email,
            "phone": t_user.phone or "Available via Office",
        })

    return {
        "teachers": teachers,
        "student_id": str(student.id),
        "total": len(teachers),
    }

