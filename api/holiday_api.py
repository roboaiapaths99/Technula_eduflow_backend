"""
Holiday Management API — School holiday calendar & upcoming countdown.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.holiday_db import HolidayDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.post("/")
def create_holiday(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    name = (payload.get("name") or payload.get("title") or "").strip()
    start_str = payload.get("start_date")
    end_str = payload.get("end_date") or start_str
    holiday_type = (payload.get("holiday_type") or payload.get("category") or "festival").lower()
    description = payload.get("description")

    if not name or not start_str:
        raise HTTPException(status_code=400, detail="Holiday name and start date are required.")

    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date.")

    h = HolidayDB(
        school_id=user.school_id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        holiday_type=holiday_type,
        description=description,
    )
    db.add(h)
    db.commit()
    db.refresh(h)

    # Dispatch notification to parents of school
    parents = db.query(UserDB).filter(UserDB.school_id == user.school_id, UserDB.role == "Parent").all()
    duration = f"{start_str} to {end_str}" if start_str != end_str else start_str
    alert_msg = f"SCHOOL HOLIDAY NOTIFICATION: {name} ({duration}). Enjoy the celebration and family break!"
    for p in parents:
        dispatch_multi_channel_notification(
            db=db,
            school_id=user.school_id,
            user_id=p.id,
            title="School Holiday Announced",
            message=alert_msg,
            event_type="HOLIDAY_PUBLISHED",
            payload={"holiday_id": str(h.id), "name": name, "start_date": start_str},
        )

    return {"success": True, "message": f"Holiday '{name}' added.", "id": str(h.id), "holiday_id": str(h.id)}


@router.put("/{holiday_id}")
def update_holiday(
    holiday_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    h = db.query(HolidayDB).filter(HolidayDB.id == holiday_id, HolidayDB.school_id == user.school_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Holiday not found.")

    new_name = payload.get("name") or payload.get("title")
    if new_name:
        h.name = new_name.strip()
    if "start_date" in payload and payload["start_date"]:
        h.start_date = datetime.strptime(payload["start_date"], "%Y-%m-%d").date()
    if "end_date" in payload and payload["end_date"]:
        h.end_date = datetime.strptime(payload["end_date"], "%Y-%m-%d").date()
    new_type = payload.get("holiday_type") or payload.get("category")
    if new_type:
        h.holiday_type = new_type.lower()
    if "description" in payload:
        h.description = payload["description"]

    if h.start_date > h.end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date.")

    db.commit()
    return {"success": True, "message": f"Holiday '{h.name}' updated."}


@router.get("/")
def get_holidays(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    holidays = db.query(HolidayDB).filter(HolidayDB.school_id == user.school_id).order_by(HolidayDB.start_date).all()
    today = date.today()
    res = []
    for h in holidays:
        duration_days = (h.end_date - h.start_date).days + 1
        days_until = (h.start_date - today).days
        res.append({
            "id": str(h.id),
            "name": h.name,
            "start_date": h.start_date.isoformat(),
            "end_date": h.end_date.isoformat(),
            "holiday_type": h.holiday_type,
            "description": h.description,
            "duration_days": duration_days,
            "days_until": days_until,
            "is_past": h.end_date < today,
            "is_today": h.start_date <= today <= h.end_date,
        })
    return res


@router.get("/upcoming")
def get_upcoming_holiday(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    next_h = db.query(HolidayDB).filter(
        HolidayDB.school_id == user.school_id,
        HolidayDB.end_date >= today
    ).order_by(HolidayDB.start_date).first()

    if not next_h:
        return {"has_upcoming": False}

    days_left = (next_h.start_date - today).days
    return {
        "has_upcoming": True,
        "id": str(next_h.id),
        "name": next_h.name,
        "start_date": next_h.start_date.isoformat(),
        "end_date": next_h.end_date.isoformat(),
        "holiday_type": next_h.holiday_type,
        "description": next_h.description,
        "days_left": max(0, days_left),
        "is_active_now": next_h.start_date <= today <= next_h.end_date,
    }


@router.delete("/{holiday_id}")
def delete_holiday(
    holiday_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    h = db.query(HolidayDB).filter(HolidayDB.id == holiday_id, HolidayDB.school_id == user.school_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Holiday not found.")
    db.delete(h)
    db.commit()
    return {"success": True, "message": "Holiday deleted."}


# ── ALIAS FOR MOBILE APP: GET SCHOOL HOLIDAYS ──────────────────────────
@router.get("/school/{school_id}")
def get_school_holidays_alias(
    school_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    holidays_list = get_holidays(user=user, db=db)
    next_h = get_upcoming_holiday(user=user, db=db)
    next_info = None
    if next_h.get("has_upcoming"):
        next_info = {
            "title": next_h.get("name"),
            **next_h,
        }
    return {
        "holidays": holidays_list,
        "next_holiday": next_info,
    }
