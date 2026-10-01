"""
Announcement API — School-wide broadcast system.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.announcement_db import AnnouncementDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from services.notification_service import (
    create_in_app_notification,
    send_whatsapp_message,
    send_email,
    dispatch_multi_channel_notification,
)
from auth.dependencies import require_role, get_current_user
from core.sanitizer import sanitize_text

router = APIRouter(prefix="/announcements", tags=["Announcements"])


class CreateAnnouncementRequest(BaseModel):
    title: str
    content: str
    target_role: Optional[str] = "ALL"
    target_grade: Optional[str] = None
    send_whatsapp: Optional[bool] = False
    send_email: Optional[bool] = False
    send_push: Optional[bool] = False
    is_pinned: Optional[bool] = False


@router.post("/")
def create_announcement(
    req: CreateAnnouncementRequest,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Create school announcement and broadcast across requested channels."""
    school_id = str(user.school_id)  # SECURE: from JWT

    clean_title = sanitize_text(req.title) or ""
    clean_content = sanitize_text(req.content) or ""

    announcement = AnnouncementDB(
        school_id=school_id,
        author_id=user.id,
        title=clean_title,
        content=clean_content,
        target_role=req.target_role or "ALL",
        target_grade=req.target_grade,
        send_whatsapp=bool(req.send_whatsapp),
        send_email=bool(req.send_email),
        send_push=bool(req.send_push),
        is_pinned=bool(req.is_pinned),
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)

    # Find recipients for broadcast
    user_query = db.query(UserDB).filter(UserDB.school_id == school_id, UserDB.is_active == True)
    if req.target_role == "PARENTS":
        user_query = user_query.filter(UserDB.role == "Parent")
    elif req.target_role == "TEACHERS":
        user_query = user_query.filter(UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]))

    recipients_dict = {str(u.id): u for u in user_query.all()}

    # Also include any parent linked to active students in this school
    if req.target_role in ["ALL", "PARENTS"]:
        linked_parents = (
            db.query(UserDB)
            .join(ParentStudentDB, ParentStudentDB.parent_user_id == UserDB.id)
            .join(StudentDB, StudentDB.id == ParentStudentDB.student_id)
            .filter(StudentDB.school_id == school_id, UserDB.is_active == True)
            .all()
        )
        for p in linked_parents:
            recipients_dict[str(p.id)] = p

    recipients = list(recipients_dict.values())

    for u in recipients:
        dispatch_multi_channel_notification(
            db=db,
            school_id=school_id,
            user_id=u.id,
            title=f"📢 {req.title}",
            message=req.content,
            event_type="ANNOUNCEMENT",
            phone=u.phone,
            email=u.email,
            payload={
                "announcement_id": str(announcement.id),
                "screen": "notices",
                "type": "ANNOUNCEMENT",
            },
            override_whatsapp=bool(req.send_whatsapp),
            override_email=bool(req.send_email),
        )

    return {
        "status": "success",
        "announcement_id": str(announcement.id),
        "recipients_targeted": len(recipients),
        "message": f"Announcement published to {len(recipients)} users.",
    }


@router.get("/")
def list_announcements(
    target_role: Optional[str] = None,
    school_id: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List announcements for user's school."""
    effective_school_id = school_id or user.school_id
    if not effective_school_id and user.role == "Parent":
        linked = (
            db.query(StudentDB.school_id)
            .join(ParentStudentDB, ParentStudentDB.student_id == StudentDB.id)
            .filter(ParentStudentDB.parent_user_id == user.id)
            .first()
        )
        if linked:
            effective_school_id = linked[0]

    if not effective_school_id:
        return []

    query = db.query(AnnouncementDB).filter(AnnouncementDB.school_id == str(effective_school_id))

    if target_role:
        query = query.filter(AnnouncementDB.target_role.in_(["ALL", target_role]))

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(AnnouncementDB.title.ilike(s) | AnnouncementDB.content.ilike(s))

    total = query.count()
    if page is not None:
        eff_limit = limit or 20
        offset = (page - 1) * eff_limit
        items = query.order_by(AnnouncementDB.is_pinned.desc(), AnnouncementDB.created_at.desc()).offset(offset).limit(eff_limit).all()
    else:
        items = query.order_by(AnnouncementDB.is_pinned.desc(), AnnouncementDB.created_at.desc()).all()

    res = [
        {
            "id": str(a.id),
            "school_id": str(a.school_id),
            "title": a.title,
            "content": a.content,
            "target_role": a.target_role,
            "target_grade": a.target_grade,
            "is_pinned": a.is_pinned,
            "send_whatsapp": a.send_whatsapp,
            "send_email": a.send_email,
            "send_push": a.send_push,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]

    if page is not None:
        eff_limit = limit or 20
        return {
            "items": res,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    return res


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Update an announcement."""
    ann = db.query(AnnouncementDB).filter(AnnouncementDB.id == announcement_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if user.role != "SuperAdmin" and str(ann.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if "title" in payload and payload["title"]:
        ann.title = sanitize_text(payload["title"]) or ""
    if "content" in payload:
        ann.content = sanitize_text(payload.get("content")) or ""
    if "target_role" in payload:
        ann.target_role = payload["target_role"]
    if "is_pinned" in payload:
        ann.is_pinned = payload["is_pinned"]

    db.commit()
    return {"status": "ok", "message": f"Announcement '{ann.title}' updated"}


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Delete an announcement."""
    ann = db.query(AnnouncementDB).filter(AnnouncementDB.id == announcement_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if user.role != "SuperAdmin" and str(ann.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(ann)
    db.commit()
    return {"status": "ok", "message": f"Announcement deleted"}


@router.post("/{announcement_id}/broadcast")
def broadcast_announcement_whatsapp(
    announcement_id: str,
    payload: Optional[dict] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Bulk WhatsApp broadcast from Admin."""
    ann = db.query(AnnouncementDB).filter(AnnouncementDB.id == announcement_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if user.role != "SuperAdmin" and str(ann.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    target_grade = ann.target_grade

    student_query = db.query(StudentDB).filter(
        StudentDB.school_id == ann.school_id,
        StudentDB.is_active == True,
    )
    if target_grade:
        student_query = student_query.filter(StudentDB.grade == target_grade)
    students = student_query.all()

    phones = set()
    for s in students:
        if s.father_phone and len(s.father_phone.strip()) >= 8:
            phones.add(s.father_phone.strip())
        if s.mother_phone and len(s.mother_phone.strip()) >= 8:
            phones.add(s.mother_phone.strip())

    parent_users = (
        db.query(UserDB)
        .filter(
            UserDB.school_id == ann.school_id,
            UserDB.role == "Parent",
            UserDB.is_active == True,
        )
        .all()
    )
    for p in parent_users:
        if p.phone and len(p.phone.strip()) >= 8:
            phones.add(p.phone.strip())

    msg_text = f"📢 *Official School Circular: {ann.title}*\n\n{ann.content}\n\n— School Administration"

    delivered = 0
    failed = 0
    for phone in phones:
        try:
            success = send_whatsapp_message(to_phone=phone, custom_text=msg_text)
            if success:
                delivered += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    ann.send_whatsapp = True
    db.commit()

    return {
        "status": "success",
        "announcement_id": str(ann.id),
        "title": ann.title,
        "total_targets": len(phones),
        "delivered": delivered,
        "failed": failed,
        "message": f"Broadcast dispatched to {delivered} parents via WhatsApp.",
    }
