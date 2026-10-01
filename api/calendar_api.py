"""
School Calendar API — Holidays, Academic Events, Examinations, and Working Days Engine.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from models.school_calendar_db import SchoolCalendarEventDB
from auth.dependencies import require_role, get_current_user

router = APIRouter(prefix="/calendar", tags=["School Calendar & Holidays"])


@router.get("/events")
def list_calendar_events(
    year: Optional[int] = None,
    month: Optional[int] = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)
    query = db.query(SchoolCalendarEventDB).filter(SchoolCalendarEventDB.school_id == school_id)

    if year and month:
        start_m = date(year, month, 1)
        end_m = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        query = query.filter(SchoolCalendarEventDB.start_date >= start_m, SchoolCalendarEventDB.start_date < end_m)
    elif year:
        query = query.filter(SchoolCalendarEventDB.start_date >= date(year, 1, 1), SchoolCalendarEventDB.start_date <= date(year, 12, 31))

    events = query.order_by(SchoolCalendarEventDB.start_date.asc()).all()
    return [
        {
            "id": str(e.id),
            "title": e.title,
            "start_date": str(e.start_date),
            "end_date": str(e.end_date),
            "event_type": e.event_type,
            "is_holiday": e.is_holiday,
            "affects_attendance": e.affects_attendance,
            "target_grades": e.target_grades,
            "description": e.description or "",
        }
        for e in events
    ]


@router.post("/events")
def create_calendar_event(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)  # SECURE: from JWT
    title = payload.get("title")
    start_date_str = payload.get("start_date")
    end_date_str = payload.get("end_date") or start_date_str
    event_type = payload.get("event_type", "HOLIDAY")
    is_holiday = bool(payload.get("is_holiday", True))
    affects_attendance = bool(payload.get("affects_attendance", is_holiday))

    if not title or not start_date_str:
        raise HTTPException(status_code=400, detail="title and start_date are required")

    start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    event = SchoolCalendarEventDB(
        school_id=school_id,
        title=title,
        start_date=start_d,
        end_date=end_d,
        event_type=event_type,
        is_holiday=is_holiday,
        affects_attendance=affects_attendance,
        target_grades=payload.get("target_grades", "ALL"),
        description=payload.get("description"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"status": "ok", "id": str(event.id), "message": f"Calendar event '{title}' created"}


@router.put("/events/{event_id}")
def update_calendar_event(
    event_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Update a calendar event."""
    e = db.query(SchoolCalendarEventDB).filter(SchoolCalendarEventDB.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")

    if user.role != "SuperAdmin" and str(e.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if "title" in payload and payload["title"]:
        e.title = payload["title"].strip()
    if "date" in payload and payload["date"]:
        e.date = datetime.strptime(payload["date"], "%Y-%m-%d").date()
    if "event_type" in payload:
        e.event_type = payload["event_type"]
    if "description" in payload:
        e.description = payload.get("description")

    db.commit()
    return {"status": "ok", "message": f"Event '{e.title}' updated"}


@router.delete("/events/{event_id}")
def delete_calendar_event(
    event_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    e = db.query(SchoolCalendarEventDB).filter(SchoolCalendarEventDB.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")

    if user.role != "SuperAdmin" and str(e.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(e)
    db.commit()
    return {"status": "ok", "message": "Event deleted successfully"}


@router.get("/working-days")
def calculate_working_days(
    from_date: str,
    to_date: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Computes precision effective school working days between from_date and to_date."""
    school_id = str(user.school_id)
    start_d = datetime.strptime(from_date, "%Y-%m-%d").date()
    end_d = datetime.strptime(to_date, "%Y-%m-%d").date()

    if start_d > end_d:
        raise HTTPException(status_code=400, detail="from_date cannot be after to_date")

    holidays = db.query(SchoolCalendarEventDB).filter(
        SchoolCalendarEventDB.school_id == school_id,
        SchoolCalendarEventDB.affects_attendance == True,
        SchoolCalendarEventDB.start_date <= end_d,
        SchoolCalendarEventDB.end_date >= start_d,
    ).all()

    holiday_dates = set()
    for h in holidays:
        cur = max(h.start_date, start_d)
        end_cur = min(h.end_date, end_d)
        while cur <= end_cur:
            holiday_dates.add(cur)
            cur += timedelta(days=1)

    total_calendar_days = (end_d - start_d).days + 1
    sundays_count = 0
    working_days = 0
    cur_date = start_d

    while cur_date <= end_d:
        if cur_date.weekday() == 6:
            sundays_count += 1
        elif cur_date in holiday_dates:
            pass
        else:
            working_days += 1
        cur_date += timedelta(days=1)

    return {
        "from_date": str(start_d),
        "to_date": str(end_d),
        "total_calendar_days": total_calendar_days,
        "sundays": sundays_count,
        "school_holidays": len(holiday_dates),
        "effective_working_days": working_days,
    }
