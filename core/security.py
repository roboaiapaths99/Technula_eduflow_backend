"""
Security and cryptographic utility for multi-tenant credential encryption.
Uses AES-256 Fernet symmetric encryption derived from PAYMENT_ENCRYPTION_KEY.
Ensures gateway secrets, merchant API keys, and sensitive institutional credentials
are encrypted at rest in the database.
"""
from __future__ import annotations
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from core.config import settings

_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Derives a deterministic 32-byte urlsafe base64 key from PAYMENT_ENCRYPTION_KEY."""
    global _fernet_instance
    if _fernet_instance is None:
        raw_key = (settings.PAYMENT_ENCRYPTION_KEY or "default-school-os-aes256-key-32b!").encode("utf-8")
        # Generate 32-byte SHA-256 digest
        digest = hashlib.sha256(raw_key).digest()
        # Encode as URL-safe base64 for Fernet
        b64_key = base64.urlsafe_b64encode(digest)
        _fernet_instance = Fernet(b64_key)
    return _fernet_instance


def encrypt_credential(plain_text: Optional[str]) -> Optional[str]:
    """Encrypts plaintext string into an AES-256 Fernet cipher token."""
    if not plain_text or not plain_text.strip():
        return None
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plain_text.strip().encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_credential(cipher_text: Optional[str]) -> Optional[str]:
    """Decrypts an AES-256 Fernet cipher token back into plaintext."""
    if not cipher_text or not cipher_text.strip():
        return None
    try:
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(cipher_text.strip().encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        # If text was stored in plaintext before encryption was enabled, fallback safely
        return cipher_text
