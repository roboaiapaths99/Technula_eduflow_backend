"""
Parent Complaints & Service Ticket API.
Handles ticket creation by parents, status tracking, admin/teacher assignment, and SLA resolution.
SECURED: All endpoints require auth and derive school_id from JWT user context.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from models.ticket_db import TicketDB
from models.user_db import UserDB
from models.student_db import StudentDB
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _get_effective_school_id(user: UserDB, school_id_override: Optional[str] = None) -> str:
    if (user.role or "").strip() == "SuperAdmin" and school_id_override:
        return school_id_override
    if not user.school_id:
        raise HTTPException(status_code=403, detail="User is not assigned to any school")
    return str(user.school_id)


class CreateTicketRequest(BaseModel):
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    school_id: Optional[str] = None
    parent_user_id: Optional[str] = None
    parent_name: Optional[str] = None
    parent_email: Optional[str] = None
    category: str = "ACADEMIC"
    subject: str = "Query"
    description: str = ""
    priority: Optional[str] = "NORMAL"

    class Config:
        extra = "ignore"


class UpdateTicketRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None

    class Config:
        extra = "ignore"


@router.post("")
@router.post("/")
def create_ticket(
    req: CreateTicketRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)

    clean_student_id = req.student_id.strip() if req.student_id and req.student_id.strip() else None
    if clean_student_id:
        student = db.query(StudentDB).filter(
            StudentDB.id == clean_student_id,
            StudentDB.school_id == target_school_id
        ).first()
        if not student:
            clean_student_id = None

    ticket = TicketDB(
        school_id=target_school_id,
        parent_user_id=current_user.id,
        student_id=clean_student_id,
        category=req.category or "ACADEMIC",
        subject=req.subject or "Support Query",
        description=req.description or "",
        priority=req.priority or "NORMAL",
        status="OPEN",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return {
        "status": "success",
        "ticket_id": str(ticket.id),
        "message": "Ticket created successfully. Our team will review shortly.",
    }


@router.get("")
@router.get("/")
def list_tickets(
    school_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_school_id = _get_effective_school_id(current_user, school_id)
    query = db.query(TicketDB).filter(TicketDB.school_id == target_school_id)

    # If parent, restrict to own tickets
    if (current_user.role or "").lower() == "parent":
        query = query.filter(TicketDB.parent_user_id == current_user.id)

    if status:
        query = query.filter(TicketDB.status == status)
    if category:
        query = query.filter(TicketDB.category == category)

    tickets = query.order_by(TicketDB.created_at.desc()).all()

    result = []
    for t in tickets:
        student = db.query(StudentDB).filter(StudentDB.id == t.student_id).first() if t.student_id else None
        parent = db.query(UserDB).filter(UserDB.id == t.parent_user_id).first()
        result.append({
            "id": str(t.id),
            "school_id": str(t.school_id),
            "parent_name": parent.full_name if parent else "Parent",
            "parent_email": parent.email if parent else None,
            "student_name": student.name if student else "All Students",
            "category": t.category,
            "subject": t.subject,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "resolution_notes": t.resolution_notes,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        })
    return result


@router.patch("/{ticket_id}")
def update_ticket(
    ticket_id: str,
    req: UpdateTicketRequest,
    current_user: UserDB = Depends(require_role(["Admin", "Teacher"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    ticket = db.query(TicketDB).filter(
        TicketDB.id == ticket_id,
        TicketDB.school_id == target_school_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found in your school")

    if req.status:
        ticket.status = req.status
        if req.status in ["RESOLVED", "CLOSED"]:
            ticket.resolved_at = datetime.now(timezone.utc)
    if req.priority:
        ticket.priority = req.priority
    if req.assigned_to:
        ticket.assigned_to = req.assigned_to
    if req.resolution_notes:
        ticket.resolution_notes = req.resolution_notes

    db.commit()
    return {"status": "success", "message": "Ticket updated successfully"}
