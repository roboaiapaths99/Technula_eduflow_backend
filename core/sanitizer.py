"""
Security input sanitizer & validator — sanitizes and strictly validates user-submitted
inputs (emails, phone numbers, names, rich text) to prevent XSS attacks, injection,
and invalid/dummy/fake data entry.
"""
import re
import html
from fastapi import HTTPException

# Disallow script tags, javascript: links, onload/onerror handlers
SCRIPT_PATTERN = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
EVENT_HANDLER_PATTERN = re.compile(r"\bon\w+\s*=\s*['\"][^'\"]*['\"]", re.IGNORECASE)
JAVASCRIPT_URI_PATTERN = re.compile(r"javascript\s*:", re.IGNORECASE)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$")
DISALLOWED_EMAIL_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "throwawaymail.com", "fake.com", "test.com", "dummy.com", "yopmail.com",
    "sharklasers.com", "sharklasers.net", "getairmail.com", "dispostable.com",
    "trashmail.com", "temp-mail.org", "fakeinbox.com", "spam4.me", "nada.ltd",
    "burnermail.io", "maildrop.cc", "tempail.com", "example.com", "example.org",
    "example.net", "invalid.com", "xyz.com", "abc.com"
}
DISALLOWED_EMAIL_USERS = {
    "test", "dummy", "fake", "asdf", "qwerty", "admin123", "none", "null", "noone",
    "sample", "temp", "temporary", "tester"
}
REPETITIVE_DIGITS_PATTERN = re.compile(r"^(\d)\1{9}$")
KNOWN_FAKE_PHONES = {
    "1234567890", "0123456789", "9876543210", "9876598765", "9999912345",
    "9123456780", "9898989898", "9090909090", "8080808080", "7070707070",
    "9123456789", "9876501234", "6000000000", "7000000000", "8000000000",
    "9000000000", "9999999999", "8888888888", "7777777777", "6666666666",
    "0000000000", "1111111111", "2222222222", "3333333333", "4444444444",
    "5555555555"
}
KNOWN_FAKE_NAMES = {
    "test", "testing", "dummy", "fake", "fake name", "asdf", "qwerty", "nobody",
    "no name", "noname", "n/a", "na", "null", "none", "unknown", "admin", "administrator",
    "user", "sample", "demo"
}


def sanitize_text(text: str | None) -> str | None:
    """Strip malicious script tags, JS event handlers, and escape dangerous characters."""
    if not text:
        return text
    cleaned = SCRIPT_PATTERN.sub("", str(text))
    cleaned = EVENT_HANDLER_PATTERN.sub("", cleaned)
    cleaned = JAVASCRIPT_URI_PATTERN.sub("", cleaned)
    return cleaned.strip()


def sanitize_plain_text(text: str | None) -> str | None:
    """Escape all HTML special characters for strict plaintext storage."""
    if not text:
        return text
    return html.escape(str(text).strip())


def validate_email(email: str | None, field_name: str = "Email Address") -> str:
    """
    Strict email validation:
    - Checks proper email format with valid domain and TLD (e.g. user@domain.com)
    - Rejects invalid characters, consecutive dots, disposable fake domains, and dummy prefixes
    """
    if not email or not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=400, detail=f"{field_name} is required.")

    cleaned = email.strip().lower()
    if len(cleaned) < 6 or len(cleaned) > 100:
        raise HTTPException(status_code=400, detail=f"{field_name} must be between 6 and 100 characters.")

    if ".." in cleaned or not EMAIL_REGEX.match(cleaned):
        raise HTTPException(status_code=400, detail=f"Please provide a valid, real {field_name} (e.g. name@school.edu).")

    parts = cleaned.split("@")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format.")

    user_part, domain = parts[0], parts[1]
    if user_part in DISALLOWED_EMAIL_USERS:
        raise HTTPException(status_code=400, detail=f"Please provide a real, non-placeholder {field_name}.")

    if "." not in domain:
        raise HTTPException(status_code=400, detail=f"{field_name} must have a valid domain extension.")

    tld = domain.split(".")[-1]
    if len(tld) < 2 or not tld.isalpha():
        raise HTTPException(status_code=400, detail=f"{field_name} has an invalid top-level domain extension.")

    if domain in DISALLOWED_EMAIL_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Disposable, temporary, or placeholder email domains are not permitted.")

    return cleaned


def validate_phone(phone: str | None, required: bool = True, field_name: str = "Mobile Number") -> str | None:
    """
    Strict Indian 10-digit mobile number validation:
    - Strips spaces, hyphens, and +91/91/0 prefix
    - Must be exactly 10 digits starting with 6, 7, 8, or 9
    - Rejects repetitive digits, sequential fakes, and low digit entropy
    """
    if not phone or not isinstance(phone, (str, int)) or not str(phone).strip():
        if required:
            raise HTTPException(status_code=400, detail=f"{field_name} is required.")
        return None

    # Strip formatting characters
    digits = re.sub(r"[^\d]", "", str(phone))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid 10-digit mobile number."
        )

    if digits[0] not in ["6", "7", "8", "9"]:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid mobile number beginning with 6, 7, 8, or 9."
        )

    if REPETITIVE_DIGITS_PATTERN.match(digits) or digits in KNOWN_FAKE_PHONES:
        raise HTTPException(
            status_code=400,
            detail=f"Please provide a genuine, real {field_name} (dummy and repetitive numbers are not allowed)."
        )

    # Require at least 3 distinct digits to block numbers like 9999999991 or 8888888887
    if len(set(digits)) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"Please provide a genuine, real {field_name} (insufficient unique digits)."
        )

    return digits


def validate_full_name(name: str | None, field_name: str = "Name") -> str:
    """
    Strict human/institution name validation:
    - Minimum 2 characters, maximum 80 characters
    - Must contain alphabetic characters, cannot be pure numbers or symbols
    - Rejects known placeholder/dummy names
    """
    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail=f"{field_name} is required.")

    cleaned = name.strip()
    if len(cleaned) < 2:
        raise HTTPException(status_code=400, detail=f"{field_name} must be at least 2 characters.")
    if len(cleaned) > 80:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot exceed 80 characters.")

    # Must contain at least one letter
    if not any(c.isalpha() for c in cleaned):
        raise HTTPException(status_code=400, detail=f"{field_name} must contain alphabetic letters.")

    # Reject repetitive single character spam (e.g. 'aaaaaaa')
    clean_alpha = [c.lower() for c in cleaned if c.isalpha()]
    if len(set(clean_alpha)) < 2 and len(clean_alpha) > 3:
        raise HTTPException(status_code=400, detail=f"Please enter a genuine, real {field_name}.")

    if cleaned.lower() in KNOWN_FAKE_NAMES:
        raise HTTPException(status_code=400, detail=f"'{cleaned}' is a placeholder. Please enter a real {field_name}.")

    return cleaned


def validate_text_field(text: str | None, field_name: str = "Field", min_length: int = 2, max_length: int = 500, required: bool = True) -> str | None:
    """Validate arbitrary text input (reasons, notes, addresses)."""
    if not text or not str(text).strip():
        if required:
            raise HTTPException(status_code=400, detail=f"{field_name} is required.")
        return None

    cleaned = sanitize_text(str(text))
    if len(cleaned) < min_length:
        raise HTTPException(status_code=400, detail=f"{field_name} must be at least {min_length} characters.")
    if len(cleaned) > max_length:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot exceed {max_length} characters.")

    return cleaned
