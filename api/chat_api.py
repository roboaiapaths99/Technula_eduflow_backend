"""
Chat API — Parent ↔ Teacher 1:1 messaging.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc

from db.session import get_db
from models.chat_message_db import ChatMessageDB
from models.user_db import UserDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.parent_student_db import ParentStudentDB
from models.student_db import StudentDB
from auth.dependencies import get_current_user
from auth.plan_guard import require_feature
from core.sanitizer import sanitize_text

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    dependencies=[Depends(require_feature("chat_diary"))],
)


def _make_conversation_id(user_a: str, user_b: str) -> str:
    """Deterministic conversation ID from two user IDs."""
    return "_".join(sorted([str(user_a), str(user_b)]))


class SendMessageRequest(BaseModel):
    receiver_user_id: str
    message_type: str = "TEXT"
    content: Optional[str] = None
    media_url: Optional[str] = None
    media_filename: Optional[str] = None


@router.get("/contacts")
def get_chat_contacts(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of available chat contacts for the authenticated user."""
    user_id = str(user.id)
    school_id = str(user.school_id)
    contacts = []
    role = (user.role or "").lower()

    if role == "parent":
        links = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == user_id).all()
        student_ids = [str(l.student_id) for l in links]
        if not student_ids:
            return []

        students = db.query(StudentDB).filter(StudentDB.id.in_(student_ids)).all()
        class_keys = set()
        for s in students:
            class_keys.add((s.grade, s.section))

        teacher_ids = set()
        for grade, section in class_keys:
            assignments = (
                db.query(TeacherAssignmentDB)
                .filter(
                    TeacherAssignmentDB.school_id == school_id,
                    TeacherAssignmentDB.grade == grade,
                    TeacherAssignmentDB.section == section,
                )
                .all()
            )
            for a in assignments:
                teacher_ids.add(str(a.teacher_user_id))

        if not teacher_ids:
            teachers = db.query(UserDB).filter(
                UserDB.school_id == school_id,
                UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"])
            ).all()
            teacher_ids = {str(t.id) for t in teachers}

        teachers = db.query(UserDB).filter(UserDB.id.in_(list(teacher_ids))).all()
        for t in teachers:
            conv_id = _make_conversation_id(user_id, str(t.id))
            unread = db.query(func.count(ChatMessageDB.id)).filter(
                ChatMessageDB.conversation_id == conv_id,
                ChatMessageDB.receiver_user_id == user_id,
                ChatMessageDB.is_read == False,
            ).scalar()

            last_msg = db.query(ChatMessageDB).filter(
                ChatMessageDB.conversation_id == conv_id
            ).order_by(desc(ChatMessageDB.created_at)).first()

            contacts.append({
                "user_id": str(t.id),
                "full_name": t.full_name,
                "role": t.role,
                "email": t.email,
                "unread_count": unread or 0,
                "last_message": last_msg.content if last_msg else None,
                "last_message_time": last_msg.created_at.isoformat() if last_msg else None,
                "last_message_type": last_msg.message_type if last_msg else None,
            })

    elif "teacher" in role:
        assignments = (
            db.query(TeacherAssignmentDB)
            .filter(TeacherAssignmentDB.teacher_user_id == user_id)
            .all()
        )
        parent_ids = set()
        for a in assignments:
            students = db.query(StudentDB).filter(
                StudentDB.school_id == school_id,
                StudentDB.grade == a.grade,
                StudentDB.section == a.section,
            ).all()
            for s in students:
                links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id == s.id).all()
                for l in links:
                    parent_ids.add(str(l.parent_user_id))

        existing_convos = db.query(ChatMessageDB.sender_user_id).filter(
            ChatMessageDB.receiver_user_id == user_id
        ).distinct().all()
        for (sid,) in existing_convos:
            parent_ids.add(str(sid))

        parents = db.query(UserDB).filter(UserDB.id.in_(list(parent_ids))).all()
        for p in parents:
            conv_id = _make_conversation_id(user_id, str(p.id))
            unread = db.query(func.count(ChatMessageDB.id)).filter(
                ChatMessageDB.conversation_id == conv_id,
                ChatMessageDB.receiver_user_id == user_id,
                ChatMessageDB.is_read == False,
            ).scalar()

            last_msg = db.query(ChatMessageDB).filter(
                ChatMessageDB.conversation_id == conv_id
            ).order_by(desc(ChatMessageDB.created_at)).first()

            link = db.query(ParentStudentDB).filter(ParentStudentDB.parent_user_id == p.id).first()
            student_name = None
            if link:
                student = db.query(StudentDB).filter(StudentDB.id == link.student_id).first()
                student_name = student.name if student else None

            contacts.append({
                "user_id": str(p.id),
                "full_name": p.full_name,
                "role": p.role,
                "email": p.email,
                "student_name": student_name,
                "unread_count": unread or 0,
                "last_message": last_msg.content if last_msg else None,
                "last_message_time": last_msg.created_at.isoformat() if last_msg else None,
                "last_message_type": last_msg.message_type if last_msg else None,
            })

    contacts.sort(key=lambda c: c.get("last_message_time") or "", reverse=True)
    return contacts


@router.get("/messages")
def get_messages(
    conversation_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated messages for a conversation."""
    # Verify user is part of this conversation
    user_id = str(user.id)
    if user_id not in conversation_id and user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Access denied to this conversation")

    q = db.query(ChatMessageDB).filter(ChatMessageDB.conversation_id == conversation_id)
    if before:
        q = q.filter(ChatMessageDB.created_at < before)
    messages = q.order_by(desc(ChatMessageDB.created_at)).limit(limit).all()

    return [
        {
            "id": str(m.id),
            "sender_user_id": str(m.sender_user_id),
            "receiver_user_id": str(m.receiver_user_id),
            "message_type": m.message_type,
            "content": m.content,
            "media_url": m.media_url,
            "media_filename": m.media_filename,
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat(),
        }
        for m in reversed(messages)
    ]


@router.post("/send")
def send_message(
    payload: SendMessageRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message (text, image, voice, video, or file)."""
    school_id = str(user.school_id)  # SECURE: from JWT

    if payload.message_type == "TEXT" and not payload.content:
        raise HTTPException(status_code=400, detail="Text messages must have content")
    if payload.message_type != "TEXT" and not payload.media_url:
        raise HTTPException(status_code=400, detail="Media messages must have media_url")

    # Verify receiver is in the same school
    receiver = db.query(UserDB).filter(UserDB.id == payload.receiver_user_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    if user.role != "SuperAdmin" and str(receiver.school_id) != school_id:
        raise HTTPException(status_code=403, detail="Cannot message users from another school")

    clean_content = sanitize_text(payload.content) if payload.content else None
    conv_id = _make_conversation_id(str(user.id), str(payload.receiver_user_id))

    msg = ChatMessageDB(
        school_id=school_id,
        conversation_id=conv_id,
        sender_user_id=user.id,
        receiver_user_id=payload.receiver_user_id,
        message_type=payload.message_type,
        content=clean_content,
        media_url=payload.media_url,
        media_filename=payload.media_filename,
        is_read=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Real-time WebSocket dispatch to receiver and active conversation
    try:
        from services.websocket_manager import manager
        ws_event = {
            "type": "new_chat_message",
            "message": {
                "id": str(msg.id),
                "conversation_id": conv_id,
                "sender_user_id": str(msg.sender_user_id),
                "receiver_user_id": str(msg.receiver_user_id),
                "message_type": msg.message_type,
                "content": msg.content,
                "media_url": msg.media_url,
                "media_filename": msg.media_filename,
                "created_at": msg.created_at.isoformat(),
            }
        }
        manager.dispatch_sync(manager.send_to_user(str(payload.receiver_user_id), ws_event))
        manager.dispatch_sync(manager.broadcast_to_conversation(conv_id, ws_event))
    except Exception:
        pass

    return {
        "id": str(msg.id),
        "conversation_id": conv_id,
        "message_type": msg.message_type,
        "content": msg.content,
        "media_url": msg.media_url,
        "created_at": msg.created_at.isoformat(),
    }


@router.patch("/mark-read/{conversation_id}")
def mark_conversation_read(
    conversation_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all messages in a conversation as read for the authenticated user."""
    updated = (
        db.query(ChatMessageDB)
        .filter(
            ChatMessageDB.conversation_id == conversation_id,
            ChatMessageDB.receiver_user_id == user.id,
            ChatMessageDB.is_read == False,
        )
        .update({"is_read": True})
    )
    db.commit()
    return {"marked_read": updated}
