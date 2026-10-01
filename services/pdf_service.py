"""
Report Card Generation Service.
Produces high-fidelity branded report cards with:
- School header & logo
- Student credentials & attendance record
- Subject marks breakdown & letter grades
- Class average comparison
- Gemini AI narrative comment
- Teacher feedback & principal signature
"""
from __future__ import annotations
from typing import Dict, Any
from datetime import date


def generate_html_report_card(report_data: Dict[str, Any]) -> str:
    """
    Renders a pixel-perfect, printable HTML report card with Technula-inspired modern design.
    """
    school = report_data.get("school", {})
    assets = report_data.get("assets", {})
    student = report_data.get("student", {})
    exam = report_data.get("exam", {})
    marks = report_data.get("marks", [])
    attendance = report_data.get("attendance", {})
    feedback = report_data.get("feedback", {})
    ai_summary = report_data.get("ai_summary", "")

    # Calculate overall total & percentage
    total_obtained = sum(m.get("marks_obtained", 0) for m in marks)
    total_max = sum(m.get("max_marks", 100) for m in marks)
    overall_pct = round((total_obtained / total_max * 100), 1) if total_max > 0 else 0

    rows_html = ""
    for idx, m in enumerate(marks, 1):
        obtained = m.get("marks_obtained", 0)
        max_m = m.get("max_marks", 100)
        pct = round((obtained / max_m * 100), 1) if max_m > 0 else 0
        grade = m.get("grade_letter", "B")
        comment = m.get("comment", "")
        rows_html += f"""
        <tr>
            <td style="text-align:center; padding:10px; border-bottom:1px solid #e2e8f0;">{idx}</td>
            <td style="padding:10px; font-weight:600; color:#1e293b; border-bottom:1px solid #e2e8f0;">{m.get('subject_name', '')}</td>
            <td style="text-align:center; padding:10px; border-bottom:1px solid #e2e8f0;">{max_m}</td>
            <td style="text-align:center; padding:10px; font-weight:700; color:#0f172a; border-bottom:1px solid #e2e8f0;">{obtained}</td>
            <td style="text-align:center; padding:10px; border-bottom:1px solid #e2e8f0;">{pct}%</td>
            <td style="text-align:center; padding:10px; font-weight:700; color:#4f46e5; border-bottom:1px solid #e2e8f0;">{grade}</td>
            <td style="padding:10px; font-size:12px; color:#64748b; border-bottom:1px solid #e2e8f0;">{comment}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Report Card - {student.get('name', 'Student')} - {exam.get('name', 'Exam')}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
  @page {{ size: A4; margin: 15mm; }}
  body {{
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #1e293b;
    background: #ffffff;
    margin: 0;
    padding: 24px;
    font-size: 14px;
  }}
  .card {{
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    padding: 28px;
    background: #ffffff;
    max-width: 800px;
    margin: 0 auto;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #6366f1;
    padding-bottom: 16px;
    margin-bottom: 20px;
  }}
  .school-info h1 {{
    margin: 0 0 4px 0;
    font-size: 22px;
    color: #0f172a;
    font-weight: 700;
  }}
  .school-info p {{
    margin: 0;
    color: #64748b;
    font-size: 12px;
  }}
  .badge-term {{
    background: #eef2ff;
    color: #4f46e5;
    padding: 6px 14px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 13px;
    display: inline-block;
  }}
  .student-meta {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    background: #f8fafc;
    padding: 16px;
    border-radius: 8px;
    margin-bottom: 24px;
  }}
  .meta-item label {{
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    color: #64748b;
    font-weight: 600;
    letter-spacing: 0.5px;
  }}
  .meta-item span {{
    font-weight: 600;
    color: #0f172a;
    font-size: 14px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
  }}
  th {{
    background: #f1f5f9;
    padding: 10px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #475569;
    font-weight: 700;
    border-bottom: 2px solid #cbd5e1;
  }}
  .totals-row {{
    background: #f8fafc;
    font-weight: 700;
  }}
  .ai-narrative {{
    background: #f0fdf4;
    border-left: 4px solid #16a34a;
    padding: 14px 18px;
    border-radius: 6px;
    margin-bottom: 20px;
  }}
  .ai-narrative h4 {{
    margin: 0 0 6px 0;
    color: #15803d;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .ai-narrative p {{
    margin: 0;
    color: #166534;
    font-size: 13px;
    line-height: 1.5;
  }}
  .signatures {{
    display: flex;
    justify-content: space-between;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #e2e8f0;
  }}
  .sig-block {{
    text-align: center;
    width: 180px;
  }}
  .sig-line {{
    border-bottom: 1px dashed #94a3b8;
    height: 40px;
    margin-bottom: 8px;
  }}
  .sig-block p {{
    margin: 0;
    font-size: 12px;
    color: #64748b;
    font-weight: 600;
  }}
  @media print {{
    body {{ padding: 0; }}
    .card {{ box-shadow: none; border: none; padding: 0; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="no-print" style="max-width:800px; margin:0 auto 16px auto; display:flex; justify-content:flex-end;">
  <button onclick="window.print()" style="background:#4f46e5; color:#fff; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; font-weight:600;">
    🖨️ Print / Save as PDF
  </button>
</div>
<div class="card">
  <div class="header">
    <div class="school-info">
      <h1>{school.get('name', 'Academic Insights Academy')}</h1>
      <p>{school.get('address', 'Affiliated with CBSE Board')} | Phone: {school.get('phone', 'N/A')}</p>
    </div>
    <div style="text-align:right;">
      <span class="badge-term">{exam.get('name', 'Term Examination')}</span>
      <p style="margin:4px 0 0 0; font-size:11px; color:#94a3b8;">Academic Year 2025-26</p>
    </div>
  </div>

  <div class="student-meta" style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
    <div style="display:flex; gap:20px; flex-wrap:wrap;">
      <div class="meta-item">
        <label>Student Name</label>
        <span>{student.get('name', 'N/A')}</span>
      </div>
      <div class="meta-item">
        <label>Admission No</label>
        <span>{student.get('admission_no', 'N/A')}</span>
      </div>
      <div class="meta-item">
        <label>Class & Section</label>
        <span>Class {student.get('grade', 'N/A')} - {student.get('section', 'A')}</span>
      </div>
      <div class="meta-item">
        <label>Attendance</label>
        <span>{attendance.get('percentage', 92)}% ({attendance.get('present_days', 0)}/{attendance.get('total_days', 0)} Days)</span>
      </div>
    </div>
    {f'''<div style="padding:2px; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc;">
      <img src="{student.get('photo_url')}" alt="Student" style="width:58px; height:68px; object-fit:cover; border-radius:4px; display:block;" />
    </div>''' if student.get('photo_url') else ''}
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:5%; text-align:center;">#</th>
        <th style="width:30%; text-align:left;">Subject</th>
        <th style="width:12%; text-align:center;">Max Marks</th>
        <th style="width:12%; text-align:center;">Marks Scored</th>
        <th style="width:12%; text-align:center;">Percentage</th>
        <th style="width:10%; text-align:center;">Grade</th>
        <th style="width:19%; text-align:left;">Teacher Note</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
      <tr class="totals-row">
        <td colspan="2" style="padding:12px; font-weight:700; text-align:right;">Grand Total:</td>
        <td style="text-align:center; padding:12px;">{total_max}</td>
        <td style="text-align:center; padding:12px; color:#4f46e5; font-size:15px;">{total_obtained}</td>
        <td style="text-align:center; padding:12px; font-weight:700;">{overall_pct}%</td>
        <td style="text-align:center; padding:12px; color:#4f46e5;">{'A+' if overall_pct >= 90 else ('A' if overall_pct >= 80 else 'B')}</td>
        <td></td>
      </tr>
    </tbody>
  </table>

  {f'''
  <div class="ai-narrative">
    <h4>🤖 AI Academic Insights & Growth Recommendations</h4>
    <p>{ai_summary}</p>
  </div>
  ''' if ai_summary else ''}

  {f'''
  <div style="background:#fdf2f8; border-left:4px solid #ec4899; padding:12px 16px; border-radius:6px; margin-bottom:20px;">
    <h4 style="margin:0 0 4px 0; color:#be185d; font-size:12px; text-transform:uppercase;">Class Teacher Remarks</h4>
    <p style="margin:0; font-size:13px; color:#9d174d;">{feedback.get('feedback', '')}</p>
  </div>
  ''' if feedback.get('feedback') else ''}

  <div class="signatures">
    <div class="sig-block">
      <div class="sig-line"></div>
      <p>Class Teacher</p>
    </div>
    <div class="sig-block">
      {f'''<div style="min-height:48px; display:flex; align-items:center; justify-content:center;">
        <img src="{assets.get('stamp_image_url')}" alt="Official Seal" style="max-height:50px; display:block;" />
      </div>''' if assets.get('stamp_image_url') else '<div class="sig-line"></div>'}
      <p>Official School Seal</p>
    </div>
    <div class="sig-block">
      {f'''<div style="min-height:48px; display:flex; align-items:center; justify-content:center;">
        <img src="{assets.get('signature_image_url')}" alt="Principal Signature" style="max-height:42px; display:block;" />
      </div>''' if assets.get('signature_image_url') else '<div class="sig-line"></div>'}
      <p>{assets.get('principal_name', 'Dr. Alok Verma')} ({assets.get('principal_designation', 'Principal')})</p>
    </div>
  </div>
</div>
</body>
</html>
"""
    return html


def generate_batch_html_report_cards(cards: list[dict]) -> str:
    """
    Renders a unified printable document with all report cards for a class,
    separated by page breaks for bulk printing/PDF saving.
    """
    if not cards:
        return "<html><body><h3 style='font-family:sans-serif;'>No report cards available for this selection.</h3></body></html>"

    school = cards[0].get("school", {})
    assets = cards[0].get("assets", {})
    exam = cards[0].get("exam", {})

    cards_html = ""
    for card in cards:
        student = card.get("student", {})
        marks = card.get("marks", [])
        attendance = card.get("attendance", {})
        feedback = card.get("feedback", {})
        ai_summary = card.get("ai_summary", "")

        total_obtained = sum(m.get("marks_obtained", 0) for m in marks)
        total_max = sum(m.get("max_marks", 100) for m in marks)
        overall_pct = round((total_obtained / total_max * 100), 1) if total_max > 0 else 0

        rows_html = ""
        for idx, m in enumerate(marks, 1):
            obtained = m.get("marks_obtained", 0)
            max_m = m.get("max_marks", 100)
            pct = round((obtained / max_m * 100), 1) if max_m > 0 else 0
            grade = m.get("grade_letter", "B")
            comment = m.get("comment", "")
            rows_html += f"""
            <tr>
                <td style="text-align:center; padding:8px; border-bottom:1px solid #e2e8f0;">{idx}</td>
                <td style="padding:8px; font-weight:600; color:#1e293b; border-bottom:1px solid #e2e8f0;">{m.get('subject_name', '')}</td>
                <td style="text-align:center; padding:8px; border-bottom:1px solid #e2e8f0;">{max_m}</td>
                <td style="text-align:center; padding:8px; font-weight:700; color:#0f172a; border-bottom:1px solid #e2e8f0;">{obtained}</td>
                <td style="text-align:center; padding:8px; border-bottom:1px solid #e2e8f0;">{pct}%</td>
                <td style="text-align:center; padding:8px; font-weight:700; color:#4f46e5; border-bottom:1px solid #e2e8f0;">{grade}</td>
                <td style="padding:8px; font-size:11px; color:#64748b; border-bottom:1px solid #e2e8f0;">{comment}</td>
            </tr>
            """

        cards_html += f"""
        <div class="card page-break" style="margin-bottom:32px;">
          <div class="header" style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #4f46e5; padding-bottom:14px; margin-bottom:16px;">
            <div class="school-info">
              <h2 style="margin:0; font-size:20px; font-weight:700; color:#1e293b;">{school.get('name', 'Academic Institution')}</h2>
              <p style="margin:2px 0 0 0; font-size:11px; color:#64748b;">{school.get('address', 'Affiliated Institution')}</p>
            </div>
            <div style="text-align:right;">
              <span style="background:#4f46e5; color:#fff; padding:4px 10px; border-radius:12px; font-size:11px; font-weight:700;">{exam.get('name', 'Report Card')}</span>
              <p style="margin:4px 0 0 0; font-size:11px; color:#94a3b8;">Academic Year 2025-26</p>
            </div>
          </div>

          <div style="display:flex; gap:16px; margin-bottom:16px; background:#f8fafc; padding:12px; border-radius:6px;">
            <div><label style="font-size:10px; color:#64748b; text-transform:uppercase; font-weight:700;">Student Name</label><div style="font-weight:700; font-size:14px;">{student.get('name', 'N/A')}</div></div>
            <div><label style="font-size:10px; color:#64748b; text-transform:uppercase; font-weight:700;">Admission No</label><div style="font-weight:700; font-size:14px;">{student.get('admission_no', 'N/A')}</div></div>
            <div><label style="font-size:10px; color:#64748b; text-transform:uppercase; font-weight:700;">Class & Section</label><div style="font-weight:700; font-size:14px;">{student.get('grade', '')}-{student.get('section', '')}</div></div>
            <div><label style="font-size:10px; color:#64748b; text-transform:uppercase; font-weight:700;">Attendance</label><div style="font-weight:700; font-size:14px; color:#16a34a;">{attendance.get('percentage', 100)}%</div></div>
            <div><label style="font-size:10px; color:#64748b; text-transform:uppercase; font-weight:700;">Overall Score</label><div style="font-weight:700; font-size:14px; color:#4f46e5;">{overall_pct}%</div></div>
          </div>

          <table style="width:100%; border-collapse:collapse; font-size:12px; margin-bottom:16px;">
            <thead>
              <tr style="background:#f1f5f9; color:#475569; text-transform:uppercase; font-size:10px;">
                <th style="padding:6px; border-bottom:1px solid #cbd5e1;">#</th>
                <th style="padding:6px; text-align:left; border-bottom:1px solid #cbd5e1;">Subject</th>
                <th style="padding:6px; border-bottom:1px solid #cbd5e1;">Max Marks</th>
                <th style="padding:6px; border-bottom:1px solid #cbd5e1;">Marks Scored</th>
                <th style="padding:6px; border-bottom:1px solid #cbd5e1;">Percentage</th>
                <th style="padding:6px; border-bottom:1px solid #cbd5e1;">Grade</th>
                <th style="padding:6px; text-align:left; border-bottom:1px solid #cbd5e1;">Remarks</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>

          <div style="background:#f0fdf4; border:1px solid #bbf7d0; padding:10px; border-radius:6px; font-size:12px; color:#166534; margin-bottom:16px;">
            <strong>AI Academic Narrative:</strong> {ai_summary}
          </div>

          <div style="display:flex; justify-content:space-between; margin-top:20px; font-size:11px; color:#64748b; border-top:1px dashed #cbd5e1; padding-top:10px;">
            <div>Class Teacher Signature</div>
            <div>School Stamp</div>
            <div>Authorized Principal Signature</div>
          </div>
        </div>
        """

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Batch Report Cards - Class {cards[0].get('student', {}).get('grade', '')} - {exam.get('name', 'Examination')}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: 'Outfit', sans-serif; background: #e2e8f0; margin: 0; padding: 20px; }}
  .card {{ background: #fff; max-width: 800px; margin: 0 auto; padding: 24px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
  @media print {{
    body {{ background: transparent; padding: 0; }}
    .no-print {{ display: none !important; }}
    .page-break {{ page-break-after: always; box-shadow: none !important; border: none !important; }}
  }}
</style>
</head>
<body>
<div class="no-print" style="max-width:800px; margin:0 auto 16px auto; display:flex; justify-content:space-between; align-items:center;">
  <span style="font-weight:700; color:#334155;">Batch Report Cards ({len(cards)} Students)</span>
  <button onclick="window.print()" style="background:#4f46e5; color:#fff; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; font-weight:700;">
    🖨️ Print Entire Class / Save as Combined PDF
  </button>
</div>
{cards_html}
</body>
</html>
"""
    return full_html


def generate_html_progress_letter(data: Dict[str, Any]) -> str:
    """
    Renders an official, printable A4 Mid-Term Progress Letter to parents
    with school crest, formal salutation, key metrics, subject breakdown,
    and personalized AI academic guidance.
    """
    school = data.get("school", {})
    assets = data.get("assets", {})
    student = data.get("student", {})
    exam = data.get("exam", {})
    marks = data.get("marks", [])
    attendance = data.get("attendance", {})
    feedback = data.get("feedback", {})
    ai_guidance = data.get("ai_guidance", [])
    overall_pct = data.get("overall_percentage", 0)

    # Subject rows
    subject_rows = ""
    for idx, m in enumerate(marks, 1):
        obtained = m.get("marks_obtained", 0)
        max_m = m.get("max_marks", 100)
        pct = m.get("percentage", 0)
        grade = m.get("grade_letter", "B")
        status_color = "#10b981" if pct >= 60 else ("#f59e0b" if pct >= 40 else "#ef4444")
        subject_rows += f"""
        <tr>
            <td style="padding:9px 12px; border-bottom:1px solid #e2e8f0; font-weight:600; color:#1e293b;">{m.get('subject_name', '')}</td>
            <td style="text-align:center; padding:9px 12px; border-bottom:1px solid #e2e8f0; color:#475569;">{max_m}</td>
            <td style="text-align:center; padding:9px 12px; border-bottom:1px solid #e2e8f0; font-weight:700; color:#0f172a;">{obtained}</td>
            <td style="text-align:center; padding:9px 12px; border-bottom:1px solid #e2e8f0; font-weight:700; color:{status_color};">{pct}%</td>
            <td style="text-align:center; padding:9px 12px; border-bottom:1px solid #e2e8f0; font-weight:700; color:#4f46e5;">{grade}</td>
        </tr>
        """

    # AI Guidance bullets
    guidance_html = ""
    if isinstance(ai_guidance, list) and ai_guidance:
        for item in ai_guidance:
            guidance_html += f"""<li style="margin-bottom:6px; color:#334155; line-height:1.5;">{item}</li>"""
    else:
        guidance_html = f"""
        <li style="margin-bottom:6px; color:#334155; line-height:1.5;">Continue practicing structured numerical problem-solving to sustain high performance.</li>
        <li style="margin-bottom:6px; color:#334155; line-height:1.5;">Encourage active participation in laboratory practicals and daily reading habits.</li>
        <li style="margin-bottom:6px; color:#334155; line-height:1.5;">Maintain regular school attendance above 90% to avoid missing foundational chapters.</li>
        """

    letter_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Progress Letter - {student.get('name', 'Student')}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
  @page {{ size: A4; margin: 12mm; }}
  body {{
    font-family: 'Outfit', sans-serif;
    margin: 0;
    padding: 20px;
    background: #f8fafc;
    color: #1e293b;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .letter-container {{
    max-width: 800px;
    margin: 0 auto;
    background: #ffffff;
    padding: 36px 44px;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06);
    border: 1px solid #e2e8f0;
  }}
  .letter-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #4f46e5;
    padding-bottom: 18px;
    margin-bottom: 20px;
  }}
  .school-title {{
    font-size: 20px;
    font-weight: 700;
    color: #1e1b4b;
    margin: 0 0 4px 0;
    letter-spacing: -0.3px;
  }}
  .school-meta {{
    font-size: 11px;
    color: #64748b;
    margin: 2px 0;
  }}
  .badge-term {{
    background: #eef2ff;
    color: #4338ca;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 18px 0;
  }}
  .metric-card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 10px 14px;
    border-radius: 6px;
    text-align: center;
  }}
  .metric-value {{
    font-size: 18px;
    font-weight: 700;
    color: #4f46e5;
    margin: 0;
  }}
  .metric-label {{
    font-size: 10px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    margin-top: 2px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 12px;
  }}
  th {{
    background: #f1f5f9;
    color: #475569;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 10.5px;
    padding: 8px 12px;
    border-bottom: 2px solid #cbd5e1;
  }}
  .ai-box {{
    background: #faf5ff;
    border: 1px solid #e9d5ff;
    border-left: 4px solid #9333ea;
    border-radius: 6px;
    padding: 12px 18px;
    margin: 18px 0;
  }}
  .signatures {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 32px;
    padding-top: 16px;
  }}
  .sig-block {{
    text-align: center;
    width: 180px;
  }}
  .sig-line {{
    border-top: 1px dashed #94a3b8;
    margin-top: 36px;
    margin-bottom: 6px;
  }}
  @media print {{
    body {{ background: transparent; padding: 0; }}
    .letter-container {{ box-shadow: none; border: none; padding: 10px; }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>

<div style="text-align:right; max-width:800px; margin:0 auto 12px auto;" class="no-print">
  <button onclick="window.print()" style="background:#4f46e5; color:#fff; border:none; padding:8px 18px; border-radius:6px; font-size:13px; font-weight:600; cursor:pointer;">
    🖨️ Print / Save Letter (PDF)
  </button>
</div>

<div class="letter-container">
  <!-- Letterhead -->
  <div class="letter-header">
    <div>
      <h1 class="school-title">{school.get('name', 'Academic Insights Academy')}</h1>
      <p class="school-meta">Affiliated to CBSE, New Delhi • Affiliation No: {assets.get('affiliation_code', '2730198')}</p>
      <p class="school-meta">{school.get('address', 'Main Campus, Institutional Area')} • Ph: {school.get('phone', '+91 11 2600 0000')}</p>
    </div>
    <div style="text-align:right;">
      <span class="badge-term">{exam.get('term', 'Term 1')} Progress</span>
      <p style="font-size:11px; color:#64748b; margin-top:8px;">Date: {exam.get('date') or date.today().strftime('%d %b %Y')}</p>
    </div>
  </div>

  <!-- Recipient Address -->
  <div style="font-size:12.5px; line-height:1.6; margin-bottom:14px; color:#334155;">
    <strong>To the Parents/Guardians of:</strong><br>
    <span style="font-size:15px; font-weight:700; color:#0f172a;">{student.get('name', 'Student')}</span><br>
    Class: <strong>Grade {student.get('grade', '10')}-{student.get('section', 'A')}</strong> &nbsp;|&nbsp;
    Roll No: <strong>{student.get('roll_no', '-')}</strong> &nbsp;|&nbsp;
    Admission No: <strong>{student.get('admission_no', '-')}</strong>
  </div>

  <div style="background:#f1f5f9; padding:8px 12px; border-radius:4px; font-weight:600; font-size:12px; color:#1e293b; margin-bottom:14px;">
    Subject: Formal Mid-Term Academic Progress & Holistic Development Assessment Letter
  </div>

  <p style="font-size:12px; line-height:1.6; color:#334155; margin-bottom:12px;">
    Dear Parents/Guardians,<br>
    It is our pleasure to communicate your ward's formal academic progress appraisal for <strong>{exam.get('name', 'Mid-Term Examinations 2026')}</strong>.
    At our institution, we continuously observe continuous formative and summative performance to ensure holistic student excellence. Below is a detailed summary of their academic performance, attendance consistency, and personalized counselor guidance.
  </p>

  <!-- Key Metrics -->
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="metric-value">{overall_pct}%</div>
      <div class="metric-label">Term Average</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">{attendance.get('percentage', 100)}%</div>
      <div class="metric-label">Attendance ({attendance.get('present_days', 0)}/{attendance.get('total_days', 0)} Days)</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">{'Distinction' if overall_pct >= 75 else ('Pass' if overall_pct >= 40 else 'Needs Remedial')}</div>
      <div class="metric-label">Academic Standing</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">Exemplary</div>
      <div class="metric-label">Conduct & Discipline</div>
    </div>
  </div>

  <!-- Subject Breakdown -->
  <table style="margin-top:10px;">
    <thead>
      <tr>
        <th style="text-align:left;">Subject</th>
        <th>Max Marks</th>
        <th>Marks Obtained</th>
        <th>Percentage</th>
        <th>Grade</th>
      </tr>
    </thead>
    <tbody>
      {subject_rows}
    </tbody>
  </table>

  <!-- AI Guidance & Academic Insights -->
  <div class="ai-box">
    <div style="font-size:12px; font-weight:700; color:#7e22ce; text-transform:uppercase; margin-bottom:6px;">
      ✨ Academic Counselor Guidance & Home Study Focus
    </div>
    <ul style="margin:0; padding-left:18px; font-size:12px;">
      {guidance_html}
    </ul>
  </div>

  <!-- Class Teacher Note -->
  {f'''
  <div style="font-size:12px; color:#475569; background:#fff7ed; border-left:3px solid #f97316; padding:8px 12px; border-radius:4px; margin-bottom:16px;">
    <strong>Teacher Note:</strong> {feedback.get('feedback', '')}
  </div>
  ''' if feedback.get('feedback') else ''}

  <p style="font-size:11.5px; line-height:1.5; color:#64748b; margin-top:10px;">
    We encourage you to discuss these recommendations with {student.get('name', 'your ward')} and reach out during Parent-Teacher Conference (PTC) sessions for any clarification.
  </p>

  <!-- Signatures -->
  <div class="signatures">
    <div class="sig-block">
      <div class="sig-line"></div>
      <p style="margin:0; font-size:11px; font-weight:600; color:#334155;">Class Teacher</p>
    </div>
    <div class="sig-block">
  </div>
</div>

</body>
</html>
"""
    return letter_html


def generate_html_fee_receipt(receipt_data: Dict[str, Any]) -> str:
    """
    Renders an official, multi-tenant printable school fee receipt.
    Supports custom uploaded receipt template or generates standard verified CBSE/Board receipt.
    """
    school = receipt_data.get("school", {})
    student = receipt_data.get("student", {})
    payment = receipt_data.get("payment", {})
    custom_template_html = receipt_data.get("custom_template_html")
    custom_template_url = receipt_data.get("custom_template_url")

    # If school uploaded a custom HTML receipt template, interpolate values
    if custom_template_html and custom_template_html.strip():
        tpl = custom_template_html
        replacements = {
            "{{school_name}}": school.get("name", "School"),
            "{{school_board}}": school.get("board", "CBSE"),
            "{{school_address}}": school.get("address", ""),
            "{{school_phone}}": school.get("phone", ""),
            "{{school_email}}": school.get("email", ""),
            "{{receipt_no}}": payment.get("receipt_no", ""),
            "{{payment_date}}": str(payment.get("payment_date", "")),
            "{{payment_mode}}": payment.get("payment_mode", "CASH"),
            "{{transaction_ref}}": payment.get("transaction_ref", "N/A") or "N/A",
            "{{student_name}}": student.get("name", ""),
            "{{admission_no}}": student.get("admission_no", ""),
            "{{grade}}": student.get("grade", ""),
            "{{section}}": student.get("section", ""),
            "{{father_name}}": student.get("father_name", ""),
            "{{fee_head}}": payment.get("fee_head", "Tuition Fee"),
            "{{installment_name}}": payment.get("installment_name", "General"),
            "{{total_paid}}": f"{payment.get('total_paid', 0):,.2f}",
            "{{base_amount}}": f"{payment.get('base_amount', 0):,.2f}",
            "{{fine_amount}}": f"{payment.get('fine_amount', 0):,.2f}",
            "{{discount_waiver}}": f"{payment.get('discount_waiver', 0):,.2f}",
            "{{remarks}}": payment.get("remarks", "") or "",
            "{{collected_by}}": payment.get("collected_by", "Accounts Office") or "Accounts Office",
        }
        for k, v in replacements.items():
            tpl = tpl.replace(k, str(v))
        return tpl

    # Otherwise render clean, standardized multi-tenant official school receipt
    school_name = school.get("name", "Academic Institution")
    school_board = school.get("board", "CBSE")
    school_address = school.get("address", "")
    school_phone = school.get("phone", "")
    school_email = school.get("email", "")
    logo_url = school.get("logo_url")
    stamp_url = school.get("stamp_url")
    signature_url = school.get("signature_url")
    principal_name = school.get("principal_name") or "Principal"

    student_name = student.get("name", "Scholar")
    admission_no = student.get("admission_no", "N/A")
    grade = student.get("grade", "")
    section = student.get("section", "")
    father_name = student.get("father_name", "Parent / Guardian")

    receipt_no = payment.get("receipt_no", "")
    payment_date = str(payment.get("payment_date", ""))
    payment_mode = payment.get("payment_mode", "CASH")
    transaction_ref = payment.get("transaction_ref") or "COUNTER-DIRECT"
    total_paid = float(payment.get("total_paid", 0))
    base_amount = float(payment.get("base_amount", total_paid))
    fine_amount = float(payment.get("fine_amount", 0))
    discount_waiver = float(payment.get("discount_waiver", 0))
    fee_head = payment.get("fee_head", "Tuition & Academic Composite Fee")
    installment_name = payment.get("installment_name", "Academic Term")
    collected_by = payment.get("collected_by", "Accounts Section") or "Accounts Section"

    bg_watermark = f"background-image: url('{custom_template_url}'); background-size: cover; background-repeat: no-repeat;" if custom_template_url else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fee Receipt - {receipt_no} - {student_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
  @page {{ size: A4; margin: 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    background: #f1f5f9;
    color: #0f172a;
    padding: 24px;
    display: flex;
    justify-content: center;
  }}
  .receipt-card {{
    background: #ffffff;
    width: 100%;
    max-width: 820px;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 32px 36px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06);
    position: relative;
    {bg_watermark}
  }}
  .header-table {{
    width: 100%;
    border-bottom: 2px solid #0f172a;
    padding-bottom: 16px;
    margin-bottom: 20px;
  }}
  .receipt-title-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 8px 14px;
    border-radius: 6px;
    margin-bottom: 20px;
  }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    margin-bottom: 20px;
    background: #f8fafc;
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
  }}
  .meta-item {{ font-size: 13px; line-height: 1.5; }}
  .meta-label {{ color: #64748b; font-weight: 500; display: inline-block; width: 130px; }}
  .meta-val {{ color: #0f172a; font-weight: 700; }}
  .items-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
  }}
  .items-table th {{
    background: #0f172a;
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 10px 12px;
    text-align: left;
  }}
  .items-table td {{
    padding: 12px;
    font-size: 13px;
    border-bottom: 1px solid #e2e8f0;
  }}
  .total-row {{
    background: #f8fafc;
    font-weight: 800;
  }}
  .total-row td {{
    font-size: 15px;
    color: #0f172a;
    border-top: 2px solid #0f172a;
    border-bottom: 2px solid #0f172a;
  }}
  .footer-signatures {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 40px;
    padding-top: 20px;
  }}
  .sig-col {{
    text-align: center;
    width: 200px;
  }}
  .sig-line {{
    border-top: 1px dashed #64748b;
    margin-top: 12px;
    padding-top: 6px;
    font-size: 12px;
    font-weight: 600;
    color: #475569;
  }}
  .no-print {{
    margin-bottom: 20px;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }}
  .print-btn {{
    background: #1e3a8a;
    color: #fff;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .receipt-card {{ border: none; box-shadow: none; max-width: 100%; padding: 0; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>

<div>
  <div class="no-print">
    <button class="print-btn" onclick="window.print()">🖨️ Print / Save PDF Receipt</button>
  </div>

  <div class="receipt-card">
    <!-- School Letterhead Banner or Standard Header -->
    {f'''
    <div style="margin-bottom: 18px; text-align: center; border-bottom: 2px solid #0f172a; padding-bottom: 14px;">
      <img src="{custom_template_url}" alt="{school_name} Letterhead" style="max-width: 100%; max-height: 130px; object-fit: contain; margin: 0 auto; display: block;" />
    </div>
    ''' if custom_template_url else f'''
    <table class="header-table">
      <tr>
        <td style="width: 80px; vertical-align: middle;">
          {f'<img src="{logo_url}" alt="Logo" style="width: 70px; height: 70px; object-fit: contain; border-radius: 8px;" />' if logo_url else '<div style="width:65px; height:65px; background:#1e3a8a; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; border-radius:8px; font-size:24px;">SCH</div>'}
        </td>
        <td style="padding-left: 16px; vertical-align: middle;">
          <h1 style="font-size: 20px; font-weight: 800; color: #0f172a; text-transform: uppercase; letter-spacing: -0.01em; margin-bottom: 3px;">
            {school_name}
          </h1>
          <div style="font-size: 12px; color: #475569; margin-bottom: 2px;">
            Affiliated to {school_board} {f'• {school_address}' if school_address else ''}
          </div>
          <div style="font-size: 11px; color: #64748b;">
            {f'Contact: {school_phone}' if school_phone else ''} {f'• Email: {school_email}' if school_email else ''}
          </div>
        </td>
        <td style="text-align: right; vertical-align: middle;">
          <span style="display: inline-block; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase;">
            Original Copy
          </span>
        </td>
      </tr>
    </table>
    '''}

    <!-- Title Bar -->
    <div class="receipt-title-bar">
      <div>
        <span style="font-size: 14px; font-weight: 800; color: #1e3a8a; text-transform: uppercase; letter-spacing: 0.05em;">
          Fee Payment Receipt
        </span>
      </div>
      <div>
        <span style="font-size: 12px; color: #64748b;">Receipt No:</span>
        <strong style="font-size: 13px; color: #0f172a; margin-left: 4px;">{receipt_no}</strong>
      </div>
    </div>

    <!-- Student & Payment Meta -->
    <div class="meta-grid">
      <div>
        <div class="meta-item"><span class="meta-label">Scholar Name:</span> <span class="meta-val">{student_name}</span></div>
        <div class="meta-item"><span class="meta-label">Admission No:</span> <span class="meta-val">{admission_no}</span></div>
        <div class="meta-item"><span class="meta-label">Class & Section:</span> <span class="meta-val">Grade {grade} - Section {section}</span></div>
        <div class="meta-item"><span class="meta-label">Father / Guardian:</span> <span class="meta-val">{father_name}</span></div>
      </div>
      <div>
        <div class="meta-item"><span class="meta-label">Payment Date:</span> <span class="meta-val">{payment_date}</span></div>
        <div class="meta-item"><span class="meta-label">Payment Mode:</span> <span class="meta-val">{payment_mode}</span></div>
        <div class="meta-item"><span class="meta-label">Transaction Ref:</span> <span class="meta-val" style="font-family: monospace;">{transaction_ref}</span></div>
        <div class="meta-item"><span class="meta-label">Academic Term:</span> <span class="meta-val">{installment_name}</span></div>
      </div>
    </div>

    <!-- Fee Itemization -->
    <table class="items-table">
      <thead>
        <tr>
          <th style="width: 45px; text-align: center;">#</th>
          <th>Fee Particulars / Head</th>
          <th style="text-align: right;">Base Amount</th>
          <th style="text-align: right;">Late Fine</th>
          <th style="text-align: right;">Concession</th>
          <th style="text-align: right;">Net Amount Paid</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="text-align: center; color: #64748b;">1</td>
          <td>
            <strong>{fee_head}</strong>
            <div style="font-size: 11px; color: #64748b;">Period: {installment_name}</div>
          </td>
          <td style="text-align: right; font-family: monospace;">₹{base_amount:,.2f}</td>
          <td style="text-align: right; font-family: monospace;">₹{fine_amount:,.2f}</td>
          <td style="text-align: right; font-family: monospace;">₹{discount_waiver:,.2f}</td>
          <td style="text-align: right; font-weight: 700; font-family: monospace;">₹{total_paid:,.2f}</td>
        </tr>
        <tr class="total-row">
          <td colspan="5" style="text-align: right; font-weight: 800; text-transform: uppercase; font-size: 13px;">
            Total Received:
          </td>
          <td style="text-align: right; font-family: monospace; font-size: 16px;">
            ₹{total_paid:,.2f}
          </td>
        </tr>
      </tbody>
    </table>

    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding: 10px 14px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px;">
      <div style="font-size: 12px; color: #065f46;">
        <strong>Status:</strong> PAYMENT VERIFIED & SETTLED
      </div>
      <div style="font-size: 12px; color: #047857; font-weight: 700;">
        Received with thanks from {student_name}
      </div>
    </div>

    <!-- Signatures & Stamp -->
    <div class="footer-signatures">
      <div class="sig-col">
        <div style="height: 48px; display: flex; align-items: flex-end; justify-content: center; font-size: 12px; color: #64748b; font-style: italic;">
          {collected_by}
        </div>
        <div class="sig-line">Cashier / Accountant</div>
      </div>

      <div class="sig-col">
        {f'<img src="{stamp_url}" alt="School Stamp" style="max-height: 48px; margin: 0 auto; display: block;" />' if stamp_url else '<div style="height: 48px;"></div>'}
        <div class="sig-line">School Seal</div>
      </div>

      <div class="sig-col">
        {f'<img src="{signature_url}" alt="Principal Signature" style="max-height: 40px; margin: 0 auto; display: block;" />' if signature_url else '<div style="height: 40px;"></div>'}
        <div class="sig-line">{principal_name}<br><span style="font-size: 10px; font-weight: normal; color: #64748b;">Authorized Signatory</span></div>
      </div>
    </div>

    <div style="margin-top: 24px; padding-top: 10px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 10px; color: #94a3b8;">
      This is an authentic, computer-generated official receipt issued by {school_name}. Reference No: {receipt_no}.
    </div>
  </div>
</div>

</body>
</html>
"""
    return html

