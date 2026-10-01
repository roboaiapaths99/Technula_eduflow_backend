"""
Attendance API — Daily class attendance marking, summary statistics, and student history.
Used by Teacher PWA and Parent App.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import date as dt_date, datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

import logging
from db.session import get_db
from models.attendance_db import AttendanceDB
from models.student_db import StudentDB
from models.school import SchoolDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from models.audit_log_db import AuditLogDB
from services.risk_engine import run_risk_evaluation
from services.notification_service import (
    create_in_app_notification,
    send_whatsapp_message,
    dispatch_multi_channel_notification,
)
from auth.dependencies import require_role, get_current_user

logger = logging.getLogger("api.attendance")

router = APIRouter(prefix="/attendance", tags=["Attendance"])


class AttendanceMarkItem(BaseModel):
    student_id: str
    status: str  # Present, Absent, Late, HalfDay
    reason: Optional[str] = None


class BatchAttendanceRequest(BaseModel):
    date: dt_date
    records: List[AttendanceMarkItem]


@router.post("/batch")
def mark_batch_attendance(
    req: BatchAttendanceRequest,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Mark attendance for an entire class/section on a given date and alert absentees."""
    school_id = str(user.school_id)  # SECURE: from JWT, not from request
    updated_count = 0
    created_count = 0

    for item in req.records:
        # Verify student belongs to the same school
        student_check = db.query(StudentDB).filter(
            StudentDB.id == item.student_id,
            StudentDB.school_id == school_id,
        ).first()
        if not student_check:
            continue  # Skip students not belonging to this school

        existing = (
            db.query(AttendanceDB)
            .filter(
                AttendanceDB.school_id == school_id,
                AttendanceDB.student_id == item.student_id,
                AttendanceDB.date == req.date,
            )
            .first()
        )
        if existing:
            existing.status = item.status
            existing.reason = item.reason
            existing.marked_by = user.id
            updated_count += 1
        else:
            new_att = AttendanceDB(
                school_id=school_id,
                student_id=item.student_id,
                date=req.date,
                status=item.status,
                reason=item.reason,
                marked_by=user.id,
            )
            db.add(new_att)
            created_count += 1

    db.commit()

    # Feature 1: Dispatch instant WhatsApp + In-App alerts for absent students
    alerts_dispatched = 0
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    school_name = school.name if school else "School"

    for item in req.records:
        if item.status and item.status.strip().lower() == "absent":
            student = db.query(StudentDB).filter(
                StudentDB.id == item.student_id,
                StudentDB.school_id == school_id,
            ).first()
            if student:
                parent_link = (
                    db.query(ParentStudentDB)
                    .filter(ParentStudentDB.student_id == student.id)
                    .first()
                )
                parent_user = (
                    db.query(UserDB).filter(UserDB.id == parent_link.parent_user_id).first()
                    if parent_link else None
                )
                parent_phone = (
                    student.father_phone
                    or student.mother_phone
                    or (parent_user.phone if parent_user else None)
                )
                parent_name = (
                    student.father_name
                    or student.mother_name
                    or (parent_user.full_name if parent_user else "Parent")
                )
                date_str = req.date.strftime("%d %b %Y") if hasattr(req.date, "strftime") else str(req.date)
                msg_text = (
                    f"Dear {parent_name}, your ward {student.name} (Class {student.grade}-{student.section}) "
                    f"was marked ABSENT today ({date_str}). If this is unexpected, please contact the school office immediately. — {school_name}"
                )

                if parent_link and parent_link.parent_user_id:
                    try:
                        dispatch_multi_channel_notification(
                            db=db,
                            school_id=school_id,
                            user_id=parent_link.parent_user_id,
                            title="⚠️ Attendance Alert: Absent Today",
                            message=msg_text,
                            event_type="ATTENDANCE_ABSENT",
                            phone=parent_phone,
                            email=parent_user.email if parent_user else None,
                            payload={
                                "student_id": str(student.id),
                                "student_name": student.name,
                                "date": str(req.date),
                                "screen": "attendance",
                                "type": "ATTENDANCE"
                            },
                        )
                        alerts_dispatched += 1
                    except Exception as e:
                        logger.warning(f"Failed to dispatch absentee notification: {e}")
                elif parent_phone:
                    try:
                        send_whatsapp_message(
                            to_phone=parent_phone,
                            custom_text=msg_text
                        )
                        alerts_dispatched += 1
                    except Exception as e:
                        logger.warning(f"Failed to dispatch absentee whatsapp: {e}")

        elif item.status and item.status.strip().lower() == "present":
            student = db.query(StudentDB).filter(
                StudentDB.id == item.student_id,
                StudentDB.school_id == school_id,
            ).first()
            if student:
                parent_link = (
                    db.query(ParentStudentDB)
                    .filter(ParentStudentDB.student_id == student.id)
                    .first()
                )
                parent_user = (
                    db.query(UserDB).filter(UserDB.id == parent_link.parent_user_id).first()
                    if parent_link else None
                )
                if parent_link and parent_link.parent_user_id:
                    try:
                        dispatch_multi_channel_notification(
                            db=db,
                            school_id=school_id,
                            user_id=parent_link.parent_user_id,
                            title="🏫 Campus Check-in: Marked Present",
                            message=f"{student.name} (Class {student.grade}-{student.section}) checked in and was marked Present on campus today.",
                            event_type="ATTENDANCE_PRESENT",
                            phone=student.father_phone or student.mother_phone or (parent_user.phone if parent_user else None),
                            email=parent_user.email if parent_user else None,
                            payload={
                                "student_id": str(student.id),
                                "student_name": student.name,
                                "date": str(req.date),
                                "screen": "attendance",
                                "type": "ATTENDANCE"
                            },
                        )
                    except Exception as e:
                        logger.warning(f"Failed to dispatch present notification: {e}")

    # Trigger automatic risk evaluation in background/sync for this school
    try:
        run_risk_evaluation(db, school_id=school_id)
    except Exception:
        pass

    # Dispatch real-time WebSocket attendance pulse
    try:
        from services.websocket_manager import manager
        manager.dispatch_sync(manager.broadcast_to_school(school_id, {
            "type": "attendance_updated",
            "date": req.date.isoformat(),
            "total_marked": len(req.records),
            "created": created_count,
            "updated": updated_count,
            "marked_by": str(user.id),
        }))
    except Exception:
        pass

    return {
        "status": "success",
        "date": req.date.isoformat(),
        "created": created_count,
        "updated": updated_count,
        "total_marked": len(req.records),
        "alerts_dispatched": alerts_dispatched,
    }


@router.get("/previous-session")
def get_previous_session_attendance(
    grade: str,
    section: str,
    before_date: Optional[dt_date] = None,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """
    Finds the most recent attendance session date strictly before `before_date`
    for the given school, grade, and section, and returns the status/reason for each student.
    """
    school_id = str(user.school_id)
    if not before_date:
        before_date = dt_date.today()

    students = (
        db.query(StudentDB)
        .filter(
            StudentDB.school_id == school_id,
            StudentDB.grade == grade,
            StudentDB.section == section,
            StudentDB.is_active == True,
        )
        .all()
    )
    if not students:
        return {"found": False, "session_date": None, "records": []}

    student_ids = [s.id for s in students]

    prev_date = (
        db.query(AttendanceDB.date)
        .filter(
            AttendanceDB.school_id == school_id,
            AttendanceDB.student_id.in_(student_ids),
            AttendanceDB.date < before_date,
        )
        .order_by(AttendanceDB.date.desc())
        .first()
    )

    if not prev_date:
        return {"found": False, "session_date": None, "records": []}

    target_date = prev_date[0]
    records = (
        db.query(AttendanceDB)
        .filter(
            AttendanceDB.school_id == school_id,
            AttendanceDB.student_id.in_(student_ids),
            AttendanceDB.date == target_date,
        )
        .all()
    )

    return {
        "found": True,
        "session_date": target_date.isoformat(),
        "records": [
            {
                "student_id": str(r.student_id),
                "status": r.status,
                "reason": r.reason,
            }
            for r in records
        ],
    }


@router.get("/class-session")
def get_class_attendance_sheet(
    grade: str,
    section: str,
    date: dt_date = Query(default_factory=dt_date.today),
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """
    Get student roster for a class with their attendance status on `date`.
    If no status marked yet, status defaults to null (ready for marking).
    """
    school_id = str(user.school_id)

    students = (
        db.query(StudentDB)
        .filter(
            StudentDB.school_id == school_id,
            StudentDB.grade == grade,
            StudentDB.section == section,
            StudentDB.is_active == True,
        )
        .order_by(StudentDB.roll_no, StudentDB.name)
        .all()
    )

    records = (
        db.query(AttendanceDB)
        .filter(
            AttendanceDB.school_id == school_id,
            AttendanceDB.date == date,
            AttendanceDB.student_id.in_([s.id for s in students]) if students else False,
        )
        .all()
    )
    status_by_student = {str(r.student_id): r for r in records}

    roster = []
    present_cnt = 0
    absent_cnt = 0

    for s in students:
        rec = status_by_student.get(str(s.id))
        st = rec.status if rec else None
        if st in ["Present", "present"]:
            present_cnt += 1
        elif st in ["Absent", "absent"]:
            absent_cnt += 1

        roster.append({
            "student_id": str(s.id),
            "name": s.name,
            "roll_no": s.roll_no,
            "admission_no": s.admission_no,
            "status": st,
            "reason": rec.reason if rec else None,
        })

    return {
        "grade": grade,
        "section": section,
        "date": date.isoformat(),
        "total_students": len(students),
        "present_count": present_cnt,
        "absent_count": absent_cnt,
        "is_marked": len(records) > 0,
        "students": roster,
    }


@router.get("/student/{student_id}")
def get_student_attendance(
    student_id: str,
    days: int = 60,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get attendance history and percentage for a student."""
    # Verify student access
    if user.role != "SuperAdmin":
        student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # For parents / students: check parent-student link or matching school
        if (user.role or "").strip().lower() in ["parent", "student"]:
            link = db.query(ParentStudentDB).filter(
                ParentStudentDB.parent_user_id == user.id,
                ParentStudentDB.student_id == student_id,
            ).first()
            if not link and user.school_id and str(student.school_id) != str(user.school_id):
                raise HTTPException(status_code=403, detail="You do not have access to this student's records")
        else:
            # For school staff: ensure student belongs to user's school
            if user.school_id and str(student.school_id) != str(user.school_id):
                raise HTTPException(status_code=403, detail="Student does not belong to your school")

    records = (
        db.query(AttendanceDB)
        .filter(AttendanceDB.student_id == student_id)
        .order_by(AttendanceDB.date.desc())
        .limit(days)
        .all()
    )

    total = len(records)
    present = sum(1 for r in records if r.status in ["Present", "present"])
    absent = sum(1 for r in records if r.status in ["Absent", "absent"])
    late = sum(1 for r in records if r.status in ["Late", "late"])
    percentage = round((present / total) * 100, 1) if total > 0 else None

    return {
        "student_id": student_id,
        "total_sessions": total,
        "present_count": present,
        "absent_count": absent,
        "late_count": late,
        "attendance_percentage": percentage,
        "history": [
            {
                "date": r.date.isoformat(),
                "status": r.status,
                "reason": r.reason,
            }
            for r in records
        ],
    }


@router.post("/student/{student_id}/send-warning")
def send_attendance_warning(
    student_id: str,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """
    Dispatches WhatsApp and in-app warning notification to the student's parents
    regarding low/critical attendance.
    """
    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.school_id == user.school_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    school = db.query(SchoolDB).filter(SchoolDB.id == student.school_id).first()
    school_name = school.name if school else "School Administration"

    # Compute overall percentage
    att_records = db.query(AttendanceDB).filter(AttendanceDB.student_id == student_id).all()
    total = len(att_records)
    present = sum(1 for r in att_records if r.status in ["Present", "present"])
    att_pct = round((present / total) * 100, 1) if total > 0 else 0.0

    parent_link = (
        db.query(ParentStudentDB)
        .filter(ParentStudentDB.student_id == student.id)
        .first()
    )
    parent_user = (
        db.query(UserDB).filter(UserDB.id == parent_link.parent_user_id).first()
        if parent_link else None
    )
    parent_phone = (
        student.father_phone
        or student.mother_phone
        or (parent_user.phone if parent_user else None)
    )
    parent_name = (
        student.father_name
        or student.mother_name
        or (parent_user.full_name if parent_user else "Parent/Guardian")
    )

    warning_msg = (
        f"Dear {parent_name}, this is an urgent notification from {school_name}. "
        f"{student.name}'s attendance has fallen to {att_pct}%, which is below the mandatory 75% CBSE requirement. "
        f"Please contact the principal's office."
    )

    dispatched = False
    if parent_phone:
        try:
            send_whatsapp_message(to_phone=parent_phone, custom_text=warning_msg)
            dispatched = True
        except Exception as e:
            logger.warning(f"Error sending warning whatsapp: {e}")

    if parent_link and parent_link.parent_user_id:
        try:
            create_in_app_notification(
                db=db,
                school_id=student.school_id,
                user_id=parent_link.parent_user_id,
                title="⚠️ Urgent: Attendance Warning",
                message=warning_msg,
                event_type="ATTENDANCE_WARNING",
                payload={"student_id": str(student.id), "attendance_percentage": att_pct}
            )
            dispatched = True
        except Exception as e:
            logger.warning(f"Error sending warning in-app: {e}")

    return {
        "status": "success",
        "message": f"Attendance warning notice dispatched for {student.name}",
        "attendance_percentage": att_pct,
        "recipient_phone": parent_phone,
    }


class AttendanceUpdateItem(BaseModel):
    status: str
    reason: Optional[str] = None


@router.put("/{attendance_id}", summary="Edit single attendance entry with audit log")
def update_attendance_record(
    attendance_id: str,
    req: AttendanceUpdateItem,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """Correct an existing attendance entry (status or reason) and track who changed it."""
    att = db.query(AttendanceDB).filter(
        AttendanceDB.id == attendance_id,
        AttendanceDB.school_id == user.school_id,
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    old_status = att.status
    old_reason = att.reason

    att.status = req.status
    att.reason = req.reason
    att.updated_by = user.id
    att.updated_at = datetime.now(timezone.utc)

    # Audit Trail
    audit = AuditLogDB(
        school_id=user.school_id,
        user_id=user.id,
        user_email=getattr(user, "email", None),
        action="attendance.update",
        resource_type="attendance",
        resource_id=str(att.id),
        details={
            "student_id": str(att.student_id),
            "date": att.date.isoformat(),
            "old_status": old_status,
            "new_status": req.status,
            "old_reason": old_reason,
            "new_reason": req.reason,
        }
    )
    db.add(audit)
    db.commit()

    return {
        "status": "success",
        "message": "Attendance record updated successfully",
        "id": str(att.id),
        "new_status": att.status,
    }


@router.delete("/{attendance_id}", summary="Delete single erroneous attendance record with audit log")
def delete_attendance_record(
    attendance_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin-only deletion of an invalid attendance entry with compliance audit log."""
    att = db.query(AttendanceDB).filter(
        AttendanceDB.id == attendance_id,
        AttendanceDB.school_id == user.school_id,
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    audit = AuditLogDB(
        school_id=user.school_id,
        user_id=user.id,
        user_email=getattr(user, "email", None),
        action="attendance.delete",
        resource_type="attendance",
        resource_id=str(att.id),
        details={
            "student_id": str(att.student_id),
            "date": att.date.isoformat(),
            "deleted_status": att.status,
        }
    )
    db.add(audit)
    db.delete(att)
    db.commit()

    return {"status": "success", "message": "Attendance record deleted successfully"}
