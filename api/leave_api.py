"""
Leave Management API — Student and Staff digital leave requests.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.leave_request_db import LeaveRequestDB
from models.attendance_db import AttendanceDB
from models.student_db import StudentDB
from models.user_db import UserDB
from auth.dependencies import require_role, get_current_user

router = APIRouter(prefix="/leaves", tags=["Leave Management"])


@router.post("/apply")
def apply_leave(
    payload: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)  # SECURE: from JWT
    student_id = payload.get("student_id")
    from_date_str = payload.get("from_date")
    to_date_str = payload.get("to_date") or from_date_str
    leave_type = payload.get("leave_type", "SICK")
    reason = payload.get("reason", "")
    attachment_url = payload.get("attachment_url")

    if not from_date_str or not reason:
        raise HTTPException(status_code=400, detail="from_date and reason are required")

    # Verify student belongs to same school if student_id provided
    if student_id:
        student = db.query(StudentDB).filter(
            StudentDB.id == student_id,
            StudentDB.school_id == school_id,
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

    from_d = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    to_d = datetime.strptime(to_date_str, "%Y-%m-%d").date()

    if from_d > to_d:
        raise HTTPException(status_code=400, detail="from_date cannot be after to_date")

    leave = LeaveRequestDB(
        school_id=school_id,
        student_id=student_id,
        user_id=user.id,
        from_date=from_d,
        to_date=to_d,
        leave_type=leave_type,
        reason=reason,
        attachment_url=attachment_url,
        status="PENDING",
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)

    return {
        "status": "ok",
        "leave_id": str(leave.id),
        "message": "Leave application submitted successfully. Awaiting class teacher approval."
    }


@router.get("/pending")
def list_pending_leaves(
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)

    leaves = db.query(LeaveRequestDB).filter(
        LeaveRequestDB.school_id == school_id,
        LeaveRequestDB.status == "PENDING"
    ).order_by(LeaveRequestDB.created_at.desc()).all()

    results = []
    for l in leaves:
        student = db.query(StudentDB).filter(StudentDB.id == l.student_id).first() if l.student_id else None
        applicant = db.query(UserDB).filter(UserDB.id == l.user_id).first()
        results.append({
            "id": str(l.id),
            "student_id": str(l.student_id) if l.student_id else None,
            "student_name": student.name if student else (applicant.full_name if applicant else "Staff"),
            "grade": student.grade if student else "",
            "section": student.section if student else "",
            "from_date": str(l.from_date),
            "to_date": str(l.to_date),
            "days_count": (l.to_date - l.from_date).days + 1,
            "leave_type": l.leave_type,
            "reason": l.reason,
            "attachment_url": l.attachment_url,
            "status": l.status,
            "applied_at": str(l.created_at),
        })

    return results


@router.get("/student/{student_id}")
def get_student_leaves(
    student_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify student belongs to user's school
    if user.role != "SuperAdmin":
        student = db.query(StudentDB).filter(
            StudentDB.id == student_id,
            StudentDB.school_id == user.school_id,
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

    leaves = db.query(LeaveRequestDB).filter(
        LeaveRequestDB.student_id == student_id
    ).order_by(LeaveRequestDB.created_at.desc()).all()

    return [
        {
            "id": str(l.id),
            "from_date": str(l.from_date),
            "to_date": str(l.to_date),
            "days_count": (l.to_date - l.from_date).days + 1,
            "leave_type": l.leave_type,
            "reason": l.reason,
            "attachment_url": l.attachment_url,
            "status": l.status,
            "admin_remarks": l.admin_remarks,
            "reviewed_at": str(l.reviewed_at) if l.reviewed_at else None,
        }
        for l in leaves
    ]


@router.patch("/{leave_id}/review")
def review_leave(
    leave_id: str,
    payload: dict,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """Approves or Rejects a leave request."""
    status = payload.get("status")
    remarks = payload.get("remarks")

    if status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="status must be APPROVED or REJECTED")

    leave = db.query(LeaveRequestDB).filter(LeaveRequestDB.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    # Verify leave belongs to user's school
    if user.role != "SuperAdmin" and str(leave.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    leave.status = status
    leave.admin_remarks = remarks
    leave.reviewed_by = user.id
    leave.reviewed_at = datetime.now(timezone.utc)

    # Automatic Attendance Register Sync
    if status == "APPROVED" and leave.student_id:
        cur_date = leave.from_date
        while cur_date <= leave.to_date:
            att = db.query(AttendanceDB).filter(
                AttendanceDB.school_id == leave.school_id,
                AttendanceDB.student_id == leave.student_id,
                AttendanceDB.date == cur_date,
            ).first()

            if att:
                att.status = "Approved Leave"
                att.reason = f"Leave Approved: {leave.leave_type} ({remarks or leave.reason})"
            else:
                new_att = AttendanceDB(
                    school_id=leave.school_id,
                    student_id=leave.student_id,
                    date=cur_date,
                    status="Approved Leave",
                    reason=f"Leave Approved: {leave.leave_type}",
                    marked_by=user.id,
                )
                db.add(new_att)

            cur_date += timedelta(days=1)

    db.commit()
    db.refresh(leave)

    # Dispatch notification to parent honoring multi-channel preferences
    try:
        from services.notification_service import dispatch_multi_channel_notification
        student = leave.student
        student_name = student.name if student else "your child"
        title = f"Leave Request {status.title()}"
        msg = f"Leave application for {student_name} ({leave.from_date} to {leave.to_date}) has been {status}."
        if remarks:
            msg += f" Remarks: {remarks}"
        dispatch_multi_channel_notification(
            db=db,
            school_id=str(leave.school_id),
            user_id=str(leave.parent_user_id),
            title=title,
            message=msg,
            event_type=f"LEAVE_{status}",
            payload={"leave_id": str(leave.id), "status": status}
        )
    except Exception as e:
        pass

    return {
        "status": "ok",
        "leave_id": str(leave.id),
        "new_status": leave.status,
        "message": f"Leave has been marked as {status} and attendance synced."
    }
