from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdminLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class AdminSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    identity: str
    role: str


class AdminUserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="admin", min_length=2, max_length=32)
    is_active: bool = True


class AdminUserUpdateIn(BaseModel):
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    role: Optional[str] = Field(default=None, min_length=2, max_length=32)
    is_active: Optional[bool] = None


class AdminUserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CarouselImageOut(BaseModel):
    id: int
    caption: str
    url: str
    created_at: datetime

    class Config:
        from_attributes = True


class ServiceRequestCreate(BaseModel):
    resident_name: str = Field(min_length=2, max_length=128)
    flat_number: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=2, max_length=64)
    priority: str = Field(min_length=2, max_length=32)
    description: str = Field(min_length=10, max_length=3000)


class ServiceRequestUpdate(BaseModel):
    status: Optional[str] = Field(default=None, min_length=2, max_length=32)
    admin_notes: Optional[str] = Field(default=None, max_length=4000)


class ServiceRequestOut(BaseModel):
    id: int
    ticket_ref: str
    resident_name: str
    flat_number: str
    category: str
    priority: str
    description: str
    status: str
    assigned_to: Optional[str] = None
    admin_notes: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceRequestPublicOut(BaseModel):
    ticket_ref: str
    category: str
    priority: str
    status: str
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceRequestActivityCreate(BaseModel):
    status: Optional[str] = Field(default=None, min_length=2, max_length=32)
    note: str = Field(default="", max_length=4000)
    actor: str = Field(default="admin", min_length=2, max_length=64)


class ServiceRequestAssignIn(BaseModel):
    assignee: str = Field(min_length=3, max_length=128)


class ServiceRequestActivityOut(BaseModel):
    id: int
    service_request_id: int
    status: str
    note: str
    actor: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=3, max_length=5000)
    tag: str = Field(default="General", min_length=2, max_length=64)


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    tag: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    body: Optional[str] = Field(default=None, min_length=3, max_length=5000)
    tag: Optional[str] = Field(default=None, min_length=2, max_length=64)


class EventCreate(BaseModel):
    event_date: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    details: str = Field(min_length=3, max_length=5000)


class EventOut(BaseModel):
    id: int
    event_date: str
    title: str
    details: str
    created_at: datetime

    class Config:
        from_attributes = True


class EventUpdate(BaseModel):
    event_date: Optional[str] = Field(default=None, min_length=3, max_length=64)
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    details: Optional[str] = Field(default=None, min_length=3, max_length=5000)


class ResourceCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3, max_length=5000)
    file_url: str = Field(min_length=3, max_length=512)


class ResourceOut(BaseModel):
    id: int
    title: str
    description: str
    file_url: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResourceUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, min_length=3, max_length=5000)
    file_url: Optional[str] = Field(default=None, min_length=3, max_length=512)


class MessageCreate(BaseModel):
    resident_name: str = Field(min_length=2, max_length=128)
    contact: str = Field(min_length=3, max_length=128)
    subject: str = Field(min_length=3, max_length=255)
    message: str = Field(min_length=5, max_length=5000)


class MessageUpdate(BaseModel):
    status: str = Field(min_length=2, max_length=32)


class MessageOut(BaseModel):
    id: int
    resident_name: str
    contact: str
    subject: str
    message: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SiteSettingOut(BaseModel):
    key: str
    value: str


class SiteSettingUpdate(BaseModel):
    value: str = Field(min_length=0, max_length=5000)


class AdminAuthConfigOut(BaseModel):
    google_enabled: bool
    google_client_id: str


class AdminUsersCsvSyncOut(BaseModel):
    processed: int
    created: int
    updated: int
    deactivated: int
    errors: list[str] = Field(default_factory=list)
