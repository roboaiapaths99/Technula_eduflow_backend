"""
Almanac API — School documents, handbooks, and policies with validity window enforcement.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.almanac_db import AlmanacDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/almanac", tags=["School Almanac"])


@router.post("/")
def create_almanac_doc(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    title = payload.get("title", "").strip()
    category = payload.get("category", "general")
    target_grade = payload.get("target_grade", "ALL")
    academic_year = payload.get("academic_year", "2025-26")
    file_url = payload.get("file_url") or ("/static/almanac/" + (payload.get("title", "handbook").replace(" ", "_").lower()) + ".pdf")
    file_size = payload.get("file_size", 1024)
    valid_from_str = payload.get("valid_from")
    valid_to_str = payload.get("valid_to")

    if not title or not valid_from_str or not valid_to_str:
        raise HTTPException(status_code=400, detail="Title, valid from, and valid to dates are required.")

    valid_from = datetime.strptime(valid_from_str, "%Y-%m-%d").date()
    valid_to = datetime.strptime(valid_to_str, "%Y-%m-%d").date()

    if valid_from > valid_to:
        raise HTTPException(status_code=400, detail="valid_from date cannot be after valid_to date.")

    doc = AlmanacDB(
        school_id=user.school_id,
        title=title,
        category=category,
        target_grade=target_grade,
        academic_year=academic_year,
        file_url=file_url,
        file_size=file_size,
        valid_from=valid_from,
        valid_to=valid_to,
        version=1,
        is_active=True,
        created_by=user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Dispatch notification to scoped parents
    st_query = db.query(StudentDB).filter(StudentDB.school_id == user.school_id, StudentDB.is_active == True)
    if target_grade != "ALL":
        st_query = st_query.filter(StudentDB.grade == target_grade)
    students = st_query.all()
    student_ids = [s.id for s in students]
    if student_ids:
        parent_links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id.in_(student_ids)).all()
        parent_user_ids = {pl.parent_user_id for pl in parent_links if pl.parent_user_id}
        alert_msg = f"ALMANAC DOCUMENT PUBLISHED: {title} ({category.replace('_', ' ').title()}). Available to view and download in School Almanac."
        for pid in parent_user_ids:
            dispatch_multi_channel_notification(
                db=db,
                school_id=user.school_id,
                user_id=pid,
                title="School Almanac Document Added",
                message=alert_msg,
                event_type="ALMANAC_PUBLISHED",
                payload={"doc_id": str(doc.id), "category": category},
            )

    return {"success": True, "id": str(doc.id), "document_id": str(doc.id), "message": "Document published to School Almanac."}


@router.put("/{doc_id}")
def update_almanac_doc(
    doc_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    doc = db.query(AlmanacDB).filter(AlmanacDB.id == doc_id, AlmanacDB.school_id == user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if "title" in payload: doc.title = payload["title"]
    if "category" in payload: doc.category = payload["category"]
    if "target_grade" in payload: doc.target_grade = payload["target_grade"]
    if "academic_year" in payload: doc.academic_year = payload["academic_year"]
    if "file_url" in payload:
        doc.file_url = payload["file_url"]
        doc.version += 1
    if "file_size" in payload: doc.file_size = payload["file_size"]
    if "valid_from" in payload: doc.valid_from = datetime.strptime(payload["valid_from"], "%Y-%m-%d").date()
    if "valid_to" in payload: doc.valid_to = datetime.strptime(payload["valid_to"], "%Y-%m-%d").date()
    if "is_active" in payload: doc.is_active = bool(payload["is_active"])

    db.commit()
    return {"success": True, "message": "Document updated.", "version": doc.version}


@router.delete("/{doc_id}")
def delete_almanac_doc(
    doc_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    doc = db.query(AlmanacDB).filter(AlmanacDB.id == doc_id, AlmanacDB.school_id == user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    # Soft-delete per specification
    doc.is_active = False
    db.commit()
    return {"success": True, "message": "Document soft-deleted (deactivated) from Almanac."}


# ── ALIAS FOR MOBILE APP: GET SCHOOL ALMANAC ───────────────────────────
@router.get("/school/{school_id}")
def get_school_almanac_alias(
    school_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    docs = db.query(AlmanacDB).filter(
        AlmanacDB.school_id == user.school_id,
        AlmanacDB.is_active == True,
        AlmanacDB.valid_from <= today,
        AlmanacDB.valid_to >= today
    ).order_by(desc(AlmanacDB.created_at)).all()

    res = []
    for d in docs:
        res.append({
            "id": str(d.id),
            "title": d.title,
            "category": d.category,
            "target_grade": d.target_grade,
            "academic_year": d.academic_year,
            "file_url": d.file_url,
            "file_size": d.file_size,
            "valid_from": d.valid_from.isoformat(),
            "valid_to": d.valid_to.isoformat(),
            "version": d.version,
            "created_at": d.created_at.isoformat(),
        })
    return res


@router.get("/admin")
def list_almanac_admin(
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    docs = db.query(AlmanacDB).filter(AlmanacDB.school_id == user.school_id).order_by(desc(AlmanacDB.created_at)).all()
    today = date.today()
    res = []
    for d in docs:
        if d.valid_from > today:
            validity_status = "upcoming"
        elif d.valid_to < today:
            validity_status = "expired"
        else:
            validity_status = "active"

        res.append({
            "id": str(d.id),
            "title": d.title,
            "category": d.category,
            "target_grade": d.target_grade,
            "academic_year": d.academic_year,
            "file_url": d.file_url,
            "file_size": d.file_size,
            "valid_from": d.valid_from.isoformat(),
            "valid_to": d.valid_to.isoformat(),
            "validity_status": validity_status,
            "version": d.version,
            "is_active": d.is_active,
            "created_at": d.created_at.isoformat(),
        })
    return res


@router.get("/parent")
def get_parent_almanac(
    student_id: Optional[str] = None,
    category: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    query = db.query(AlmanacDB).filter(
        AlmanacDB.school_id == user.school_id,
        AlmanacDB.is_active == True,
        AlmanacDB.valid_from <= today,
        AlmanacDB.valid_to >= today,
    )

    if category and category.lower() != "all":
        query = query.filter(AlmanacDB.category == category.lower())

    if student_id:
        student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
        if student:
            query = query.filter((AlmanacDB.target_grade == "ALL") | (AlmanacDB.target_grade == student.grade))

    docs = query.order_by(desc(AlmanacDB.valid_from)).all()
    return [{
        "id": str(d.id),
        "title": d.title,
        "category": d.category,
        "target_grade": d.target_grade,
        "academic_year": d.academic_year,
        "file_url": d.file_url,
        "file_size": d.file_size,
        "valid_from": d.valid_from.isoformat(),
        "valid_to": d.valid_to.isoformat(),
        "version": d.version,
    } for d in docs]
