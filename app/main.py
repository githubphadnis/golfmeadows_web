import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import CAROUSEL_DIR, DATA_DIR
from app.database import Base, SessionLocal, engine, get_db
from app.auth import (
    authenticate_admin_credentials,
    create_admin_user as create_admin_user_record,
    create_session_for_user,
    ensure_default_admin_user,
    hash_password,
    sync_admin_users_from_csv,
    validate_user_sync_secret,
)
from app.image_utils import process_image_for_carousel
from app.security import (
    AdminPrincipal,
    admin_auth_config,
    parse_cors_settings,
    require_admin,
    revoke_session,
)
from app.seed import seed_initial_data

VALID_SERVICE_STATUSES = {"Submitted", "In Review", "In Progress", "Resolved", "Closed"}
VALID_MESSAGE_STATUSES = {"New", "Reviewed", "Replied", "Archived"}
PUBLIC_SITE_SETTINGS_KEYS = {"about_text", "hero_background_url", "hero_overlay_opacity"}
VALID_ROTA_CATEGORIES = {"general_message", "service_request", "faq_review"}
VALID_CONTACT_CHANNELS = {"email"}


def _serialize_announcement(item: models.Announcement) -> dict:
    return schemas.AnnouncementOut.model_validate(item).model_dump(mode="json")


def _serialize_event(item: models.Event) -> dict:
    return schemas.EventOut.model_validate(item).model_dump(mode="json")


def _serialize_resource(item: models.Resource) -> dict:
    return schemas.ResourceOut.model_validate(item).model_dump(mode="json")


def _serialize_service_request(item: models.ServiceRequest) -> dict:
    return schemas.ServiceRequestOut.model_validate(item).model_dump(mode="json")


def _serialize_public_service_request(item: models.ServiceRequest) -> dict:
    return schemas.ServiceRequestPublicOut.model_validate(item).model_dump(mode="json")


def _serialize_faq(item: models.FaqEntry) -> dict:
    return schemas.FaqOut.model_validate(item).model_dump(mode="json")


def _serialize_interaction_emails(db: Session) -> dict:
    def read_setting(key: str, fallback: str = "") -> str:
        row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
        return row.value if row and row.value else fallback

    return {
        "service_requests": read_setting("interaction_email_service_requests"),
        "contact_messages": read_setting("interaction_email_contact_messages"),
        "general_announcements": read_setting("interaction_email_general_announcements"),
    }


def _serialize_rota(db: Session) -> dict:
    categories = (
        ("service_requests", "service_request"),
        ("contact_messages", "general_message"),
        ("faq_review", "faq_review"),
    )
    payload: dict[str, dict[str, str]] = {}
    for public_key, category in categories:
        row = (
            db.query(models.InteractionRota)
            .filter(
                models.InteractionRota.category == category,
                models.InteractionRota.is_active.is_(True),
            )
            .first()
        )
        secondary = ""
        if row and row.notes.startswith("secondary:"):
            secondary = row.notes.split(":", 1)[1].strip()
        payload[public_key] = {
            "primary": row.assignee_email if row else "",
            "secondary": secondary,
        }
    return payload


def _upsert_site_setting(db: Session, key: str, value: str) -> None:
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        row = models.SiteSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value


def _upsert_rota_category(db: Session, category: str, primary: str, secondary: str) -> None:
    row = db.query(models.InteractionRota).filter(models.InteractionRota.category == category).first()
    note = f"secondary:{secondary}" if secondary else ""
    if not row:
        db.add(
            models.InteractionRota(
                category=category,
                assignee_email=primary,
                notes=note,
                is_active=True,
            )
        )
        return
    row.assignee_email = primary
    row.notes = note
    row.is_active = True


def _admin_actor(principal: AdminPrincipal) -> str:
    identity = (principal.identity or "").strip()
    return (identity[:64] if identity else "admin-token")


def _ensure_service_request_schema(db: Session) -> None:
    columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(service_requests)")).fetchall()
    }
    if "assigned_to" not in columns:
        db.execute(text("ALTER TABLE service_requests ADD COLUMN assigned_to VARCHAR(128)"))
        db.commit()
    if "routed_to_email" not in columns:
        db.execute(
            text(
                "ALTER TABLE service_requests ADD COLUMN routed_to_email VARCHAR(255) DEFAULT '' NOT NULL"
            )
        )
        db.commit()


def _ensure_message_schema(db: Session) -> None:
    columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(messages)")).fetchall()
    }
    if "routed_to_email" not in columns:
        db.execute(
            text(
                "ALTER TABLE messages ADD COLUMN routed_to_email VARCHAR(255) DEFAULT '' NOT NULL"
            )
        )
        db.commit()
    if "admin_response" not in columns:
        db.execute(
            text(
                "ALTER TABLE messages ADD COLUMN admin_response TEXT DEFAULT '' NOT NULL"
            )
        )
        db.commit()


def _ensure_interaction_rota_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS interaction_rota (
                id INTEGER PRIMARY KEY,
                category VARCHAR(64) NOT NULL UNIQUE,
                assignee_email VARCHAR(255) NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    db.commit()


def _ensure_faq_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS faq_entries (
                id INTEGER PRIMARY KEY,
                question VARCHAR(512) NOT NULL,
                answer TEXT NOT NULL,
                source_type VARCHAR(64) NOT NULL DEFAULT 'manual',
                source_ref VARCHAR(128) NOT NULL DEFAULT '',
                is_public BOOLEAN NOT NULL DEFAULT 1,
                created_by VARCHAR(128) NOT NULL DEFAULT 'admin',
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    db.commit()


def _enforce_assignment(record: models.ServiceRequest, admin: AdminPrincipal) -> None:
    actor = _admin_actor(admin)
    if record.assigned_to and record.assigned_to != actor:
        raise HTTPException(
            status_code=409,
            detail=f"Request is assigned to {record.assigned_to}. Take over before updating.",
        )


def _public_service_query(db: Session, status: Optional[str] = None):
    query = db.query(models.ServiceRequest)
    if status:
        query = query.filter(models.ServiceRequest.status == status)
    return query


def _normalize_email(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=400, detail=f"Invalid email: {value}")
    return normalized


def _resolve_contact_email(db: Session, category: str) -> str:
    rota = (
        db.query(models.InteractionRota)
        .filter(
            models.InteractionRota.category == category,
            models.InteractionRota.is_active.is_(True),
        )
        .order_by(models.InteractionRota.id.asc())
        .first()
    )
    if rota:
        return rota.assignee_email
    default_email = (
        db.query(models.SiteSetting)
        .filter(models.SiteSetting.key == "default_contact_email")
        .first()
    )
    if default_email and default_email.value.strip():
        return default_email.value.strip()
    fallback = (
        db.query(models.AdminUser)
        .filter(models.AdminUser.is_active.is_(True))
        .order_by(models.AdminUser.id.asc())
        .first()
    )
    return fallback.email if fallback else ""


def _ensure_faq_from_service_request(db: Session, record: models.ServiceRequest) -> None:
    question = f"{record.category}: {record.description.strip()[:220]}"
    existing = db.query(models.FaqEntry).filter(models.FaqEntry.question == question).first()
    if existing:
        existing.answer = (
            f"Status: {record.status}. "
            + (record.admin_notes.strip() if record.admin_notes.strip() else "Under review by the society office.")
        )
        existing.is_public = True
        existing.source_type = "service_request"
        existing.created_by = record.assigned_to or "admin"
        db.commit()
        return

    db.add(
        models.FaqEntry(
            question=question,
            answer=(
                f"Status: {record.status}. "
                + (record.admin_notes.strip() if record.admin_notes.strip() else "Under review by the society office.")
            ),
            source_type="service_request",
            source_ref=record.ticket_ref,
            is_public=True,
            created_by=record.assigned_to or "admin",
        )
    )
    db.commit()


def _ensure_faq_from_message(db: Session, message: models.Message, admin_identity: str) -> None:
    subject = message.subject.strip()
    question = subject if subject.endswith("?") else f"{subject}?"
    answer = (
        message.admin_response.strip()
        if message.admin_response.strip()
        else "This query has been reviewed by the society office."
    )
    existing = db.query(models.FaqEntry).filter(models.FaqEntry.question == question).first()
    if existing:
        existing.answer = answer
        existing.source_type = "message"
        existing.source_ref = str(message.id)
        existing.created_by = admin_identity
        existing.is_public = True
        db.commit()
        return
    db.add(
        models.FaqEntry(
            question=question,
            answer=answer,
            source_type="message",
            source_ref=str(message.id),
            is_public=True,
            created_by=admin_identity,
        )
    )
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _ensure_service_request_schema(db)
        _ensure_message_schema(db)
        _ensure_interaction_rota_schema(db)
        _ensure_faq_schema(db)
        ensure_default_admin_user(db)
        seed_initial_data(db)
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

cors_allow_origins, cors_allow_origin_regex = parse_cors_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=cors_allow_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "data_dir": str(DATA_DIR)}


@app.get("/api/v1/admin/auth/config", response_model=schemas.AdminAuthConfigOut)
def get_admin_auth_config():
    return admin_auth_config()


@app.post("/api/v1/admin/auth/login", response_model=schemas.AdminSessionOut)
def admin_login(payload: schemas.AdminLoginIn, db: Session = Depends(get_db)):
    user = authenticate_admin_credentials(db, payload.email, payload.password)
    token = create_session_for_user(db, user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "identity": user.email,
        "role": user.role,
    }


@app.post("/api/v1/admin/auth/logout")
def admin_logout(
    authorization: Optional[str] = Header(default=None),
    _: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif authorization:
        token = authorization.strip()
    revoke_session(token, db)
    return {"ok": True}


@app.get("/api/v1/admin/session")
def validate_admin_session(admin: AdminPrincipal = Depends(require_admin)) -> dict:
    return {"authenticated": True, "method": admin.method, "identity": admin.identity}


@app.get("/api/v1/admin/users", response_model=list[schemas.AdminUserOut])
def list_admin_users(
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return db.query(models.AdminUser).order_by(models.AdminUser.created_at.desc()).all()


@app.post("/api/v1/admin/users", response_model=schemas.AdminUserOut)
def create_admin_user(
    payload: schemas.AdminUserCreateIn,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return create_admin_user_record(
        db=db,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        is_active=payload.is_active if payload.is_active is not None else True,
    )


@app.patch("/api/v1/admin/users/{user_id}", response_model=schemas.AdminUserOut)
def update_admin_user(
    user_id: int,
    payload: schemas.AdminUserUpdateIn,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    user = db.query(models.AdminUser).filter(models.AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Admin user not found.")
    updates = payload.model_dump(exclude_none=True)
    if "password" in updates:
        user.password_hash = hash_password(updates.pop("password"))
    for key, value in updates.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@app.post(
    "/api/v1/admin/users-sync-csv",
    response_model=schemas.AdminUsersCsvSyncOut,
    include_in_schema=False,
)
async def sync_admin_users_csv(
    secret: str = Header(default="", alias="X-Users-Sync-Secret"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    validate_user_sync_secret(db, secret)
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    raw = await file.read()
    result = sync_admin_users_from_csv(db, raw.decode("utf-8-sig"))
    return result


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


@app.post("/api/v1/admin/carousel/upload")
async def upload_carousel_image(
    caption: str = Form(""),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
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


@app.delete("/api/v1/admin/carousel/{image_id}")
def delete_carousel_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
) -> dict:
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


@app.post("/api/v1/public/service-requests", response_model=schemas.ServiceRequestPublicOut)
def create_service_request(payload: schemas.ServiceRequestCreate, db: Session = Depends(get_db)):
    ticket_ref = _generate_ticket_ref(db)
    record = models.ServiceRequest(
        ticket_ref=ticket_ref,
        routed_to_email=_resolve_contact_email(db, "service_request"),
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
    db.refresh(record)
    return record


@app.get("/api/v1/public/service-requests/recent", response_model=list[schemas.ServiceRequestPublicOut])
def list_recent_service_requests(
    limit: int = Query(default=6, ge=1, le=30),
    db: Session = Depends(get_db),
):
    return (
        _public_service_query(db)
        .order_by(desc(models.ServiceRequest.created_at))
        .limit(limit)
        .all()
    )


@app.get("/api/v1/public/service-requests/{ticket_ref}", response_model=schemas.ServiceRequestPublicOut)
def get_public_service_request(ticket_ref: str, db: Session = Depends(get_db)):
    record = (
        db.query(models.ServiceRequest)
        .filter(models.ServiceRequest.ticket_ref == ticket_ref)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    return record


@app.get("/api/v1/admin/service-requests", response_model=list[schemas.ServiceRequestOut])
def list_service_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return _public_service_query(db, status).order_by(desc(models.ServiceRequest.created_at)).all()


@app.get("/api/v1/admin/service-requests/{request_id}", response_model=schemas.ServiceRequestOut)
def get_admin_service_request(
    request_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    return record


@app.patch("/api/v1/admin/service-requests/{request_id}", response_model=schemas.ServiceRequestOut)
def update_service_request(
    request_id: int,
    payload: schemas.ServiceRequestUpdate,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    _enforce_assignment(record, admin)

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
                actor=_admin_actor(admin),
            )
        )
        db.commit()
    return record


@app.post("/api/v1/admin/service-requests/{request_id}/assign", response_model=schemas.ServiceRequestOut)
def assign_service_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")

    actor = _admin_actor(admin)
    if record.assigned_to and record.assigned_to != actor:
        raise HTTPException(
            status_code=409,
            detail=f"Request is already assigned to {record.assigned_to}. Use takeover first.",
        )
    if record.assigned_to == actor:
        return record

    record.assigned_to = actor
    db.add(
        models.ServiceRequestActivity(
            service_request_id=record.id,
            status=record.status,
            note=f"Assigned to {actor}.",
            actor=actor,
        )
    )
    db.commit()
    db.refresh(record)
    return record


@app.post("/api/v1/admin/service-requests/{request_id}/takeover", response_model=schemas.ServiceRequestOut)
def takeover_service_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")

    actor = _admin_actor(admin)
    previous_owner = record.assigned_to
    if previous_owner == actor:
        return record

    record.assigned_to = actor
    note = (
        f"Ownership taken over by {actor} from {previous_owner}."
        if previous_owner
        else f"Assigned to {actor}."
    )
    db.add(
        models.ServiceRequestActivity(
            service_request_id=record.id,
            status=record.status,
            note=note,
            actor=actor,
        )
    )
    db.commit()
    db.refresh(record)
    return record


@app.get(
    "/api/v1/admin/service-requests/{request_id}/activities",
    response_model=list[schemas.ServiceRequestActivityOut],
)
def list_service_request_activities(
    request_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
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
    "/api/v1/admin/service-requests/{request_id}/activities",
    response_model=schemas.ServiceRequestActivityOut,
)
def create_service_request_activity(
    request_id: int,
    payload: schemas.ServiceRequestActivityCreate,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Service request not found.")
    _enforce_assignment(record, admin)

    next_status = payload.status or record.status
    if next_status not in VALID_SERVICE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {sorted(VALID_SERVICE_STATUSES)}")

    record.status = next_status
    activity = models.ServiceRequestActivity(
        service_request_id=request_id,
        status=next_status,
        note=payload.note,
        actor=_admin_actor(admin),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@app.get("/api/v1/announcements", response_model=list[schemas.AnnouncementOut])
def list_announcements(db: Session = Depends(get_db)):
    return db.query(models.Announcement).order_by(desc(models.Announcement.created_at)).all()


@app.post("/api/v1/admin/announcements", response_model=schemas.AnnouncementOut)
def create_announcement(
    payload: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    record = models.Announcement(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.patch("/api/v1/admin/announcements/{announcement_id}", response_model=schemas.AnnouncementOut)
def update_announcement(
    announcement_id: int,
    payload: schemas.AnnouncementUpdate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/admin/announcements/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    db.delete(row)
    db.commit()
    return {"deleted": announcement_id}


@app.get("/api/v1/events", response_model=list[schemas.EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.query(models.Event).order_by(desc(models.Event.created_at)).all()


@app.post("/api/v1/admin/events", response_model=schemas.EventOut)
def create_event(
    payload: schemas.EventCreate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    record = models.Event(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.patch("/api/v1/admin/events/{event_id}", response_model=schemas.EventOut)
def update_event(
    event_id: int,
    payload: schemas.EventUpdate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/admin/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")
    db.delete(row)
    db.commit()
    return {"deleted": event_id}


@app.get("/api/v1/resources", response_model=list[schemas.ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    return db.query(models.Resource).order_by(desc(models.Resource.created_at)).all()


@app.post("/api/v1/admin/resources", response_model=schemas.ResourceOut)
def create_resource(
    payload: schemas.ResourceCreate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    record = models.Resource(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.patch("/api/v1/admin/resources/{resource_id}", response_model=schemas.ResourceOut)
def update_resource(
    resource_id: int,
    payload: schemas.ResourceUpdate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Resource not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/admin/resources/{resource_id}")
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Resource not found.")
    db.delete(row)
    db.commit()
    return {"deleted": resource_id}


@app.post("/api/v1/public/messages", response_model=schemas.MessageOut)
def create_message(payload: schemas.MessageCreate, db: Session = Depends(get_db)):
    record = models.Message(
        **payload.model_dump(),
        routed_to_email=_resolve_contact_email(db, "general_message"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/v1/admin/messages", response_model=list[schemas.MessageOut])
def list_messages(db: Session = Depends(get_db), _: AdminPrincipal = Depends(require_admin)):
    return db.query(models.Message).order_by(desc(models.Message.created_at)).all()


@app.patch("/api/v1/admin/messages/{message_id}", response_model=schemas.MessageOut)
def update_message(
    message_id: int,
    payload: schemas.MessageUpdate,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    record = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Message not found.")
    if payload.status not in VALID_MESSAGE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {sorted(VALID_MESSAGE_STATUSES)}")
    record.status = payload.status
    if payload.answer is not None:
        record.admin_response = payload.answer.strip()
    db.commit()
    db.refresh(record)
    if payload.answer or payload.status in {"Reviewed", "Replied", "Archived"}:
        _ensure_faq_from_message(db, record, _admin_actor(admin))
    return record


@app.get("/api/v1/admin/interaction-emails", response_model=schemas.InteractionEmailsOut)
def read_interaction_emails(
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return _serialize_interaction_emails(db)


@app.put("/api/v1/admin/interaction-emails", response_model=schemas.InteractionEmailsOut)
def create_or_update_interaction_emails(
    payload: schemas.InteractionEmailsUpdateIn,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    _upsert_site_setting(
        db,
        "interaction_email_service_requests",
        _normalize_email(payload.service_requests),
    )
    _upsert_site_setting(
        db,
        "interaction_email_contact_messages",
        _normalize_email(payload.contact_messages),
    )
    _upsert_site_setting(
        db,
        "interaction_email_general_announcements",
        _normalize_email(payload.general_announcements),
    )
    db.commit()
    return _serialize_interaction_emails(db)


@app.get("/api/v1/admin/rota", response_model=schemas.RotaOut)
def read_rota(
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return _serialize_rota(db)


@app.put("/api/v1/admin/rota", response_model=schemas.RotaOut)
def create_or_update_rota(
    payload: schemas.RotaUpdateIn,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    _upsert_rota_category(
        db,
        "service_request",
        _normalize_email(payload.service_requests.primary),
        _normalize_email(payload.service_requests.secondary) if payload.service_requests.secondary else "",
    )
    _upsert_rota_category(
        db,
        "general_message",
        _normalize_email(payload.contact_messages.primary),
        _normalize_email(payload.contact_messages.secondary) if payload.contact_messages.secondary else "",
    )
    _upsert_rota_category(
        db,
        "faq_review",
        _normalize_email(payload.faq_review.primary),
        _normalize_email(payload.faq_review.secondary) if payload.faq_review.secondary else "",
    )
    db.commit()
    return _serialize_rota(db)


@app.get("/api/v1/faqs", response_model=list[schemas.FaqOut])
def list_public_faqs(db: Session = Depends(get_db)):
    items = (
        db.query(models.FaqEntry)
        .filter(models.FaqEntry.is_public.is_(True))
        .order_by(desc(models.FaqEntry.updated_at))
        .all()
    )
    return items


@app.get("/api/v1/admin/faqs", response_model=list[schemas.FaqOut])
def list_admin_faqs(
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    return db.query(models.FaqEntry).order_by(desc(models.FaqEntry.updated_at)).all()


@app.post("/api/v1/admin/faqs", response_model=schemas.FaqOut)
def create_admin_faq(
    payload: schemas.FaqCreateIn,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    row = models.FaqEntry(
        question=payload.question.strip(),
        answer=payload.answer.strip(),
        is_public=payload.is_public,
        source_type=payload.source_type.strip().lower(),
        source_ref=(payload.source_ref or "").strip(),
        created_by=_admin_actor(admin),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/v1/admin/faqs/{faq_id}", response_model=schemas.FaqOut)
def update_admin_faq(
    faq_id: int,
    payload: schemas.FaqCreateIn,
    db: Session = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.FaqEntry).filter(models.FaqEntry.id == faq_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    row.question = payload.question.strip()
    row.answer = payload.answer.strip()
    row.is_public = payload.is_public
    row.source_type = payload.source_type.strip().lower()
    row.source_ref = (payload.source_ref or "").strip()
    row.created_by = _admin_actor(admin)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/v1/admin/faqs/{faq_id}")
def delete_admin_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.FaqEntry).filter(models.FaqEntry.id == faq_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    db.delete(row)
    db.commit()
    return {"deleted": faq_id}


@app.get("/api/v1/site-settings/{key}", response_model=schemas.SiteSettingOut)
def get_site_setting(key: str, db: Session = Depends(get_db)):
    if key not in PUBLIC_SITE_SETTINGS_KEYS:
        raise HTTPException(status_code=404, detail="Setting not found.")
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found.")
    return row


@app.get("/api/v1/admin/site-settings/{key}", response_model=schemas.SiteSettingOut)
def get_admin_site_setting(
    key: str,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
):
    row = db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found.")
    return row


@app.put("/api/v1/admin/site-settings/{key}", response_model=schemas.SiteSettingOut)
def update_site_setting(
    key: str,
    payload: schemas.SiteSettingUpdate,
    db: Session = Depends(get_db),
    _: AdminPrincipal = Depends(require_admin),
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


@app.get("/api/v1/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict:
    hero_bg = db.query(models.SiteSetting).filter(models.SiteSetting.key == "hero_background_url").first()
    hero_overlay = db.query(models.SiteSetting).filter(models.SiteSetting.key == "hero_overlay_opacity").first()
    about = db.query(models.SiteSetting).filter(models.SiteSetting.key == "about_text").first()
    announcements = list_announcements(db)
    events = list_events(db)
    resources = list_resources(db)
    requests = (
        _public_service_query(db)
        .order_by(desc(models.ServiceRequest.created_at))
        .limit(5)
        .all()
    )
    return {
        "announcements": [_serialize_announcement(item) for item in announcements],
        "events": [_serialize_event(item) for item in events],
        "resources": [_serialize_resource(item) for item in resources],
        "about_text": about.value if about else "",
        "hero_background_url": hero_bg.value if hero_bg else "",
        "hero_overlay_opacity": hero_overlay.value if hero_overlay else "0.48",
        "recent_service_requests": [_serialize_public_service_request(item) for item in requests],
        "public_faqs": [_serialize_faq(item) for item in list_public_faqs(db)],
        "interaction_emails": _serialize_interaction_emails(db),
        "rota": _serialize_rota(db),
    }


app.mount("/storage", StaticFiles(directory=DATA_DIR), name="storage")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
