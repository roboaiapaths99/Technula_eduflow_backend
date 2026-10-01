"""
Datesheet API — Examination schedule management and class-scoped distribution.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.datesheet_db import DatesheetDB, DatesheetEntryDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/datesheets", tags=["Datesheet"])


@router.post("/")
def create_datesheet(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    title = (payload.get("title") or payload.get("exam_title") or "").strip()
    grade = str(payload.get("grade", "")).strip()
    section = str(payload.get("section", "ALL")).strip().upper()
    academic_year = payload.get("academic_year") or payload.get("session_year") or "2025-26"
    pdf_url = payload.get("pdf_url")
    entries_data = payload.get("entries", [])

    if not title or not grade:
        raise HTTPException(status_code=400, detail="Title and grade are required.")

    ds = DatesheetDB(
        school_id=user.school_id,
        title=title,
        grade=grade,
        section=section,
        academic_year=academic_year,
        pdf_url=pdf_url,
        is_published=False,
        created_by=user.id,
    )
    db.add(ds)
    db.flush()

    for idx, e in enumerate(entries_data):
        exam_date = datetime.strptime(e["exam_date"], "%Y-%m-%d").date()
        entry = DatesheetEntryDB(
            datesheet_id=ds.id,
            subject_name=e["subject_name"],
            subject_code=e.get("subject_code"),
            exam_date=exam_date,
            start_time=e.get("start_time", "09:30 AM"),
            end_time=e.get("end_time", "12:30 PM"),
            venue=e.get("venue"),
            syllabus_remarks=e.get("syllabus_remarks"),
            sort_order=e.get("sort_order", idx),
        )
        db.add(entry)

    db.commit()
    return {"success": True, "message": "Datesheet created in draft mode.", "datesheet_id": str(ds.id)}


@router.put("/{datesheet_id}")
def update_datesheet(
    datesheet_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    ds = db.query(DatesheetDB).filter(DatesheetDB.id == datesheet_id, DatesheetDB.school_id == user.school_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datesheet not found.")

    if "title" in payload: ds.title = payload["title"]
    if "grade" in payload: ds.grade = str(payload["grade"])
    if "section" in payload: ds.section = str(payload["section"]).upper()
    if "academic_year" in payload: ds.academic_year = payload["academic_year"]
    if "pdf_url" in payload: ds.pdf_url = payload["pdf_url"]

    if "entries" in payload:
        # Replace entries
        db.query(DatesheetEntryDB).filter(DatesheetEntryDB.datesheet_id == ds.id).delete()
        for idx, e in enumerate(payload["entries"]):
            exam_date = datetime.strptime(e["exam_date"], "%Y-%m-%d").date()
            entry = DatesheetEntryDB(
                datesheet_id=ds.id,
                subject_name=e["subject_name"],
                subject_code=e.get("subject_code"),
                exam_date=exam_date,
                start_time=e.get("start_time", "09:30 AM"),
                end_time=e.get("end_time", "12:30 PM"),
                venue=e.get("venue"),
                syllabus_remarks=e.get("syllabus_remarks"),
                sort_order=e.get("sort_order", idx),
            )
            db.add(entry)

    db.commit()
    return {"success": True, "message": "Datesheet updated."}


@router.post("/{datesheet_id}/publish")
def toggle_publish_datesheet(
    datesheet_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    ds = db.query(DatesheetDB).filter(DatesheetDB.id == datesheet_id, DatesheetDB.school_id == user.school_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datesheet not found.")

    ds.is_published = not ds.is_published
    ds.published_at = datetime.now(timezone.utc) if ds.is_published else None
    db.commit()

    # If now published, notify all scoped parents
    if ds.is_published:
        # Find students in this grade / section
        st_query = db.query(StudentDB).filter(StudentDB.school_id == user.school_id, StudentDB.is_active == True)
        if ds.grade != "ALL":
            st_query = st_query.filter(StudentDB.grade == ds.grade)
        if ds.section != "ALL":
            st_query = st_query.filter(StudentDB.section == ds.section)
        students = st_query.all()
        student_ids = [s.id for s in students]

        if student_ids:
            parent_links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id.in_(student_ids)).all()
            parent_user_ids = {pl.parent_user_id for pl in parent_links if pl.parent_user_id}
            alert_msg = f"EXAM DATESHEET PUBLISHED: {ds.title} (Class {ds.grade}-{ds.section}) has been published. View timetable & exam schedule."
            for pid in parent_user_ids:
                dispatch_multi_channel_notification(
                    db=db,
                    school_id=user.school_id,
                    user_id=pid,
                    title="Exam Datesheet Published",
                    message=alert_msg,
                    event_type="DATESHEET_PUBLISHED",
                    payload={"datesheet_id": str(ds.id), "grade": ds.grade, "section": ds.section},
                )

    return {
        "success": True,
        "is_published": ds.is_published,
        "message": f"Datesheet has been {'PUBLISHED to parents' if ds.is_published else 'moved back to draft'}.",
    }


@router.delete("/{datesheet_id}")
def delete_datesheet(
    datesheet_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    ds = db.query(DatesheetDB).filter(DatesheetDB.id == datesheet_id, DatesheetDB.school_id == user.school_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datesheet not found.")
    db.delete(ds)
    db.commit()
    return {"success": True, "message": "Datesheet deleted."}


# ── ALIAS FOR MOBILE APP: GET CLASS DATESHEETS ─────────────────────────
@router.get("/class/{grade}")
def get_class_datesheets_alias(
    grade: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sheets = db.query(DatesheetDB).filter(
        DatesheetDB.school_id == user.school_id,
        DatesheetDB.is_published == True,
        (DatesheetDB.grade == grade) | (DatesheetDB.grade == "ALL")
    ).order_by(desc(DatesheetDB.published_at)).all()

    res = []
    for s in sheets:
        entries = [{
            "id": str(e.id),
            "subject_name": e.subject_name,
            "subject_code": e.subject_code,
            "exam_date": e.exam_date.isoformat(),
            "start_time": e.start_time,
            "end_time": e.end_time,
            "venue": e.venue,
            "syllabus_remarks": e.syllabus_remarks,
        } for e in s.entries]

        res.append({
            "id": str(s.id),
            "title": s.title,
            "grade": s.grade,
            "section": s.section,
            "academic_year": s.academic_year,
            "pdf_url": s.pdf_url,
            "is_published": s.is_published,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "created_at": s.created_at.isoformat(),
            "entries_count": len(entries),
            "entries": entries,
        })
    return res


@router.get("/admin")
def list_datesheets_admin(
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    sheets = db.query(DatesheetDB).filter(DatesheetDB.school_id == user.school_id).order_by(desc(DatesheetDB.created_at)).all()
    res = []
    for s in sheets:
        entries = [{
            "id": str(e.id),
            "subject_name": e.subject_name,
            "subject_code": e.subject_code,
            "exam_date": e.exam_date.isoformat(),
            "start_time": e.start_time,
            "end_time": e.end_time,
            "venue": e.venue,
            "syllabus_remarks": e.syllabus_remarks,
        } for e in s.entries]

        res.append({
            "id": str(s.id),
            "title": s.title,
            "grade": s.grade,
            "section": s.section,
            "academic_year": s.academic_year,
            "pdf_url": s.pdf_url,
            "is_published": s.is_published,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "created_at": s.created_at.isoformat(),
            "entries_count": len(entries),
            "entries": entries,
        })
    return res


@router.get("/parent")
def get_parent_datesheet(
    student_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Find published datesheet for this student's grade and section (or section ALL)
    sheets = db.query(DatesheetDB).filter(
        DatesheetDB.school_id == user.school_id,
        DatesheetDB.is_published == True,
        (DatesheetDB.grade == student.grade) | (DatesheetDB.grade == "ALL"),
        (DatesheetDB.section == student.section) | (DatesheetDB.section == "ALL")
    ).order_by(desc(DatesheetDB.published_at)).all()

    res = []
    today = date.today()
    for s in sheets:
        entries = []
        for e in s.entries:
            days_left = (e.exam_date - today).days
            entries.append({
                "id": str(e.id),
                "subject_name": e.subject_name,
                "subject_code": e.subject_code,
                "exam_date": e.exam_date.isoformat(),
                "start_time": e.start_time,
                "end_time": e.end_time,
                "venue": e.venue,
                "syllabus_remarks": e.syllabus_remarks,
                "days_left": days_left,
                "is_upcoming": days_left >= 0,
            })

        res.append({
            "id": str(s.id),
            "title": s.title,
            "grade": s.grade,
            "section": s.section,
            "academic_year": s.academic_year,
            "pdf_url": s.pdf_url,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "entries": sorted(entries, key=lambda x: x["exam_date"]),
        })

    return res


# ── ALIAS FOR MOBILE APP: GET DATESHEETS BY GRADE ──────────────────────
@router.get("/class/{grade}")
def get_datesheets_by_grade(
    grade: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias for mobile app: GET /datesheets/class/{grade}."""
    sheets = db.query(DatesheetDB).filter(
        DatesheetDB.school_id == user.school_id,
        DatesheetDB.is_published == True,
        (DatesheetDB.grade == grade) | (DatesheetDB.grade == "ALL"),
    ).order_by(desc(DatesheetDB.published_at)).all()

    today = date.today()
    res = []
    for s in sheets:
        entries = []
        for e in s.entries:
            days_left = (e.exam_date - today).days
            entries.append({
                "id": str(e.id),
                "subject_name": e.subject_name,
                "subject_code": e.subject_code,
                "exam_date": e.exam_date.isoformat(),
                "start_time": e.start_time,
                "end_time": e.end_time,
                "venue": e.venue,
                "syllabus_remarks": e.syllabus_remarks,
                "days_left": days_left,
                "is_upcoming": days_left >= 0,
            })
        res.append({
            "id": str(s.id),
            "title": s.title,
            "grade": s.grade,
            "section": s.section,
            "academic_year": s.academic_year,
            "pdf_url": s.pdf_url,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "entries": sorted(entries, key=lambda x: x["exam_date"]),
        })
    return res


@router.post("/ai-parse-document")
async def ai_parse_datesheet_document(
    file: UploadFile = File(...),
    grade: Optional[str] = Form("10"),
    academic_year: Optional[str] = Form("2025-26"),
    auto_create: Optional[bool] = Form(False),
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal"])),
    db: Session = Depends(get_db),
):
    """
    Extracts structured examination datesheets from uploaded PDF or Image schedules using Gemini AI.
    """
    import base64
    import io
    import json
    import os
    import uuid
    import pypdf
    from services.gemini_service import get_genai_client

    filename = (file.filename or "").lower()
    if not (filename.endswith(".pdf") or filename.endswith((".png", ".jpg", ".jpeg"))):
        raise HTTPException(status_code=400, detail="Only PDF and Image files (.pdf, .png, .jpg, .jpeg) are supported.")

    content_bytes = await file.read()
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Save uploaded file
    os.makedirs("static/uploads", exist_ok=True)
    saved_filename = f"datesheet_{uuid.uuid4().hex[:10]}_{file.filename}"
    saved_path = os.path.join("static/uploads", saved_filename)
    with open(saved_path, "wb") as f_out:
        f_out.write(content_bytes)
    pdf_url = f"/static/uploads/{saved_filename}"

    extracted_text = ""
    is_pdf = filename.endswith(".pdf")
    if is_pdf:
        try:
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    extracted_text += t + "\n"
        except Exception:
            pass

    client = get_genai_client()
    if not client:
        raise HTTPException(status_code=503, detail="Gemini AI engine is not configured.")

    cur_year = date.today().year
    system_prompt = f"""
You are an expert school administrative assistant specialized in parsing official examination datesheets, exam timetables, and date schedules.
Target Class/Grade: {grade} (Academic Year {academic_year}, Current Year: {cur_year}).

Task:
Extract all scheduled examination papers from the uploaded document into a structured JSON schedule.

Requirements:
1. "title": Detected exam title (e.g., "Term 1 Mid-Term Examination 2026" or "Annual Board Pre-Board Exams").
2. "grade": Target grade/class (e.g. "{grade}").
3. "section": Target section or "ALL".
4. "entries": Array of scheduled papers:
   - "subject_name": Name of the subject (e.g., Mathematics, Science, English, Hindi, Social Science, Physics, Chemistry, Computer Science).
   - "subject_code": Subject code if listed (e.g. "041", "086", or null).
   - "exam_date": Strict format YYYY-MM-DD. (Infer the year as {cur_year} or next year if month is early).
   - "start_time": Format "09:30 AM" or "10:00 AM".
   - "end_time": Format "12:30 PM" or "01:00 PM".
   - "venue": Hall or room if listed (e.g. "Examination Hall 1" or "Main Auditorium"), or null.
   - "syllabus_remarks": Any remarks, chapter list, or notes if specified.

Return ONLY a valid, raw JSON object (strictly no markdown formatting, no ``` code blocks):
{{
  "title": "Term 1 Examination 2026",
  "grade": "{grade}",
  "section": "ALL",
  "academic_year": "{academic_year}",
  "entries": [
    {{
      "subject_name": "Mathematics",
      "subject_code": "041",
      "exam_date": "{cur_year}-10-15",
      "start_time": "09:30 AM",
      "end_time": "12:30 PM",
      "venue": "Exam Hall 1",
      "syllabus_remarks": "Chapters 1 to 6"
    }}
  ]
}}
"""

    gemini_prompt_parts = []
    if extracted_text and len(extracted_text.strip()) > 40:
        gemini_prompt_parts.append(f"{system_prompt}\n\nDOCUMENT CONTENT:\n{extracted_text[:12000]}")
    else:
        mime = "application/pdf" if is_pdf else "image/png" if filename.endswith(".png") else "image/jpeg"
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        gemini_prompt_parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        gemini_prompt_parts.append(system_prompt)

    try:
        res = client.generate_content(gemini_prompt_parts)
        raw_text = res.text.strip() if hasattr(res, "text") else str(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini parsing failed: {str(e)}")

    cleaned = raw_text.strip()
    if "```" in cleaned:
        for p in cleaned.split("```"):
            p_s = p.strip()
            if p_s.startswith("json"):
                p_s = p_s[4:].strip()
            if p_s.startswith("{") and p_s.endswith("}"):
                cleaned = p_s
                break

    try:
        parsed_data = json.loads(cleaned)
    except Exception:
        s_idx = cleaned.find("{")
        e_idx = cleaned.rfind("}")
        if s_idx != -1 and e_idx != -1:
            try:
                parsed_data = json.loads(cleaned[s_idx:e_idx+1])
            except Exception:
                raise HTTPException(status_code=500, detail="Could not parse JSON from AI response.")
        else:
            raise HTTPException(status_code=500, detail="Could not parse JSON from AI response.")

    entries = parsed_data.get("entries", [])
    if not entries:
        raise HTTPException(status_code=422, detail="No exam dates or papers could be detected in this document.")

    # Auto-create datesheet if requested
    if auto_create:
        d_title = parsed_data.get("title") or f"Class {grade} Examination Datesheet"
        ds = DatesheetDB(
            school_id=user.school_id,
            title=d_title,
            grade=str(parsed_data.get("grade") or grade),
            section=str(parsed_data.get("section") or "ALL").upper(),
            academic_year=str(parsed_data.get("academic_year") or academic_year),
            pdf_url=pdf_url,
            is_published=False,
            created_by=user.id,
        )
        db.add(ds)
        db.flush()

        for e in entries:
            try:
                e_date = datetime.strptime(e["exam_date"], "%Y-%m-%d").date()
            except Exception:
                e_date = date.today()

            entry_obj = DatesheetEntryDB(
                datesheet_id=ds.id,
                subject_name=e.get("subject_name") or "General Exam",
                subject_code=e.get("subject_code"),
                exam_date=e_date,
                start_time=e.get("start_time") or "09:30 AM",
                end_time=e.get("end_time") or "12:30 PM",
                venue=e.get("venue"),
                syllabus_remarks=e.get("syllabus_remarks"),
            )
            db.add(entry_obj)

        db.commit()
        return {
            "status": "created",
            "datesheet_id": str(ds.id),
            "title": ds.title,
            "entries_count": len(entries),
            "pdf_url": pdf_url,
            "message": f"Datesheet '{ds.title}' with {len(entries)} papers parsed and created successfully.",
        }

    return {
        "status": "preview",
        "title": parsed_data.get("title") or f"Class {grade} Examination Datesheet",
        "grade": parsed_data.get("grade") or grade,
        "section": parsed_data.get("section") or "ALL",
        "academic_year": parsed_data.get("academic_year") or academic_year,
        "pdf_url": pdf_url,
        "entries": entries,
    }


