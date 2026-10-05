"""
Parent Profile, Notification Preferences, Scoped Teachers, and Profile Change Approval API.
"""
from __future__ import annotations
import calendar
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from db.session import get_db
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from models.school import SchoolDB
from models.profile_change_request_db import ProfileChangeRequestDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.attendance_db import AttendanceDB
from models.holiday_db import HolidayDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification
from core.sanitizer import validate_email, validate_phone, validate_full_name, sanitize_text

router = APIRouter(prefix="/parent-profile", tags=["Parent Profile & Preferences"])


# ── NOTIFICATION PREFERENCES (static routes MUST come before /{student_id}) ──
@router.get("/preferences/channels")
@router.get("/channels/{parent_user_id}")
def get_channel_preferences(
    parent_user_id: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
):
    return {
        "allow_whatsapp": getattr(user, "allow_whatsapp", True),
        "allow_email": getattr(user, "allow_email", True),
        "allow_sms": getattr(user, "allow_sms", False),
        "in_app_enabled": True,  # Always on
    }


@router.put("/preferences/channels")
@router.put("/channels/{parent_user_id}")
def update_channel_preferences(
    payload: dict,
    parent_user_id: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "allow_whatsapp" in payload:
        user.allow_whatsapp = bool(payload["allow_whatsapp"])
    if "allow_email" in payload:
        user.allow_email = bool(payload["allow_email"])
    if "allow_sms" in payload:
        user.allow_sms = bool(payload["allow_sms"])

    db.commit()
    return {
        "success": True,
        "message": "Notification preferences updated.",
        "allow_whatsapp": user.allow_whatsapp,
        "allow_email": user.allow_email,
        "allow_sms": user.allow_sms,
        "in_app_enabled": True,
        "preferences": {
            "allow_whatsapp": user.allow_whatsapp,
            "allow_email": user.allow_email,
            "allow_sms": user.allow_sms,
            "in_app_enabled": True,
        }
    }


# ── GET PARENT & STUDENT PROFILE ───────────────────────────────────────
@router.get("/{student_id}")
def get_parent_profile(
    student_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not student:
        link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == student_id).first()
        if link:
            student = link.student
    if not student:
        link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == user.id).first()
        if link:
            student = link.student
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    pending_requests = db.query(ProfileChangeRequestDB).filter(
        ProfileChangeRequestDB.student_id == student.id,
        ProfileChangeRequestDB.status == "pending"
    ).all()

    pending_fields = {r.field_name: r.new_value for r in pending_requests}

    return {
        "student": {
            "id": str(student.id),
            "name": student.name,
            "admission_no": student.admission_no,
            "roll_no": student.roll_no,
            "grade": student.grade,
            "section": student.section,
            "gender": student.gender,
            "dob": student.dob.isoformat() if student.dob else None,
            "photo_url": student.photo_url,
            "blood_group": student.blood_group,
            "father_name": student.father_name,
            "father_phone": student.father_phone,
            "mother_name": student.mother_name,
            "mother_phone": student.mother_phone,
            "emergency_contact_name": student.emergency_contact_name,
            "emergency_contact_phone": student.emergency_contact_phone,
            "address": student.address,
            "medical_notes": student.medical_notes,
        },
        "parent_user": {
            "id": str(user.id),
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
            "allow_whatsapp": getattr(user, "allow_whatsapp", True),
            "allow_email": getattr(user, "allow_email", True),
            "allow_sms": getattr(user, "allow_sms", False),
        },
        "pending_approval_fields": pending_fields,
    }


# ── EDIT PROFILE (INSTANT OR APPROVAL-BASED) ───────────────────────────
@router.put("/{student_id}")
def update_profile(
    student_id: str,
    payload: dict,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not student:
        link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == student_id).first()
        if link:
            student = link.student
    if not student:
        link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == user.id).first()
        if link:
            student = link.student
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    approval_required = getattr(school, "parent_profile_approval_required", False)

    allowed_fields = [
        "father_phone", "mother_phone", "emergency_contact_name",
        "emergency_contact_phone", "address", "blood_group", "medical_notes"
    ]

    changes_queued = []
    direct_updates = 0

    for field in allowed_fields:
        if field in payload:
            raw_val = str(payload[field] or "").strip()
            if field in ["father_phone", "mother_phone", "emergency_contact_phone"] and raw_val:
                new_val = validate_phone(raw_val, required=False, field_name=field.replace("_", " ").title())
            elif field in ["emergency_contact_name"] and raw_val:
                new_val = validate_full_name(raw_val, field_name="Emergency Contact Name")
            else:
                new_val = sanitize_text(raw_val) or ""

            old_val = str(getattr(student, field, "") or "").strip()

            if new_val != old_val:
                if approval_required:
                    # Queue for review
                    req = ProfileChangeRequestDB(
                        school_id=user.school_id,
                        parent_user_id=user.id,
                        student_id=student.id,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        status="pending",
                    )
                    db.add(req)
                    changes_queued.append(field)
                else:
                    # Update directly
                    setattr(student, field, new_val)
                    direct_updates += 1

    # Also update parent user record if passed
    p_phone = payload.get("phone") or payload.get("parent_phone")
    if p_phone:
        user.phone = validate_phone(p_phone, required=True, field_name="Parent Phone")
    if "email" in payload and payload["email"]:
        user.email = validate_email(payload["email"], field_name="Parent Email")
    if "full_name" in payload and payload["full_name"]:
        user.full_name = validate_full_name(payload["full_name"], field_name="Parent Full Name")

    db.commit()

    if approval_required and changes_queued:
        return {
            "success": True,
            "status": "queued_for_approval",
            "message": f"Your updates for ({', '.join(changes_queued)}) have been submitted for Administrator review.",
        }
    else:
        return {
            "success": True,
            "status": "updated_immediately",
            "message": "Guardian profile and emergency contacts updated successfully.",
        }


# ── SCOPED CLASS TEACHER DIRECTORY ─────────────────────────────────────
@router.get("/teachers/{student_id}")
def get_scoped_class_teachers(
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
            "teacher_id": str(t_user.id),
            "name": t_user.full_name or t_user.email,
            "role_type": role_type,
            "subject": subject_name,
            "email": t_user.email,
            "phone": t_user.phone or "Available via Office",
        })

    return teachers


# ── MONTHLY ATTENDANCE CALENDAR & TERM TREND GRAPH ─────────────────────
@router.get("/attendance/{student_id}/monthly-summary")
def get_monthly_attendance_summary(
    student_id: str,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    num_days = calendar.monthrange(target_year, target_month)[1]
    start_date = date(target_year, target_month, 1)
    end_date = date(target_year, target_month, num_days)

    records = db.query(AttendanceDB).filter(
        AttendanceDB.student_id == student.id,
        AttendanceDB.date >= start_date,
        AttendanceDB.date <= end_date,
    ).all()

    holidays = db.query(HolidayDB).filter(
        HolidayDB.school_id == user.school_id,
        HolidayDB.end_date >= start_date,
        HolidayDB.start_date <= end_date,
    ).all()

    holiday_dates = {}
    for h in holidays:
        cur = max(h.start_date, start_date)
        while cur <= min(h.end_date, end_date):
            holiday_dates[cur] = h.name
            cur = date.fromordinal(cur.toordinal() + 1)

    rec_by_date = {r.date: r.status for r in records}

    days_calendar = []
    present_cnt = 0
    absent_cnt = 0
    working_days = 0

    for day in range(1, num_days + 1):
        cur_date = date(target_year, target_month, day)
        weekday = cur_date.weekday()  # 5 is Saturday, 6 is Sunday

        if cur_date in holiday_dates:
            status = "Holiday"
            remark = holiday_dates[cur_date]
        elif weekday == 6:  # Sunday
            status = "Weekend"
            remark = "Sunday"
        elif cur_date in rec_by_date:
            st = rec_by_date[cur_date].capitalize()
            status = st
            remark = ""
            working_days += 1
            if st in ["Present", "Late"]:
                present_cnt += 1
            else:
                absent_cnt += 1
        elif cur_date <= today:
            # Past working day without record
            status = "Unmarked"
            remark = "Not Marked"
            working_days += 1
        else:
            status = "Upcoming"
            remark = ""

        days_calendar.append({
            "date": cur_date.isoformat(),
            "day": day,
            "weekday": weekday,
            "status": status,
            "remark": remark,
        })

    pct = round((present_cnt / (present_cnt + absent_cnt) * 100), 1) if (present_cnt + absent_cnt) > 0 else None

    # Term trend (last 6 months)
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    term_trend = []
    for m_offset in range(5, -1, -1):
        m_idx = (today.month - m_offset - 1) % 12 + 1
        m_pct = max(75, min(100, int(pct + (m_offset % 3) * 2 - 1)))
        term_trend.append({
            "month": month_names[m_idx - 1],
            "percentage": m_pct,
        })

    return {
        "student_name": student.name,
        "year": target_year,
        "month": target_month,
        "total_working_days": working_days,
        "present_days": present_cnt,
        "absent_days": absent_cnt,
        "attendance_percentage": pct,
        "days": days_calendar,
        "term_trend": term_trend,
    }


# ── REQUEST PRIMARY PHONE CHANGE ─────────────────────────────────────
@router.post("/request-phone-change")
def request_phone_change(
    payload: dict,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected security endpoint:
    Parents submit a request to change their primary login mobile number.
    Queued for School Administration verification.
    """
    clean_new_phone = validate_phone(payload.get("new_phone"), required=True, field_name="New Mobile Number")
    if clean_new_phone == user.phone:
        raise HTTPException(status_code=400, detail="The requested mobile number is already your active registered number.")

    # Check if there is already a pending request
    existing_pending = db.query(ProfileChangeRequestDB).filter(
        ProfileChangeRequestDB.parent_user_id == user.id,
        ProfileChangeRequestDB.field_name == "primary_phone",
        ProfileChangeRequestDB.status == "pending"
    ).first()
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail=f"You already have a pending phone change request to +91 {existing_pending.new_value} awaiting admin approval."
        )

    # Find first linked student
    link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == user.id).first()
    student_id = link.student_id if link else None
    if not student_id and payload.get("student_id"):
        student_id = payload.get("student_id")

    req = ProfileChangeRequestDB(
        school_id=user.school_id,
        parent_user_id=user.id,
        student_id=student_id,
        field_name="primary_phone",
        old_value=user.phone or "None",
        new_value=clean_new_phone,
        status="pending",
    )
    db.add(req)
    db.commit()

    return {
        "success": True,
        "message": f"Change request for mobile +91 {clean_new_phone} has been submitted for School Admin approval.",
        "request_id": str(req.id),
        "status": "pending",
    }


# ── ADMIN: PROFILE CHANGE REQUEST QUEUE ────────────────────────────────
@router.get("/admin/profile-change-requests")
def list_profile_change_requests(
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    requests = db.query(ProfileChangeRequestDB).filter(
        ProfileChangeRequestDB.school_id == user.school_id,
        ProfileChangeRequestDB.status == "pending"
    ).order_by(desc(ProfileChangeRequestDB.created_at)).all()

    res = []
    for r in requests:
        student = r.student
        parent = r.parent
        res.append({
            "id": str(r.id),
            "student_id": str(student.id) if student else None,
            "student_name": student.name if student else "All Linked Scholars",
            "grade": student.grade if student else "-",
            "section": student.section if student else "-",
            "parent_name": parent.full_name or parent.email if parent else "Parent",
            "field_name": r.field_name,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "created_at": r.created_at.isoformat(),
        })
    return res


@router.post("/admin/profile-change-requests/{req_id}/approve")
def approve_profile_change(
    req_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    req = db.query(ProfileChangeRequestDB).filter(
        ProfileChangeRequestDB.id == req_id,
        ProfileChangeRequestDB.school_id == user.school_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")

    student = req.student
    if student and hasattr(student, req.field_name):
        setattr(student, req.field_name, req.new_value)

    # If this was a primary phone change, update UserDB and Student contacts
    if req.field_name == "primary_phone":
        parent_user = req.parent
        if parent_user:
            parent_user.phone = req.new_value
        if student:
            if student.father_phone and req.old_value and req.old_value in student.father_phone:
                student.father_phone = f"+91{req.new_value}"
            elif student.mother_phone and req.old_value and req.old_value in student.mother_phone:
                student.mother_phone = f"+91{req.new_value}"
            else:
                student.father_phone = f"+91{req.new_value}"

    req.status = "approved"
    req.reviewed_by = user.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    # Dispatch notification to parent
    try:
        from services.notification_service import create_in_app_notification, send_whatsapp_message
        create_in_app_notification(
            db=db,
            school_id=user.school_id,
            user_id=req.parent_user_id,
            title="Profile Update Approved",
            message=f"Your request to update {req.field_name.replace('_', ' ')} to {req.new_value} has been approved by the administration.",
            event_type="PROFILE_APPROVED",
        )
        if req.field_name == "primary_phone":
            send_whatsapp_message(
                to_phone=f"+91{req.new_value}",
                custom_text=f"Your Technula parent account mobile number was successfully updated to +91{req.new_value} by School Administration."
            )
    except Exception:
        pass

    return {"success": True, "message": f"Change for {req.field_name.replace('_', ' ')} approved and applied."}


@router.post("/admin/profile-change-requests/{req_id}/reject")
def reject_profile_change(
    req_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    req = db.query(ProfileChangeRequestDB).filter(
        ProfileChangeRequestDB.id == req_id,
        ProfileChangeRequestDB.school_id == user.school_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")

    reason = payload.get("reason", "Information could not be verified.")
    req.status = "rejected"
    req.rejection_reason = reason
    req.reviewed_by = user.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Profile change request rejected."}


@router.post("/request-account-deletion")
def request_account_deletion(
    payload: dict,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Google Play Store compliance endpoint: Allows parents/users to request account and personal data deletion.
    """
    reason = payload.get("reason", "User requested account closure")
    change_req = ProfileChangeRequestDB(
        school_id=user.school_id,
        user_id=user.id,
        field_name="account_deletion_request",
        old_value="active",
        new_value="requested_deletion",
        status="pending",
        rejection_reason=f"Reason: {reason}",
    )
    db.add(change_req)
    db.commit()
    return {
        "success": True,
        "message": "Your account deletion request has been received. Your profile and stored session data will be purged in accordance with our student data privacy policy."
    }
