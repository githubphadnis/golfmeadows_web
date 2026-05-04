import os
import smtplib
from datetime import date, datetime, time
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from sqlalchemy import inspect, text
from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

from app.auth import (
    admin_required,
    permission_required,
    require_feature_flag,
    super_admin_required,
)
from app.config import Config
from app.extensions import db, login_manager
from app.google_drive import fetch_drive_documents
from app.models import (
    Admin,
    Amenity,
    Announcement,
    Booking,
    DirectoryItem,
    DriveDocumentMapping,
    Event,
    MCNotice,
    Notice,
    RecipientConfig,
    ResidentDirectory,
    Role,
    ServiceStaff,
    ServiceTicket,
    SiteSettings,
    TileContent,
    UploadedFile,
    User,
    VisitorLog,
)
from app.utils import (
    allowed_file,
    ensure_storage_directories,
    file_icon_for_extension,
    normalize_email,
    save_amenity_image,
    save_directory_image,
    save_hero_image,
    save_uploaded_file,
)

HERO_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

FORM_CARD_IMAGE_BY_EXTENSION = {
    "pdf": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1400&q=80",
    "docx": "https://images.unsplash.com/photo-1517842645767-c639042777db?auto=format&fit=crop&w=1400&q=80",
    "xlsx": "https://images.unsplash.com/photo-1554224154-22dec7ec8818?auto=format&fit=crop&w=1400&q=80",
    "jpg": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=80",
    "jpeg": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=80",
    "png": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=80",
    "zip": "https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=1400&q=80",
}
DEFAULT_FORM_CARD_IMAGE = (
    "https://images.unsplash.com/photo-1517048676732-d65bc937f952?auto=format&fit=crop&w=1400&q=80"
)
DIRECTORY_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
AMENITY_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

DIRECTORY_ITEM_CATEGORIES = {
    "society_office": "Society Office",
    "service_requests": "Service Requests",
    "services_directory": "Services Directory",
}

DEFAULT_DIRECTORY_ITEMS = [
    {
        "category": "services_directory",
        "title": "GreenCare Family Clinic",
        "description": "Medical support and family physician guidance.",
        "contact_name": "Dr. Meera Joshi",
        "phone": "+91 98765 43210",
        "email": "greencare@example.com",
        "website_url": "https://greencare-clinic.example.com",
        "image_url": "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "services_directory",
        "title": "MetroLink Travel Desk",
        "description": "Public transport reservations and route help.",
        "contact_name": "Amit Kale",
        "phone": "+91 97654 32109",
        "email": "metrolink@example.com",
        "website_url": "https://metrolink-transit.example.com",
        "image_url": "https://images.unsplash.com/photo-1474487548417-781cb71495f3?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "services_directory",
        "title": "QuickRide Auto Point",
        "description": "Last-mile auto bookings for residents.",
        "contact_name": "Rafiq Shaikh",
        "phone": "+91 99887 66554",
        "email": "quickride@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1542282088-fe8426682b8f?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "services_directory",
        "title": "Fresh Basket Greens",
        "description": "Daily vegetables and seasonal produce delivery.",
        "contact_name": "Lata Pawar",
        "phone": "+91 98220 33445",
        "email": "",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "services_directory",
        "title": "DairyMorning Supplies",
        "description": "Fresh milk and dairy delivery plans.",
        "contact_name": "Rohan Nair",
        "phone": "+91 98111 22334",
        "email": "dairy@example.com",
        "website_url": "https://dairymorning.example.com",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "services_directory",
        "title": "DailyNeeds Mart",
        "description": "Groceries and home essentials near you.",
        "contact_name": "Sanjay Kulkarni",
        "phone": "+91 99300 44556",
        "email": "dailyneeds@example.com",
        "website_url": "https://dailyneedsmart.example.com",
        "image_url": "https://images.unsplash.com/photo-1543168256-418811576931?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "society_office",
        "title": "Accounting",
        "description": "Request bills, report offcycle payments.",
        "contact_name": "Accounts Desk",
        "phone": "",
        "email": "accounts@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "society_office",
        "title": "Tenant Management",
        "description": "Trigger new tenant process and departures.",
        "contact_name": "Tenant Relations",
        "phone": "",
        "email": "tenants@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "society_office",
        "title": "General Resident Topics",
        "description": "General resident inquiries and support.",
        "contact_name": "Resident Desk",
        "phone": "",
        "email": "office@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "Entry & Parking",
        "description": "Register vehicles, parking spaces, and rentals.",
        "contact_name": "Gate Ops",
        "phone": "+91 90000 10001",
        "email": "entry@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "Plumber",
        "description": "Plumbing emergencies and maintenance.",
        "contact_name": "Plumbing Team",
        "phone": "+91 90000 10002",
        "email": "plumber@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "General Maintenance",
        "description": "Infrastructure repairs, lights, and doors.",
        "contact_name": "Maintenance Team",
        "phone": "+91 90000 10003",
        "email": "maintenance@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "Housekeeping",
        "description": "Cleaning common areas and support.",
        "contact_name": "Housekeeping Team",
        "phone": "+91 90000 10004",
        "email": "housekeeping@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1563453392212-326f5e854473?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "Goods Movement",
        "description": "Delivery/removal coordination for large items.",
        "contact_name": "Logistics Desk",
        "phone": "+91 90000 10005",
        "email": "logistics@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1600518464441-9154a4dea21b?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "service_requests",
        "title": "Packers & Movers",
        "description": "Move-in and move-out assistance.",
        "contact_name": "Move Desk",
        "phone": "+91 90000 10006",
        "email": "moves@example.com",
        "website_url": "",
        "image_url": "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=1400&q=80",
    },
]
DEFAULT_DIRECTORY_IMAGE_BY_KEY = {
    (row["category"], row["title"]): row.get("image_url", "") for row in DEFAULT_DIRECTORY_ITEMS
}

BOOKING_TIME_SLOTS = [
    "06:00",
    "07:00",
    "08:00",
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
    "20:00",
    "21:00",
]

DEFAULT_AMENITIES = [
    {
        "name": "Clubhouse",
        "description": "Indoor gathering space for resident events and meetings.",
        "image_url": "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
    {
        "name": "Jacuzzi",
        "description": "Relaxing hydrotherapy slot with paid booking.",
        "image_url": "https://images.unsplash.com/photo-1611078489935-0cb964de46d6?auto=format&fit=crop&w=1400&q=80",
        "cost": 750.0,
    },
    {
        "name": "Tennis Court",
        "description": "Outdoor tennis court for singles or doubles sessions.",
        "image_url": "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
    {
        "name": "Cricket Pitch",
        "description": "Practice pitch for cricket nets and friendly matches.",
        "image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
    {
        "name": "MultiPurpose Court",
        "description": "Convertible court for basketball, futsal, and more.",
        "image_url": "https://images.unsplash.com/photo-1517649763962-0c623066013b?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
    {
        "name": "Table Tennis",
        "description": "Indoor table tennis table for quick games.",
        "image_url": "https://images.unsplash.com/photo-1517438322307-e67111335449?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
    {
        "name": "Pool Table",
        "description": "Residents' pool table for recreation.",
        "image_url": "https://images.unsplash.com/photo-1612872087720-bb876e2e67d1?auto=format&fit=crop&w=1400&q=80",
        "cost": 0.0,
    },
]

ROLE_PERMISSIONS = {
    "society_office": "Society Office",
    "service_requests": "Service Requests",
    "services_directory": "Services Directory",
    "resident_directory": "Resident Directory",
    "tickets": "Tickets",
    "amenities": "Amenities",
    "bookings": "Bookings",
    "notices": "Notices & Documents",
    "hero_images": "Hero Images",
    "global_settings": "Global Settings",
    "visitors": "Visitors",
}

SERVICE_TICKET_STATUS_FLOW = [
    "Open",
    "Assigned",
    "Pending Verification",
    "Resolved",
]
SERVICE_TICKET_STATUS_INDEX = {
    value: idx for idx, value in enumerate(SERVICE_TICKET_STATUS_FLOW)
}

DIRECTORY_PERMISSION_BY_CATEGORY = {
    "society_office": "society_office",
    "service_requests": "service_requests",
    "services_directory": "services_directory",
}

VISITOR_CATEGORIES = [
    "Personal/Guest",
    "Family",
    "Domestic Staff",
    "Driver",
    "Service/Repair",
    "Cab/Taxi",
    "Delivery",
]

VISITOR_COMPANIES = [
    "Zomato",
    "Swiggy",
    "Blinkit",
    "Zepto",
    "Amazon",
    "Flipkart",
    "Blue Dart",
    "Delhivery",
    "Urban Company",
    "Uber",
    "Ola",
    "Rapido",
    "Other",
]

VISITOR_COMPANY_REQUIRED_CATEGORIES = {"Delivery", "Cab/Taxi", "Service/Repair"}

VISITOR_STATUS_PRE_APPROVED = "Pre-Approved"
VISITOR_STATUS_ENTERED = "Entered"
VISITOR_STATUS_EXITED = "Exited"

VISITOR_STATUS_OPTIONS = [
    VISITOR_STATUS_PRE_APPROVED,
    VISITOR_STATUS_ENTERED,
    VISITOR_STATUS_EXITED,
]

OCCUPANCY_TYPES = {"Owner", "Tenant"}
HOUSEHOLD_OWNER_ROLES = ["First Owner", "Second Owner", "Owner Family"]
HOUSEHOLD_TENANT_ROLES = ["Main Tenant", "Tenant Family"]
HOUSEHOLD_DIRECTORY_ROLES = HOUSEHOLD_OWNER_ROLES + HOUSEHOLD_TENANT_ROLES
HOUSEHOLD_GENDERS = ["Male", "Female", "Other"]
HOUSEHOLD_AGE_GROUPS = ["Adult", "Child"]
STAFF_CATEGORY_OPTIONS = ["Maid", "Driver", "Cleaner", "Nurse", "Cook", "Other"]

ADMIN_TILE_DEFINITIONS = [
    {
        "permission": "society_office",
        "title": "Manage Society Office",
        "description": "Create and edit cards for Society Office page.",
        "endpoint": ("admin_manage_directory", {"category": "society_office"}),
    },
    {
        "permission": "service_requests",
        "title": "Manage Service Requests",
        "description": "Manage service request cards and contact actions.",
        "endpoint": ("admin_manage_directory", {"category": "service_requests"}),
    },
    {
        "permission": "tickets",
        "title": "Manage Tickets",
        "description": "Track resident tickets through the accountability workflow.",
        "endpoint": ("admin_manage_tickets", {}),
    },
    {
        "permission": "services_directory",
        "title": "Manage Services Directory",
        "description": "Maintain local services and business listings.",
        "endpoint": ("admin_manage_directory", {"category": "services_directory"}),
    },
    {
        "permission": "resident_directory",
        "title": "Manage Resident Directory",
        "description": "View resident households and service staff access by flat.",
        "endpoint": ("admin_core_directory", {}),
    },
    {
        "permission": "amenities",
        "title": "Manage Amenities",
        "description": "Add amenities and update booking windows.",
        "endpoint": ("admin_manage_amenities", {}),
    },
    {
        "permission": "bookings",
        "title": "Manage Bookings",
        "description": "Review amenity bookings with filters.",
        "endpoint": ("admin_manage_bookings", {}),
    },
    {
        "permission": "notices",
        "title": "Manage Notices",
        "description": "Create and maintain MC notices and announcements.",
        "endpoint": ("admin_manage_notices", {}),
    },
    {
        "permission": "hero_images",
        "title": "Manage Hero Images",
        "description": "Upload and remove homepage hero images.",
        "endpoint": ("admin_manage_hero", {}),
    },
    {
        "permission": "global_settings",
        "title": "Global Settings",
        "description": "Select website-wide background and branding options.",
        "endpoint": ("admin_manage_settings", {}),
    },
    {
        "permission": "visitors",
        "title": "Manage Visitors",
        "description": "Audit resident pre-approvals and security gate movements.",
        "endpoint": ("admin_manage_visitors", {}),
    },
]


def _normalize_permissions(values: list[str] | set[str] | tuple[str, ...] | None) -> str:
    if not values:
        return ""
    ordered = sorted(
        {
            value.strip().lower()
            for value in values
            if isinstance(value, str) and value.strip() in ROLE_PERMISSIONS
        }
    )
    return ",".join(ordered)


def _permissions_for_user(admin: Admin | None) -> set[str]:
    if not admin:
        return set()
    if admin.is_super_admin:
        return set(ROLE_PERMISSIONS.keys())
    if not admin.role:
        return set()
    return {
        value.strip().lower()
        for value in (admin.role.permissions or "").split(",")
        if value.strip().lower() in ROLE_PERMISSIONS
    }


def _user_has_permission(permission: str) -> bool:
    if not current_user.is_authenticated:
        return False
    return permission in _permissions_for_user(current_user)


def _user_can_manage_directory_category(category: str) -> bool:
    permission_key = DIRECTORY_PERMISSION_BY_CATEGORY.get(category)
    if not permission_key:
        return False
    return _user_has_permission(permission_key)


def _is_domain_allowed_email(email: str, allowed_domain: str = "golfmeadows.org") -> bool:
    normalized_email = normalize_email(email)
    domain = (allowed_domain or "").strip().lower()
    return bool(normalized_email) and bool(domain) and normalized_email.endswith(f"@{domain}")


def _normalize_ticket_status(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    for allowed in SERVICE_TICKET_STATUS_FLOW:
        if candidate == allowed.lower():
            return allowed
    return "Open"


def _is_feature_enabled(flag_name: str) -> bool:
    settings = _get_site_settings()
    return bool(getattr(settings, flag_name, True))


def _enforce_feature_enabled(flag_name: str):
    if _is_feature_enabled(flag_name):
        return None
    flash("This feature is currently disabled by the administrator.", "error")
    return redirect(url_for("index"))


def _generate_visitor_entry_code() -> str:
    while True:
        candidate = f"{int.from_bytes(os.urandom(4), 'big') % 1000000:06d}"
        if not VisitorLog.query.filter_by(entry_code=candidate).first():
            return candidate


def _visitor_security_label(visitor: VisitorLog) -> str:
    user = visitor.user
    if not user:
        return "Unknown resident"
    flat = (user.flat_number or "").strip()
    if flat:
        return f"{user.full_name} (Flat {flat})"
    return user.full_name


def _visitor_status_badge_class(status: str) -> str:
    if status == VISITOR_STATUS_ENTERED:
        return "bg-emerald-100 text-emerald-800"
    if status == VISITOR_STATUS_EXITED:
        return "bg-slate-100 text-slate-700"
    return "bg-indigo-100 text-indigo-800"


def _active_visitor_preapprovals_for_user(user_id: int) -> list[VisitorLog]:
    return (
        VisitorLog.query.filter(
            VisitorLog.user_id == user_id,
            VisitorLog.status.in_([VISITOR_STATUS_PRE_APPROVED, VISITOR_STATUS_ENTERED]),
        )
        .order_by(VisitorLog.expected_date.asc(), VisitorLog.id.desc())
        .all()
    )


def _visitor_logs_filtered_for_admin(status_filter: str, expected_date: date | None) -> list[VisitorLog]:
    query = VisitorLog.query.join(User, VisitorLog.user_id == User.id)
    if status_filter:
        query = query.filter(VisitorLog.status == status_filter)
    if expected_date:
        query = query.filter(VisitorLog.expected_date == expected_date)
    return query.order_by(VisitorLog.expected_date.desc(), VisitorLog.id.desc()).all()


def _coerce_visitor_status(status_raw: str | None) -> str:
    candidate = (status_raw or "").strip()
    if candidate not in VISITOR_STATUS_OPTIONS:
        abort(400, description="Invalid visitor status.")
    return candidate


def _normalize_expected_date(value: str) -> date:
    parsed = _parse_iso_date(value)
    if not parsed:
        abort(400, description="Expected date must be YYYY-MM-DD.")
    if parsed < date.today():
        abort(400, description="Expected date cannot be in the past.")
    return parsed


def _safe_int_setting(value: int | str | None, fallback: int) -> int:
    try:
        parsed = int(value) if value is not None else fallback
    except (TypeError, ValueError):
        parsed = fallback
    return max(0, parsed)


def _normalized_flat_number(value: str | None) -> str:
    return (value or "").strip().upper()


def _coerce_occupancy_type(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in OCCUPANCY_TYPES:
        abort(400, description="Invalid occupancy type.")
    return candidate


def _coerce_household_role(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in HOUSEHOLD_DIRECTORY_ROLES:
        abort(400, description="Invalid household role.")
    return candidate


def _coerce_household_gender(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in HOUSEHOLD_GENDERS:
        abort(400, description="Invalid household gender.")
    return candidate


def _coerce_household_age_group(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in HOUSEHOLD_AGE_GROUPS:
        abort(400, description="Invalid age group.")
    return candidate


def _coerce_staff_category(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in STAFF_CATEGORY_OPTIONS:
        abort(400, description="Invalid service staff category.")
    return candidate


def _linked_flats_set(value: str | None) -> set[str]:
    return {
        _normalized_flat_number(item)
        for item in (value or "").split(",")
        if _normalized_flat_number(item)
    }


def _linked_flats_csv(values: set[str]) -> str:
    return ",".join(sorted({entry for entry in values if entry}))


def _household_directory_context(
    resident_user: User | None,
    settings: SiteSettings,
) -> dict[str, object]:
    profile = _resident_profile_from_session()
    flat_number = _normalized_flat_number(
        (resident_user.flat_number if resident_user else "") or profile.get("flat_number", "")
    )
    resident_entries: list[ResidentDirectory] = []
    staff_entries: list[ServiceStaff] = []
    occupancy_type = "Owner"
    owner_family_count = 0
    tenant_family_count = 0
    family_limit = _safe_int_setting(settings.max_owner_family, 4)

    owner_family_limit = _safe_int_setting(settings.max_owner_family, 4)
    tenant_family_limit = _safe_int_setting(settings.max_tenant_family, 4)

    if flat_number:
        resident_entries = (
            ResidentDirectory.query.filter_by(flat_number=flat_number)
            .order_by(ResidentDirectory.created_at.asc(), ResidentDirectory.id.asc())
            .all()
        )
        owner_roles = {
            row.role
            for row in resident_entries
            if row.occupancy_type == "Owner" and row.role in {"First Owner", "Second Owner"}
        }
        tenant_roles = {
            row.role for row in resident_entries if row.occupancy_type == "Tenant" and row.role == "Main Tenant"
        }
        if tenant_roles and not owner_roles:
            occupancy_type = "Tenant"
        owner_family_count = sum(
            1 for row in resident_entries if row.occupancy_type == "Owner" and row.role == "Owner Family"
        )
        tenant_family_count = sum(
            1 for row in resident_entries if row.occupancy_type == "Tenant" and row.role == "Tenant Family"
        )
        if occupancy_type == "Tenant":
            family_limit = tenant_family_limit
        matching_staff = (
            ServiceStaff.query.order_by(ServiceStaff.created_at.asc(), ServiceStaff.id.asc()).all()
        )
        staff_entries = [
            row
            for row in matching_staff
            if flat_number in {
                _normalized_flat_number(flat) for flat in (row.linked_flats or "").split(",") if flat.strip()
            }
        ]

    family_count = owner_family_count if occupancy_type == "Owner" else tenant_family_count
    family_limit_reached = family_count >= family_limit
    owner_roles_enabled = occupancy_type == "Owner"
    role_options = HOUSEHOLD_OWNER_ROLES if owner_roles_enabled else HOUSEHOLD_TENANT_ROLES

    return {
        "resident_profile": profile,
        "flat_number": flat_number,
        "resident_entries": resident_entries,
        "staff_entries": staff_entries,
        "occupancy_type": occupancy_type,
        "role_options": role_options,
        "family_limit": family_limit,
        "family_count": family_count,
        "family_limit_reached": family_limit_reached,
        "owner_family_count": owner_family_count,
        "tenant_family_count": tenant_family_count,
        "owner_family_limit": owner_family_limit,
        "tenant_family_limit": tenant_family_limit,
    }


def _service_staff_for_flat(flat_number: str) -> list[ServiceStaff]:
    normalized_flat = _normalized_flat_number(flat_number)
    if not normalized_flat:
        return []
    rows = ServiceStaff.query.order_by(ServiceStaff.created_at.asc(), ServiceStaff.id.asc()).all()
    return [
        row
        for row in rows
        if normalized_flat
        in {
            _normalized_flat_number(flat)
            for flat in (row.linked_flats or "").split(",")
            if flat.strip()
        }
    ]


def _validate_visitor_entry_code(
    entry_code: str,
    *,
    now_dt: datetime | None = None,
) -> tuple[bool, str, VisitorLog | None]:
    normalized_code = (entry_code or "").strip()
    if len(normalized_code) != 6 or not normalized_code.isdigit():
        return False, "Invalid Code", None

    visitor = VisitorLog.query.filter_by(entry_code=normalized_code).first()
    if not visitor:
        return False, "Invalid Code", None
    if visitor.status in {VISITOR_STATUS_ENTERED, VISITOR_STATUS_EXITED}:
        return False, "Code Already Used or Expired", visitor

    current_dt = now_dt or datetime.now()
    if visitor.expected_date != current_dt.date():
        return False, "Outside of valid hours", visitor

    valid_from = visitor.valid_from_time or time.min
    valid_to = visitor.valid_to_time or time.max
    current_time = current_dt.time()
    if valid_from > valid_to or not (valid_from <= current_time <= valid_to):
        return False, "Outside of valid hours", visitor

    return True, "", visitor


def _validate_visitor_company(category: str, company_name: str) -> str | None:
    cleaned = (company_name or "").strip()
    if category in VISITOR_COMPANY_REQUIRED_CATEGORIES:
        if not cleaned:
            abort(400, description="Company is required for selected visitor category.")
        if cleaned not in VISITOR_COMPANIES:
            abort(400, description="Selected company is invalid.")
        return cleaned
    return cleaned or None


def _coerce_ticket_status(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate not in SERVICE_TICKET_STATUS_INDEX:
        abort(400, description="Invalid ticket status.")
    return candidate


def _resident_profile_from_session() -> dict[str, str]:
    resident_id_raw = session.get("resident_user_id")
    profile = {"full_name": "", "flat_number": "", "email": ""}
    if not resident_id_raw:
        return profile
    try:
        resident_id = int(resident_id_raw)
    except (TypeError, ValueError):
        session.pop("resident_user_id", None)
        return profile
    resident = db.session.get(User, resident_id)
    if not resident:
        session.pop("resident_user_id", None)
        return profile
    return {
        "full_name": (resident.full_name or "").strip(),
        "flat_number": (resident.flat_number or "").strip(),
        "email": normalize_email(resident.email),
    }


def _resident_user_from_session() -> User | None:
    resident_id_raw = session.get("resident_user_id")
    if not resident_id_raw:
        return None
    try:
        resident_id = int(resident_id_raw)
    except (TypeError, ValueError):
        session.pop("resident_user_id", None)
        return None
    resident = db.session.get(User, resident_id)
    if not resident:
        session.pop("resident_user_id", None)
        return None
    return resident


def _upsert_resident_user(*, full_name: str, flat_number: str, email: str) -> User:
    resident = (
        User.query.filter(
            User.email == email,
            User.flat_number == flat_number,
        )
        .order_by(User.id.asc())
        .first()
    )
    if not resident:
        resident = User(
            full_name=full_name,
            flat_number=flat_number,
            email=email,
        )
        db.session.add(resident)
        db.session.flush()
        return resident
    if resident.full_name != full_name:
        resident.full_name = full_name
    return resident


def _safe_amenity_time(value: time | None, fallback: time) -> time:
    if isinstance(value, time):
        return value
    return fallback


def _parse_time_window(value: str, fallback: time) -> time:
    parsed = _parse_booking_time(value)
    return parsed or fallback


def _amenity_booking_window_violation(amenity: Amenity, start_time: time, end_time: time) -> str:
    available_from = _safe_amenity_time(amenity.available_from, time(6, 0))
    available_to = _safe_amenity_time(amenity.available_to, time(22, 0))
    if start_time < available_from or end_time > available_to:
        return (
            f"Booking time must be within {available_from.strftime('%H:%M')} "
            f"and {available_to.strftime('%H:%M')}."
        )
    return ""


def _send_booking_confirmation_email(
    app_obj: Flask,
    *,
    booking: Booking,
    amenity: Amenity,
) -> tuple[bool, str]:
    smtp_server = (os.getenv("SMTP_SERVER") or "").strip()
    smtp_port_raw = (os.getenv("SMTP_PORT") or "").strip()
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASS") or "").strip()
    if not (smtp_server and smtp_port_raw and smtp_user and smtp_pass):
        return False, "SMTP configuration missing; confirmation email skipped."
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        return False, "Invalid SMTP_PORT; confirmation email skipped."

    message = EmailMessage()
    message["Subject"] = f"{app_obj.config['SOCIETY_NAME']} Booking Confirmation - {amenity.name}"
    message["From"] = smtp_user
    message["To"] = booking.resident_email
    message.set_content(
        "\n".join(
            [
                f"Hello {booking.resident_name},",
                "",
                "Your amenity booking is confirmed.",
                f"Amenity: {amenity.name}",
                f"Date: {booking.booking_date.isoformat()}",
                f"Time: {booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}",
                f"Cost: INR {float(amenity.cost or 0.0):.2f}",
                "",
                f"Thank you,",
                app_obj.config["SOCIETY_NAME"],
            ]
        )
    )
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - external SMTP
        return False, f"Failed to send confirmation email: {exc}"
    return True, "Confirmation email sent."

def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config())
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    ensure_storage_directories(app.config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin_login"

    oauth = OAuth(app)
    if app.config["GOOGLE_OAUTH_CLIENT_ID"] and app.config["GOOGLE_OAUTH_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(Admin, int(user_id))

    with app.app_context():
        db.create_all()
        _patch_database_schema(app)
        _ensure_default_roles()
        _ensure_default_amenities()
        _ensure_default_directory_items()
        _ensure_default_recipient_config()
        _ensure_default_tile_content()
        _ensure_default_site_settings()
        _ensure_super_admin(app.config["SUPER_ADMIN_EMAIL"])

    @app.context_processor
    def inject_society_name():
        settings = _get_site_settings()
        brand_name = (settings.society_name or "").strip() or app.config["SOCIETY_NAME"] or "Golf Meadows"
        global_background_url = _resolved_global_background_url(app.config)
        global_background_style = (
            f"background-image: url('{global_background_url}');" if global_background_url else ""
        )
        overlay_alpha = _normalized_background_opacity(settings.background_opacity)
        footer_email_parts = _split_email_parts(settings.contact_email)
        return {
            "society_name": brand_name,
            "tile_content": _get_tile_content(),
            "global_background_url": global_background_url,
            "global_background_style": global_background_style,
            "global_overlay_style": f"background-color: rgba(245, 240, 235, {overlay_alpha});",
            "site_settings": settings,
            "footer_email_user": footer_email_parts["user"],
            "footer_email_domain": footer_email_parts["domain"],
            "resident_profile": _resident_profile_from_session(),
            "current_year": date.today().year,
        }

    @app.route("/")
    def index():
        settings = _get_site_settings()
        tile_content = _get_tile_content()
        category_cards = [
            {
                "title": tile_content["society_office"]["title"],
                "description": tile_content["society_office"]["blurb"],
                "href": url_for("society_office_page"),
                "enabled": settings.feature_directory,
            },
            {
                "title": tile_content["service_requests"]["title"],
                "description": tile_content["service_requests"]["blurb"],
                "href": url_for("service_requests_page"),
                "enabled": settings.feature_ticketing,
            },
            {
                "title": tile_content["forms"]["title"],
                "description": tile_content["forms"]["blurb"],
                "href": url_for("forms_page"),
                "enabled": True,
            },
            {
                "title": "Services Directory",
                "description": "Trusted neighborhood businesses and essential contacts.",
                "href": url_for("services_directory_page"),
                "enabled": settings.feature_directory,
            },
            {
                "title": tile_content["book_amenities"]["title"],
                "description": tile_content["book_amenities"]["blurb"],
                "href": url_for("book_amenities_page"),
                "enabled": settings.feature_amenities,
            },
        ]
        return render_template(
            "index.html",
            category_cards=category_cards,
            carousel_images=resolve_carousel_images(app.config),
            active_mc_notices=_active_mc_notices(),
            tile_content=tile_content,
        )

    @app.route("/hero/<path:filename>")
    def hero_file(filename: str):
        hero_root = Path(app.config["HERO_UPLOADS_PATH"])
        return send_from_directory(hero_root, filename)

    @app.route("/notices")
    def notices_page():
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Notices from the Managing Committee",
            tile_key="notices_desc",
            tile_content=_get_tile_content(),
            cards=[
                {"title": notice.title, "description": notice.content, "meta": "Priority" if notice.priority else ""}
                for notice in notices
            ],
        )

    @app.route("/announcements")
    def announcements_page():
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Announcements",
            tile_key="announcements",
            tile_content=_get_tile_content(),
            cards=[
                {"title": row.title, "description": row.content, "meta": row.created_at.strftime("%Y-%m-%d")}
                for row in announcements
            ],
        )

    @app.route("/events")
    def events_page():
        events = Event.query.order_by(Event.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Events",
            tile_key="events",
            tile_content=_get_tile_content(),
            cards=[
                {"title": row.title, "description": row.details or "Community event", "meta": row.event_date}
                for row in events
            ],
        )

    @app.route("/book-amenities")
    def book_amenities_page():
        gate = _enforce_feature_enabled("feature_amenities")
        if gate:
            return gate
        amenity_cards = _ordered_amenities(active_only=True)
        return render_template(
            "book_amenities.html",
            amenity_cards=amenity_cards,
            tile_content=_get_tile_content(),
        )

    @app.route("/book-amenities/<int:amenity_id>")
    def book_amenity_detail(amenity_id: int):
        gate = _enforce_feature_enabled("feature_amenities")
        if gate:
            return gate
        amenity = db.session.get(Amenity, amenity_id)
        if not amenity or not amenity.is_active:
            abort(404)
        amenities = _ordered_amenities(active_only=True)
        selected_bookings = (
            Booking.query.filter_by(amenity_id=amenity.id)
            .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
            .all()
        )
        return render_template(
            "amenities_booking.html",
            amenities=amenities,
            selected_amenity=amenity,
            existing_bookings=selected_bookings,
            booking_time_options=BOOKING_TIME_SLOTS,
            tile_content=_get_tile_content(),
        )

    @app.route("/api/amenities/<int:amenity_id>/bookings")
    @require_feature_flag("feature_amenities")
    def api_amenity_bookings(amenity_id: int):
        amenity = db.session.get(Amenity, amenity_id)
        if not amenity or not amenity.is_active:
            return jsonify({"error": "Amenity not found."}), 404
        rows = (
            Booking.query.filter_by(amenity_id=amenity_id)
            .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
            .all()
        )
        events = [
            {
                "id": row.id,
                "title": f"{amenity.name} booking",
                "start": f"{row.booking_date.isoformat()}T{row.start_time.strftime('%H:%M:%S')}",
                "end": f"{row.booking_date.isoformat()}T{row.end_time.strftime('%H:%M:%S')}",
                "extendedProps": {
                    "resident_name": row.resident_name,
                    "resident_email": row.resident_email,
                },
            }
            for row in rows
        ]
        return jsonify({"amenity": amenity.name, "events": events})

    @app.route("/api/amenities/book", methods=["POST"])
    @require_feature_flag("feature_amenities")
    def api_create_amenity_booking():
        payload = request.get_json(silent=True) or request.form
        amenity_id_raw = (payload.get("amenity_id") or "").strip()
        resident_name = (payload.get("resident_name") or "").strip()
        resident_email = normalize_email(payload.get("resident_email", ""))
        booking_date = _parse_booking_date(payload.get("booking_date", ""))
        start_time = _parse_booking_time(payload.get("start_time", ""))
        end_time = _parse_booking_time(payload.get("end_time", ""))

        if not amenity_id_raw.isdigit():
            return jsonify({"error": "Amenity is required."}), 400
        amenity = db.session.get(Amenity, int(amenity_id_raw))
        if not amenity or not amenity.is_active:
            return jsonify({"error": "Amenity not found."}), 404
        if not resident_name or not resident_email:
            return jsonify({"error": "Resident name and email are required."}), 400
        if not booking_date or not start_time or not end_time:
            return jsonify({"error": "Valid date and time slots are required."}), 400
        if start_time >= end_time:
            return jsonify({"error": "End time must be later than start time."}), 400
        if booking_date < date.today():
            return jsonify({"error": "Booking date cannot be in the past."}), 400
        if booking_date == date.today() and start_time <= datetime.now().time():
            return jsonify({"error": "Past time slots cannot be booked for today."}), 400
        window_violation = _amenity_booking_window_violation(amenity, start_time, end_time)
        if window_violation:
            return jsonify({"error": window_violation}), 400
        if _booking_conflict_exists(amenity.id, booking_date, start_time, end_time):
            return jsonify({"error": "Selected slot is already booked for this amenity."}), 409

        booking = Booking(
            resident_name=resident_name,
            resident_email=resident_email,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            amenity_id=amenity.id,
        )
        db.session.add(booking)
        db.session.commit()
        email_sent, email_status = _send_booking_confirmation_email(
            app,
            booking=booking,
            amenity=amenity,
        )

        return (
            jsonify(
                {
                    "id": booking.id,
                    "amenity": amenity.name,
                    "booking_date": booking.booking_date.isoformat(),
                    "start_time": booking.start_time.strftime("%H:%M"),
                    "end_time": booking.end_time.strftime("%H:%M"),
                    "cost": float(amenity.cost or 0.0),
                    "email_sent": email_sent,
                    "email_status": email_status,
                }
            ),
            201,
        )

    @app.route("/admin/amenities/pricing", methods=["POST"])
    @permission_required("amenities")
    @require_feature_flag("feature_amenities")
    def admin_update_amenity_pricing():
        amenity_id_raw = (request.form.get("amenity_id") or "").strip()
        if not amenity_id_raw.isdigit():
            abort(400, description="Amenity ID must be numeric.")
        amenity = db.session.get(Amenity, int(amenity_id_raw))
        if not amenity:
            abort(404)
        cost_raw = (request.form.get("cost") or "").strip()
        available_from = _parse_time_window(request.form.get("available_from", ""), time(6, 0))
        available_to = _parse_time_window(request.form.get("available_to", ""), time(22, 0))
        try:
            cost_value = float(cost_raw or 0.0)
        except ValueError as exc:
            raise abort(400, description="Cost must be a number.") from exc
        if cost_value < 0:
            abort(400, description="Cost cannot be negative.")
        if available_from >= available_to:
            abort(400, description="Availability end time must be later than start time.")
        amenity.cost = cost_value
        amenity.available_from = available_from
        amenity.available_to = available_to
        db.session.commit()
        return redirect(url_for("admin_manage_amenities"))

    @app.route("/society-office")
    def society_office_page():
        gate = _enforce_feature_enabled("feature_directory")
        if gate:
            return gate
        return render_template(
            "society_office.html",
            items=_directory_items_for_category("society_office"),
            tile_content=_get_tile_content(),
        )

    @app.route("/service-requests")
    def service_requests_page():
        gate = _enforce_feature_enabled("feature_ticketing")
        if gate:
            return gate
        return render_template(
            "service_requests.html",
            items=_directory_items_for_category("service_requests"),
            tile_content=_get_tile_content(),
            ticket_statuses=SERVICE_TICKET_STATUS_FLOW,
            resident_profile=_resident_profile_from_session(),
        )

    @app.route("/service-tickets", methods=["POST"])
    @require_feature_flag("feature_ticketing")
    def create_service_ticket():
        full_name = (request.form.get("full_name") or "").strip()
        flat_number = (request.form.get("flat_number") or "").strip()
        email = normalize_email(request.form.get("email", ""))
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not full_name or not flat_number or not email:
            flash("Name, flat number, and email are required to raise a ticket.", "error")
            return redirect(url_for("service_requests_page"))
        if not category:
            flash("Service category is required.", "error")
            return redirect(url_for("service_requests_page"))
        if not description:
            flash("Please describe the issue before submitting.", "error")
            return redirect(url_for("service_requests_page"))
        category_item = DirectoryItem.query.filter_by(
            category="service_requests",
            title=category,
        ).first()
        if not category_item:
            flash("Selected category is invalid.", "error")
            return redirect(url_for("service_requests_page"))
        resident_user = _upsert_resident_user(
            full_name=full_name,
            flat_number=flat_number,
            email=email,
        )
        db.session.add(
            ServiceTicket(
                user_id=resident_user.id,
                category=category,
                description=description,
                status="Open",
            )
        )
        db.session.commit()
        session["resident_user_id"] = resident_user.id
        session["resident_full_name"] = resident_user.full_name
        session["resident_flat_number"] = resident_user.flat_number
        session["resident_email"] = resident_user.email
        flash("Ticket raised successfully.", "success")
        return redirect(url_for("my_tickets_page"))

    @app.route("/my-tickets")
    def my_tickets_page():
        gate = _enforce_feature_enabled("feature_ticketing")
        if gate:
            return gate
        resident_user = _resident_user_from_session()
        resident = _resident_profile_from_session()
        tickets: list[ServiceTicket] = []
        if resident_user:
            tickets = (
                ServiceTicket.query.filter_by(user_id=resident_user.id)
                .order_by(ServiceTicket.created_at.desc(), ServiceTicket.id.desc())
                .all()
            )
        return render_template(
            "my_tickets.html",
            tickets=tickets,
            resident_profile=resident,
            ticket_statuses=SERVICE_TICKET_STATUS_FLOW,
        )

    @app.route("/my-visitors")
    @require_feature_flag("feature_visitors")
    def my_visitors_page():
        resident_user = _resident_user_from_session()
        resident = _resident_profile_from_session()
        visitor_logs: list[VisitorLog] = []
        if resident_user:
            visitor_logs = _active_visitor_preapprovals_for_user(resident_user.id)
        return render_template(
            "my_visitors.html",
            resident_profile=resident,
            visitor_logs=visitor_logs,
            visitor_categories=VISITOR_CATEGORIES,
            visitor_companies=VISITOR_COMPANIES,
            visitor_company_required_categories=list(VISITOR_COMPANY_REQUIRED_CATEGORIES),
            visitor_status_preapproved=VISITOR_STATUS_PRE_APPROVED,
            visitor_badge_class_resolver=_visitor_status_badge_class,
        )

    @app.route("/my-visitors", methods=["POST"])
    @require_feature_flag("feature_visitors")
    def create_my_visitor():
        resident_user = _resident_user_from_session()
        if not resident_user:
            flash("Please create a ticket once so your resident profile is available.", "error")
            return redirect(url_for("service_requests_page"))

        visitor_name = (request.form.get("visitor_name") or "").strip()
        category = (request.form.get("category") or "").strip()
        company_name = (request.form.get("company_name") or "").strip()
        vehicle_number = (request.form.get("vehicle_number") or "").strip()
        expected_date_raw = (request.form.get("expected_date") or "").strip()
        valid_from_time_raw = (request.form.get("valid_from_time") or "").strip()
        valid_to_time_raw = (request.form.get("valid_to_time") or "").strip()

        if not visitor_name:
            flash("Visitor name is required.", "error")
            return redirect(url_for("my_visitors_page"))
        if category not in VISITOR_CATEGORIES:
            flash("Visitor category is invalid.", "error")
            return redirect(url_for("my_visitors_page"))

        expected_date = _normalize_expected_date(expected_date_raw)
        valid_from_time = _parse_booking_time(valid_from_time_raw)
        valid_to_time = _parse_booking_time(valid_to_time_raw)
        if not valid_from_time or not valid_to_time:
            flash("Both valid from and valid to times are required.", "error")
            return redirect(url_for("my_visitors_page"))
        if valid_from_time >= valid_to_time:
            flash("Valid to time must be later than valid from time.", "error")
            return redirect(url_for("my_visitors_page"))
        normalized_company = _validate_visitor_company(category, company_name)
        entry_code = _generate_visitor_entry_code()

        db.session.add(
            VisitorLog(
                user_id=resident_user.id,
                visitor_name=visitor_name,
                category=category,
                company_name=normalized_company,
                vehicle_number=vehicle_number or None,
                entry_code=entry_code,
                status=VISITOR_STATUS_PRE_APPROVED,
                expected_date=expected_date,
                valid_from_time=valid_from_time,
                valid_to_time=valid_to_time,
            )
        )
        db.session.commit()
        flash("Visitor pre-approval created successfully.", "success")
        return redirect(url_for("my_visitors_page"))

    @app.route("/my-household")
    @require_feature_flag("feature_directory")
    def my_household_page():
        resident_user = _resident_user_from_session()
        settings = _get_site_settings()
        context = _household_directory_context(resident_user, settings)
        return render_template(
            "my_household.html",
            **context,
            household_genders=HOUSEHOLD_GENDERS,
            household_age_groups=HOUSEHOLD_AGE_GROUPS,
            household_staff_categories=STAFF_CATEGORY_OPTIONS,
        )

    @app.route("/my-household/family", methods=["POST"])
    @require_feature_flag("feature_directory")
    def create_household_member():
        resident_user = _resident_user_from_session()
        if not resident_user:
            flash("Please create a ticket once so your resident profile is available.", "error")
            return redirect(url_for("service_requests_page"))
        settings = _get_site_settings()
        context = _household_directory_context(resident_user, settings)
        if context["family_limit_reached"]:
            flash("Maximum family members reached. Contact admin.", "error")
            return redirect(url_for("my_household_page"))

        member_name = (request.form.get("name") or "").strip()
        role = _coerce_household_role(request.form.get("role"))
        gender = _coerce_household_gender(request.form.get("gender"))
        age_group = _coerce_household_age_group(request.form.get("age_group"))
        phone_number = (request.form.get("phone_number") or "").strip()
        occupancy_type = context["occupancy_type"]
        flat_number = context["flat_number"]

        if not flat_number:
            flash("Flat number is required before adding household members.", "error")
            return redirect(url_for("my_household_page"))
        if not member_name:
            flash("Family member name is required.", "error")
            return redirect(url_for("my_household_page"))
        if occupancy_type == "Owner" and role not in HOUSEHOLD_OWNER_ROLES:
            flash("Selected role is invalid for Owner households.", "error")
            return redirect(url_for("my_household_page"))
        if occupancy_type == "Tenant" and role not in HOUSEHOLD_TENANT_ROLES:
            flash("Selected role is invalid for Tenant households.", "error")
            return redirect(url_for("my_household_page"))
        if role in {"First Owner", "Second Owner", "Main Tenant"}:
            existing_primary = ResidentDirectory.query.filter_by(
                flat_number=flat_number,
                role=role,
            ).first()
            if existing_primary:
                flash(f"{role} already exists for this flat.", "error")
                return redirect(url_for("my_household_page"))

        db.session.add(
            ResidentDirectory(
                flat_number=flat_number,
                name=member_name,
                occupancy_type=occupancy_type,
                role=role,
                gender=gender,
                age_group=age_group,
                phone_number=phone_number or None,
                user_id=resident_user.id,
            )
        )
        db.session.commit()
        flash("Family member added successfully.", "success")
        return redirect(url_for("my_household_page"))

    @app.route("/my-household/staff", methods=["POST"])
    @require_feature_flag("feature_directory")
    def create_household_staff():
        resident_user = _resident_user_from_session()
        if not resident_user:
            flash("Please create a ticket once so your resident profile is available.", "error")
            return redirect(url_for("service_requests_page"))
        settings = _get_site_settings()
        context = _household_directory_context(resident_user, settings)
        flat_number = context["flat_number"]
        if not flat_number:
            flash("Flat number is required before registering service staff.", "error")
            return redirect(url_for("my_household_page"))

        name = (request.form.get("name") or "").strip()
        service_category = _coerce_staff_category(request.form.get("service_category"))
        gender = _coerce_household_gender(request.form.get("gender"))
        phone_number = (request.form.get("phone_number") or "").strip()

        if not name:
            flash("Service staff name is required.", "error")
            return redirect(url_for("my_household_page"))
        if not phone_number:
            flash("Service staff phone number is required.", "error")
            return redirect(url_for("my_household_page"))

        existing_staff = ServiceStaff.query.filter_by(phone_number=phone_number).first()
        if existing_staff:
            linked = {
                _normalized_flat_number(value)
                for value in (existing_staff.linked_flats or "").split(",")
                if value.strip()
            }
            linked.add(flat_number)
            existing_staff.name = name
            existing_staff.service_category = service_category
            existing_staff.gender = gender
            existing_staff.linked_flats = ",".join(sorted(linked))
        else:
            db.session.add(
                ServiceStaff(
                    name=name,
                    service_category=service_category,
                    gender=gender,
                    phone_number=phone_number,
                    linked_flats=flat_number,
                )
            )
        db.session.commit()
        flash("Service staff registered successfully.", "success")
        return redirect(url_for("my_household_page"))

    @app.route("/security/visitors")
    @permission_required("visitors")
    @require_feature_flag("feature_visitors")
    def security_visitors_page():
        active_entries = (
            VisitorLog.query.join(User, VisitorLog.user_id == User.id)
            .filter(VisitorLog.status == VISITOR_STATUS_ENTERED)
            .order_by(VisitorLog.entry_time.desc(), VisitorLog.id.desc())
            .all()
        )
        return render_template(
            "security_visitors.html",
            entry_result=None,
            active_entries=active_entries,
            visitor_status_entered=VISITOR_STATUS_ENTERED,
            visitor_status_exited=VISITOR_STATUS_EXITED,
            visitor_badge_class_resolver=_visitor_status_badge_class,
            visitor_security_label_resolver=_visitor_security_label,
        )

    @app.route("/api/security/validate-code/<code>")
    @permission_required("visitors")
    @require_feature_flag("feature_visitors")
    def security_validate_visitor_code(code: str):
        is_valid, message, visitor = _validate_visitor_entry_code(code)
        if not is_valid or not visitor:
            return jsonify({"valid": False, "message": message})
        resident_flat = ((visitor.user.flat_number if visitor.user else "") or "").strip()
        return jsonify(
            {
                "valid": True,
                "visitor": {
                    "name": visitor.visitor_name,
                    "category": visitor.category,
                    "flat_number": resident_flat,
                },
            }
        )

    @app.route("/security/visitors/enter", methods=["POST"])
    @permission_required("visitors")
    @require_feature_flag("feature_visitors")
    def security_mark_visitor_entered():
        entry_code = (request.form.get("entry_code") or "").strip()
        is_valid, message, visitor = _validate_visitor_entry_code(entry_code)
        if not is_valid or not visitor:
            flash(message, "error")
            return redirect(url_for("security_visitors_page"))

        visitor.status = VISITOR_STATUS_ENTERED
        visitor.entry_time = datetime.utcnow()
        db.session.commit()
        flash(f"Marked entry for {visitor.visitor_name}.", "success")
        return redirect(url_for("security_visitors_page"))

    @app.route("/security/visitors/<int:visitor_id>/exit", methods=["POST"])
    @permission_required("visitors")
    @require_feature_flag("feature_visitors")
    def security_mark_visitor_exited(visitor_id: int):
        visitor = db.session.get(VisitorLog, visitor_id)
        if not visitor:
            abort(404)
        if visitor.status != VISITOR_STATUS_ENTERED:
            flash("Only entered visitors can be marked exited.", "error")
            return redirect(url_for("security_visitors_page"))

        visitor.status = VISITOR_STATUS_EXITED
        visitor.exit_time = datetime.utcnow()
        db.session.commit()
        flash(f"Marked exit for {visitor.visitor_name}.", "success")
        return redirect(url_for("security_visitors_page"))

    @app.route("/admin/manage-visitors")
    @permission_required("visitors")
    @require_feature_flag("feature_visitors")
    def admin_manage_visitors():
        status_filter = (request.args.get("status") or "").strip()
        expected_date_raw = (request.args.get("expected_date") or "").strip()
        if status_filter and status_filter not in VISITOR_STATUS_OPTIONS:
            abort(400, description="Visitor status filter is invalid.")
        expected_date = _parse_iso_date(expected_date_raw) if expected_date_raw else None
        if expected_date_raw and not expected_date:
            abort(400, description="Expected date filter must be YYYY-MM-DD.")
        visitor_logs = _visitor_logs_filtered_for_admin(status_filter, expected_date)
        return render_template(
            "admin_manage_visitors.html",
            visitor_logs=visitor_logs,
            status_filter=status_filter,
            expected_date_filter=expected_date_raw,
            visitor_status_options=VISITOR_STATUS_OPTIONS,
            visitor_badge_class_resolver=_visitor_status_badge_class,
            visitor_security_label_resolver=_visitor_security_label,
        )

    @app.route("/forms")
    def forms_page():
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).limit(24).all()
        form_cards = [
            {
                "title": item.title,
                "description": f"{item.extension.upper()} form",
                "href": url_for("uploads_file", filename=item.relative_path),
                "image_url": FORM_CARD_IMAGE_BY_EXTENSION.get(
                    (item.extension or "").lower(), DEFAULT_FORM_CARD_IMAGE
                ),
            }
            for item in uploads
        ]
        return render_template("forms.html", form_cards=form_cards, tile_content=_get_tile_content())

    @app.route("/services-directory")
    def services_directory_page():
        gate = _enforce_feature_enabled("feature_directory")
        if gate:
            return gate
        return render_template(
            "services_directory.html",
            items=_directory_items_for_category("services_directory"),
            tile_content=_get_tile_content(),
        )

    @app.route("/drive-documents")
    def drive_documents_page():
        documents, docs_error = resolve_drive_documents(app.config)
        return render_template(
            "drive_documents.html",
            drive_documents=documents,
            drive_documents_error=docs_error,
            tile_content=_get_tile_content(),
        )

    @app.route("/api/health")
    def health():
        settings = _get_site_settings()
        return jsonify(
            {
                "status": "ok",
                "database_path": str(app.config["DB_PATH"]),
                "uploads_path": str(app.config["UPLOADS_PATH"]),
                "hero_uploads_path": str(app.config["HERO_UPLOADS_PATH"]),
                "society_name": (settings.society_name or "").strip()
                or app.config["SOCIETY_NAME"]
                or "Golf Meadows",
            }
        )

    @app.route("/api/email-links")
    def api_email_links():
        category = (request.args.get("category") or "").strip().lower()
        subject = request.args.get("subject", "").strip()
        body = request.args.get("body", "").strip()
        recipient = _recipient_for_category(category, app.config["SUPER_ADMIN_EMAIL"])
        if not recipient:
            return jsonify({"error": "No recipient configured for this category."}), 400
        email_links = build_email_links(recipient, subject, body)
        return jsonify({"to": recipient, **email_links})

    @app.route("/api/carousel-images")
    def api_carousel_images():
        return jsonify({"images": resolve_carousel_images(app.config)})

    @app.route("/api/drive-documents")
    def api_drive_documents():
        documents, docs_error = resolve_drive_documents(app.config)
        return jsonify({"documents": documents, "error": docs_error})

    @app.route("/admin-login")
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for("admin_dashboard"))
        oauth_enabled = bool(
            app.config["GOOGLE_OAUTH_CLIENT_ID"] and app.config["GOOGLE_OAUTH_CLIENT_SECRET"]
        )
        return render_template("admin_login.html", oauth_enabled=oauth_enabled)

    @app.route("/auth/google")
    def auth_google():
        if "google" not in oauth._clients:  # noqa: SLF001
            abort(503, description="Google OAuth is not configured.")
        redirect_uri = app.config["OAUTH_REDIRECT_URI"] or url_for(
            "auth_google_callback", _external=True
        )
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/callback")
    @app.route("/auth/google/callback")
    def auth_google_callback():
        if "google" not in oauth._clients:  # noqa: SLF001
            abort(503, description="Google OAuth is not configured.")
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo") or oauth.google.userinfo()
        email = normalize_email((user_info.get("email") or "").lower())
        if not email:
            abort(403, description="Google account email unavailable.")
        if not _is_domain_allowed_email(email):
            flash("Only @golfmeadows.org accounts are allowed for admin access.", "error")
            return redirect(url_for("index"))

        super_admin_email = normalize_email(app.config["SUPER_ADMIN_EMAIL"])
        is_super_admin = email == super_admin_email
        admin = Admin.query.filter_by(email=email, is_active=True).first()

        if is_super_admin and not admin:
            admin = Admin(
                email=email,
                is_super_admin=True,
                is_active=True,
                display_name=user_info.get("name", ""),
                role_id=None,
            )
            db.session.add(admin)
            db.session.commit()

        if not admin:
            flash("Your account is not authorized for admin access.", "error")
            return redirect(url_for("index"))
        if not is_super_admin and (not admin.role_id or not admin.role):
            flash("Your account does not have an assigned role.", "error")
            return redirect(url_for("index"))

        admin.display_name = user_info.get("name", admin.display_name)
        admin.is_super_admin = admin.is_super_admin or is_super_admin
        if admin.is_super_admin:
            admin.role_id = None
        db.session.commit()
        login_user(admin)
        session["admin_email"] = admin.email
        return redirect(url_for("admin_dashboard"))

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        settings = _get_site_settings()
        permissions = _permissions_for_user(current_user)
        tiles = []
        for tile in ADMIN_TILE_DEFINITIONS:
            if tile["permission"] not in permissions and not current_user.is_super_admin:
                continue
            endpoint_name = tile["endpoint"][0]
            if endpoint_name == "admin_manage_tickets" and not settings.feature_ticketing:
                continue
            if endpoint_name in {
                "admin_manage_amenities",
                "admin_manage_bookings",
            } and not settings.feature_amenities:
                continue
            if endpoint_name == "admin_manage_directory" and not settings.feature_directory:
                continue
            if endpoint_name == "admin_core_directory" and not settings.feature_directory:
                continue
            if endpoint_name == "admin_manage_visitors" and not settings.feature_visitors:
                continue
            endpoint, kwargs = tile["endpoint"]
            tiles.append(
                {
                    "title": tile["title"],
                    "description": tile["description"],
                    "href": url_for(endpoint, **kwargs),
                }
            )
        if current_user.is_super_admin:
            tiles.extend(
                [
                    {
                        "title": "Manage Roles",
                        "description": "Create and update role permission bundles.",
                        "href": url_for("admin_manage_roles"),
                    },
                    {
                        "title": "Manage Administrators",
                        "description": "Invite, assign roles, and control admin access.",
                        "href": url_for("admin_manage_administrators"),
                    },
                ]
            )
        roles = Role.query.order_by(Role.name.asc()).all() if current_user.is_super_admin else []
        admins = Admin.query.order_by(Admin.created_at.desc()).all() if current_user.is_super_admin else []
        return render_template(
            "admin.html",
            tiles=tiles,
            roles=roles,
            admins=admins,
            role_permissions=ROLE_PERMISSIONS,
        )

    @app.route("/admin/manage-directory/<category>")
    @admin_required
    def admin_manage_directory(category: str):
        gate = _enforce_feature_enabled("feature_directory")
        if gate:
            return gate
        normalized = _coerce_directory_category(category)
        if not _user_can_manage_directory_category(normalized):
            abort(403)
        items = (
            DirectoryItem.query.filter_by(category=normalized)
            .order_by(DirectoryItem.title.asc(), DirectoryItem.created_at.asc())
            .all()
        )
        return render_template(
            "admin_manage_directory.html",
            selected_category=normalized,
            category_label=DIRECTORY_ITEM_CATEGORIES[normalized],
            directory_categories=DIRECTORY_ITEM_CATEGORIES,
            directory_items=items,
        )

    @app.route("/admin/manage-amenities")
    @permission_required("amenities")
    def admin_manage_amenities():
        gate = _enforce_feature_enabled("feature_amenities")
        if gate:
            return gate
        amenities = _ordered_amenities(active_only=False)
        return render_template("admin_manage_amenities.html", amenities=amenities)

    @app.route("/admin/manage-bookings")
    @permission_required("bookings")
    def admin_manage_bookings():
        gate = _enforce_feature_enabled("feature_amenities")
        if gate:
            return gate
        amenity_id_raw = (request.args.get("amenity_id") or "").strip()
        booking_date_raw = (request.args.get("booking_date") or "").strip()
        query = Booking.query.join(Amenity, Booking.amenity_id == Amenity.id)
        selected_amenity_id = ""
        if amenity_id_raw:
            if not amenity_id_raw.isdigit():
                abort(400, description="Amenity filter must be numeric.")
            selected_amenity_id = amenity_id_raw
            query = query.filter(Booking.amenity_id == int(amenity_id_raw))
        selected_booking_date = ""
        if booking_date_raw:
            booking_date = _parse_booking_date(booking_date_raw)
            if not booking_date:
                abort(400, description="Booking date filter must be YYYY-MM-DD.")
            selected_booking_date = booking_date.isoformat()
            query = query.filter(Booking.booking_date == booking_date)
        bookings = (
            query.order_by(
                Booking.booking_date.desc(),
                Booking.start_time.asc(),
                Booking.created_at.desc(),
            ).all()
        )
        amenities = _ordered_amenities(active_only=False)
        return render_template(
            "admin_manage_bookings.html",
            bookings=bookings,
            amenities=amenities,
            selected_amenity_id=selected_amenity_id,
            selected_booking_date=selected_booking_date,
        )

    @app.route("/admin/directory")
    @permission_required("resident_directory")
    @require_feature_flag("feature_directory")
    def admin_core_directory():
        active_tab = (request.args.get("tab") or "residents").strip().lower()
        if active_tab not in {"residents", "staff"}:
            active_tab = "residents"
        resident_rows = (
            ResidentDirectory.query.order_by(
                ResidentDirectory.flat_number.asc(),
                ResidentDirectory.occupancy_type.asc(),
                ResidentDirectory.role.asc(),
                ResidentDirectory.name.asc(),
            ).all()
        )
        staff_rows = ServiceStaff.query.order_by(
            ServiceStaff.service_category.asc(),
            ServiceStaff.name.asc(),
        ).all()
        return render_template(
            "admin_directory.html",
            active_tab=active_tab,
            resident_rows=resident_rows,
            staff_rows=staff_rows,
        )

    @app.route("/admin/manage-tickets")
    @permission_required("tickets")
    def admin_manage_tickets():
        gate = _enforce_feature_enabled("feature_ticketing")
        if gate:
            return gate
        tickets = (
            ServiceTicket.query.join(User, ServiceTicket.user_id == User.id)
            .order_by(ServiceTicket.created_at.desc(), ServiceTicket.id.desc())
            .all()
        )
        return render_template(
            "admin_manage_tickets.html",
            tickets=tickets,
            ticket_statuses=SERVICE_TICKET_STATUS_FLOW,
        )

    @app.route("/admin/manage-tickets/<int:ticket_id>")
    @permission_required("tickets")
    def admin_edit_ticket(ticket_id: int):
        gate = _enforce_feature_enabled("feature_ticketing")
        if gate:
            return gate
        ticket = db.session.get(ServiceTicket, ticket_id)
        if not ticket:
            abort(404)
        return render_template(
            "admin_edit_ticket.html",
            ticket=ticket,
            ticket_statuses=SERVICE_TICKET_STATUS_FLOW,
        )

    @app.route("/admin/manage-tickets/<int:ticket_id>/update", methods=["POST"])
    @permission_required("tickets")
    @require_feature_flag("feature_ticketing")
    def admin_update_ticket(ticket_id: int):
        ticket = db.session.get(ServiceTicket, ticket_id)
        if not ticket:
            abort(404)
        status = _coerce_ticket_status(request.form.get("status"))
        admin_notes = (request.form.get("admin_notes") or "").strip()
        ticket.status = status
        ticket.admin_notes = admin_notes or None
        db.session.commit()
        flash("Ticket updated successfully.", "success")
        return redirect(url_for("admin_edit_ticket", ticket_id=ticket.id))

    @app.route("/admin/manage-notices")
    @permission_required("notices")
    def admin_manage_notices():
        recipient = _get_recipient_config()
        mc_notices = MCNotice.query.order_by(MCNotice.start_date.desc(), MCNotice.created_at.desc()).all()
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).all()
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
        events = Event.query.order_by(Event.created_at.desc()).all()
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).all()
        drive_documents, docs_error = resolve_drive_documents(app.config)
        aliases = DriveDocumentMapping.query.order_by(DriveDocumentMapping.created_at.desc()).all()
        drive_aliases = {row.drive_file_id: row.display_name for row in aliases}
        alias_index = {row.drive_file_id: row.id for row in aliases}
        return render_template(
            "admin_manage_notices.html",
            recipient=recipient,
            mc_notices=mc_notices,
            notices=notices,
            announcements=announcements,
            events=events,
            admins=admins,
            uploads=uploads,
            drive_documents=drive_documents,
            drive_docs_error=docs_error,
            drive_aliases=drive_aliases,
            alias_index=alias_index,
            tile_content=_get_tile_content(),
            icon_resolver=file_icon_for_extension,
        )

    @app.route("/admin/manage-hero")
    @permission_required("hero_images")
    def admin_manage_hero():
        hero_images = list_hero_images(app.config["HERO_UPLOADS_PATH"])
        return render_template("admin_manage_hero.html", hero_images=hero_images)

    @app.route("/admin/manage-settings")
    @permission_required("global_settings")
    def admin_manage_settings():
        settings = _get_site_settings()
        hero_images = list_hero_images(app.config["HERO_UPLOADS_PATH"])
        return render_template(
            "admin_manage_settings.html",
            settings=settings,
            hero_images=hero_images,
            selected_background=settings.global_background_image,
        )

    @app.route("/admin/global-settings", methods=["POST"])
    @permission_required("global_settings")
    def admin_update_global_settings():
        selected = (request.form.get("global_background_image") or "").strip()
        background_opacity_raw = (request.form.get("background_opacity") or "").strip()
        society_name = (request.form.get("society_name") or "").strip()
        postal_address = (request.form.get("postal_address") or "").strip()
        contact_email = normalize_email(request.form.get("contact_email", ""))
        bank_details = (request.form.get("bank_details") or "").strip()
        feature_ticketing = request.form.get("feature_ticketing") == "on"
        feature_amenities = request.form.get("feature_amenities") == "on"
        feature_directory = request.form.get("feature_directory") == "on"
        feature_visitors = request.form.get("feature_visitors") == "on"
        logo_file = request.files.get("society_logo")
        available_filenames = {
            image["filename"] for image in list_hero_images(app.config["HERO_UPLOADS_PATH"])
        }
        if selected and selected not in available_filenames:
            abort(400, description="Selected background image is not available.")
        try:
            opacity_value = float(background_opacity_raw or 90.0)
        except ValueError as exc:
            raise abort(400, description="Background opacity must be numeric.") from exc
        normalized_society_name = society_name[:120] if society_name else "Golf Meadows"
        if not normalized_society_name.strip():
            normalized_society_name = "Golf Meadows"

        settings = _get_site_settings()
        settings.global_background_image = selected
        settings.background_opacity = max(0.0, min(opacity_value, 100.0))
        settings.society_name = normalized_society_name
        settings.postal_address = postal_address
        settings.contact_email = contact_email
        settings.bank_details = bank_details
        settings.feature_ticketing = feature_ticketing
        settings.feature_amenities = feature_amenities
        settings.feature_directory = feature_directory
        settings.feature_visitors = feature_visitors
        settings.max_owner_family = _safe_int_setting(
            request.form.get("max_owner_family"),
            4,
        )
        settings.max_tenant_family = _safe_int_setting(
            request.form.get("max_tenant_family"),
            4,
        )

        if logo_file and logo_file.filename:
            safe_name = secure_filename(logo_file.filename)
            if not safe_name:
                abort(400, description="Uploaded logo filename is invalid.")
            branding_dir = Path(app.static_folder or "static") / "uploads" / "branding"
            branding_dir.mkdir(parents=True, exist_ok=True)
            extension = Path(safe_name).suffix.lower()

            if extension == ".svg":
                logo_file.stream.seek(0)
                svg_bytes = logo_file.stream.read()
                if not svg_bytes.strip():
                    abort(400, description="SVG logo file cannot be empty.")
                if b"<svg" not in svg_bytes.lower():
                    abort(400, description="Uploaded SVG logo is invalid.")
                logo_output_path = branding_dir / "logo.svg"
                with logo_output_path.open("wb") as logo_output:
                    logo_output.write(svg_bytes)
                settings.logo_path = "uploads/branding/logo.svg"
            else:
                logo_file.stream.seek(0)
                try:
                    with Image.open(logo_file.stream) as raw_image:
                        if raw_image.mode in {"RGBA", "LA"} or (
                            raw_image.mode == "P" and "transparency" in raw_image.info
                        ):
                            rgba_image = raw_image.convert("RGBA")
                            composed = Image.new("RGB", rgba_image.size, (255, 255, 255))
                            composed.paste(rgba_image, mask=rgba_image.split()[-1])
                            logo_image = composed
                        else:
                            logo_image = raw_image.convert("RGB")

                        if logo_image.height > 200:
                            resized_width = max(
                                1, int(logo_image.width * (200 / float(logo_image.height)))
                            )
                            resampling = (
                                Image.Resampling.LANCZOS
                                if hasattr(Image, "Resampling")
                                else Image.LANCZOS
                            )
                            logo_image = logo_image.resize((resized_width, 200), resampling)

                        output_buffer = BytesIO()
                        logo_image.save(output_buffer, format="WEBP", quality=90, method=6)
                        output_buffer.seek(0)
                except OSError:
                    abort(400, description="Logo file must be a valid image.")

                logo_output_path = branding_dir / "logo.webp"
                with logo_output_path.open("wb") as logo_output:
                    logo_output.write(output_buffer.read())
                settings.logo_path = "uploads/branding/logo.webp"

        if settings.logo_path:
            normalized_logo_path = (settings.logo_path or "").strip()
            if normalized_logo_path.startswith("/"):
                normalized_logo_path = normalized_logo_path[1:]
            settings.logo_path = normalized_logo_path or None

        db.session.commit()
        return redirect(url_for("admin_manage_settings"))

    @app.route("/admin/amenities", methods=["POST"])
    @permission_required("amenities")
    @require_feature_flag("feature_amenities")
    def admin_create_amenity():
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        cost_raw = (request.form.get("cost") or "0").strip()
        available_from = _parse_time_window(request.form.get("available_from", ""), time(6, 0))
        available_to = _parse_time_window(request.form.get("available_to", ""), time(22, 0))
        if not name or not description:
            abort(400, description="Amenity name and description are required.")
        if available_from >= available_to:
            abort(400, description="Availability end time must be later than start time.")
        if Amenity.query.filter_by(name=name).first():
            abort(400, description="Amenity with this name already exists.")
        try:
            cost_value = float(cost_raw or 0.0)
        except ValueError as exc:
            raise abort(400, description="Amenity cost must be numeric.") from exc
        if cost_value < 0:
            abort(400, description="Amenity cost cannot be negative.")

        image_file = request.files.get("image_file")
        image_url = ""
        if image_file and image_file.filename:
            if not allowed_file(image_file.filename, AMENITY_IMAGE_ALLOWED_EXTENSIONS):
                abort(400, description="Amenity image must be JPG, PNG, or WEBP.")
            stored_name, _ = save_amenity_image(image_file, app.config["AMENITY_UPLOADS_PATH"])
            image_url = url_for("uploads_file", filename=f"amenities/{stored_name}")

        if not image_url:
            image_url = (
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1400&q=80"
            )

        db.session.add(
            Amenity(
                name=name,
                description=description,
                image_url=image_url,
                cost=cost_value,
                is_active=True,
                available_from=available_from,
                available_to=available_to,
            )
        )
        db.session.commit()
        return redirect(url_for("admin_manage_amenities"))

    @app.route("/admin/mc-notices", methods=["POST"])
    @permission_required("notices")
    def admin_create_mc_notice():
        title = (request.form.get("title") or "").strip()
        message = (request.form.get("message") or "").strip()
        start_date_raw = (request.form.get("start_date") or "").strip()
        end_date_raw = (request.form.get("end_date") or "").strip()
        if not title or not message or not start_date_raw or not end_date_raw:
            abort(400, description="Title, message, start date, and end date are required.")

        start_date = _parse_iso_date(start_date_raw)
        end_date = _parse_iso_date(end_date_raw)
        if not start_date or not end_date:
            abort(400, description="Dates must be valid ISO format (YYYY-MM-DD).")
        if end_date < start_date:
            abort(400, description="End date must be on or after start date.")

        db.session.add(
            MCNotice(
                title=title,
                message=message,
                start_date=start_date,
                end_date=end_date,
            )
        )
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/mc-notices/<int:notice_id>/delete", methods=["POST"])
    @permission_required("notices")
    def admin_delete_mc_notice(notice_id: int):
        notice = db.session.get(MCNotice, notice_id)
        if not notice:
            abort(404)
        db.session.delete(notice)
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/notices", methods=["POST"])
    @permission_required("notices")
    def admin_create_notice():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        priority = request.form.get("priority") == "on"
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Notice(title=title, content=content, priority=priority))
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/notices/<int:notice_id>/delete", methods=["POST"])
    @permission_required("notices")
    def admin_delete_notice(notice_id: int):
        notice = db.session.get(Notice, notice_id)
        if not notice:
            abort(404)
        db.session.delete(notice)
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/announcements", methods=["POST"])
    @permission_required("notices")
    def admin_create_announcement():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Announcement(title=title, content=content))
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/events", methods=["POST"])
    @permission_required("notices")
    def admin_create_event():
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date", "").strip()
        details = request.form.get("details", "").strip()
        if not title or not event_date:
            abort(400, description="Title and event date are required.")
        db.session.add(Event(title=title, event_date=event_date, details=details))
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/recipients", methods=["POST"])
    @permission_required("notices")
    def admin_update_recipients():
        recipient = _get_recipient_config()
        recipient.service_requests_email = normalize_email(
            request.form.get("service_requests_email", "")
        )
        recipient.amenities_email = normalize_email(request.form.get("amenities_email", ""))
        recipient.forms_email = normalize_email(request.form.get("forms_email", ""))
        recipient.office_email = normalize_email(request.form.get("office_email", ""))
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/directory-items", methods=["POST"])
    @admin_required
    @require_feature_flag("feature_directory")
    def admin_create_directory_item():
        payload = _directory_item_payload_from_form(request.form)
        if not _user_can_manage_directory_category(payload["category"]):
            abort(403)
        if not payload["title"]:
            abort(400, description="Title is required.")

        image = request.files.get("image_file")
        if image and image.filename:
            if not allowed_file(image.filename, DIRECTORY_IMAGE_ALLOWED_EXTENSIONS):
                abort(400, description="Directory images must be JPG, PNG, or WEBP.")
            stored_name, _ = save_directory_image(image, app.config["DIRECTORY_UPLOADS_PATH"])
            payload["image_filename"] = stored_name

        db.session.add(DirectoryItem(**payload))
        db.session.commit()
        return redirect(url_for("admin_manage_directory", category=payload["category"]))

    @app.route("/admin/directory-items/<int:item_id>/update", methods=["POST"])
    @admin_required
    @require_feature_flag("feature_directory")
    def admin_update_directory_item(item_id: int):
        item = db.session.get(DirectoryItem, item_id)
        if not item:
            abort(404)
        if not _user_can_manage_directory_category(item.category):
            abort(403)

        payload = _directory_item_payload_from_form(request.form)
        if not payload["title"]:
            abort(400, description="Title is required.")

        image = request.files.get("image_file")
        if image and image.filename:
            if not allowed_file(image.filename, DIRECTORY_IMAGE_ALLOWED_EXTENSIONS):
                abort(400, description="Directory images must be JPG, PNG, or WEBP.")
            _delete_directory_image_file(item.image_filename, app.config["DIRECTORY_UPLOADS_PATH"])
            stored_name, _ = save_directory_image(image, app.config["DIRECTORY_UPLOADS_PATH"])
            payload["image_filename"] = stored_name
        else:
            payload["image_filename"] = item.image_filename

        for field, value in payload.items():
            setattr(item, field, value)

        db.session.commit()
        return redirect(url_for("admin_manage_directory", category=item.category))

    @app.route("/admin/directory-items/<int:item_id>/delete", methods=["POST"])
    @admin_required
    @require_feature_flag("feature_directory")
    def admin_delete_directory_item(item_id: int):
        item = db.session.get(DirectoryItem, item_id)
        if not item:
            abort(404)
        if not _user_can_manage_directory_category(item.category):
            abort(403)
        category = item.category
        _delete_directory_image_file(item.image_filename, app.config["DIRECTORY_UPLOADS_PATH"])
        db.session.delete(item)
        db.session.commit()
        return redirect(url_for("admin_manage_directory", category=category))

    @app.route("/admin/directory-items/<int:item_id>/image/delete", methods=["POST"])
    @admin_required
    @require_feature_flag("feature_directory")
    def admin_delete_directory_item_image(item_id: int):
        item = db.session.get(DirectoryItem, item_id)
        if not item:
            abort(404)
        if not _user_can_manage_directory_category(item.category):
            abort(403)
        _delete_directory_image_file(item.image_filename, app.config["DIRECTORY_UPLOADS_PATH"])
        item.image_filename = ""
        db.session.commit()
        return redirect(url_for("admin_manage_directory", category=item.category))

    @app.route("/admin/tile-content", methods=["POST"])
    @permission_required("notices")
    def admin_update_tile_content():
        for key in _tile_defaults().keys():
            title = (request.form.get(f"{key}_title") or "").strip()
            blurb = (request.form.get(f"{key}_blurb") or "").strip()
            row = TileContent.query.filter_by(tile_key=key).first()
            if not row:
                row = TileContent(
                    tile_key=key,
                    title=title or key.replace("_", " ").title(),
                    blurb=blurb,
                )
                db.session.add(row)
            else:
                if title:
                    row.title = title
                row.blurb = blurb
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/upload", methods=["POST"])
    @permission_required("notices")
    def admin_upload_file():
        title = request.form.get("title", "").strip()
        file = request.files.get("file")
        if not title or not file or not file.filename:
            abort(400, description="Title and file are required.")
        if not allowed_file(file.filename, app.config["ALLOWED_UPLOAD_EXTENSIONS"]):
            abort(400, description="Unsupported file type.")
        stored_name, relative_path, extension = save_uploaded_file(
            file, app.config["UPLOADS_PATH"]
        )
        db.session.add(
            UploadedFile(
                title=title,
                filename=stored_name,
                relative_path=relative_path,
                extension=extension,
                uploaded_by=current_user.email,
            )
        )
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/hero-images", methods=["POST"])
    @permission_required("hero_images")
    def admin_upload_hero_image():
        file = request.files.get("hero_file")
        if not file or not file.filename:
            abort(400, description="Hero image file is required.")
        if not allowed_file(file.filename, HERO_ALLOWED_EXTENSIONS):
            abort(400, description="Hero images must be JPG, PNG, or WEBP.")
        save_hero_image(file, app.config["HERO_UPLOADS_PATH"])
        return redirect(url_for("admin_manage_hero"))

    @app.route("/admin/hero-images/<path:filename>/delete", methods=["POST"])
    @permission_required("hero_images")
    def admin_delete_hero_image(filename: str):
        hero_root = Path(app.config["HERO_UPLOADS_PATH"]).resolve()
        target = (hero_root / filename).resolve()
        if hero_root not in target.parents and target != hero_root:
            abort(400, description="Invalid hero image path.")
        if target.exists() and target.is_file():
            target.unlink()
        return redirect(url_for("admin_manage_hero"))

    @app.route("/admin/drive-documents/alias", methods=["POST"])
    @permission_required("notices")
    def admin_save_drive_alias():
        drive_file_id = (request.form.get("drive_file_id") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        if not drive_file_id:
            abort(400, description="Drive file ID is required.")
        alias = DriveDocumentMapping.query.filter_by(drive_file_id=drive_file_id).first()
        if not alias:
            alias = DriveDocumentMapping(
                drive_file_id=drive_file_id,
                display_name=display_name,
            )
            db.session.add(alias)
        else:
            alias.display_name = display_name
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/admin/drive-documents/alias/<int:alias_id>/delete", methods=["POST"])
    @permission_required("notices")
    def admin_delete_drive_alias(alias_id: int):
        alias = db.session.get(DriveDocumentMapping, alias_id)
        if not alias:
            abort(404)
        db.session.delete(alias)
        db.session.commit()
        return redirect(url_for("admin_manage_notices"))

    @app.route("/uploads/<path:filename>")
    def uploads_file(filename: str):
        upload_root = Path(app.config["UPLOADS_PATH"])
        return send_from_directory(upload_root, filename)

    @app.route("/admin/manage-roles")
    @super_admin_required
    def admin_manage_roles():
        roles = Role.query.order_by(Role.name.asc()).all()
        return render_template(
            "admin_manage_roles.html",
            roles=roles,
            role_permissions=ROLE_PERMISSIONS,
        )

    @app.route("/admin/manage-administrators")
    @super_admin_required
    def admin_manage_administrators():
        roles = Role.query.order_by(Role.name.asc()).all()
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        return render_template(
            "admin_manage_administrators.html",
            roles=roles,
            admins=admins,
        )

    @app.route("/admin/roles", methods=["POST"])
    @super_admin_required
    def admin_create_role():
        name = (request.form.get("name") or "").strip()
        selected_permissions = request.form.getlist("permissions")
        normalized_permissions = _normalize_permissions(selected_permissions)
        if not name:
            abort(400, description="Role name is required.")
        existing = Role.query.filter(Role.name.ilike(name)).first()
        if existing:
            abort(400, description="Role name already exists.")
        db.session.add(Role(name=name, permissions=normalized_permissions))
        db.session.commit()
        return redirect(url_for("admin_manage_roles"))

    @app.route("/admin/roles/<int:role_id>/update", methods=["POST"])
    @super_admin_required
    def admin_update_role(role_id: int):
        role = db.session.get(Role, role_id)
        if not role:
            abort(404)
        if role.name == "Super Admin":
            abort(400, description="Super Admin role permissions cannot be changed.")
        selected_permissions = request.form.getlist("permissions")
        role.permissions = _normalize_permissions(selected_permissions)
        db.session.commit()
        return redirect(url_for("admin_manage_roles"))

    @app.route("/admin/roles/<int:role_id>/delete", methods=["POST"])
    @super_admin_required
    def admin_delete_role(role_id: int):
        role = db.session.get(Role, role_id)
        if not role:
            abort(404)
        if role.name == "Super Admin":
            abort(400, description="Super Admin role cannot be deleted.")
        if role.admins.count() > 0:
            abort(400, description="Cannot delete role while administrators are assigned.")
        db.session.delete(role)
        db.session.commit()
        return redirect(url_for("admin_manage_roles"))

    @app.route("/admin/admins", methods=["POST"])
    @super_admin_required
    def admin_add_admin():
        email = normalize_email(request.form.get("email", ""))
        role_id_raw = (request.form.get("role_id") or "").strip()
        if not email:
            abort(400, description="Valid email required.")
        is_super_admin_target = email == normalize_email(app.config["SUPER_ADMIN_EMAIL"])
        role_id = None
        if not is_super_admin_target:
            if not role_id_raw.isdigit():
                abort(400, description="Role selection is required.")
            role = db.session.get(Role, int(role_id_raw))
            if not role:
                abort(400, description="Selected role does not exist.")
            role_id = role.id
        existing = Admin.query.filter_by(email=email).first()
        if not existing:
            db.session.add(
                Admin(
                    email=email,
                    is_super_admin=is_super_admin_target,
                    is_active=True,
                    role_id=role_id,
                )
            )
        else:
            existing.role_id = role_id
            existing.is_super_admin = is_super_admin_target or existing.is_super_admin
            existing.is_active = True
        db.session.commit()
        return redirect(url_for("admin_manage_administrators"))

    @app.route("/admin/admins/<int:admin_id>/role", methods=["POST"])
    @super_admin_required
    def admin_update_admin_role(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if admin.is_super_admin:
            return redirect(url_for("admin_manage_administrators"))
        role_id_raw = (request.form.get("role_id") or "").strip()
        if not role_id_raw.isdigit():
            abort(400, description="Role selection is required.")
        role = db.session.get(Role, int(role_id_raw))
        if not role:
            abort(400, description="Selected role does not exist.")
        admin.role_id = role.id
        db.session.commit()
        return redirect(url_for("admin_manage_administrators"))

    @app.route("/admin/admins/<int:admin_id>/toggle", methods=["POST"])
    @super_admin_required
    def admin_toggle_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if normalize_email(admin.email) == normalize_email(app.config["SUPER_ADMIN_EMAIL"]):
            return redirect(url_for("admin_manage_administrators"))
        admin.is_active = not admin.is_active
        db.session.commit()
        return redirect(url_for("admin_manage_administrators"))

    @app.route("/admin/admins/<int:admin_id>/remove", methods=["POST"])
    @super_admin_required
    def admin_remove_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if admin.is_super_admin:
            return redirect(url_for("admin_manage_administrators"))
        db.session.delete(admin)
        db.session.commit()
        return redirect(url_for("admin_manage_administrators"))

    return app


def resolve_carousel_images(config_obj: dict) -> list[dict[str, str]]:
    return list_hero_images(config_obj["HERO_UPLOADS_PATH"])


def list_hero_images(hero_root: Path) -> list[dict[str, str]]:
    root = Path(hero_root)
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    images: list[dict[str, str]] = []
    if not root.exists():
        return images

    for file_path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not file_path.is_file() or file_path.suffix.lower() not in allowed:
            continue
        images.append(
            {
                "name": file_path.name,
                "filename": file_path.name,
                "url": url_for("hero_file", filename=file_path.name),
            }
        )
    return images


def resolve_drive_documents(config_obj: dict) -> tuple[list[dict], bool]:
    folder_id = (config_obj.get("GOOGLE_DRIVE_DOCS_FOLDER_ID") or "").strip()
    api_key = config_obj.get("GOOGLE_DRIVE_API_KEY", "").strip()
    if not folder_id or not api_key:
        return [], False

    docs, had_error = fetch_drive_documents(folder_id, api_key)
    aliases = {
        row.drive_file_id: row.display_name
        for row in DriveDocumentMapping.query.order_by(DriveDocumentMapping.created_at.desc()).all()
    }
    normalized: list[dict] = []
    for doc in docs:
        file_id = (doc.get("file_id") or "").strip()
        if not file_id:
            continue
        original_name = (doc.get("name") or "").strip()
        mapped = aliases.get(file_id, "").strip()
        normalized.append(
            {
                "file_id": file_id,
                "name": original_name,
                "display_name": mapped or original_name,
                "thumbnail_link": (doc.get("thumbnail_link") or "").strip(),
                "web_content_link": (doc.get("web_content_link") or "").strip(),
                "web_view_link": (doc.get("web_view_link") or "").strip(),
                "extension": (doc.get("extension") or "").strip(),
            }
        )
    return normalized, had_error or len(normalized) == 0


def _parse_iso_date(value: str) -> date | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _active_mc_notices(today: date | None = None) -> list[MCNotice]:
    today = today or date.today()
    return (
        MCNotice.query.filter(MCNotice.start_date <= today, MCNotice.end_date >= today)
        .order_by(MCNotice.start_date.desc(), MCNotice.created_at.desc())
        .all()
    )


def _tile_defaults() -> dict[str, dict[str, str]]:
    return {
        "hero_subtitle": {
            "title": "Hero Subtitle",
            "blurb": "Stay updated with notices, events, services, and community resources.",
        },
        "notices_desc": {
            "title": "Notices from the Managing Committee",
            "blurb": "Priority notices and updates from the Managing Committee.",
        },
        "announcements": {
            "title": "Announcements",
            "blurb": "Latest society announcements and updates.",
        },
        "events": {
            "title": "Events",
            "blurb": "Upcoming cultural and community events.",
        },
        "service_requests": {
            "title": "Service Requests",
            "blurb": "Raise and track internal service tickets from Open to Resolved.",
        },
        "book_amenities": {
            "title": "Book Amenities",
            "blurb": "Reserve clubhouse, hall, and common spaces.",
        },
        "forms": {
            "title": "Forms",
            "blurb": "Access downloadable forms and circulars.",
        },
        "society_office": {
            "title": "Society Office",
            "blurb": "Contact the office for administrative support.",
        },
        "useful_links": {
            "title": "Useful Links",
            "blurb": "Essential external links for residents.",
        },
    }


def _ensure_default_amenities() -> None:
    existing = {row.name: row for row in Amenity.query.all()}
    changed = False
    for definition in DEFAULT_AMENITIES:
        name = (definition.get("name") or "").strip()
        if not name:
            continue
        row = existing.get(name)
        description = (definition.get("description") or "").strip()
        image_url = (definition.get("image_url") or "").strip()
        if not row:
            db.session.add(
                Amenity(
                    name=name,
                    description=description,
                    image_url=image_url,
                    cost=float(definition.get("cost") or 0.0),
                    is_active=True,
                )
            )
            changed = True
            continue

        if not row.description and description:
            row.description = description
            changed = True
        if image_url and row.image_url != image_url:
            row.image_url = image_url
            changed = True
        if name != "Jacuzzi" and row.cost != 0.0:
            row.cost = 0.0
            changed = True

    if changed:
        db.session.commit()


def _ordered_amenities(*, active_only: bool = False) -> list[Amenity]:
    query = Amenity.query
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(Amenity.name.asc()).all()


def _parse_booking_date(value: str) -> date | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _parse_booking_time(value: str) -> time | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        return datetime.strptime(candidate, "%H:%M").time()
    except ValueError:
        return None


def _times_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


def _booking_conflict_exists(
    amenity_id: int,
    booking_date: date,
    start_time: time,
    end_time: time,
    *,
    exclude_booking_id: int | None = None,
) -> bool:
    query = Booking.query.filter_by(amenity_id=amenity_id, booking_date=booking_date)
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)
    for row in query.all():
        if _times_overlap(start_time, end_time, row.start_time, row.end_time):
            return True
    return False


def _ensure_default_recipient_config() -> None:
    existing = RecipientConfig.query.first()
    if not existing:
        db.session.add(RecipientConfig())
        db.session.commit()


def _patch_database_schema(app: Flask) -> None:
    _patch_site_settings_schema(app)
    _patch_role_schema(app)
    _patch_admin_schema(app)
    _patch_amenity_schema(app)
    _patch_directory_schema(app)
    _patch_ticket_schema(app)
    _patch_visitor_schema(app)
    _patch_resident_directory_schema(app)


def _patch_role_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        if "role" not in table_names:
            return
        columns = {col["name"] for col in inspector.get_columns("role")}
        with db.engine.connect() as conn:
            if "permissions" not in columns:
                conn.execute(
                    text("ALTER TABLE role ADD COLUMN permissions TEXT DEFAULT ''")
                )
            conn.commit()


def _patch_admin_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        admin_table = "admin"
        if admin_table not in table_names:
            return
        columns = {col["name"] for col in inspector.get_columns(admin_table)}
        with db.engine.connect() as conn:
            if "role_id" not in columns:
                conn.execute(
                    text(f"ALTER TABLE {admin_table} ADD COLUMN role_id INTEGER")
                )
            conn.commit()


def _patch_amenity_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        if "amenity" not in table_names:
            return
        columns = {col["name"] for col in inspector.get_columns("amenity")}
        with db.engine.connect() as conn:
            if "available_from" not in columns:
                conn.execute(
                    text("ALTER TABLE amenity ADD COLUMN available_from TIME DEFAULT '06:00:00'")
                )
            if "available_to" not in columns:
                conn.execute(
                    text("ALTER TABLE amenity ADD COLUMN available_to TIME DEFAULT '22:00:00'")
                )
            conn.commit()


def _patch_directory_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        if "directory_item" not in table_names:
            return
        columns = {col["name"] for col in inspector.get_columns("directory_item")}
        with db.engine.connect() as conn:
            if "email_template" not in columns:
                conn.execute(
                    text("ALTER TABLE directory_item ADD COLUMN email_template TEXT DEFAULT ''")
                )
            conn.commit()


def _patch_site_settings_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        if "site_settings" not in inspector.get_table_names():
            return
        columns = {col["name"] for col in inspector.get_columns("site_settings")}
        with db.engine.connect() as conn:
            if "background_opacity" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN background_opacity FLOAT DEFAULT 0.8"
                    )
                )
            if "postal_address" not in columns:
                conn.execute(text("ALTER TABLE site_settings ADD COLUMN postal_address TEXT"))
            if "contact_email" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN contact_email VARCHAR(255)"
                    )
                )
            if "bank_details" not in columns:
                conn.execute(text("ALTER TABLE site_settings ADD COLUMN bank_details TEXT"))
            if "feature_ticketing" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN feature_ticketing INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "feature_amenities" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN feature_amenities INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "feature_directory" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN feature_directory INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "feature_visitors" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN feature_visitors INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "max_owner_family" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN max_owner_family INTEGER NOT NULL DEFAULT 4"
                    )
                )
            if "max_tenant_family" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN max_tenant_family INTEGER NOT NULL DEFAULT 4"
                    )
                )
            if "society_name" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE site_settings "
                        "ADD COLUMN society_name VARCHAR(120) NOT NULL DEFAULT 'Golf Meadows'"
                    )
                )
            if "logo_path" not in columns:
                conn.execute(text("ALTER TABLE site_settings ADD COLUMN logo_path VARCHAR(255)"))
            conn.commit()


def _patch_ticket_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        with db.engine.connect() as conn:
            if "resident_user" not in table_names:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS resident_user ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "full_name VARCHAR(255) NOT NULL DEFAULT '', "
                        "flat_number VARCHAR(64) NOT NULL DEFAULT '', "
                        "email VARCHAR(255) NOT NULL DEFAULT '', "
                        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                    )
                )
            if "service_ticket" not in table_names:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS service_ticket ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "category VARCHAR(128) NOT NULL, "
                        "description TEXT NOT NULL DEFAULT '', "
                        "status VARCHAR(64) NOT NULL DEFAULT 'Open', "
                        "admin_notes TEXT, "
                        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "FOREIGN KEY(user_id) REFERENCES resident_user(id))"
                    )
                )
            conn.commit()

        inspector = inspect(db.engine)
        resident_columns = (
            {col["name"] for col in inspector.get_columns("resident_user")}
            if "resident_user" in inspector.get_table_names()
            else set()
        )
        ticket_columns = (
            {col["name"] for col in inspector.get_columns("service_ticket")}
            if "service_ticket" in inspector.get_table_names()
            else set()
        )
        with db.engine.connect() as conn:
            if "created_at" not in resident_columns:
                conn.execute(
                    text(
                        "ALTER TABLE resident_user ADD COLUMN created_at DATETIME "
                        "DEFAULT CURRENT_TIMESTAMP"
                    )
                )
            if "updated_at" not in resident_columns:
                conn.execute(
                    text(
                        "ALTER TABLE resident_user ADD COLUMN updated_at DATETIME "
                        "DEFAULT CURRENT_TIMESTAMP"
                    )
                )
            if "status" not in ticket_columns:
                conn.execute(
                    text("ALTER TABLE service_ticket ADD COLUMN status VARCHAR(64) DEFAULT 'Open'")
                )
            if "admin_notes" not in ticket_columns:
                conn.execute(text("ALTER TABLE service_ticket ADD COLUMN admin_notes TEXT"))
            if "created_at" not in ticket_columns:
                conn.execute(
                    text(
                        "ALTER TABLE service_ticket ADD COLUMN created_at DATETIME "
                        "DEFAULT CURRENT_TIMESTAMP"
                    )
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_service_ticket_user_id "
                    "ON service_ticket(user_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_service_ticket_status "
                    "ON service_ticket(status)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resident_user_email "
                    "ON resident_user(email)"
                )
            )
            conn.commit()


def _patch_visitor_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        with db.engine.connect() as conn:
            if "visitor_log" not in table_names:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS visitor_log ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "visitor_name VARCHAR(255) NOT NULL, "
                        "category VARCHAR(64) NOT NULL, "
                        "company_name VARCHAR(255), "
                        "vehicle_number VARCHAR(64), "
                        "entry_code VARCHAR(6) NOT NULL, "
                        "status VARCHAR(32) NOT NULL DEFAULT 'Pre-Approved', "
                        "expected_date DATE NOT NULL, "
                        "valid_from_time TIME, "
                        "valid_to_time TIME, "
                        "entry_time DATETIME, "
                        "exit_time DATETIME, "
                        "FOREIGN KEY(user_id) REFERENCES resident_user(id))"
                    )
                )
            conn.commit()

        inspector = inspect(db.engine)
        visitor_columns = (
            {col["name"] for col in inspector.get_columns("visitor_log")}
            if "visitor_log" in inspector.get_table_names()
            else set()
        )
        with db.engine.connect() as conn:
            if "valid_from_time" not in visitor_columns:
                conn.execute(text("ALTER TABLE visitor_log ADD COLUMN valid_from_time TIME"))
            if "valid_to_time" not in visitor_columns:
                conn.execute(text("ALTER TABLE visitor_log ADD COLUMN valid_to_time TIME"))
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_visitor_log_entry_code "
                    "ON visitor_log(entry_code)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_visitor_log_user_id "
                    "ON visitor_log(user_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_visitor_log_status "
                    "ON visitor_log(status)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_visitor_log_expected_date "
                    "ON visitor_log(expected_date)"
                )
            )
            conn.commit()


def _patch_resident_directory_schema(app: Flask) -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        with db.engine.connect() as conn:
            if "resident_directory" not in table_names:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS resident_directory ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "flat_number VARCHAR(64) NOT NULL, "
                        "name VARCHAR(255) NOT NULL, "
                        "occupancy_type VARCHAR(16) NOT NULL, "
                        "role VARCHAR(32) NOT NULL, "
                        "gender VARCHAR(32) NOT NULL, "
                        "age_group VARCHAR(16) NOT NULL, "
                        "phone_number VARCHAR(32), "
                        "user_id INTEGER, "
                        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "FOREIGN KEY(user_id) REFERENCES resident_user(id))"
                    )
                )
            if "service_staff" not in table_names:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS service_staff ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "name VARCHAR(255) NOT NULL, "
                        "service_category VARCHAR(32) NOT NULL, "
                        "gender VARCHAR(32) NOT NULL, "
                        "phone_number VARCHAR(32) NOT NULL, "
                        "linked_flats TEXT NOT NULL DEFAULT '', "
                        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                    )
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resident_directory_flat_number "
                    "ON resident_directory(flat_number)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resident_directory_occupancy_type "
                    "ON resident_directory(occupancy_type)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resident_directory_role "
                    "ON resident_directory(role)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resident_directory_user_id "
                    "ON resident_directory(user_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_service_staff_name "
                    "ON service_staff(name)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_service_staff_service_category "
                    "ON service_staff(service_category)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_service_staff_phone_number "
                    "ON service_staff(phone_number)"
                )
            )
            conn.commit()


def _ensure_default_site_settings() -> None:
    existing = SiteSettings.query.order_by(SiteSettings.id.asc()).all()
    if not existing:
        db.session.add(
            SiteSettings(
                society_name="Golf Meadows",
                logo_path=None,
                global_background_image="",
                background_opacity=90,
                postal_address="Golf Meadows Cooperative Housing Society, Sector 21, Pune, Maharashtra 411045",
                contact_email="support@golfmeadows.example.com",
                bank_details="Account Name: Golf Meadows CHS\nBank: ABC Bank\nIFSC: ABCD0001234",
                feature_ticketing=True,
                feature_amenities=True,
                feature_directory=True,
                feature_visitors=True,
                max_owner_family=4,
                max_tenant_family=4,
            )
        )
        db.session.commit()
        return
    primary = existing[0]
    updated = False
    if len(existing) > 1:
        for row in existing[1:]:
            db.session.delete(row)
        updated = True
    if primary.global_background_image is None:
        primary.global_background_image = ""
        updated = True
    if primary.background_opacity is None:
        primary.background_opacity = 90
        updated = True
    if not (primary.postal_address or "").strip():
        primary.postal_address = (
            "Golf Meadows Cooperative Housing Society, Sector 21, Pune, Maharashtra 411045"
        )
        updated = True
    if not (primary.contact_email or "").strip():
        primary.contact_email = "support@golfmeadows.example.com"
        updated = True
    if not (primary.bank_details or "").strip():
        primary.bank_details = (
            "Account Name: Golf Meadows CHS\nBank: ABC Bank\nIFSC: ABCD0001234"
        )
        updated = True
    if primary.feature_ticketing is None:
        primary.feature_ticketing = True
        updated = True
    if primary.feature_amenities is None:
        primary.feature_amenities = True
        updated = True
    if primary.feature_directory is None:
        primary.feature_directory = True
        updated = True
    if primary.feature_visitors is None:
        primary.feature_visitors = True
        updated = True
    if primary.max_owner_family is None:
        primary.max_owner_family = 4
        updated = True
    if primary.max_tenant_family is None:
        primary.max_tenant_family = 4
        updated = True
    if not (primary.society_name or "").strip():
        primary.society_name = "Golf Meadows"
        updated = True
    if primary.logo_path:
        normalized_logo = (primary.logo_path or "").strip()
        if normalized_logo.startswith("/"):
            normalized_logo = normalized_logo[1:]
        if normalized_logo != primary.logo_path:
            primary.logo_path = normalized_logo
            updated = True
    if updated:
        db.session.commit()


def _ensure_default_tile_content() -> None:
    defaults = _tile_defaults()
    existing = {row.tile_key: row for row in TileContent.query.all()}
    created = False
    for key, value in defaults.items():
        if key not in existing:
            db.session.add(
                TileContent(
                    tile_key=key,
                    title=value["title"],
                    blurb=value["blurb"],
                )
            )
            created = True
    if created:
        db.session.commit()


def _ensure_super_admin(email: str) -> None:
    normalized = normalize_email(email)
    if not normalized:
        return
    super_admin_role = Role.query.filter_by(name="Super Admin").first()
    if not super_admin_role:
        super_admin_role = Role(
            name="Super Admin",
            permissions=_normalize_permissions(set(ROLE_PERMISSIONS.keys())),
        )
        db.session.add(super_admin_role)
        db.session.flush()
    admin = Admin.query.filter_by(email=normalized).first()
    if not admin:
        admin = Admin(
            email=normalized,
            is_super_admin=True,
            is_active=True,
            role_id=super_admin_role.id,
        )
        db.session.add(admin)
    else:
        admin.is_super_admin = True
        admin.is_active = True
        admin.role_id = super_admin_role.id
    db.session.commit()


def _ensure_default_roles() -> None:
    defaults = {
        "Super Admin": _normalize_permissions(set(ROLE_PERMISSIONS.keys())),
        "Operations": _normalize_permissions(
            {
                "society_office",
                "service_requests",
                "services_directory",
                "tickets",
                "notices",
                "resident_directory",
            }
        ),
        "Amenities Manager": _normalize_permissions({"amenities", "bookings"}),
        "Security": _normalize_permissions({"visitors"}),
    }
    changed = False
    for role_name, permissions in defaults.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            db.session.add(Role(name=role_name, permissions=permissions))
            changed = True
            continue
        if role_name in {"Super Admin", "Operations", "Amenities Manager", "Security"}:
            existing_permissions = {
                value.strip().lower()
                for value in (role.permissions or "").split(",")
                if value.strip().lower() in ROLE_PERMISSIONS
            }
            default_permissions = {
                value.strip().lower()
                for value in permissions.split(",")
                if value.strip().lower() in ROLE_PERMISSIONS
            }
            merged_permissions = _normalize_permissions(existing_permissions | default_permissions)
            if merged_permissions != (role.permissions or ""):
                role.permissions = merged_permissions
                changed = True
            continue
        if not role.permissions:
            role.permissions = permissions
            changed = True
    if changed:
        db.session.commit()


def _get_recipient_config() -> RecipientConfig:
    recipient = RecipientConfig.query.first()
    if not recipient:
        recipient = RecipientConfig()
        db.session.add(recipient)
        db.session.commit()
    return recipient


def _get_tile_content() -> dict[str, dict[str, str]]:
    defaults = _tile_defaults()
    data = {
        row.tile_key: {"title": row.title, "blurb": row.blurb}
        for row in TileContent.query.all()
    }
    for key, value in defaults.items():
        data.setdefault(key, value)
    return data


def _recipient_for_category(category: str, fallback_email: str) -> str:
    recipient = _get_recipient_config()
    fallback = normalize_email(fallback_email)
    if category == "service_requests":
        return recipient.service_requests_email or fallback
    if category == "book_amenities":
        return recipient.amenities_email or fallback
    if category == "forms":
        return recipient.forms_email or fallback
    if category == "society_office":
        return recipient.office_email or fallback
    return recipient.office_email or recipient.service_requests_email or fallback


def _coerce_directory_category(raw_value: str) -> str:
    candidate = (raw_value or "").strip()
    if candidate not in DIRECTORY_ITEM_CATEGORIES:
        abort(400, description="Directory item category is invalid.")
    return candidate


def _directory_image_url(image_filename: str) -> str:
    filename = (image_filename or "").strip()
    if not filename:
        return ""
    return url_for("uploads_file", filename=f"directory/{filename}")


def _directory_items_for_category(category: str) -> list[dict[str, str]]:
    normalized = _coerce_directory_category(category)
    rows = (
        DirectoryItem.query.filter_by(category=normalized)
        .order_by(DirectoryItem.title.asc(), DirectoryItem.created_at.asc())
        .all()
    )
    payload: list[dict[str, str]] = []
    for row in rows:
        phone_digits = "".join(ch for ch in (row.phone or "") if ch.isdigit())
        email_parts = _split_email_parts(row.email or "")
        payload.append(
            {
                "id": row.id,
                "category": row.category,
                "title": row.title,
                "description": row.description,
                "contact_name": row.contact_name,
                "phone": row.phone,
                "email": row.email,
                "email_template": row.email_template or "",
                "email_user": email_parts["user"],
                "email_domain": email_parts["domain"],
                "website_url": row.website_url,
                "image_url": _directory_image_url(row.image_filename)
                or DEFAULT_DIRECTORY_IMAGE_BY_KEY.get((row.category, row.title), ""),
                "whatsapp_url": f"https://wa.me/{phone_digits}" if phone_digits else "",
            }
        )
    return payload


def _split_email_parts(email_value: str) -> dict[str, str]:
    normalized = normalize_email(email_value)
    if "@" not in normalized:
        return {"user": "", "domain": ""}
    user, domain = normalized.split("@", 1)
    return {"user": user.strip(), "domain": domain.strip()}


def _normalized_background_opacity(raw_value: float | int | str | None) -> float:
    try:
        parsed = float(raw_value if raw_value is not None else 90)
    except (TypeError, ValueError):
        parsed = 90.0
    if parsed > 1:
        parsed = parsed / 100
    return min(max(parsed, 0.0), 1.0)


def _directory_item_payload_from_form(form_obj) -> dict[str, str]:
    category = _coerce_directory_category(form_obj.get("category", ""))
    title = (form_obj.get("title") or "").strip()
    description = (form_obj.get("description") or "").strip()
    contact_name = (form_obj.get("contact_name") or "").strip()
    phone = (form_obj.get("phone") or "").strip()
    email = normalize_email(form_obj.get("email", ""))
    email_template = (form_obj.get("email_template") or "").strip()
    website_url = (form_obj.get("website_url") or "").strip()
    return {
        "category": category,
        "title": title,
        "description": description,
        "contact_name": contact_name,
        "phone": phone,
        "email": email,
        "email_template": email_template,
        "website_url": website_url,
        "image_filename": "",
    }


def _delete_directory_image_file(image_filename: str, directory_root: Path) -> None:
    filename = (image_filename or "").strip()
    if not filename:
        return
    root = Path(directory_root).resolve()
    target = (root / filename).resolve()
    if root not in target.parents:
        return
    if target.exists() and target.is_file():
        target.unlink()


def _ensure_default_directory_items() -> None:
    existing = {(row.category, row.title) for row in DirectoryItem.query.all()}
    created = False
    for row in DEFAULT_DIRECTORY_ITEMS:
        key = (row["category"], row["title"])
        if key in existing:
            continue
        db.session.add(
            DirectoryItem(
                category=row["category"],
                title=row["title"],
                description=row.get("description", ""),
                contact_name=row.get("contact_name", ""),
                phone=row.get("phone", ""),
                email=normalize_email(row.get("email", "")),
                email_template=row.get("email_template", ""),
                website_url=row.get("website_url", ""),
                image_filename="",
            )
        )
        created = True
    if created:
        db.session.commit()


def _get_site_settings() -> SiteSettings:
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings(global_background_image="")
        db.session.add(settings)
        db.session.commit()
    return settings


def _resolved_global_background_url(config_obj: dict) -> str:
    settings = _get_site_settings()
    selected = (settings.global_background_image or "").strip()
    if not selected:
        return ""
    hero_images = list_hero_images(config_obj["HERO_UPLOADS_PATH"])
    matched = next((image for image in hero_images if image["filename"] == selected), None)
    if not matched:
        return ""
    return matched["url"]



app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "4273"))
    app.run(host="0.0.0.0", port=port)
