"""
Gemini AI Service — replaces OpenAI for academic insights generation.
Uses Google's Generative AI SDK (google-generativeai).
Falls back to rule-based summary if no API key is configured.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timezone

from core.config import settings

class GeminiResponse:
    def __init__(self, text: str):
        self.text = text


class GeminiRestClient:
    """Direct REST client for Google Gemini API — avoids grpc/cygrpc native DLL issues."""
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model

    def generate_content(self, prompt: str, generation_config: Optional[Dict[str, Any]] = None) -> GeminiResponse:
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        gen_cfg = {}
        if generation_config:
            if "temperature" in generation_config:
                gen_cfg["temperature"] = generation_config["temperature"]
            if "max_output_tokens" in generation_config:
                gen_cfg["maxOutputTokens"] = generation_config["max_output_tokens"]
            elif "maxOutputTokens" in generation_config:
                gen_cfg["maxOutputTokens"] = generation_config["maxOutputTokens"]
            if "response_mime_type" in generation_config:
                gen_cfg["responseMimeType"] = generation_config["response_mime_type"]
        if isinstance(prompt, list):
            parts = []
            for item in prompt:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif isinstance(item, dict):
                    if "inline_data" in item:
                        parts.append({"inlineData": item["inline_data"]})
                    elif "inlineData" in item:
                        parts.append({"inlineData": item["inlineData"]})
                    elif "text" in item:
                        parts.append({"text": item["text"]})
                    else:
                        parts.append(item)
            payload = {"contents": [{"parts": parts}]}
        else:
            payload = {"contents": [{"parts": [{"text": str(prompt)}]}]}

        if gen_cfg:
            payload["generationConfig"] = gen_cfg

        headers = {"Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            return GeminiResponse(text)
        return GeminiResponse("")


# Initialize Gemini client
genai_client = None


def get_effective_gemini_model() -> str:
    model = (settings.GEMINI_MODEL or "").strip()
    if not model or model == "gemini-2.0-flash":
        return "gemini-2.5-flash"
    return model


def get_genai_client():
    global genai_client
    if genai_client is not None:
        return genai_client
    if settings.GEMINI_API_KEY:
        model_name = get_effective_gemini_model()
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            genai_client = genai.GenerativeModel(model_name)
            print(f"[AI] Gemini configured via SDK with model: {model_name}")
            return genai_client
        except Exception as e:
            print(f"[AI] SDK init unavailable ({e}), using direct Gemini REST client.")
            genai_client = GeminiRestClient(api_key=settings.GEMINI_API_KEY, model=model_name)
            return genai_client
    return None


# Attempt initial setup
get_genai_client()


def _safe_float(x) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def _compute_patterns(metrics: Dict, overall_trend: List, student_vs_class: List, highlights: List) -> Dict:
    """Compute crisp signals to help AI generate better insights."""
    trend_points = [(str(t.get("exam_name", "")), _safe_float(t.get("percentage"))) for t in overall_trend]
    valid_pcts = [p for _, p in trend_points if p is not None]

    direction = delta = volatility = None
    if len(valid_pcts) >= 2:
        delta = round(valid_pcts[-1] - valid_pcts[0], 2)
        direction = "Improving" if delta >= 2 else ("Declining" if delta <= -2 else "Stable")
        volatility = round(max(valid_pcts) - min(valid_pcts), 2)

    strongest = _safe_float(metrics.get("strongest_percentage"))
    weakest = _safe_float(metrics.get("weakest_percentage"))
    spread = round(strongest - weakest, 2) if strongest is not None and weakest is not None else None

    above = below = 0
    focus_subjects = []
    for row in student_vs_class:
        d = _safe_float(row.get("delta"))
        sub = row.get("subject")
        if d is None or not sub:
            continue
        if d > 0:
            above += 1
        elif d < 0:
            below += 1
            focus_subjects.append(sub)

    top5 = [h.get("subject") for h in highlights if h.get("type") == "TOP" and h.get("subject")]
    bottom5 = [h.get("subject") for h in highlights if h.get("type") == "BOTTOM" and h.get("subject")]

    volatility_label = None
    if volatility is not None:
        volatility_label = "Consistent" if volatility <= 5 else ("Some ups and downs" if volatility <= 12 else "Highly variable")

    return {
        "trend_direction": direction,
        "trend_delta_pct_points": delta,
        "trend_volatility_range": volatility,
        "trend_consistency_label": volatility_label,
        "subject_spread_pct_points": spread,
        "above_class_subjects_count": above,
        "below_class_subjects_count": below,
        "below_class_focus_subjects": focus_subjects[:3],
        "top5_subjects": top5[:3],
        "bottom5_subjects": bottom5[:3],
    }


def _extract_teacher_feedback(dashboard_data: Dict) -> Optional[Dict]:
    """Extract teacher feedback if present in dashboard data."""
    tf = dashboard_data.get("teacher_feedback")
    if isinstance(tf, dict):
        remark = (tf.get("remark") or "").strip()
        note = (tf.get("note") or "").strip()
        if remark or note:
            return {"remark": remark or None, "note": note or None, "exam_name": tf.get("exam_name")}
    return None


def _build_academic_prompt(dashboard_data: Dict) -> str:
    """Build a crisp, insight-rich prompt for Gemini."""
    student = dashboard_data.get("student", {}) or {}
    metrics = dashboard_data.get("metrics", {}) or {}
    subject_bar = dashboard_data.get("subject_bar", []) or []
    overall_trend = dashboard_data.get("overall_trend", []) or []
    class_summary = dashboard_data.get("class_summary", {}) or {}
    student_vs_class = dashboard_data.get("student_vs_class_subject_avg", []) or []
    highlights = dashboard_data.get("highlights", []) or []
    class_trend = dashboard_data.get("class_trend", []) or []

    name = student.get("name", "the student")
    grade = student.get("grade", "?")
    section = student.get("section", "")

    latest_subjects = [{"subject": s.get("subject"), "student_pct": s.get("percentage")} for s in subject_bar]
    trend_points = [{"exam": t.get("exam_name"), "pct": t.get("percentage")} for t in overall_trend]

    svc_points = [{
        "subject": row.get("subject"),
        "student_pct": row.get("student_percentage"),
        "class_avg_pct": row.get("class_average_percentage"),
        "delta": row.get("delta"),
        "max_in_class": row.get("subject_max_percentage"),
        "min_in_class": row.get("subject_min_percentage"),
    } for row in student_vs_class]

    hl_points = [{"subject": h.get("subject"), "type": h.get("type"), "rank": h.get("rank"), "class_size": h.get("class_size")} for h in highlights]

    topper = (class_summary.get("topper") or {}) if isinstance(class_summary, dict) else {}
    bottom = (class_summary.get("bottom") or {}) if isinstance(class_summary, dict) else {}

    patterns = _compute_patterns(metrics, overall_trend, student_vs_class, highlights)
    teacher_feedback = _extract_teacher_feedback(dashboard_data)

    facts = {
        "student": {"name": name, "grade": f"{grade}{section}"},
        "overall": {
            "overall_average_pct": metrics.get("overall_average"),
            "trend_label": metrics.get("trend_label"),
            "strongest_subject": metrics.get("strongest_subject"),
            "strongest_pct": metrics.get("strongest_percentage"),
            "weakest_subject": metrics.get("weakest_subject"),
            "weakest_pct": metrics.get("weakest_percentage"),
        },
        "latest_subjects": latest_subjects,
        "trend_points": trend_points,
        "class_summary": {
            "exam_name": class_summary.get("exam_name") if isinstance(class_summary, dict) else None,
            "class_avg_pct": class_summary.get("class_avg") if isinstance(class_summary, dict) else None,
            "topper_pct": topper.get("percentage"),
            "bottom_pct": bottom.get("percentage"),
            "student_pct_current_exam": class_summary.get("student_percentage") if isinstance(class_summary, dict) else None,
        },
        "student_vs_class": svc_points,
        "highlights": hl_points,
        "class_trend": class_trend,
        "derived_patterns": patterns,
        "teacher_feedback": teacher_feedback,
    }

    facts_json = json.dumps(facts, ensure_ascii=False)

    return f"""You are an experienced school counselor writing a parent note.

Rules (must follow):
- Be warm, supportive, and practical. No jargon.
- Do NOT mention systems, models, prompts, prototypes, or AI.
- Use insights from "derived_patterns" to recognize consistency, direction, and focus areas.
- If teacher_feedback is present, incorporate it especially in Needs Support / Next Step.
- Avoid repeating percentages: use at most THREE numbers in the whole response.
- If class comparison facts are missing, do not invent them.

Use exactly this structure and limits:
1) Overview (max 40 words)
2) Patterns & Strengths (max 80 words) — mention consistency / improving / top areas
3) Needs Support (max 80 words) — mention focus subjects / below class avg signals
4) Actions at Home: exactly 6 bullets, each max 11 words
5) Next Step (4 sentences, max 40 words)

FACTS (JSON):
{facts_json}"""


def _fallback_summary(dashboard_data: Dict) -> str:
    """Generate a rule-based fallback summary when Gemini is not available."""
    student = dashboard_data.get("student", {}) or {}
    metrics = dashboard_data.get("metrics", {}) or {}

    name = student.get("name", "The student")
    grade = student.get("grade", "?")
    overall = metrics.get("overall_average", "?")
    strongest = metrics.get("strongest_subject", "their stronger subjects")
    strongest_perc = metrics.get("strongest_percentage", "?")
    weakest = metrics.get("weakest_subject", "their weaker subjects")
    weakest_perc = metrics.get("weakest_percentage", "?")
    trend_label = metrics.get("trend_label", "stable")

    return (
        f"{name} (Grade {grade}) is currently performing at an overall average of around {overall}%. "
        f"The strongest subject at the moment appears to be {strongest} (about {strongest_perc}%), while "
        f"{weakest} (about {weakest_perc}%) needs more consistent focus.\n\n"
        f"The overall performance trend looks **{trend_label}** over the recent exams. "
        f"We recommend regular revision in weaker subjects, short daily practice, and open "
        f"communication between parents and teachers to maintain progress."
    )


def generate_academic_summary(dashboard_data: Dict) -> str:
    """
    Main function used by the API.
    Uses Gemini if configured, otherwise falls back to rule-based summary.
    """
    key_present = bool(settings.GEMINI_API_KEY)
    print(f"[AI] GEMINI_API_KEY present: {key_present}")
    print(f"[AI] GEMINI_MODEL: {settings.GEMINI_MODEL}")

    client = get_genai_client()
    if client is None or not settings.GEMINI_API_KEY:
        print("[AI] Using fallback because Gemini client/key missing.")
        return _fallback_summary(dashboard_data)

    prompt = _build_academic_prompt(dashboard_data)

    try:
        response = client.generate_content(
            prompt,
            generation_config={
                "temperature": 0.35,
                "max_output_tokens": 520,
            },
        )
        content = response.text
        if not content:
            print("[AI] Empty content returned, using fallback.")
            return _fallback_summary(dashboard_data)

        # Store in MongoDB for audit
        try:
            from db.mongo import ai_insights_collection
            ai_insights_collection.insert_one({
                "student_id": str(dashboard_data.get("student", {}).get("id", "")),
                "model": settings.GEMINI_MODEL,
                "prompt_length": len(prompt),
                "response_length": len(content),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

        return content.strip()

    except Exception as e:
        print(f"[AI] Gemini exception: {repr(e)}")
        return _fallback_summary(dashboard_data)


# Alias
generate_academic_insights = generate_academic_summary



def generate_report_comment(student_name: str, subject: str, marks: float, max_marks: float, class_avg: float) -> str:
    """Generate AI narrative comment for a single subject on report card."""
    client = get_genai_client()
    if client is None or not settings.GEMINI_API_KEY:
        pct = round((marks / max_marks) * 100, 1) if max_marks > 0 else 0
        if pct >= 90:
            return f"Excellent performance in {subject}. Keep up the outstanding work."
        elif pct >= 75:
            return f"Good understanding of {subject} concepts. Room for excellence with more practice."
        elif pct >= 60:
            return f"Satisfactory performance in {subject}. Regular practice will help improve."
        else:
            return f"Needs focused attention in {subject}. Daily practice sessions recommended."

    try:
        prompt = f"""Write one brief, encouraging sentence (max 20 words) as a teacher's report card comment for:
Student: {student_name}
Subject: {subject}
Marks: {marks}/{max_marks} ({round((marks/max_marks)*100, 1)}%)
Class Average: {class_avg}%
Be warm, specific, and constructive. No generic praise."""

        response = client.generate_content(
            prompt,
            generation_config={"temperature": 0.4, "max_output_tokens": 50},
        )
        return response.text.strip() if response.text else f"Good effort in {subject}."
    except Exception:
        pct = round((marks / max_marks) * 100, 1) if max_marks > 0 else 0
        return f"{'Excellent' if pct >= 80 else 'Good'} effort in {subject}."


def generate_weekly_executive_summary(kpis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Feature 10: Generate comprehensive weekly executive briefing for the school principal,
    combining attendance health, fee cashflow, risk caseload, and operational actions.
    """
    att_rate = kpis.get("attendance_rate", 0.0)
    total_students = kpis.get("total_students", 0)
    critical_risks = kpis.get("critical_risks", 0)
    high_risks = kpis.get("high_risks", 0)
    collected_amount = kpis.get("weekly_collected_amount", 0)
    pending_amount = kpis.get("total_pending_amount", 0)
    open_tickets = kpis.get("open_tickets", 0)
    school_name = kpis.get("school_name", "Academic Insights Academy")

    fallback_summary = {
        "executive_summary": (
            f"Over the past 7 days, {school_name} maintained an overall attendance rate of {att_rate}% across {total_students} enrolled students. "
            f"Academic and behavioural risk management identified {critical_risks} critical and {high_risks} high-priority student cases requiring active teacher-counselor interventions. "
            f"On the financial front, the school registered ₹{collected_amount:,.2f} in fee receipts this week, leaving ₹{pending_amount:,.2f} in term balance collections. "
            f"Campus operations handled {open_tickets} pending support and inquiry tickets with healthy resolution velocity."
        ),
        "key_highlights": [
            f"Student attendance stabilized at {att_rate}%, well above the 75% CBSE regulatory threshold.",
            f"Intervention workflows active for {critical_risks + high_risks} flagged student cases across grades.",
            f"Weekly fee collections added ₹{collected_amount:,.2f} with {kpis.get('resolved_tickets', 0)} inquiry tickets resolved.",
        ],
        "action_items": [
            "Convene an academic review meeting with Grade 10 & 12 class teachers regarding borderline student cases.",
            "Dispatch automated WhatsApp fee reminders to parents with overdue term installments exceeding 15 days.",
            "Review chronic absentee rosters and schedule Parent-Teacher Conferences for students below 75% attendance.",
        ],
    }

    client = get_genai_client()
    if client is None or not settings.GEMINI_API_KEY:
        return fallback_summary

    try:
        prompt = f"""You are the Executive AI Advisor to the Principal of {school_name}.
Generate a professional, high-level weekly executive summary based on the following real-time school KPIs:
- Total Enrolled Students: {total_students}
- 7-Day Average Student Attendance: {att_rate}%
- Critical Risk Students (Academic/Attendance): {critical_risks}
- High Risk Students: {high_risks}
- Fee Collected This Week: ₹{collected_amount:,.2f}
- Outstanding Fee Balance: ₹{pending_amount:,.2f}
- Open Helpdesk Tickets: {open_tickets}

Output valid JSON with the exact structure:
{{
  "executive_summary": "A 2-to-3 paragraph authoritative, encouraging, yet vigilant executive report for the school principal and board.",
  "key_highlights": ["3 concise positive or notable achievement bullet points"],
  "action_items": ["3 high-priority strategic management actions for the coming week"]
}}
Return ONLY valid JSON without markdown fences.
"""
        response = client.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 2048,
                "response_mime_type": "application/json",
            },
        )
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        print(f"[AI] Weekly report generation error: {e}")
        return fallback_summary


def test_gemini_connection() -> Dict[str, Any]:
    """Test Gemini API connectivity and return diagnostic results."""
    client = get_genai_client()
    if not client or not settings.GEMINI_API_KEY:
        return {
            "status": "unconfigured",
            "message": "GEMINI_API_KEY not configured",
        }
    try:
        import time
        start_t = time.time()
        resp = client.generate_content("Respond with: 'Gemini AI connection successful!'")
        duration_ms = round((time.time() - start_t) * 1000, 2)
        return {
            "status": "connected",
            "model": get_effective_gemini_model(),
            "response": resp.text.strip(),
            "latency_ms": duration_ms,
        }
    except Exception as e:
        return {
            "status": "error",
            "model": get_effective_gemini_model(),
            "message": str(e),
        }
