from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import CAROUSEL_DIR, DATA_DIR
from app.database import Base, SessionLocal, engine, get_db
from app.image_utils import process_image_for_carousel
from app.seed import seed_initial_data
from app.notifications import send_feedback_email, send_service_request_email

DEFAULT_SLIDES: list[dict] = []
VALID_SERVICE_STATUSES = {"Submitted", "In Review", "In Progress", "Resolved", "Closed"}
VALID_MESSAGE_STATUSES = {"New", "Reviewed", "Replied", "Archived"}
SERVICE_RECIPIENTS_KEY = "service_request_recipients"
FEEDBACK_RECIPIENTS_KEY = "feedback_recipients"
HERO_IMAGE_KEY = "hero_image_url"


def _compute_sla(priority: str, created_at: datetime) -> tuple[datetime, datetime]:
    normalized = priority.strip().lower()
    if normalized == "high":
        return created_at + timedelta(hours=2), created_at + timedelta(hours=24)
    if normalized == "medium":
        return created_at + timedelta(hours=8), created_at + timedelta(hours=72)
    return created_at + timedelta(hours=24), created_at + timedelta(days=7)


def _parse_recipients(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
    except Exception:  # noqa: BLE001
        return []


def _ensure_service_request_columns() -> None:
    """
    Keep live SQLite upgrades safe without requiring external migration tooling.
    """
    required_columns = {
        "resident_email": "TEXT NOT NULL DEFAULT ''",
        "response_due_at": "DATETIME",
        "resolve_due_at": "DATETIME",
        "acknowledged_at": "DATETIME",
        "resolved_at": "DATETIME",
    }
    with engine.begin() as conn:
        existing_rows = conn.execute(text("PRAGMA table_info(service_requests)")).fetchall()
        existing_names = {row[1] for row in existing_rows}
        for name, ddl in required_columns.items():
            if name in existing_names:
                continue
            conn.execute(text(f"ALTER TABLE service_requests ADD COLUMN {name} {ddl}"))


def _ensure_setting(db: Session, key: str, value: str) -> None:
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if row:
        return
    db.add(models.SiteSetting(key=key, value=value))
    db.commit()


def _get_setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    return row.value if row else default


def _set_setting_value(db: Session, key: str, value: str) -> None:
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        row = models.SiteSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def _ensure_notification_audit_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS notification_audit (
                    id INTEGER PRIMARY KEY,
                    event_type VARCHAR(64) NOT NULL,
                    recipients TEXT NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at DATETIME
                )
                """
            )
        )


def _service_request_to_out(item: models.ServiceRequest) -> schemas.ServiceRequestOut:
    now = datetime.utcnow()
    response_breached = bool(
        item.response_due_at
        and item.status not in {"In Review", "In Progress", "Resolved", "Closed"}
        and now > item.response_due_at
    )
    resolve_breached = bool(
        item.resolve_due_at and item.status not in {"Resolved", "Closed"} and now > item.resolve_due_at
    )
    payload = {
        "id": item.id,
        "ticket_ref": item.ticket_ref,
        "resident_name": item.resident_name,
        "flat_number": item.flat_number,
        "category": item.category,
        "priority": item.priority,
        "description": item.description,
        "status": item.status,
        "resident_email": item.resident_email,
        "admin_notes": item.admin_notes,
        "response_due_at": item.response_due_at,
        "resolve_due_at": item.resolve_due_at,
        "acknowledged_at": item.acknowledged_at,
        "resolved_at": item.resolved_at,
        "response_sla_breached": response_breached,
        "resolve_sla_breached": resolve_breached,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
    return schemas.ServiceRequestOut.model_validate(payload)


def _audit_notification(
    db: Session,
    *,
    event_type: str,
    recipients: list[str],
    subject: str,
    status: str,
    detail: str,
) -> None:
    db.add(
        models.NotificationAudit(
            event_type=event_type,
            recipients=json.dumps(recipients),
            subject=subject,
            status=status,
            detail=detail[:2000],
        )
    )
    db.commit()


def _get_recipient_settings(db: Session) -> schemas.RecipientSettingsOut:
    return schemas.RecipientSettingsOut(
        service_request_recipients=_parse_recipients(
            _get_setting_value(db, SERVICE_RECIPIENTS_KEY, "[]")
        ),
        feedback_recipients=_parse_recipients(_get_setting_value(db, FEEDBACK_RECIPIENTS_KEY, "[]")),
    )


def _update_recipient_settings(
    payload: schemas.RecipientSettingsUpdate,
    db: Session,
) -> schemas.RecipientSettingsOut:
    service_request_recipients = _parse_recipients(json.dumps(payload.service_request_recipients))
    feedback_recipients = _parse_recipients(json.dumps(payload.feedback_recipients))
    _set_setting_value(db, SERVICE_RECIPIENTS_KEY, json.dumps(service_request_recipients))
    _set_setting_value(db, FEEDBACK_RECIPIENTS_KEY, json.dumps(feedback_recipients))
    return schemas.RecipientSettingsOut(
        service_request_recipients=service_request_recipients,
        feedback_recipients=feedback_recipients,
    )


def _list_notification_audit(db: Session) -> list[dict]:
    rows = db.query(models.NotificationAudit).order_by(desc(models.NotificationAudit.created_at)).limit(100).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "recipients": _parse_recipients(row.recipients),
            "subject": row.subject,
            "status": row.status,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _set_hero_image(payload: schemas.HeroImageUpdate, db: Session) -> dict:
    value = payload.hero_image_url.strip()
    _set_setting_value(db, HERO_IMAGE_KEY, value)
    return {"hero_image_url": value}


def _serialize_announcement(item: models.Announcement) -> dict:
    return schemas.AnnouncementOut.model_validate(item).model_dump(mode="json")


def _serialize_event(item: models.Event) -> dict:
    return schemas.EventOut.model_validate(item).model_dump(mode="json")


def _serialize_resource(item: models.Resource) -> dict:
    return schemas.ResourceOut.model_validate(item).model_dump(mode="json")


def _serialize_service_request(item: models.ServiceRequest) -> dict:
    return _service_request_to_out(item).model_dump(mode="json")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_service_request_columns()
    with SessionLocal() as db:
        seed_initial_data(db)
        _ensure_setting(db, SERVICE_RECIPIENTS_KEY, "[]")
        _ensure_setting(db, FEEDBACK_RECIPIENTS_KEY, "[]")
        _ensure_setting(db, HERO_IMAGE_KEY, "")
    yield


app = FastAPI(
    title="GolfMeadows API",
    description=(
        "API for GolfMeadows community portal. Designed with versioned endpoints "
        "and clear contracts to support future CONDO platform integration."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "data_dir": str(DATA_DIR)}


@app.get("/api/v1/carousel")
def list_carousel_images(db: Session = Depends(get_db)) -> dict:
    db_images = (
        db.query(models.CarouselImage)
        .order_by(desc(models.CarouselImage.created_at))
        .all()
    )
    uploaded = [
        {
            "id": item.id,
            "caption": item.caption,
            "url": item.url_path,
            "created_at": item.created_at.isoformat(),
            "source": "uploaded",
        }
        for item in db_images
    ]
    return {"items": uploaded}


@app.post("/api/v1/carousel/upload")
async def upload_carousel_image(
    caption: str = Form(""),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported.")

    raw = await image.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max size is 12MB.")

    try:
        filename, _ = process_image_for_carousel(raw, CAROUSEL_DIR)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Image processing failed: {exc}") from exc

    safe_caption = (caption or Path(image.filename or "").stem or "GolfMeadows").strip()[:255]
    url = f"/storage/uploads/carousel/{filename}"
    record = models.CarouselImage(
        filename=filename,
        original_name=image.filename or f"upload-{uuid4().hex}",
        caption=safe_caption or "GolfMeadows",
        url_path=url,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"item": {"id": record.id, "caption": record.caption, "url": record.url_path}}


@app.delete("/api/v1/carousel/{image_id}")
def delete_carousel_image(image_id: int, db: Session = Depends(get_db)) -> dict:
    record = db.query(models.CarouselImage).filter(models.CarouselImage.id == image_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Image not found.")
    file_path = CAROUSEL_DIR / record.filename
    if file_path.exists():
        file_path.unlink()
    db.delete(record)
    db.commit()
    return {"deleted": image_id}


def _generate_ticket_ref(db: Session) -> str:
    next_id = db.query(models.ServiceRequest).count() + 1
    return f"GM-SR-{next_id:05d}"


@app.post("/api/v1/service-requests", response_model=schemas.ServiceRequestOut)
def create_service_request(payload: schemas.ServiceRequestCreate, db: Session = Depends(get_db)):
    ticket_ref = _generate_ticket_ref(db)
    created = datetime.utcnow()
    response_by, resolve_by = _compute_sla(payload.priority, created)
    record = models.ServiceRequest(
        ticket_ref=ticket_ref,
        response_due_at=response_by,
        resolve_due_at=resolve_by,
        **payload.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    db.add(
        models.ServiceRequestActivity(
            service_request_id=record.id,
            status=record.status,
            note="Request submitted by resident.",
            actor="resident",
        )
    )
    db.commit()

    recipients_row = (
        db.query(models.SiteSetting).filter(models.SiteSetting.key == SERVICE_RECIPIENTS_KEY).first()
    )
    recipients = _parse_recipients(recipients_row.value if recipients_row else "[]")
    status, detail, subject = send_service_request_email(record, recipients, event="created")
    _audit_notification(
        db,
        event_type="service_request_created",
        recipients=recipients,
        subject=subject,
        status=status,
        detail=detail,
    )
    return record


@app.get("/api/v1/service-requests", response_model=list[schemas.ServiceRequestOut])
def list_service_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.ServiceRequest)
    if status:
        query = query.filter(models.ServiceRequest.status == status)
    return query.order_by(desc(models.ServiceRequest.created_at)).all()


@app.get("/api/v1/service-requests/{ticket_ref}", response_model=schemas.ServiceRequestOut)
def get_service_request(ticket_ref: str, db: Session = Depends(get_db)):
    record = (
        db.query(models.ServiceRequest)
        .filter(models.ServiceRequest.ticket_ref == ticket_ref)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    return record


@app.patch("/api/v1/service-requests/{request_id}", response_model=schemas.ServiceRequestOut)
def update_service_request(
    request_id: int,
    payload: schemas.ServiceRequestUpdate,
    db: Session = Depends(get_db),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")

    updates = payload.model_dump(exclude_none=True)
    if "status" in updates and updates["status"] not in VALID_SERVICE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {sorted(VALID_SERVICE_STATUSES)}")

    for key, value in updates.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    if updates:
        db.add(
            models.ServiceRequestActivity(
                service_request_id=record.id,
                status=record.status,
                note=record.admin_notes if "admin_notes" in updates else "",
                actor="admin",
            )
        )
        db.commit()
        recipients_row = (
            db.query(models.SiteSetting).filter(models.SiteSetting.key == SERVICE_RECIPIENTS_KEY).first()
        )
        recipients = _parse_recipients(recipients_row.value if recipients_row else "[]")
        status, detail, subject = send_service_request_email(record, recipients, event="updated")
        _audit_notification(
            db,
            event_type="service_request_updated",
            recipients=recipients,
            subject=subject,
            status=status,
            detail=detail,
        )
    return record


@app.get(
    "/api/v1/service-requests/{request_id}/activities",
    response_model=list[schemas.ServiceRequestActivityOut],
)
def list_service_request_activities(request_id: int, db: Session = Depends(get_db)):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    return (
        db.query(models.ServiceRequestActivity)
        .filter(models.ServiceRequestActivity.service_request_id == request_id)
        .order_by(desc(models.ServiceRequestActivity.created_at))
        .all()
    )


@app.post(
    "/api/v1/service-requests/{request_id}/activities",
    response_model=schemas.ServiceRequestActivityOut,
)
def create_service_request_activity(
    request_id: int,
    payload: schemas.ServiceRequestActivityCreate,
    db: Session = Depends(get_db),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")

    next_status = payload.status or record.status
    if next_status not in VALID_SERVICE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {sorted(VALID_SERVICE_STATUSES)}")

    record.status = next_status
    activity = models.ServiceRequestActivity(
        service_request_id=request_id,
        status=next_status,
        note=payload.note,
        actor=payload.actor,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    recipients_row = (
        db.query(models.SiteSetting).filter(models.SiteSetting.key == SERVICE_RECIPIENTS_KEY).first()
    )
    recipients = _parse_recipients(recipients_row.value if recipients_row else "[]")
    status, detail, subject = send_service_request_email(record, recipients, event="activity")
    _audit_notification(
        db,
        event_type="service_request_activity",
        recipients=recipients,
        subject=subject,
        status=status,
        detail=detail,
    )
    return activity


@app.post("/api/v1/announcements", response_model=schemas.AnnouncementOut)
def create_announcement(payload: schemas.AnnouncementCreate, db: Session = Depends(get_db)):
    record = models.Announcement(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/v1/announcements", response_model=list[schemas.AnnouncementOut])
def list_announcements(db: Session = Depends(get_db)):
    return db.query(models.Announcement).order_by(desc(models.Announcement.created_at)).all()


@app.patch("/api/v1/announcements/{announcement_id}", response_model=schemas.AnnouncementOut)
def update_announcement(
    announcement_id: int,
    payload: schemas.AnnouncementUpdate,
    db: Session = Depends(get_db),
):
    row = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/announcements/{announcement_id}")
def delete_announcement(announcement_id: int, db: Session = Depends(get_db)):
    row = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    db.delete(row)
    db.commit()
    return {"deleted": announcement_id}


@app.post("/api/v1/events", response_model=schemas.EventOut)
def create_event(payload: schemas.EventCreate, db: Session = Depends(get_db)):
    record = models.Event(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/v1/events", response_model=list[schemas.EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.query(models.Event).order_by(desc(models.Event.created_at)).all()


@app.patch("/api/v1/events/{event_id}", response_model=schemas.EventOut)
def update_event(event_id: int, payload: schemas.EventUpdate, db: Session = Depends(get_db)):
    row = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    row = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")
    db.delete(row)
    db.commit()
    return {"deleted": event_id}


@app.post("/api/v1/resources", response_model=schemas.ResourceOut)
def create_resource(payload: schemas.ResourceCreate, db: Session = Depends(get_db)):
    record = models.Resource(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/v1/resources", response_model=list[schemas.ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    return db.query(models.Resource).order_by(desc(models.Resource.created_at)).all()


@app.patch("/api/v1/resources/{resource_id}", response_model=schemas.ResourceOut)
def update_resource(
    resource_id: int,
    payload: schemas.ResourceUpdate,
    db: Session = Depends(get_db),
):
    row = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Resource not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/resources/{resource_id}")
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    row = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Resource not found.")
    db.delete(row)
    db.commit()
    return {"deleted": resource_id}


@app.post("/api/v1/messages", response_model=schemas.MessageOut)
def create_message(payload: schemas.MessageCreate, db: Session = Depends(get_db)):
    record = models.Message(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    recipients_row = db.query(models.SiteSetting).filter(models.SiteSetting.key == FEEDBACK_RECIPIENTS_KEY).first()
    recipients = _parse_recipients(recipients_row.value if recipients_row else "[]")
    status, detail, subject = send_feedback_email(record, recipients)
    _audit_notification(
        db,
        event_type="feedback_created",
        recipients=recipients,
        subject=subject,
        status=status,
        detail=detail,
    )
    return record


@app.get("/api/v1/messages", response_model=list[schemas.MessageOut])
def list_messages(db: Session = Depends(get_db)):
    return db.query(models.Message).order_by(desc(models.Message.created_at)).all()


@app.patch("/api/v1/messages/{message_id}", response_model=schemas.MessageOut)
def update_message(message_id: int, payload: schemas.MessageUpdate, db: Session = Depends(get_db)):
    record = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Message not found.")

    if payload.status not in VALID_MESSAGE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {sorted(VALID_MESSAGE_STATUSES)}")

    record.status = payload.status
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/v1/site-settings/{key}", response_model=schemas.SiteSettingOut)
def get_site_setting(key: str, db: Session = Depends(get_db)):
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found.")
    return row


@app.put("/api/v1/site-settings/{key}", response_model=schemas.SiteSettingOut)
def update_site_setting(
    key: str,
    payload: schemas.SiteSettingUpdate,
    db: Session = Depends(get_db),
):
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        row = models.SiteSetting(key=key, value=payload.value)
        db.add(row)
    else:
        row.value = payload.value
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/v1/admin/recipient-settings", response_model=schemas.RecipientSettingsOut)
def get_recipient_settings(db: Session = Depends(get_db)):
    return _get_recipient_settings(db)


@app.put("/api/v1/admin/recipient-settings", response_model=schemas.RecipientSettingsOut)
def update_recipient_settings(payload: schemas.RecipientSettingsUpdate, db: Session = Depends(get_db)):
    return _update_recipient_settings(payload, db)


@app.get("/api/v1/admin/notification-audit")
def list_notification_audit(db: Session = Depends(get_db)) -> list[dict]:
    return _list_notification_audit(db)


@app.put("/api/v1/admin/hero-image")
def set_hero_image(payload: schemas.HeroImageUpdate, db: Session = Depends(get_db)):
    return _set_hero_image(payload, db)


@app.get("/api/v1/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict:
    about = db.query(models.SiteSetting).filter(models.SiteSetting.key == "about_text").first()
    hero_image = db.query(models.SiteSetting).filter(models.SiteSetting.key == HERO_IMAGE_KEY).first()
    announcements = list_announcements(db)
    events = list_events(db)
    resources = list_resources(db)
    requests = list_service_requests(db=db)[:5]
    return {
        "announcements": [_serialize_announcement(item) for item in announcements],
        "events": [_serialize_event(item) for item in events],
        "resources": [_serialize_resource(item) for item in resources],
        "about_text": about.value if about else "",
        "hero_image_url": hero_image.value if hero_image else "",
        "recent_service_requests": [_serialize_service_request(item) for item in requests],
    }


app.mount("/storage", StaticFiles(directory=DATA_DIR), name="storage")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
