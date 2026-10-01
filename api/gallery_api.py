"""
Gallery API — Photo albums, event showcases, and media lightboxes.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from models.gallery_db import GalleryAlbumDB, GalleryPhotoDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/gallery", tags=["Photo Gallery"])


@router.post("/albums")
def create_album(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    title = payload.get("title", "").strip()
    description = payload.get("description")
    event_date_str = payload.get("event_date")
    target_grade = payload.get("target_grade", "ALL")
    cover_photo_url = payload.get("cover_photo_url")

    if not title or not event_date_str:
        raise HTTPException(status_code=400, detail="Title and event date are required.")

    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()

    album = GalleryAlbumDB(
        school_id=user.school_id,
        title=title,
        description=description,
        event_date=event_date,
        target_grade=target_grade,
        cover_photo_url=cover_photo_url,
        created_by=user.id,
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    # If photos included initially
    photos = payload.get("photos", [])
    for idx, p in enumerate(photos):
        photo = GalleryPhotoDB(
            album_id=album.id,
            image_url=p["image_url"],
            caption=p.get("caption"),
            sort_order=idx,
        )
        db.add(photo)
    if photos:
        if not album.cover_photo_url and len(photos) > 0:
            album.cover_photo_url = photos[0]["image_url"]
        db.commit()

    # Dispatch notification to parents
    st_query = db.query(StudentDB).filter(StudentDB.school_id == user.school_id, StudentDB.is_active == True)
    if target_grade != "ALL":
        st_query = st_query.filter(StudentDB.grade == target_grade)
    students = st_query.all()
    student_ids = [s.id for s in students]
    if student_ids:
        parent_links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id.in_(student_ids)).all()
        parent_user_ids = {pl.parent_user_id for pl in parent_links if pl.parent_user_id}
        alert_msg = f"NEW PHOTO ALBUM: '{title}' ({len(photos)} photos). Check out the campus moments in Photo Gallery!"
        for pid in parent_user_ids:
            dispatch_multi_channel_notification(
                db=db,
                school_id=user.school_id,
                user_id=pid,
                title="New School Photo Album",
                message=alert_msg,
                event_type="GALLERY_PUBLISHED",
                payload={"album_id": str(album.id), "title": title},
            )

    return {"success": True, "id": str(album.id), "album_id": str(album.id), "message": "Album created."}


@router.post("/albums/{album_id}/photos")
def add_photos_to_album(
    album_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    album = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.id == album_id, GalleryAlbumDB.school_id == user.school_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found.")

    photos = payload.get("photos", [])
    if not photos:
        raise HTTPException(status_code=400, detail="No photos provided.")

    added = 0
    for idx, p in enumerate(photos):
        url = p.get("image_url") or p.get("photo_url")
        if not url:
            continue
        photo = GalleryPhotoDB(
            album_id=album.id,
            image_url=url,
            caption=p.get("caption"),
            sort_order=idx,
        )
        db.add(photo)
        if not album.cover_photo_url:
            album.cover_photo_url = url
        added += 1

    db.commit()
    return {"success": True, "message": f"{added} photos added to album."}


@router.get("/albums")
def list_albums(
    student_id: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.school_id == user.school_id)

    if student_id:
        student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
        if student:
            query = query.filter((GalleryAlbumDB.target_grade == "ALL") | (GalleryAlbumDB.target_grade == student.grade))

    albums = query.order_by(desc(GalleryAlbumDB.event_date)).all()
    res = []
    for a in albums:
        res.append({
            "id": str(a.id),
            "title": a.title,
            "description": a.description,
            "event_date": a.event_date.isoformat(),
            "target_grade": a.target_grade,
            "cover_photo_url": a.cover_photo_url or (a.photos[0].image_url if a.photos else None),
            "photo_count": len(a.photos),
            "created_at": a.created_at.isoformat(),
        })
    return res


@router.get("/albums/{album_id}")
def get_album_detail(
    album_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    album = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.id == album_id, GalleryAlbumDB.school_id == user.school_id).first()
    if not album:
        # Check if the param is actually a school_id requested by client
        target_school_id = album_id if album_id else user.school_id
        school_albums = db.query(GalleryAlbumDB).filter(
            (GalleryAlbumDB.school_id == target_school_id) | (GalleryAlbumDB.school_id == user.school_id)
        ).order_by(desc(GalleryAlbumDB.event_date)).all()
        if school_albums or str(album_id) == str(user.school_id):
            return [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "description": a.description,
                    "event_date": a.event_date.isoformat(),
                    "target_grade": a.target_grade,
                    "cover_photo_url": a.cover_photo_url or (a.photos[0].image_url if a.photos else None),
                    "photo_count": len(a.photos),
                    "created_at": a.created_at.isoformat(),
                }
                for a in school_albums
            ]
        raise HTTPException(status_code=404, detail="Album not found.")

    photos = [{
        "id": str(p.id),
        "image_url": p.image_url,
        "caption": p.caption,
        "sort_order": p.sort_order,
    } for p in album.photos]

    return {
        "id": str(album.id),
        "title": album.title,
        "description": album.description,
        "event_date": album.event_date.isoformat(),
        "target_grade": album.target_grade,
        "cover_photo_url": album.cover_photo_url,
        "photos": photos,
    }


@router.put("/albums/{album_id}")
def update_album(
    album_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    album = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.id == album_id, GalleryAlbumDB.school_id == user.school_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found.")

    if "title" in payload and payload["title"]:
        album.title = payload["title"].strip()
    if "description" in payload:
        album.description = payload["description"]
    if "event_date" in payload and payload["event_date"]:
        album.event_date = datetime.strptime(payload["event_date"], "%Y-%m-%d").date()
    if "target_grade" in payload:
        album.target_grade = payload["target_grade"]
    if "cover_photo_url" in payload:
        album.cover_photo_url = payload["cover_photo_url"]

    db.commit()
    return {"success": True, "message": "Album details updated."}


@router.delete("/albums/{album_id}/photos/{photo_id}")
def delete_photo_from_album(
    album_id: str,
    photo_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    photo = db.query(GalleryPhotoDB).filter(
        GalleryPhotoDB.id == photo_id,
        GalleryPhotoDB.album_id == album_id
    ).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    album = photo.album
    db.delete(photo)
    db.commit()

    # If deleted photo was cover, update cover
    if album and album.cover_photo_url == photo.image_url:
        remaining = db.query(GalleryPhotoDB).filter(GalleryPhotoDB.album_id == album.id).first()
        album.cover_photo_url = remaining.image_url if remaining else None
        db.commit()

    return {"success": True, "message": "Photo removed from album."}


@router.delete("/albums/{album_id}")
def delete_album(
    album_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    album = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.id == album_id, GalleryAlbumDB.school_id == user.school_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found.")
    db.delete(album)
    db.commit()
    return {"success": True, "message": "Album deleted."}


# ── ALIAS FOR MOBILE APP: GET SCHOOL GALLERY ALBUMS ───────────────────
@router.get("/albums/school/{school_id}")
@router.get("/albums/{school_id}")
def get_school_gallery_albums_alias(
    school_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Check if this parameter is actually an album UUID or school_id
    # If an album exists with this ID, return album details
    existing_album = db.query(GalleryAlbumDB).filter(GalleryAlbumDB.id == school_id, GalleryAlbumDB.school_id == user.school_id).first()
    if existing_album:
        return get_album_detail(album_id=school_id, user=user, db=db)

    # Otherwise return list of albums for user's school
    return list_albums(student_id=None, user=user, db=db)
