"""
Automated Birthday Engine Scheduler.
Periodically checks for students celebrating birthdays across schools
and auto-dispatches personalized wishes without duplicate messaging.
"""
import asyncio
import logging
from datetime import datetime, timezone, date
from sqlalchemy import extract

from db.session import SessionLocal
from models.student_db import StudentDB
from models.school import SchoolDB
from models.parent_student_db import ParentStudentDB
from models.notification_db import NotificationDB
from services.notification_service import dispatch_multi_channel_notification

logger = logging.getLogger("scheduler.birthday")

DEFAULT_BIRTHDAY_TEMPLATE = (
    "Dear Parent, {school_name} extends warmest wishes to {student_name} (Class {grade}) "
    "on their Birthday! May this year bring happiness, growth, and stellar success! 🎂🎉"
)


def run_daily_birthday_wishes():
    """Scan all active schools and send birthday wishes to celebrating students."""
    db = SessionLocal()
    try:
        today = date.today()
        schools = db.query(SchoolDB).filter(SchoolDB.is_active == True).all()

        total_dispatched = 0
        for school in schools:
            template = getattr(school, "birthday_template", None) or DEFAULT_BIRTHDAY_TEMPLATE
            students = db.query(StudentDB).filter(
                StudentDB.school_id == school.id,
                StudentDB.is_active == True,
                StudentDB.dob != None,
                extract("month", StudentDB.dob) == today.month,
                extract("day", StudentDB.dob) == today.day,
            ).all()

            for s in students:
                # Check if wish was already logged today for this student
                today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
                already_sent = db.query(NotificationDB).filter(
                    NotificationDB.school_id == school.id,
                    NotificationDB.event_type == "BIRTHDAY_WISH",
                    NotificationDB.created_at >= today_start,
                    NotificationDB.payload_json.like(f"%{s.id}%")
                ).first()

                if already_sent:
                    continue

                # Find linked parent user
                link = db.query(ParentStudentDB).filter(ParentStudentDB.student_id == s.id).first()
                parent_user_id = link.parent_user_id if link else None
                phone = (link.parent.phone if link and link.parent else None) or s.father_phone or s.mother_phone
                email = (link.parent.email if link and link.parent else None)

                msg = template.replace("{school_name}", school.name or "Technula EduFlow").replace(
                    "{student_name}", s.name
                ).replace("{grade}", f"{s.grade}-{s.section}")

                dispatch_multi_channel_notification(
                    db=db,
                    school_id=school.id,
                    user_id=parent_user_id,
                    title=f"Happy Birthday {s.name}! 🎂",
                    message=msg,
                    event_type="BIRTHDAY_WISH",
                    phone=phone,
                    email=email,
                    payload={"student_id": str(s.id), "student_name": s.name, "date": today.isoformat()},
                )
                total_dispatched += 1

        if total_dispatched > 0:
            logger.info(f"[Birthday Scheduler] Dispatched {total_dispatched} birthday wishes for {today.isoformat()}")
    except Exception as e:
        logger.error(f"[Birthday Scheduler] Error executing daily birthday scan: {e}")
    finally:
        db.close()


async def start_birthday_scheduler_loop():
    """Background worker running every 6 hours to check and dispatch wishes."""
    # Short wait for database and server initialization
    await asyncio.sleep(15)
    while True:
        try:
            # Run in threadpool so DB calls don't block event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_daily_birthday_wishes)
        except Exception as e:
            logger.error(f"[Birthday Scheduler Loop Error]: {e}")
        # Re-check every 6 hours (21600 seconds)
        await asyncio.sleep(21600)
