from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Dict, Any, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_

from db.session import SessionLocal
from models.subject import Subject
from models.student_db import StudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.teacher_feedback import TeacherFeedback
from auth.dependencies import require_role

router = APIRouter()

# ✅ one-time per process
_TF_SCHEMA_READY = False


def _db() -> Session:
    return SessionLocal()


def _ensure_teacher_feedback_schema(db: Session) -> None:
    """
    ✅ SAFE (no data loss): add teacher_user_id if missing.
    Prevents sqlite error when model has teacher_user_id but table doesn't.
    """
    global _TF_SCHEMA_READY
    if _TF_SCHEMA_READY:
        return
    try:
        cols = db.execute(text("PRAGMA table_info(teacher_feedback)")).fetchall()
        col_names = {c[1] for c in cols}
        if "teacher_user_id" not in col_names:
            db.execute(text("ALTER TABLE teacher_feedback ADD COLUMN teacher_user_id INTEGER"))
            db.commit()

        db.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_feedback_student_exam_teacher "
                "ON teacher_feedback(student_id, exam_id, teacher_user_id)"
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        _TF_SCHEMA_READY = True


def _resolve_exam_id(db: Session, exam_name: str, exam_date_iso: str) -> int | None:
    """
    Resolve exam_id from SQLite exams table using (exam_name, exam_date).
    Returns None if not found.
    """
    exam_name = (exam_name or "").strip()
    exam_date_iso = (exam_date_iso or "").strip()
    if not exam_name or not exam_date_iso:
        return None
    try:
        # exams table schema: id, exam_name, exam_date, max_score
        row = db.execute(
            text("SELECT id FROM exams WHERE exam_name = :nm AND exam_date = :dt ORDER BY id DESC LIMIT 1"),
            {"nm": exam_name, "dt": exam_date_iso},
        ).fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None


def _get_subject_names(db: Session) -> List[str]:
    rows = db.query(Subject).order_by(Subject.name.asc()).all()
    return [s.name for s in rows]


def _get_all_admission_nos(db: Session) -> set[str]:
    rows = db.query(StudentDB.admission_no).all()
    return {r[0] for r in rows if r and r[0]}


def _parse_exam_date(s: str) -> date:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty date")

    # YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except Exception:
        pass

    # DD-MM-YYYY
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        pass

    raise ValueError(f"invalid date: {s}")


def _make_template_csv() -> str:
    db = _db()
    try:
        subjects = _get_subject_names(db)
        if not subjects:
            raise HTTPException(status_code=400, detail="No subjects found in DB. Admin must add subjects first.")

        adm_nos = sorted(list(_get_all_admission_nos(db)))
        example_adm = adm_nos[0] if adm_nos else "GVPS-6A-001"

        cols = ["admission_no", "exam_name", "exam_date", *subjects, "max_score"]
        example = [example_adm, "Final", "2026-03-05", *["0" for _ in subjects], "100"]

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(cols)
        w.writerow(example)
        return out.getvalue()
    finally:
        db.close()


def _enforce_teacher_assigned_to_class(user, grade: str, section: str, db: Session) -> None:
    role = (getattr(user, "role", "") or "").lower()
    if role == "admin":
        return
    if role != "teacher":
        return

    ok = (
        db.query(TeacherAssignmentDB)
        .filter(
            TeacherAssignmentDB.teacher_user_id == user.id,
            TeacherAssignmentDB.grade == str(grade),
            TeacherAssignmentDB.section == str(section),
        )
        .first()
    )
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/template", summary="Download CSV template for marks upload")
def download_template(
    user=Depends(require_role(["Teacher", "Admin"])),
):
    csv_text = _make_template_csv()
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marks_template.csv"},
    )


@router.get("/recent-uploads", summary="Get recently uploaded exams")
def recent_uploads(
    limit: int = 10,
    user=Depends(require_role(["Teacher", "Admin"])),
) -> Dict[str, Any]:
    rows = load_uploaded_marks()
    seen = set()
    exams = []

    def _safe_date(s: str) -> date:
        try:
            return _parse_exam_date(s)
        except Exception:
            return date(1900, 1, 1)

    rows_sorted = sorted(rows, key=lambda r: _safe_date(r.get("exam_date", "")), reverse=True)

    for r in rows_sorted:
        key = (r.get("exam_name"), r.get("exam_date"), r.get("max_score"))
        if key in seen:
            continue
        seen.add(key)
        exams.append(
            {
                "exam_name": r.get("exam_name"),
                "exam_date": r.get("exam_date"),
                "max_score": r.get("max_score"),
            }
        )
        if len(exams) >= limit:
            break

    return {"count": len(exams), "items": exams}


@router.post("/upload-marks", summary="Teacher uploads marks CSV for an exam")
async def upload_marks_csv(
    file: UploadFile = File(...),
    user=Depends(require_role(["Teacher", "Admin"])),
) -> Dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = await file.read()
    try:
        text_csv = raw.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text_csv))

    required = {"admission_no", "exam_name", "exam_date", "max_score"}
    missing = [c for c in required if c not in (reader.fieldnames or [])]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    db = _db()
    try:
        db_subjects = _get_subject_names(db)
        if not db_subjects:
            raise HTTPException(status_code=400, detail="No subjects found in DB. Admin must add subjects first.")

        allowed_adm = _get_all_admission_nos(db)

        csv_fields = set(reader.fieldnames or [])
        csv_subjects = sorted(list(csv_fields - required))

        missing_in_db = [s for s in csv_subjects if s not in set(db_subjects)]
        if missing_in_db:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Unknown subjects in CSV. Ask admin to add them first.",
                    "missing_subjects": missing_in_db,
                    "known_subjects": db_subjects,
                },
            )

        rows_to_store: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        seen_adm: List[str] = []

        for idx, row in enumerate(reader, start=2):
            admission_no = (row.get("admission_no") or "").strip()
            exam_name = (row.get("exam_name") or "").strip()
            exam_date_raw = (row.get("exam_date") or "").strip()

            if not admission_no:
                errors.append({"row": idx, "field": "admission_no", "message": "Missing admission_no"})
                continue

            if allowed_adm and admission_no not in allowed_adm:
                errors.append({"row": idx, "field": "admission_no", "message": f"Unknown admission_no: {admission_no}"})
                continue

            if not exam_name:
                errors.append({"row": idx, "field": "exam_name", "message": "Missing exam_name"})
                continue

            try:
                parsed_d = _parse_exam_date(exam_date_raw)
                exam_date_str = parsed_d.isoformat()
            except Exception:
                errors.append(
                    {
                        "row": idx,
                        "field": "exam_date",
                        "message": f"Invalid exam_date: {exam_date_raw} (use YYYY-MM-DD or DD-MM-YYYY)",
                    }
                )
                continue

            try:
                max_score = int(float(row.get("max_score") or 100))
            except Exception:
                errors.append({"row": idx, "field": "max_score", "message": "Invalid max_score"})
                continue

            scores: Dict[str, float] = {}
            score_ok = True
            for sub in csv_subjects:
                val = (row.get(sub) or "").strip()
                try:
                    scores[sub] = float(val) if val != "" else 0.0
                except Exception:
                    errors.append({"row": idx, "field": sub, "message": f"Invalid score '{val}' for subject {sub}"})
                    score_ok = False

            if not score_ok:
                continue

            seen_adm.append(admission_no)
            rows_to_store.append(
                {
                    "admission_no": admission_no,
                    "exam_name": exam_name,
                    "exam_date": exam_date_str,
                    "max_score": max_score,
                    "scores": scores,
                }
            )

        if errors:
            raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": errors})

        role = (getattr(user, "role", "") or "").lower()
        if role == "teacher":
            uniq_adm = sorted(set(seen_adm))
            if not uniq_adm:
                raise HTTPException(status_code=400, detail="No valid rows to upload")

            st_rows = (
                db.query(StudentDB.admission_no, StudentDB.grade, StudentDB.section)
                .filter(StudentDB.admission_no.in_(uniq_adm))
                .all()
            )
            adm_to_class = {r[0]: (str(r[1]), str(r[2])) for r in st_rows if r and r[0]}
            class_set = {adm_to_class.get(a) for a in uniq_adm if a in adm_to_class}

            if not class_set:
                raise HTTPException(status_code=400, detail="Could not resolve class for uploaded admission_no(s)")

            if len(class_set) != 1:
                raise HTTPException(status_code=400, detail="Upload CSV must contain students from only one grade/section")

            only_grade, only_section = list(class_set)[0]
            _enforce_teacher_assigned_to_class(user, only_grade, only_section, db)

        existing = load_uploaded_marks()

        def k(r):
            return (r["admission_no"], r["exam_name"], r["exam_date"])

        existing_map = {k(r): r for r in existing}
        for r in rows_to_store:
            existing_map[k(r)] = r

        merged = list(existing_map.values())
        save_uploaded_marks(merged)

        return {
            "status": "ok",
            "uploaded_rows": len(rows_to_store),
            "stored_total_rows": len(merged),
            "note": "Uploaded marks saved. Parent dashboard will reflect updates on refresh.",
        }

    finally:
        db.close()


@router.get("/marks-preview", summary="Preview all marks currently stored (teacher read-only)")
def marks_preview(
    user=Depends(require_role(["Teacher", "Admin"])),
) -> Dict[str, Any]:
    rows = load_uploaded_marks()
    return {"count": len(rows), "items": rows}


@router.get("/class-marks", summary="Get class marks table for teacher (grade/section + exam)")
def class_marks(
    grade: str,
    section: str,
    exam_name: str,
    exam_id: int | None = Query(None),
    examId: int | None = Query(None),
    user=Depends(require_role(["Teacher", "Admin"])),
) -> Dict[str, Any]:
    db = _db()
    exam_id_final = exam_id if exam_id is not None else examId
    _ensure_teacher_feedback_schema(db)  # ✅ prevent teacher_user_id column crash
    try:
        _enforce_teacher_assigned_to_class(user, grade, section, db)

        subjects = _get_subject_names(db)
        if not subjects:
            raise HTTPException(status_code=400, detail="No subjects found in DB. Admin must add subjects first.")

        students = (
            db.query(StudentDB)
            .filter(StudentDB.grade == str(grade), StudentDB.section == str(section))
            .order_by(StudentDB.admission_no.asc(), StudentDB.id.asc())
            .all()
        )

        all_rows = load_uploaded_marks()
        exam_rows = [r for r in all_rows if (r.get("exam_name") or "").strip() == (exam_name or "").strip()]

        if not exam_rows:
            return {
                "count": 0,
                "items": [],
                "meta": {
                    "grade": grade,
                    "section": section,
                    "exam_name": exam_name,
                    "exam_id": exam_id_final,
                    "exam_date": None,
                    "max_score": None,
                    "subjects": subjects,
                },
            }

        def _safe_date(s: str) -> date:
            try:
                return _parse_exam_date(s)
            except Exception:
                return date(1900, 1, 1)

        latest_row = max(exam_rows, key=lambda r: _safe_date(r.get("exam_date", "")))
        latest_exam_date = latest_row.get("exam_date")
        latest_max_score = int(float(latest_row.get("max_score") or 100))

        # ✅ NEW: resolve exam_id from exams table if UI didn't send it
        if exam_id_final is None and latest_exam_date:
            exam_id_final = _resolve_exam_id(db, exam_name, str(latest_exam_date))

        rows_latest = [r for r in exam_rows if r.get("exam_date") == latest_exam_date]
        by_adm = {r.get("admission_no"): r for r in rows_latest}

        feedback_map: Dict[int, Dict[str, Any]] = {}
        if exam_id_final is not None:
            role = (getattr(user, "role", "") or "").lower()
            teacher_id = user.id if role == "teacher" else None

            q = (
                db.query(TeacherFeedback)
                .filter(TeacherFeedback.exam_id == exam_id_final)
                .filter(TeacherFeedback.student_id.in_([st.id for st in students]))
            )
            # teacher sees their feedback; fallback to legacy rows (NULL teacher_user_id)
            if teacher_id is not None and hasattr(TeacherFeedback, "teacher_user_id"):
                q = q.filter(
                    or_(
                        TeacherFeedback.teacher_user_id == teacher_id,
                        TeacherFeedback.teacher_user_id.is_(None),
                    )
                ).order_by(TeacherFeedback.teacher_user_id.desc())

            fb_rows = q.all()
            for fb in fb_rows:
                sid = int(fb.student_id)
                if sid in feedback_map:
                    continue
                feedback_map[sid] = {"remark": fb.remark, "note": fb.note}

        items: List[Dict[str, Any]] = []
        for s in students:
            r = by_adm.get(s.admission_no)
            scores_map = (r or {}).get("scores", {}) or {}
            fb = feedback_map.get(int(s.id), {}) if feedback_map else {}

            row_out: Dict[str, Any] = {
                "admission_no": s.admission_no,
                "student_id": int(s.id),  # ✅ NEW: so UI doesn't need /students mapping
                "student_name": s.name,
                "exam_name": exam_name,
                "exam_id": exam_id_final,  # ✅ NEW: always filled if resolvable
                "exam_date": latest_exam_date,
                "max_score": latest_max_score,
                "teacher_remark": (fb.get("remark") or "").strip(),
                "special_note": (fb.get("note") or "").strip(),
            }

            total = 0.0
            for sub in subjects:
                val = float(scores_map.get(sub, 0.0) or 0.0)
                row_out[sub] = val
                total += val

            row_out["total"] = total
            denom = float(latest_max_score * max(len(subjects), 1))
            row_out["percentage"] = round((total / denom) * 100.0, 2) if denom > 0 else 0.0

            items.append(row_out)

        return {
            "count": len(items),
            "items": items,
            "meta": {
                "grade": grade,
                "section": section,
                "exam_name": exam_name,
                "exam_id": exam_id_final,
                "exam_date": latest_exam_date,
                "max_score": latest_max_score,
                "subjects": subjects,
            },
        }

    finally:
        db.close()
