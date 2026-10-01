"""
Parent-Teacher Conference (PTC) Scheduling System.
- Admin creates conference events (e.g. "Term 2 Board Review PTM").
- System auto-generates 15-minute appointment slots for teachers.
- Parents self-book 1-on-1 slots with student's class/subject teachers.
- Teachers view consolidated meeting schedules with parent agenda topics.
SECURED: All endpoints require auth and derive school_id from JWT user context.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.user_db import UserDB
from models.student_db import StudentDB
from models.ptc_db import PTCEventDB, PTCSlotDB, PTCBookingDB
from models.parent_student_db import ParentStudentDB
from auth.dependencies import get_current_user, require_role
from auth.plan_guard import require_feature

router = APIRouter(
    prefix="/ptc",
    tags=["Parent-Teacher Conferences"],
    dependencies=[Depends(require_feature("ptc"))],
)


def _get_effective_school_id(user: UserDB, school_id_override: Optional[str] = None) -> str:
    if (user.role or "").strip() == "SuperAdmin" and school_id_override:
        return school_id_override
    if not user.school_id:
        raise HTTPException(status_code=403, detail="User is not assigned to any school")
    return str(user.school_id)


@router.post("/events")
def create_ptc_event(
    payload: dict,
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, payload.get("school_id"))
    title = payload.get("title", "Term 2 Parent-Teacher Conference")
    description = payload.get("description", "1-on-1 Academic Review & Board Readiness Discussion")
    event_date_str = payload.get("event_date")
    start_time_str = payload.get("start_time", "09:00")
    end_time_str = payload.get("end_time", "12:00")
    slot_duration = int(payload.get("slot_duration_mins", 15))
    grade = payload.get("grade")
    teacher_ids = payload.get("teacher_ids", [])

    if not event_date_str:
        raise HTTPException(status_code=400, detail="event_date is required")

    event_d = datetime.strptime(event_date_str, "%Y-%m-%d").date()

    event = PTCEventDB(
        school_id=target_school_id,
        title=title,
        description=description,
        event_date=event_d,
        start_time=start_time_str,
        end_time=end_time_str,
        slot_duration_mins=slot_duration,
        grade=grade,
        is_active=True
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    if not teacher_ids:
        teachers = db.query(UserDB).filter(
            UserDB.school_id == target_school_id,
            UserDB.role.in_(["ClassTeacher", "SubjectTeacher", "TEACHER", "Teacher"])
        ).all()
        teacher_ids = [str(t.id) for t in teachers]

    start_dt = datetime.strptime(start_time_str, "%H:%M")
    end_dt = datetime.strptime(end_time_str, "%H:%M")

    slots_created = 0
    for t_id in teacher_ids:
        curr = start_dt
        while curr + timedelta(minutes=slot_duration) <= end_dt:
            slot_end = curr + timedelta(minutes=slot_duration)
            s_slot = PTCSlotDB(
                event_id=event.id,
                teacher_id=t_id,
                start_time=curr.strftime("%H:%M"),
                end_time=slot_end.strftime("%H:%M"),
                is_booked=False,
                room_or_link=payload.get("room_or_link", "Academic Block - Room 102")
            )
            db.add(s_slot)
            slots_created += 1
            curr = slot_end

    db.commit()

    return {
        "status": "ok",
        "event_id": event.id,
        "slots_created": slots_created,
        "message": f"PTC Event '{title}' created with {slots_created} self-booking slots."
    }


@router.get("/events")
def list_ptc_events(
    school_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, school_id)
    rows = db.query(PTCEventDB).filter(
        PTCEventDB.school_id == target_school_id,
        PTCEventDB.is_active == True
    ).order_by(PTCEventDB.event_date.asc()).all()

    return [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "event_date": str(r.event_date),
            "start_time": r.start_time,
            "end_time": r.end_time,
            "slot_duration_mins": r.slot_duration_mins,
            "grade": r.grade or "All Classes",
        }
        for r in rows
    ]


@router.get("/slots")
def get_available_ptc_slots(
    event_id: str,
    teacher_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    event = db.query(PTCEventDB).filter(
        PTCEventDB.id == event_id,
        PTCEventDB.school_id == target_school_id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="PTC Event not found in your school")

    query = db.query(PTCSlotDB).filter(PTCSlotDB.event_id == event_id)
    if teacher_id:
        query = query.filter(PTCSlotDB.teacher_id == teacher_id)

    slots = query.order_by(PTCSlotDB.start_time.asc()).all()
    results = []
    for s in slots:
        t = db.query(UserDB).filter(UserDB.id == s.teacher_id).first()
        results.append({
            "slot_id": s.id,
            "event_id": s.event_id,
            "teacher_id": s.teacher_id,
            "teacher_name": t.full_name if t else "Educator",
            "start_time": s.start_time,
            "end_time": s.end_time,
            "is_booked": s.is_booked,
            "room_or_link": s.room_or_link
        })
    return results


@router.post("/book")
def book_ptc_slot(
    payload: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    slot_id = payload.get("slot_id")
    student_id = payload.get("student_id")
    agenda_topic = payload.get("agenda_topic", "General Academic & Board Progress")

    if not slot_id or not student_id:
        raise HTTPException(status_code=400, detail="slot_id and student_id are required")

    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.school_id == target_school_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school")

    # If parent, verify link
    if (current_user.role or "").lower() == "parent":
        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student_id,
            ParentStudentDB.is_verified == True
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Access denied: You are not authorized for this student")

    slot = db.query(PTCSlotDB).filter(PTCSlotDB.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if slot.is_booked:
        raise HTTPException(status_code=409, detail="This slot has already been booked by another parent. Please choose another slot.")

    existing = db.query(PTCBookingDB).filter(
        PTCBookingDB.event_id == slot.event_id,
        PTCBookingDB.student_id == student_id,
        PTCBookingDB.status == "CONFIRMED"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You already have a confirmed slot for this conference.")

    slot.is_booked = True

    booking = PTCBookingDB(
        slot_id=slot_id,
        event_id=slot.event_id,
        student_id=student_id,
        parent_user_id=current_user.id,
        agenda_topic=agenda_topic,
        status="CONFIRMED"
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    teacher = db.query(UserDB).filter(UserDB.id == slot.teacher_id).first()

    return {
        "status": "ok",
        "booking_id": booking.id,
        "appointment_time": f"{slot.start_time} - {slot.end_time}",
        "teacher_name": teacher.full_name if teacher else "Educator",
        "room": slot.room_or_link,
        "message": f"Appointment confirmed with {teacher.full_name if teacher else 'Teacher'} at {slot.start_time}."
    }


@router.get("/parent")
@router.get("/parent/{parent_user_id}")
def get_parent_ptc_appointments(
    parent_user_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_user_id = current_user.id
    if (current_user.role or "").strip() == "SuperAdmin" and parent_user_id:
        target_user_id = parent_user_id

    bookings = db.query(PTCBookingDB).filter(
        PTCBookingDB.parent_user_id == target_user_id,
        PTCBookingDB.status == "CONFIRMED"
    ).all()

    results = []
    for b in bookings:
        slot = db.query(PTCSlotDB).filter(PTCSlotDB.id == b.slot_id).first()
        event = db.query(PTCEventDB).filter(PTCEventDB.id == b.event_id).first()
        student = db.query(StudentDB).filter(StudentDB.id == b.student_id).first()
        teacher = db.query(UserDB).filter(UserDB.id == slot.teacher_id).first() if slot else None

        results.append({
            "booking_id": b.id,
            "id": b.id,
            "event_title": event.title if event else "Parent-Teacher Meeting",
            "event_date": str(event.event_date) if event else "",
            "time_slot": f"{slot.start_time} - {slot.end_time}" if slot else "",
            "start_time": slot.start_time if slot else "",
            "end_time": slot.end_time if slot else "",
            "teacher_name": teacher.full_name if teacher else "Educator",
            "student_name": student.name if student else "Scholar",
            "room_or_link": slot.room_or_link if slot else "Room 102",
            "agenda_topic": b.agenda_topic,
            "status": b.status,
        })
    return results


@router.post("/slots/{slot_id}/book")
def book_slot_by_path(
    slot_id: str,
    payload: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    payload["slot_id"] = slot_id
    return book_ptc_slot(payload, current_user, db)


@router.get("/my-bookings")
def get_my_bookings_alias(
    parent_user_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_parent_ptc_appointments(parent_user_id, current_user, db)


@router.post("/bookings/{booking_id}/cancel")
def cancel_ptc_booking(
    booking_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(PTCBookingDB).filter(PTCBookingDB.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Only booking owner or school admin can cancel
    if (current_user.role or "").lower() != "admin" and booking.parent_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    booking.status = "CANCELLED"
    slot = db.query(PTCSlotDB).filter(PTCSlotDB.id == booking.slot_id).first()
    if slot:
        slot.is_booked = False
    db.commit()
    return {"status": "ok", "message": "Booking cancelled and slot released"}
