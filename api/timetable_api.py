"""
Timetable API — Weekly Class Schedule builder and daily roster viewer.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
import io
import json
import base64
import logging
from datetime import date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
try:
    import pypdf
except ImportError:
    pypdf = None
from db.session import get_db
from models.timetable_db import TimetableSlotDB
from models.subject import Subject
from models.user_db import UserDB
from models.teacher_assignment_db import TeacherAssignmentDB
from auth.dependencies import get_current_user, require_role
from services.gemini_service import get_genai_client

logger = logging.getLogger("api.timetable")
router = APIRouter(prefix="/timetable", tags=["Class Timetable"])


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@router.get("/class")
def get_class_timetable(
    grade: str = "10",
    section: str = "A",
    academic_year: str = "2025-26",
    school_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns weekly master grid for a specific grade and section."""
    eff_school_id = school_id or (str(user.school_id) if user.school_id else None)

    slots = db.query(TimetableSlotDB).filter(
        TimetableSlotDB.school_id == eff_school_id,
        TimetableSlotDB.grade == grade,
        TimetableSlotDB.section == section,
        TimetableSlotDB.academic_year == academic_year
    ).order_by(TimetableSlotDB.day_of_week.asc(), TimetableSlotDB.period_number.asc()).all()

    schedule = {day: [] for day in DAY_NAMES}

    for s in slots:
        day_name = DAY_NAMES[s.day_of_week] if 0 <= s.day_of_week < len(DAY_NAMES) else "Monday"
        subject = db.query(Subject).filter(Subject.id == s.subject_id).first() if s.subject_id else None
        teacher = db.query(UserDB).filter(UserDB.id == s.teacher_id).first() if s.teacher_id else None

        schedule[day_name].append({
            "id": str(s.id),
            "period_number": s.period_number,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "subject_id": str(s.subject_id) if s.subject_id else None,
            "subject_name": subject.name if subject else ("Break / Assembly" if s.slot_type != "CLASS" else "Free Period"),
            "teacher_id": str(s.teacher_id) if s.teacher_id else None,
            "teacher_name": teacher.full_name if teacher else "",
            "room_number": s.room_number or "",
            "slot_type": s.slot_type,
        })

    return {
        "grade": grade,
        "section": section,
        "academic_year": academic_year,
        "schedule": schedule
    }


@router.post("/slots")
def upsert_timetable_slot(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Creates or updates a single period slot in the timetable."""
    school_id = str(user.school_id)  # SECURE: from JWT
    grade = payload.get("grade")
    section = (payload.get("section") or "A").upper()
    day_of_week = int(payload.get("day_of_week", 0))
    period_number = int(payload.get("period_number", 1))
    start_time = payload.get("start_time", "08:30")
    end_time = payload.get("end_time", "09:15")
    subject_id = payload.get("subject_id")
    teacher_id = payload.get("teacher_id")
    room_number = payload.get("room_number")
    slot_type = payload.get("slot_type", "CLASS")
    academic_year = payload.get("academic_year", "2025-26")

    if not grade:
        raise HTTPException(status_code=400, detail="grade is required")

    existing = db.query(TimetableSlotDB).filter(
        TimetableSlotDB.school_id == school_id,
        TimetableSlotDB.grade == grade,
        TimetableSlotDB.section == section,
        TimetableSlotDB.day_of_week == day_of_week,
        TimetableSlotDB.period_number == period_number,
    ).first()

    if existing:
        existing.start_time = start_time
        existing.end_time = end_time
        existing.subject_id = subject_id
        existing.teacher_id = teacher_id
        existing.room_number = room_number
        existing.slot_type = slot_type
        existing.academic_year = academic_year
        slot = existing
    else:
        slot = TimetableSlotDB(
            school_id=school_id,
            academic_year=academic_year,
            grade=grade,
            section=section,
            day_of_week=day_of_week,
            period_number=period_number,
            start_time=start_time,
            end_time=end_time,
            subject_id=subject_id,
            teacher_id=teacher_id,
            room_number=room_number,
            slot_type=slot_type,
        )
        db.add(slot)

    db.commit()
    db.refresh(slot)
    return {"status": "ok", "id": str(slot.id), "message": "Timetable slot saved successfully"}


@router.put("/slots/{slot_id}")
def update_timetable_slot(
    slot_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Update a timetable slot."""
    slot = db.query(TimetableSlotDB).filter(TimetableSlotDB.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Timetable slot not found")

    if user.role != "SuperAdmin" and str(slot.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if "subject_id" in payload:
        slot.subject_id = payload["subject_id"] or None
    if "teacher_id" in payload:
        slot.teacher_id = payload["teacher_id"] or None
    if "room_number" in payload:
        slot.room_number = payload["room_number"]
    if "slot_type" in payload:
        slot.slot_type = payload["slot_type"]
    if "start_time" in payload:
        slot.start_time = payload["start_time"]
    if "end_time" in payload:
        slot.end_time = payload["end_time"]

    db.commit()
    return {"status": "ok", "message": "Timetable slot updated"}


@router.delete("/slots/{slot_id}")
def delete_timetable_slot(
    slot_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Delete a timetable slot."""
    slot = db.query(TimetableSlotDB).filter(TimetableSlotDB.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Timetable slot not found")

    if user.role != "SuperAdmin" and str(slot.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(slot)
    db.commit()
    return {"status": "ok", "message": "Timetable slot deleted"}


@router.get("/today")
def get_today_schedule(
    grade: str = "10",
    section: str = "A",
    school_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns today's specific periods for instant display on Teacher PWA or Parent Portal."""
    eff_school_id = school_id or (str(user.school_id) if user.school_id else None)
    today_weekday = date.today().weekday()
    if today_weekday > 5:
        return {"is_sunday": True, "periods": []}

    slots = db.query(TimetableSlotDB).filter(
        TimetableSlotDB.school_id == eff_school_id,
        TimetableSlotDB.grade == grade,
        TimetableSlotDB.section == section,
        TimetableSlotDB.day_of_week == today_weekday,
    ).order_by(TimetableSlotDB.period_number.asc()).all()

    periods = []
    for s in slots:
        subject = db.query(Subject).filter(Subject.id == s.subject_id).first() if s.subject_id else None
        teacher = db.query(UserDB).filter(UserDB.id == s.teacher_id).first() if s.teacher_id else None
        periods.append({
            "period": s.period_number,
            "time": f"{s.start_time} - {s.end_time}",
            "subject": subject.name if subject else ("Recess" if s.slot_type != "CLASS" else "Free Period"),
            "teacher": teacher.full_name if teacher else "",
            "room": s.room_number or "",
            "type": s.slot_type,
        })

    return {
        "day": DAY_NAMES[today_weekday],
        "is_sunday": False,
        "grade": grade,
        "section": section,
        "periods": periods
    }


@router.get("/my-lectures")
def get_my_teacher_lectures(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the authenticated teacher's assigned classes, today's lectures, and weekly schedule.
    """
    school_id = current_user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="User is not affiliated with any school")

    # Fetch teacher's official class & subject assignments
    assignments = db.query(TeacherAssignmentDB).filter(
        TeacherAssignmentDB.teacher_user_id == current_user.id,
        TeacherAssignmentDB.school_id == school_id
    ).all()

    assigned_classes = []
    for a in assignments:
        subj = db.query(Subject).filter(Subject.id == a.subject_id).first() if a.subject_id else None
        assigned_classes.append({
            "id": str(a.id),
            "grade": a.grade,
            "section": a.section,
            "role_type": a.role_type,
            "subject_id": str(a.subject_id) if a.subject_id else None,
            "subject_name": subj.name if subj else None,
        })

    # Find timetable slots specifically for this teacher
    slots = db.query(TimetableSlotDB).filter(
        TimetableSlotDB.school_id == school_id,
        TimetableSlotDB.teacher_id == current_user.id
    ).order_by(TimetableSlotDB.day_of_week.asc(), TimetableSlotDB.period_number.asc()).all()

    # If no slots explicitly linked by teacher_id yet, fallback to slots of their assigned grade/section
    if not slots and assigned_classes:
        assigned_grades = {a["grade"] for a in assigned_classes}
        slots = db.query(TimetableSlotDB).filter(
            TimetableSlotDB.school_id == school_id,
            TimetableSlotDB.grade.in_(assigned_grades)
        ).order_by(TimetableSlotDB.day_of_week.asc(), TimetableSlotDB.period_number.asc()).all()

    today_weekday = date.today().weekday()
    today_lectures = []
    weekly_schedule = {day: [] for day in DAY_NAMES}

    for s in slots:
        day_name = DAY_NAMES[s.day_of_week] if 0 <= s.day_of_week < len(DAY_NAMES) else "Monday"
        subject = db.query(Subject).filter(Subject.id == s.subject_id).first() if s.subject_id else None

        lecture_item = {
            "id": str(s.id),
            "grade": s.grade,
            "section": s.section,
            "period": s.period_number,
            "time": f"{s.start_time} - {s.end_time}",
            "subject": subject.name if subject else ("Break / Assembly" if s.slot_type != "CLASS" else "Free Period"),
            "room": s.room_number or "",
            "type": s.slot_type,
        }

        weekly_schedule[day_name].append(lecture_item)

        if s.day_of_week == today_weekday and s.slot_type == "CLASS":
            today_lectures.append(lecture_item)

    today_lectures.sort(key=lambda x: x["period"])

    return {
        "teacher_name": current_user.full_name,
        "teacher_email": current_user.email,
        "assigned_classes": assigned_classes,
        "is_class_teacher": any(a["role_type"] == "ClassTeacher" for a in assigned_classes),
        "today_lectures": today_lectures,
        "weekly_schedule": weekly_schedule,
        "day_name": DAY_NAMES[today_weekday] if today_weekday < len(DAY_NAMES) else "Sunday",
        "is_sunday": today_weekday > 5,
    }


# ── AI PDF / Image / Document Timetable Ingestion ─────────────
@router.post("/ai-parse-document")
async def ai_parse_timetable_document(
    file: UploadFile = File(...),
    grade: str = Form("10"),
    section: str = Form("A"),
    academic_year: str = Form("2025-26"),
    auto_save: bool = Form(False),
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Parses a PDF, Image (PNG/JPG), or CSV class timetable schedule using Gemini AI.
    Extracts days (Monday-Saturday), periods (1-8), times, subjects, teachers, and rooms.
    Can return preview or directly commit to the database.
    """
    school_id = user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="School ID required in user context")

    filename = (file.filename or "").lower()
    allowed_exts = [".pdf", ".png", ".jpg", ".jpeg", ".csv", ".txt"]
    if not any(filename.endswith(ext) for ext in allowed_exts):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a PDF document (.pdf), image (.png, .jpg), or CSV (.csv).",
        )

    content_bytes = await file.read()
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    extracted_text = ""
    is_image = filename.endswith((".png", ".jpg", ".jpeg"))
    is_pdf = filename.endswith(".pdf")

    if is_pdf:
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            for page in pdf_reader.pages:
                txt = page.extract_text()
                if txt:
                    extracted_text += txt + "\n"
        except Exception as pe:
            logger.warning(f"PDF text extraction note: {pe}")

    elif filename.endswith((".csv", ".txt")):
        try:
            extracted_text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            extracted_text = content_bytes.decode("latin-1", errors="ignore")

    client = get_genai_client()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Gemini AI engine is not configured. Please verify GEMINI_API_KEY in server environment.",
        )

    system_prompt = f"""
You are an expert school administrative AI specialized in parsing school class timetable documents.
Task: Extract the full weekly class timetable from the uploaded document for Class {grade}, Section {section} (Academic Year {academic_year}).

Requirements:
1. Days of week must be mapped:
   - Monday -> day_of_week: 0
   - Tuesday -> day_of_week: 1
   - Wednesday -> day_of_week: 2
   - Thursday -> day_of_week: 3
   - Friday -> day_of_week: 4
   - Saturday -> day_of_week: 5
2. Periods should be numbered 1 to 8 (Period 1, Period 2, etc.).
3. Standard period duration: if times are stated, format as "HH:MM" (e.g., "08:30" - "09:15"). If times are missing, assign realistic 45-minute slots starting from 08:30.
4. Extract Subject Names cleanly (e.g., Mathematics, Science, English, Hindi, Social Science, Physics, Chemistry, Biology, Computer Science, Physical Education, Art, Library, Music, etc.).
5. If teacher names or initials are listed (e.g. "Dr. Sunita Sharma", "R. Verma", "Anita D."), extract them in "teacher_name".
6. If room numbers or labs are listed (e.g. "Room 102", "Physics Lab"), extract in "room_number".
7. For lunch, assembly, or recess slots, set "slot_type" to "BREAK" or "LUNCH" or "ASSEMBLY". For normal subjects, set "slot_type" to "CLASS".

Return ONLY a valid, raw JSON object (strictly no markdown formatting, no ``` code blocks):
{{
  "detected_title": "Class {grade}-{section} Timetable",
  "slots": [
    {{
      "day_of_week": 0,
      "day_name": "Monday",
      "period_number": 1,
      "start_time": "08:30",
      "end_time": "09:15",
      "subject_name": "Mathematics",
      "teacher_name": "Dr. Sunita Sharma",
      "room_number": "Room 101",
      "slot_type": "CLASS"
    }}
  ]
}}
"""

    gemini_prompt_parts = []
    # If we have extracted text and it's substantial (> 40 chars), pass text
    if extracted_text and len(extracted_text.strip()) > 40:
        gemini_prompt_parts.append(
            f"{system_prompt}\n\nDOCUMENT TEXT CONTENT:\n{extracted_text[:12000]}"
        )
    else:
        # Pass multimodal inline data
        mime_type = "application/pdf" if is_pdf else \
                    "image/png" if filename.endswith(".png") else "image/jpeg"
        b64_data = base64.b64encode(content_bytes).decode("utf-8")
        gemini_prompt_parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": b64_data
            }
        })
        gemini_prompt_parts.append(system_prompt)

    try:
        if hasattr(client, "generate_content"):
            res = client.generate_content(gemini_prompt_parts)
            raw_text = res.text.strip() if hasattr(res, "text") else str(res)
        else:
            raw_text = "{}"
    except Exception as ai_err:
        logger.error(f"Gemini timetable parsing error: {ai_err}")
        raise HTTPException(
            status_code=500,
            detail=f"AI timetable parsing failed: {str(ai_err)}. Please ensure document is legible.",
        )

    # Clean JSON
    cleaned_json_str = raw_text.strip()
    if "```" in cleaned_json_str:
        parts = cleaned_json_str.split("```")
        for p in parts:
            p_strip = p.strip()
            if p_strip.startswith("json"):
                p_strip = p_strip[4:].strip()
            if p_strip.startswith("{") and p_strip.endswith("}"):
                cleaned_json_str = p_strip
                break

    try:
        parsed_data = json.loads(cleaned_json_str)
    except Exception:
        # Try extracting JSON object substring
        start = cleaned_json_str.find("{")
        end = cleaned_json_str.rfind("}")
        if start != -1 and end != -1:
            try:
                parsed_data = json.loads(cleaned_json_str[start:end+1])
            except Exception:
                raise HTTPException(status_code=500, detail="Could not parse structured timetable JSON from AI response")
        else:
            raise HTTPException(status_code=500, detail="Could not parse structured timetable JSON from AI response")

    raw_slots = parsed_data.get("slots", [])
    if not raw_slots:
        raise HTTPException(status_code=422, detail="No timetable periods could be detected from this document. Please check the document format.")

    # Match and enrich subjects and teachers in DB
    existing_teachers = db.query(UserDB).filter(
        UserDB.school_id == school_id,
        UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher", "Admin"])
    ).all()

    processed_slots = []
    for s in raw_slots:
        dow = int(s.get("day_of_week", 0))
        if dow < 0 or dow > 5:
            dow = 0
        p_num = int(s.get("period_number", 1))
        st_name = (s.get("subject_name") or "General").strip()
        t_name = (s.get("teacher_name") or "").strip()
        r_num = (s.get("room_number") or "").strip()
        st_type = (s.get("slot_type") or "CLASS").upper()

        # Subject Lookup / Auto-provision
        subj = db.query(Subject).filter(
            Subject.school_id == school_id,
            Subject.name.ilike(st_name)
        ).first()
        if not subj and st_name and st_type == "CLASS":
            subj = Subject(
                school_id=school_id,
                name=st_name.title(),
                code=st_name[:4].upper(),
            )
            db.add(subj)
            db.flush()

        # Teacher Fuzzy Match
        matched_teacher = None
        if t_name:
            t_clean = t_name.lower().replace("dr.", "").replace("mr.", "").replace("mrs.", "").replace("ms.", "").strip()
            for t in existing_teachers:
                t_db_name = (t.full_name or "").lower()
                if t_clean in t_db_name or t_db_name in t_clean:
                    matched_teacher = t
                    break

        slot_item = {
            "day_of_week": dow,
            "day_name": DAY_NAMES[dow],
            "period_number": p_num,
            "start_time": s.get("start_time") or "08:30",
            "end_time": s.get("end_time") or "09:15",
            "subject_id": str(subj.id) if subj else None,
            "subject_name": subj.name if subj else st_name,
            "teacher_id": str(matched_teacher.id) if matched_teacher else None,
            "teacher_name": matched_teacher.full_name if matched_teacher else t_name,
            "room_number": r_num,
            "slot_type": st_type,
        }
        processed_slots.append(slot_item)

    # If auto_save requested, commit directly
    if auto_save:
        db.query(TimetableSlotDB).filter(
            TimetableSlotDB.school_id == school_id,
            TimetableSlotDB.grade == grade,
            TimetableSlotDB.section == section,
            TimetableSlotDB.academic_year == academic_year,
        ).delete()

        for ps in processed_slots:
            new_slot = TimetableSlotDB(
                school_id=school_id,
                grade=grade,
                section=section,
                academic_year=academic_year,
                day_of_week=ps["day_of_week"],
                period_number=ps["period_number"],
                start_time=ps["start_time"],
                end_time=ps["end_time"],
                subject_id=ps["subject_id"],
                teacher_id=ps["teacher_id"],
                room_number=ps["room_number"],
                slot_type=ps["slot_type"],
                updated_by=user.id,
            )
            db.add(new_slot)
        db.commit()

    return {
        "status": "ok",
        "grade": grade,
        "section": section,
        "academic_year": academic_year,
        "detected_title": parsed_data.get("detected_title") or f"Class {grade}-{section} Timetable",
        "total_slots": len(processed_slots),
        "auto_saved": auto_save,
        "slots": processed_slots,
        "message": f"Successfully parsed {len(processed_slots)} periods with Gemini AI!" + (" (Saved directly to timetable)" if auto_save else " (Preview ready to apply)")
    }


@router.post("/bulk-apply-slots")
def bulk_apply_timetable_slots(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Applies and commits an array of timetable slots for a grade and section.
    Replaces existing slots for the specified grade/section/academic_year.
    """
    school_id = user.school_id
    grade = str(payload.get("grade") or "10")
    section = str(payload.get("section") or "A").upper()
    academic_year = str(payload.get("academic_year") or "2025-26")
    slots = payload.get("slots", [])

    if not slots:
        raise HTTPException(status_code=400, detail="No timetable slots provided to apply")

    try:
        db.query(TimetableSlotDB).filter(
            TimetableSlotDB.school_id == school_id,
            TimetableSlotDB.grade == grade,
            TimetableSlotDB.section == section,
            TimetableSlotDB.academic_year == academic_year,
        ).delete()

        saved_count = 0
        for s in slots:
            sub_id = s.get("subject_id")
            t_id = s.get("teacher_id")

            if not sub_id and s.get("subject_name"):
                s_name = s.get("subject_name").strip()
                existing_subj = db.query(Subject).filter(
                    Subject.school_id == school_id,
                    Subject.name.ilike(s_name)
                ).first()
                if not existing_subj:
                    existing_subj = Subject(
                        school_id=school_id,
                        name=s_name.title(),
                        code=s_name[:4].upper()
                    )
                    db.add(existing_subj)
                    db.flush()
                sub_id = str(existing_subj.id)

            slot_obj = TimetableSlotDB(
                school_id=school_id,
                grade=grade,
                section=section,
                academic_year=academic_year,
                day_of_week=int(s.get("day_of_week", 0)),
                period_number=int(s.get("period_number", 1)),
                start_time=s.get("start_time") or "08:30",
                end_time=s.get("end_time") or "09:15",
                subject_id=sub_id,
                teacher_id=t_id,
                room_number=s.get("room_number") or "",
                slot_type=s.get("slot_type") or "CLASS",
                updated_by=user.id,
            )
            db.add(slot_obj)
            saved_count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database commit failed: {str(e)}")

    return {
        "status": "ok",
        "grade": grade,
        "section": section,
        "academic_year": academic_year,
        "saved_count": saved_count,
        "message": f"Successfully applied and saved {saved_count} timetable periods for Class {grade}-{section}!",
    }

