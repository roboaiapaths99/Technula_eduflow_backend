"""
SMS Service — DLT / Indian SMS Gateway Integration (AGPK Academy)
Approved Template: "Welcome to AGPK Academy login. Your verification code is {#var#}. This OTP will expire in 5 minutes"
Handles:
- DLT Header & PE/TE-ID validation
- Dynamic parameter injection ({#var#} -> 6-digit OTP)
- Resilient HTTP dispatch (supporting GET query & POST JSON formats)
- MongoDB logging & audit trail
"""
from __future__ import annotations
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from core.config import settings
from db.mongo import log_mongo_document

logger = logging.getLogger("service.sms")

# Exact registered DLT Template for AGPK Academy
DLT_LOGIN_OTP_TEMPLATE = "Welcome to AGPK Academy login. Your verification code is {otp}. This OTP will expire in 5 minutes"


def format_dlt_login_otp(otp: str) -> str:
    """Format OTP matching registered DLT Template text verbatim."""
    return DLT_LOGIN_OTP_TEMPLATE.format(otp=str(otp).strip())


def send_dlt_sms(
    to_phone: str,
    message: str,
    template_id: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> bool:
    """
    Dispatch SMS via configured DLT SMS gateway (e.g. Meta Reach / Bulk SMS provider).
    Reads credentials strictly from core.config.settings (.env).
    """
    clean_phone = "".join(c for c in to_phone if c.isdigit())[-10:]
    if len(clean_phone) != 10:
        logger.error(f"[SMS DLT] Invalid 10-digit phone number: {to_phone}")
        return False

    api_url = (settings.SMS_API_URL or "https://sms.metareach.in/vb/apikey.php").strip()
    api_key = (getattr(settings, "effective_sms_api_key", "") or settings.SMS_API_KEY or "").strip()
    sender_id = (getattr(settings, "effective_sms_sender_id", "AGPKAC") or settings.SMS_SENDER_ID or "AGPKAC").strip()
    pe_id = (entity_id or settings.SMS_PE_ID or "").strip()
    te_id = (template_id or getattr(settings, "effective_sms_template_id", "") or settings.SMS_TE_ID or "1707177071739047190").strip()

    if not api_key:
        logger.error(f"[SMS DLT] SMS_API_KEY / METAREACH_API_KEY not configured. Cannot dispatch real SMS to +91{clean_phone}")
        return False

    # Build request based on HTTP method or URL pattern
    try:
        # Standard MetaReach / DLT GET HTTP format
        if "apikey.php" in api_url or "?" in api_url or "get" in api_url.lower():
            params = {
                "apikey": api_key,
                "senderid": sender_id,
                "number": clean_phone,
                "message": message,
            }
            if te_id:
                params["templateid"] = te_id
            if pe_id:
                params["peid"] = pe_id

            # If GET format
            query_str = urllib.parse.urlencode(params)
            sep = "&" if "?" in api_url else "?"
            full_url = f"{api_url}{sep}{query_str}"

            req = urllib.request.Request(
                full_url,
                headers={
                    "User-Agent": "SchoolOS-SMS/1.0",
                    "Accept": "application/json, text/plain, */*",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode("utf-8")
                logger.info(f"[SMS DLT] MetaReach response for +91{clean_phone}: HTTP {resp.status} - {resp_body[:120]}")
                
                # Check for MetaReach error response
                is_ok = True
                try:
                    res_json = json.loads(resp_body)
                    if str(res_json.get("status", "")).lower() == "false":
                        logger.error(f"[SMS DLT] MetaReach dispatch error: {res_json}")
                        is_ok = False
                except Exception:
                    pass

                log_mongo_document("sms_logs", {
                    "to": f"+91{clean_phone}",
                    "sender_id": sender_id,
                    "pe_id": pe_id,
                    "te_id": te_id,
                    "mode": "LIVE_GET",
                    "status": "SENT" if is_ok else "GATEWAY_ERROR",
                    "response": resp_body[:300],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return is_ok
        else:
            # POST JSON format
            payload = {
                "apiKey": api_key,
                "sender": sender_id,
                "number": clean_phone,
                "phone": clean_phone,
                "message": message,
                "peId": pe_id,
                "entityId": pe_id,
                "templateId": te_id,
                "teId": te_id,
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}" if api_key else "",
                    "Content-Type": "application/json",
                    "User-Agent": "SchoolOS-SMS/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode("utf-8")
                logger.info(f"[SMS DLT] Sent POST to +91{clean_phone}: HTTP {resp.status} - {resp_body[:100]}")
                log_mongo_document("sms_logs", {
                    "to": f"+91{clean_phone}",
                    "sender_id": sender_id,
                    "pe_id": pe_id,
                    "te_id": te_id,
                    "mode": "LIVE_POST",
                    "status": "SENT",
                    "response": resp_body[:300],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return True
    except Exception as e:
        logger.error(f"[SMS DLT] Failed to dispatch SMS to +91{clean_phone}: {e}")
        log_mongo_document("sms_logs", {
            "to": f"+91{clean_phone}",
            "sender_id": sender_id,
            "pe_id": pe_id,
            "te_id": te_id,
            "mode": "LIVE",
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return False


def dispatch_login_otp(to_phone: str, otp: str) -> bool:
    """
    Format and dispatch the official AGPK Academy login verification OTP.
    Ensures exact DLT template compliance.
    """
    formatted_msg = format_dlt_login_otp(otp)
    return send_dlt_sms(
        to_phone=to_phone,
        message=formatted_msg,
        template_id=getattr(settings, "effective_sms_template_id", "1707177071739047190"),
        entity_id=settings.SMS_PE_ID,
    )
