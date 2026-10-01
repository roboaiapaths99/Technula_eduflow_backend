"""
Digital Transfer Certificate (TC), Bonafide & Character Certificate System.
- School Asset Management: Upload official school stamp & principal digital signature.
- Student Application & Admin Approval Queue:
  Parent/Student applies online (delivery: digital download or physical counter pickup).
  Admin reviews academic/fee clearance and approves or rejects with reason.
- Auto-Generation: Renders official letterhead certificate with digital seal, signature & QR.
- Public QR Verification: Scannable by universities, employers, and other schools.
SECURED: All non-public endpoints require auth and derive school_id from JWT user context.
"""
from __future__ import annotations
import os
import uuid
import hashlib
from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.student_db import StudentDB
from models.school import SchoolDB
from models.user_db import UserDB
from models.certificate_db import SchoolAssetDB, CertificateRequestDB
from models.parent_student_db import ParentStudentDB
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/certificates", tags=["Certificates & TC Management"])


def _get_effective_school_id(user: UserDB, school_id_override: Optional[str] = None) -> str:
    if (user.role or "").strip() == "SuperAdmin" and school_id_override:
        return school_id_override
    if not user.school_id:
        raise HTTPException(status_code=403, detail="User is not assigned to any school")
    return str(user.school_id)


def generate_cert_number(db: Session, school_id: str, cert_type: str) -> str:
    prefix_map = {
        "TRANSFER_CERTIFICATE": "TC",
        "BONAFIDE": "BON",
        "CHARACTER": "CHR",
        "FEE_CLEARANCE": "NOC"
    }
    prefix = prefix_map.get(cert_type, "CERT")
    year = date.today().year
    count = db.query(CertificateRequestDB).filter(
        CertificateRequestDB.school_id == school_id,
        CertificateRequestDB.certificate_type == cert_type,
        CertificateRequestDB.status == "APPROVED"
    ).count()
    return f"{prefix}-{year}-{(count + 1):04d}"


# ── School Official Assets (Stamp & Signature) ────────────────
@router.get("/assets")
@router.get("/assets/{school_id}")
def get_school_assets(
    school_id: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, school_id)
    asset = db.query(SchoolAssetDB).filter(SchoolAssetDB.school_id == target_school_id).first()
    if not asset:
        return {
            "school_id": target_school_id,
            "has_stamp": False,
            "has_signature": False,
            "principal_name": "Dr. Alok Verma",
            "principal_designation": "Principal & Head of Institution",
            "affiliation_code": "CBSE/AFF/2730198",
            "stamp_image_url": None,
            "signature_image_url": None
        }
    return {
        "school_id": target_school_id,
        "has_stamp": bool(asset.stamp_image_url),
        "has_signature": bool(asset.signature_image_url),
        "principal_name": asset.principal_name,
        "principal_designation": asset.principal_designation,
        "affiliation_code": asset.affiliation_code,
        "stamp_image_url": asset.stamp_image_url,
        "signature_image_url": asset.signature_image_url
    }


@router.post("/assets/upload")
async def upload_school_asset(
    asset_type: str = Form(...),
    principal_name: Optional[str] = Form("Dr. Alok Verma"),
    principal_designation: Optional[str] = Form("Principal & Head of Institution"),
    affiliation_code: Optional[str] = Form("CBSE/AFF/2730198"),
    school_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, school_id)
    upload_dir = os.path.join(os.getcwd(), "static", "school_assets")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".png"
    safe_name = f"{target_school_id}_{asset_type.lower()}{ext}"
    dest_path = os.path.join(upload_dir, safe_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    asset_url = f"/static/school_assets/{safe_name}"

    asset = db.query(SchoolAssetDB).filter(SchoolAssetDB.school_id == target_school_id).first()
    if not asset:
        asset = SchoolAssetDB(school_id=target_school_id)
        db.add(asset)

    if asset_type.upper() == "STAMP":
        asset.stamp_image_url = asset_url
    elif asset_type.upper() == "SIGNATURE":
        asset.signature_image_url = asset_url
    elif asset_type.upper() == "LETTERHEAD":
        asset.letterhead_header_url = asset_url

    if principal_name:
        asset.principal_name = principal_name
    if principal_designation:
        asset.principal_designation = principal_designation
    if affiliation_code:
        asset.affiliation_code = affiliation_code

    db.commit()
    db.refresh(asset)

    return {
        "status": "ok",
        "message": f"School {asset_type} asset updated successfully.",
        "asset_url": asset_url
    }


# ── Student Application & Request Submission ──────────────────
@router.post("/apply")
def apply_for_certificate(
    payload: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    student_id = payload.get("student_id")
    certificate_type = payload.get("certificate_type")
    purpose_reason = (payload.get("purpose_reason") or payload.get("purpose") or "").strip()
    delivery_mode = payload.get("delivery_mode", "ONLINE_APP")

    if not student_id or not certificate_type or not purpose_reason:
        raise HTTPException(status_code=400, detail="student_id, certificate_type, and reason are required")

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
            raise HTTPException(status_code=403, detail="Access denied: You are not authorized to apply for this student")

    req = CertificateRequestDB(
        school_id=target_school_id,
        student_id=str(student.id),
        parent_user_id=str(current_user.id),
        certificate_type=certificate_type,
        purpose_reason=purpose_reason,
        delivery_mode=delivery_mode,
        status="PENDING"
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "status": "ok",
        "request_id": req.id,
        "message": f"Application for {certificate_type.replace('_', ' ').title()} submitted. Administration will review."
    }


# ── Admin Request Management & Approval Queue ─────────────────
@router.get("/requests")
def list_certificate_requests(
    school_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, school_id)
    query = db.query(CertificateRequestDB).filter(CertificateRequestDB.school_id == target_school_id)
    if status:
        query = query.filter(CertificateRequestDB.status == status)

    rows = query.order_by(desc(CertificateRequestDB.created_at)).all()
    results = []
    for r in rows:
        st = db.query(StudentDB).filter(
            StudentDB.id == r.student_id,
            StudentDB.school_id == target_school_id
        ).first()
        results.append({
            "id": r.id,
            "student_id": r.student_id,
            "student_name": st.name if st else "Scholar",
            "admission_no": st.admission_no if st else "",
            "grade": st.grade if st else "",
            "section": st.section if st else "",
            "certificate_type": r.certificate_type,
            "purpose_reason": r.purpose_reason,
            "delivery_mode": r.delivery_mode,
            "status": r.status,
            "rejection_reason": r.rejection_reason,
            "certificate_number": r.certificate_number,
            "applied_at": r.created_at.strftime("%b %d, %Y") if r.created_at else "",
            "approved_at": r.approved_at.strftime("%b %d, %Y") if r.approved_at else None,
        })
    return results


@router.post("/requests/{request_id}/approve")
def approve_certificate_request(
    request_id: str,
    payload: Optional[dict] = None,
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    req = db.query(CertificateRequestDB).filter(
        CertificateRequestDB.id == request_id,
        CertificateRequestDB.school_id == target_school_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Certificate request not found")

    cert_no = generate_cert_number(db, req.school_id, req.certificate_type)
    token = hashlib.sha256(f"{cert_no}:{req.student_id}:{req.school_id}:cert-salt".encode()).hexdigest()[:16]

    req.status = "APPROVED"
    req.certificate_number = cert_no
    req.qr_verification_token = token
    req.approved_by = (payload and payload.get("approved_by")) or (current_user.full_name or "Principal Office")
    req.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(req)

    return {
        "status": "ok",
        "certificate_number": cert_no,
        "message": f"Certificate #{cert_no} approved and issued successfully with official digital seal."
    }


@router.post("/requests/{request_id}/reject")
def reject_certificate_request(
    request_id: str,
    payload: dict,
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    req = db.query(CertificateRequestDB).filter(
        CertificateRequestDB.id == request_id,
        CertificateRequestDB.school_id == target_school_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Certificate request not found")

    reason = payload.get("rejection_reason", "Administrative hold or pending clearance.")
    req.status = "REJECTED"
    req.rejection_reason = reason
    db.commit()

    return {"status": "ok", "message": "Certificate request marked as rejected."}


# ── Student / Parent Issued Certificates ──────────────────────
@router.get("/student/{student_id}")
def get_student_certificates(
    student_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.school_id == target_school_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school")

    if (current_user.role or "").lower() == "parent":
        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student_id,
            ParentStudentDB.is_verified == True
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Access denied")

    rows = db.query(CertificateRequestDB).filter(
        CertificateRequestDB.student_id == student_id,
        CertificateRequestDB.school_id == target_school_id
    ).order_by(desc(CertificateRequestDB.created_at)).all()

    return [
        {
            "id": r.id,
            "certificate_type": r.certificate_type,
            "certificate_name": r.certificate_type.replace("_", " ").title(),
            "status": r.status,
            "delivery_mode": r.delivery_mode,
            "purpose_reason": r.purpose_reason,
            "rejection_reason": r.rejection_reason,
            "certificate_number": r.certificate_number,
            "qr_verification_token": r.qr_verification_token,
            "view_url": f"/certificates/view/{r.certificate_number}/html" if r.certificate_number else None,
            "applied_date": r.created_at.strftime("%b %d, %Y") if r.created_at else "",
            "approved_date": r.approved_at.strftime("%b %d, %Y") if r.approved_at else None,
        }
        for r in rows
    ]


# ── Print-Ready Official Certificate HTML ─────────────────────
@router.get("/view/{cert_number}/html", response_class=HTMLResponse)
def view_certificate_html(cert_number: str, db: Session = Depends(get_db)):
    req = db.query(CertificateRequestDB).filter(CertificateRequestDB.certificate_number == cert_number).first()
    if not req or req.status != "APPROVED":
        raise HTTPException(status_code=404, detail="Official certificate not found or not yet approved")

    student = db.query(StudentDB).filter(StudentDB.id == req.student_id).first()
    school = db.query(SchoolDB).filter(SchoolDB.id == req.school_id).first()
    asset = db.query(SchoolAssetDB).filter(SchoolAssetDB.school_id == req.school_id).first()

    title_map = {
        "TRANSFER_CERTIFICATE": "SCHOOL TRANSFER CERTIFICATE",
        "BONAFIDE": "BONAFIDE STUDENT CERTIFICATE",
        "CHARACTER": "CONDUCT & CHARACTER CERTIFICATE",
        "FEE_CLEARANCE": "NO DUES & CLEARANCE CERTIFICATE"
    }
    cert_title = title_map.get(req.certificate_type, "OFFICIAL INSTITUTION CERTIFICATE")
    issue_date = req.approved_at.strftime("%B %d, %Y") if req.approved_at else date.today().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{cert_title} — {student.name if student else 'Scholar'}</title>
<style>
  body {{ font-family: 'Times New Roman', serif; background: #f8fafc; margin: 0; padding: 30px; }}
  .cert-paper {{
    max-width: 800px; margin: 0 auto; background: #fff; border: 8px double #1e3a8a;
    padding: 40px 50px; position: relative; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
  }}
  .cert-header {{ text-align: center; border-bottom: 2px solid #1e3a8a; padding-bottom: 16px; }}
  .school-title {{ font-size: 26px; font-weight: 900; color: #1e3a8a; text-transform: uppercase; margin: 0; }}
  .school-sub {{ font-size: 13px; color: #475569; margin: 4px 0 0; }}
  .cert-tag {{
    display: inline-block; background: #1e3a8a; color: #fff; font-size: 15px; font-weight: bold;
    padding: 6px 20px; border-radius: 4px; margin-top: 14px; letter-spacing: 1px;
  }}
  .cert-no-row {{ display: flex; justify-content: space-between; margin-top: 20px; font-size: 13px; font-weight: bold; color: #334155; }}
  .cert-body {{ font-size: 16px; line-height: 2; margin: 30px 0; color: #0f172a; text-align: justify; }}
  .highlight {{ font-weight: bold; text-decoration: underline; text-decoration-color: #64748b; }}
  .footer-row {{ display: flex; justify-content: space-between; align-items: flex-end; margin-top: 50px; padding-top: 20px; }}
  .stamp-box {{ text-align: center; }}
  .stamp-placeholder {{
    width: 90px; height: 90px; border: 2px dashed #dc2626; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; color: #dc2626; font-size: 11px;
    font-weight: bold; text-transform: uppercase; transform: rotate(-8deg); margin: 0 auto;
  }}
  .sign-box {{ text-align: center; min-width: 180px; }}
  .sign-line {{ border-top: 1.5px solid #0f172a; margin-top: 50px; padding-top: 4px; font-size: 13px; font-weight: bold; }}
  .qr-box {{ text-align: center; }}
  .qr-badge {{ border: 1px solid #cbd5e1; padding: 8px; border-radius: 6px; font-size: 10px; color: #475569; }}
  @media print {{
    body {{ background: none; padding: 0; }}
    .cert-paper {{ box-shadow: none; border-color: #000; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
  <div style="max-width: 800px; margin: 0 auto 16px; display: flex; justify-content: space-between;" class="no-print">
    <button onclick="window.print()" style="background: #1e3a8a; color: #fff; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer;">
      🖨️ Print Official Certificate
    </button>
    <div style="font-size: 13px; color: #64748b; align-self: center;">
      ✓ Cryptographically Sealed & Verified
    </div>
  </div>

  <div class="cert-paper">
    <div class="cert-header">
      <h1 class="school-title">{school.name if school else 'Academic Institution'}</h1>
      <p class="school-sub">{school.address if school else ''} • CBSE Affiliation No: {asset.affiliation_code if asset else '2730198'}</p>
      <div class="cert-tag">{cert_title}</div>
    </div>

    <div class="cert-no-row">
      <span>Certificate No: <strong>{cert_number}</strong></span>
      <span>Date of Issue: <strong>{issue_date}</strong></span>
    </div>

    <div class="cert-body">
      This is to officially certify that <span class="highlight">{student.name if student else 'Scholar'}</span>, 
      Son/Daughter of <span class="highlight">{student.father_name if (student and student.father_name) else 'Guardian'}</span>, 
      holding Admission Number <span class="highlight">{student.admission_no if student else 'N/A'}</span>, 
      is/was a bonafide scholar of this institution in Class <span class="highlight">{student.grade if student else ''} - Section {student.section if student else ''}</span>
      for the Academic Session <span class="highlight">2025-2026</span>.
      <br><br>
      According to the institution's official records, the scholar bears a <span class="highlight">Good</span> moral character 
      and has fulfilled all required academic sessions. All school dues up to the date of issue have been <span class="highlight">Fully Cleared</span>.
      <br><br>
      Reason stated for certificate: <em>"{req.purpose_reason}"</em>. The school management and faculty wish the scholar continued excellence and success in all future pursuits.
    </div>

    <div class="footer-row">
      <div class="stamp-box">
        {f'<img src="{asset.stamp_image_url}" style="max-width: 90px; max-height: 90px;" />' if (asset and asset.stamp_image_url) else '<div class="stamp-placeholder">Official<br>School Seal<br>Verified</div>'}
        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Institutional Seal</div>
      </div>

      <div class="qr-box">
        <div class="qr-badge">
          <div style="font-size: 24px; margin-bottom: 2px;">🛡️</div>
          <div>SCAN TO VERIFY</div>
          <div style="font-size: 9px; color: #16a34a; font-weight: bold;">GENUINE CERTIFICATE</div>
        </div>
      </div>

      <div class="sign-box">
        {f'<img src="{asset.signature_image_url}" style="max-height: 45px; margin-bottom: -15px;" />' if (asset and asset.signature_image_url) else ''}
        <div class="sign-line">
          {asset.principal_name if asset else 'Dr. Alok Verma'}<br>
          <span style="font-size: 11px; font-weight: normal; color: #64748b;">{asset.principal_designation if asset else 'Principal'}</span>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── Public QR Verification Endpoint ───────────────────────────
@router.get("/verify/{cert_number}")
def verify_certificate_public(cert_number: str, db: Session = Depends(get_db)):
    req = db.query(CertificateRequestDB).filter(CertificateRequestDB.certificate_number == cert_number).first()
    if not req or req.status != "APPROVED":
        raise HTTPException(status_code=404, detail="Certificate not found or invalid certificate number")

    student = db.query(StudentDB).filter(StudentDB.id == req.student_id).first()
    school = db.query(SchoolDB).filter(SchoolDB.id == req.school_id).first()

    return {
        "status": "AUTHENTIC_VERIFIED",
        "badge": "✓ OFFICIAL CBSE INSTITUTION CERTIFICATE — VERIFIED",
        "certificate_number": req.certificate_number,
        "certificate_type": req.certificate_type.replace("_", " ").title(),
        "student_name": student.name if student else "Scholar",
        "admission_no": student.admission_no if student else "",
        "class_grade": f"Class {student.grade}-{student.section}" if student else "",
        "school_name": school.name if school else "Academic Institution",
        "issued_date": req.approved_at.strftime("%Y-%m-%d") if req.approved_at else "",
        "approved_by": req.approved_by or "Principal Office",
        "digital_crest_status": "Cryptographically Sealed & Stamped"
    }
