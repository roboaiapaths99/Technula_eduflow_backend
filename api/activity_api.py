"""
Activity & Event Feed API — Campus happenings, celebrations, and timeline posts.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.activity_db import ActivityDB
from models.gallery_db import GalleryAlbumDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/activities", tags=["Activities & Events"])


@router.post("/")
def create_activity(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    title = payload.get("title", "").strip()
    description = payload.get("description", "").strip()
    event_date_str = payload.get("event_date")
    target_grade = payload.get("target_grade", "ALL")
    category = payload.get("category", "cultural")
    cover_image_url = payload.get("cover_image_url")
    linked_album_id = payload.get("linked_album_id")

    if not title or not description or not event_date_str:
        raise HTTPException(status_code=400, detail="Title, description, and event date are required.")

    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()

    activity = ActivityDB(
        school_id=user.school_id,
        title=title,
        description=description,
        event_date=event_date,
        target_grade=target_grade,
        category=category,
        cover_image_url=cover_image_url,
        linked_album_id=linked_album_id,
        is_published=True,
        created_by=user.id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    # Dispatch notification to parents
    st_query = db.query(StudentDB).filter(StudentDB.school_id == user.school_id, StudentDB.is_active == True)
    if target_grade != "ALL":
        st_query = st_query.filter(StudentDB.grade == target_grade)
    students = st_query.all()
    student_ids = [s.id for s in students]
    if student_ids:
        parent_links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id.in_(student_ids)).all()
        parent_user_ids = {pl.parent_user_id for pl in parent_links if pl.parent_user_id}
        alert_msg = f"NEW CAMPUS ACTIVITY: {title} ({event_date_str}). {description[:100]}..."
        for pid in parent_user_ids:
            dispatch_multi_channel_notification(
                db=db,
                school_id=user.school_id,
                user_id=pid,
                title="School Activity Update",
                message=alert_msg,
                event_type="ACTIVITY_PUBLISHED",
                payload={"activity_id": str(activity.id), "title": title},
            )

    return {"success": True, "id": str(activity.id), "activity_id": str(activity.id), "message": "Activity published to timeline."}


@router.get("/feed")
def get_activity_feed(
    student_id: Optional[str] = None,
    category: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ActivityDB).filter(
        ActivityDB.school_id == user.school_id,
        ActivityDB.is_published == True,
    )

    if category and category.lower() != "all":
        query = query.filter(ActivityDB.category == category.lower())

    if student_id:
        student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
        if student:
            query = query.filter((ActivityDB.target_grade == "ALL") | (ActivityDB.target_grade == student.grade))

    activities = query.order_by(desc(ActivityDB.event_date)).all()
    today = date.today()
    res = []
    for a in activities:
        album = a.linked_album
        res.append({
            "id": str(a.id),
            "title": a.title,
            "description": a.description,
            "event_date": a.event_date.isoformat(),
            "category": a.category,
            "target_grade": a.target_grade,
            "cover_image_url": a.cover_image_url or (album.cover_photo_url if album else None),
            "linked_album_id": str(a.linked_album_id) if a.linked_album_id else None,
            "album_title": album.title if album else None,
            "is_upcoming": a.event_date >= today,
            "created_at": a.created_at.isoformat(),
        })
    return res


@router.put("/{activity_id}")
def update_activity(
    activity_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    act = db.query(ActivityDB).filter(ActivityDB.id == activity_id, ActivityDB.school_id == user.school_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found.")

    if "title" in payload and payload["title"]:
        act.title = payload["title"].strip()
    if "description" in payload and payload["description"]:
        act.description = payload["description"].strip()
    if "event_date" in payload and payload["event_date"]:
        act.event_date = datetime.strptime(payload["event_date"], "%Y-%m-%d").date()
    if "target_grade" in payload:
        act.target_grade = payload["target_grade"]
    if "category" in payload:
        act.category = payload["category"]
    if "cover_image_url" in payload:
        act.cover_image_url = payload["cover_image_url"]
    if "linked_album_id" in payload:
        act.linked_album_id = payload["linked_album_id"] or None

    db.commit()
    return {"success": True, "message": "Activity updated successfully."}


@router.delete("/{activity_id}")
def delete_activity(
    activity_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    act = db.query(ActivityDB).filter(ActivityDB.id == activity_id, ActivityDB.school_id == user.school_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found.")
    db.delete(act)
    db.commit()
    return {"success": True, "message": "Activity removed."}


# ── ALIAS FOR MOBILE APP: GET SCHOOL ACTIVITIES ───────────────────────
@router.get("/school/{school_id}")
def get_school_activities_alias(
    school_id: str,
    category: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_activity_feed(student_id=None, category=category, user=user, db=db)
