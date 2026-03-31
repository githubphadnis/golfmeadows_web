from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import CAROUSEL_DIR, DATA_DIR
from app.database import Base, SessionLocal, engine, get_db
from app.image_utils import process_image_for_carousel
from app.security import AdminPrincipal, admin_auth_config, parse_cors_settings, require_admin
from app.seed import seed_initial_data

DEFAULT_SLIDES = [
    {"caption": "GolfMeadows central courtyard", "url": "/assets/carousel_default_1.svg"},
    {"caption": "Children's play zone and gardens", "url": "/assets/carousel_default_2.svg"},
    {"caption": "Community clubhouse social evening", "url": "/assets/carousel_default_3.svg"},
]

VALID_SERVICE_STATUSES = {"Submitted", "In Review", "In Progress", "Resolved", "Closed"}
VALID_MESSAGE_STATUSES = {"New", "Reviewed", "Replied", "Archived"}
PUBLIC_SITE_SETTINGS_KEYS = {"about_text"}


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


def _admin_actor(principal: AdminPrincipal) -> str:
    if principal.method == "google":
        return principal.identity[:64]
    return "admin"


def _public_service_query(db: Session, status: Optional[str] = None):
    query = db.query(models.ServiceRequest)
    if status:
        query = query.filter(models.ServiceRequest.status == status)
    return query


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
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


@app.get("/api/v1/admin/session")
def validate_admin_session(admin: AdminPrincipal = Depends(require_admin)) -> dict:
    return {"authenticated": True, "method": admin.method, "identity": admin.identity}


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
    defaults = [
        {"id": f"default-{i}", **slide, "source": "default"}
        for i, slide in enumerate(DEFAULT_SLIDES, start=1)
    ]
    return {"items": defaults + uploaded}


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
    record = models.ServiceRequest(ticket_ref=ticket_ref, **payload.model_dump())
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
    record = models.Message(**payload.model_dump())
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
    _: AdminPrincipal = Depends(require_admin),
):
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
        "recent_service_requests": [_serialize_public_service_request(item) for item in requests],
    }


app.mount("/storage", StaticFiles(directory=DATA_DIR), name="storage")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
