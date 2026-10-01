"""
Generic File Upload API — supports images, PDFs, voice notes, videos.
Used by: Leave proof attachments, Chat media, Homework attachments.
"""
from __future__ import annotations
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from services.storage_service import upload_bytes

router = APIRouter(prefix="/upload", tags=["File Upload"])

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",  # Images
    ".pdf", ".doc", ".docx",                     # Documents
    ".mp3", ".ogg", ".webm", ".m4a", ".wav",     # Audio / Voice notes
    ".mp4", ".mov", ".avi",                       # Video
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/file")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and return its public URL (AWS S3 or local static fallback)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB")

    result = upload_bytes(
        data=contents,
        original_filename=file.filename,
        content_type=file.content_type,
        subfolder="uploads",
    )

    return result
