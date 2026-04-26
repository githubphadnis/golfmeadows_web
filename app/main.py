import os
from datetime import date, datetime, time
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix

from app.auth import admin_required, super_admin_required
from app.config import Config
from app.extensions import db, login_manager
from app.google_drive import fetch_drive_documents
from app.models import (
    Admin,
    Amenity,
    Announcement,
    Booking,
    DriveDocumentMapping,
    Event,
    MCNotice,
    Notice,
    RecipientConfig,
    TileContent,
    UploadedFile,
)
from app.utils import (
    allowed_file,
    build_email_links,
    ensure_storage_directories,
    file_icon_for_extension,
    normalize_email,
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

SERVICES_DIRECTORY_ENTRIES = [
    {
        "category": "Medical",
        "business_name": "GreenCare Family Clinic",
        "contact_person": "Dr. Meera Joshi",
        "phone": "+91 98765 43210",
        "whatsapp_number": "+919876543210",
        "website": "https://greencare-clinic.example.com",
        "social_label": "Instagram",
        "social_url": "https://instagram.com/greencare.clinic",
        "image_url": "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "Public Transport",
        "business_name": "MetroLink Travel Desk",
        "contact_person": "Amit Kale",
        "phone": "+91 97654 32109",
        "whatsapp_number": "+919765432109",
        "website": "https://metrolink-transit.example.com",
        "social_label": "X",
        "social_url": "https://x.com/metrolinkdesk",
        "image_url": "https://images.unsplash.com/photo-1474487548417-781cb71495f3?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "Auto",
        "business_name": "QuickRide Auto Point",
        "contact_person": "Rafiq Shaikh",
        "phone": "+91 99887 66554",
        "whatsapp_number": "+919988766554",
        "website": "",
        "social_label": "Facebook",
        "social_url": "https://facebook.com/quickrideauto",
        "image_url": "https://images.unsplash.com/photo-1542282088-fe8426682b8f?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "Vegetables Vendor",
        "business_name": "Fresh Basket Greens",
        "contact_person": "Lata Pawar",
        "phone": "+91 98220 33445",
        "whatsapp_number": "+919822033445",
        "website": "",
        "social_label": "",
        "social_url": "",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "Milk",
        "business_name": "DairyMorning Supplies",
        "contact_person": "Rohan Nair",
        "phone": "+91 98111 22334",
        "whatsapp_number": "+919811122334",
        "website": "https://dairymorning.example.com",
        "social_label": "",
        "social_url": "",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "category": "Groceries",
        "business_name": "DailyNeeds Mart",
        "contact_person": "Sanjay Kulkarni",
        "phone": "+91 99300 44556",
        "whatsapp_number": "+919930044556",
        "website": "https://dailyneedsmart.example.com",
        "social_label": "Instagram",
        "social_url": "https://instagram.com/dailyneedsmart",
        "image_url": "https://images.unsplash.com/photo-1543168256-418811576931?auto=format&fit=crop&w=1400&q=80",
    },
]

SOCIETY_OFFICE_CARDS = [
    {
        "title": "Accounting",
        "description": "Request bills, Report offcycle payment",
        "image_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "Tenant Management",
        "description": "Trigger New Tenant process, Tenant Departure",
        "image_url": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "General Resident Topics",
        "description": "General inquiries",
        "image_url": "https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&w=1400&q=80",
    },
]

SERVICE_REQUEST_CARDS = [
    {
        "title": "Entry & Parking",
        "description": "Register Vehicles, parking spaces, rental",
        "image_url": "https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "Plumber",
        "description": "Plumbing emergencies and maintenance",
        "image_url": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "General Maintenance",
        "description": "Malfunctioning infrastructure, fused lights, doors",
        "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "Housekeeping",
        "description": "Cleaning Common Areas",
        "image_url": "https://images.unsplash.com/photo-1563453392212-326f5e854473?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "Goods Movement",
        "description": "Delivery/Removal of Furniture, Ikea, Croma",
        "image_url": "https://images.unsplash.com/photo-1600518464441-9154a4dea21b?auto=format&fit=crop&w=1400&q=80",
    },
    {
        "title": "Packers & Movers",
        "description": "Moving in or Out",
        "image_url": "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=1400&q=80",
    },
]

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
        _ensure_default_amenities()
        _ensure_default_recipient_config()
        _ensure_default_tile_content()
        _ensure_super_admin(app.config["SUPER_ADMIN_EMAIL"])

    @app.context_processor
    def inject_society_name():
        return {
            "society_name": app.config["SOCIETY_NAME"],
            "tile_content": _get_tile_content(),
        }

    @app.route("/")
    def index():
        tile_content = _get_tile_content()
        category_cards = [
            {
                "title": tile_content["society_office"]["title"],
                "description": tile_content["society_office"]["blurb"],
                "href": url_for("society_office_page"),
            },
            {
                "title": tile_content["service_requests"]["title"],
                "description": tile_content["service_requests"]["blurb"],
                "href": url_for("service_requests_page"),
            },
            {
                "title": tile_content["forms"]["title"],
                "description": tile_content["forms"]["blurb"],
                "href": url_for("forms_page"),
            },
            {
                "title": "Services Directory",
                "description": "Trusted neighborhood businesses and essential contacts.",
                "href": url_for("services_directory_page"),
            },
            {
                "title": tile_content["book_amenities"]["title"],
                "description": tile_content["book_amenities"]["blurb"],
                "href": url_for("book_amenities_page"),
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
        amenity_cards = _ordered_amenities(active_only=True)
        return render_template(
            "book_amenities.html",
            amenity_cards=amenity_cards,
            tile_content=_get_tile_content(),
        )

    @app.route("/book-amenities/<int:amenity_id>")
    def book_amenity_detail(amenity_id: int):
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

        return (
            jsonify(
                {
                    "id": booking.id,
                    "amenity": amenity.name,
                    "booking_date": booking.booking_date.isoformat(),
                    "start_time": booking.start_time.strftime("%H:%M"),
                    "end_time": booking.end_time.strftime("%H:%M"),
                    "cost": float(amenity.cost or 0.0),
                }
            ),
            201,
        )

    @app.route("/admin/amenities/pricing", methods=["POST"])
    @super_admin_required
    def admin_update_amenity_pricing():
        jacuzzi = Amenity.query.filter_by(name="Jacuzzi").first()
        if not jacuzzi:
            abort(404)

        cost_raw = (request.form.get("jacuzzi_cost") or "").strip()
        if not cost_raw:
            fallback_key = f"cost_{jacuzzi.id}"
            cost_raw = (request.form.get(fallback_key) or "").strip()
        if not cost_raw:
            cost_raw = (request.form.get("cost") or "").strip()

        amenity_id_raw = (request.form.get("amenity_id") or "").strip()
        amenity = jacuzzi
        if amenity_id_raw:
            if not amenity_id_raw.isdigit():
                abort(400, description="Amenity ID must be numeric.")
            amenity = db.session.get(Amenity, int(amenity_id_raw))
        if not amenity:
            abort(404)
        if amenity.name != "Jacuzzi":
            abort(400, description="Only Jacuzzi pricing can be modified from admin.")
        try:
            cost_value = float(cost_raw or 0.0)
        except ValueError as exc:
            raise abort(400, description="Cost must be a number.") from exc
        if cost_value < 0:
            abort(400, description="Cost cannot be negative.")
        amenity.cost = cost_value
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/society-office")
    def society_office_page():
        return render_template(
            "society_office.html",
            society_office_cards=SOCIETY_OFFICE_CARDS,
            tile_content=_get_tile_content(),
        )

    @app.route("/service-requests")
    def service_requests_page():
        return render_template(
            "service_requests.html",
            service_request_cards=SERVICE_REQUEST_CARDS,
            tile_content=_get_tile_content(),
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
        services_directory_entries = []
        for entry in SERVICES_DIRECTORY_ENTRIES:
            whatsapp_raw = (entry.get("whatsapp_number") or "").strip()
            whatsapp_digits = "".join(ch for ch in whatsapp_raw if ch.isdigit())
            services_directory_entries.append(
                {
                    **entry,
                    "whatsapp_url": f"https://wa.me/{whatsapp_digits}" if whatsapp_digits else "",
                }
            )
        return render_template(
            "services_directory.html",
            services_directory_entries=services_directory_entries,
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
        return jsonify(
            {
                "status": "ok",
                "database_path": str(app.config["DB_PATH"]),
                "uploads_path": str(app.config["UPLOADS_PATH"]),
                "hero_uploads_path": str(app.config["HERO_UPLOADS_PATH"]),
                "society_name": app.config["SOCIETY_NAME"],
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

        super_admin_email = normalize_email(app.config["SUPER_ADMIN_EMAIL"])
        is_super_admin = email == super_admin_email
        admin = Admin.query.filter_by(email=email, is_active=True).first()

        if is_super_admin and not admin:
            admin = Admin(
                email=email,
                is_super_admin=True,
                is_active=True,
                display_name=user_info.get("name", ""),
            )
            db.session.add(admin)
            db.session.commit()

        if not admin:
            abort(403, description="This Google account is not authorized as admin.")

        admin.display_name = user_info.get("name", admin.display_name)
        admin.is_super_admin = admin.is_super_admin or is_super_admin
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
        recipient = _get_recipient_config()
        mc_notices = MCNotice.query.order_by(MCNotice.start_date.desc(), MCNotice.created_at.desc()).all()
        amenities = _ordered_amenities(active_only=False)
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).all()
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).all()
        drive_documents, docs_error = resolve_drive_documents(app.config)
        aliases = DriveDocumentMapping.query.order_by(DriveDocumentMapping.created_at.desc()).all()
        drive_aliases = {row.drive_file_id: row.display_name for row in aliases}
        alias_index = {row.drive_file_id: row.id for row in aliases}
        hero_images = list_hero_images(app.config["HERO_UPLOADS_PATH"])
        return render_template(
            "admin.html",
            recipient=recipient,
            mc_notices=mc_notices,
            notices=notices,
            admins=admins,
            uploads=uploads,
            drive_documents=drive_documents,
            drive_docs_error=docs_error,
            drive_aliases=drive_aliases,
            alias_index=alias_index,
            tile_content=_get_tile_content(),
            hero_images=hero_images,
            amenities=amenities,
            icon_resolver=file_icon_for_extension,
        )

    @app.route("/admin/mc-notices", methods=["POST"])
    @admin_required
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
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/mc-notices/<int:notice_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_mc_notice(notice_id: int):
        notice = db.session.get(MCNotice, notice_id)
        if not notice:
            abort(404)
        db.session.delete(notice)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/notices", methods=["POST"])
    @admin_required
    def admin_create_notice():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        priority = request.form.get("priority") == "on"
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Notice(title=title, content=content, priority=priority))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/notices/<int:notice_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_notice(notice_id: int):
        notice = db.session.get(Notice, notice_id)
        if not notice:
            abort(404)
        db.session.delete(notice)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/announcements", methods=["POST"])
    @admin_required
    def admin_create_announcement():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Announcement(title=title, content=content))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/events", methods=["POST"])
    @admin_required
    def admin_create_event():
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date", "").strip()
        details = request.form.get("details", "").strip()
        if not title or not event_date:
            abort(400, description="Title and event date are required.")
        db.session.add(Event(title=title, event_date=event_date, details=details))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/recipients", methods=["POST"])
    @admin_required
    def admin_update_recipients():
        recipient = _get_recipient_config()
        recipient.service_requests_email = normalize_email(
            request.form.get("service_requests_email", "")
        )
        recipient.amenities_email = normalize_email(request.form.get("amenities_email", ""))
        recipient.forms_email = normalize_email(request.form.get("forms_email", ""))
        recipient.office_email = normalize_email(request.form.get("office_email", ""))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/tile-content", methods=["POST"])
    @admin_required
    def admin_update_tile_content():
        for key in _tile_defaults().keys():
            title = (request.form.get(f"{key}_title") or "").strip()
            blurb = (request.form.get(f"{key}_blurb") or "").strip()
            row = TileContent.query.filter_by(tile_key=key).first()
            if not row:
                row = TileContent(tile_key=key, title=title or key.replace("_", " ").title(), blurb=blurb)
                db.session.add(row)
            else:
                if title:
                    row.title = title
                row.blurb = blurb
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/upload", methods=["POST"])
    @admin_required
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
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/hero-images", methods=["POST"])
    @admin_required
    def admin_upload_hero_image():
        file = request.files.get("hero_file")
        if not file or not file.filename:
            abort(400, description="Hero image file is required.")
        if not allowed_file(file.filename, HERO_ALLOWED_EXTENSIONS):
            abort(400, description="Hero images must be JPG, PNG, or WEBP.")
        save_hero_image(file, app.config["HERO_UPLOADS_PATH"])
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/hero-images/<path:filename>/delete", methods=["POST"])
    @admin_required
    def admin_delete_hero_image(filename: str):
        hero_root = Path(app.config["HERO_UPLOADS_PATH"]).resolve()
        target = (hero_root / filename).resolve()
        if hero_root not in target.parents and target != hero_root:
            abort(400, description="Invalid hero image path.")
        if target.exists() and target.is_file():
            target.unlink()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/drive-documents/alias", methods=["POST"])
    @admin_required
    def admin_save_drive_alias():
        drive_file_id = (request.form.get("drive_file_id") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        if not drive_file_id:
            abort(400, description="Drive file ID is required.")
        alias = DriveDocumentMapping.query.filter_by(drive_file_id=drive_file_id).first()
        if not alias:
            alias = DriveDocumentMapping(drive_file_id=drive_file_id, display_name=display_name)
            db.session.add(alias)
        else:
            alias.display_name = display_name
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/drive-documents/alias/<int:alias_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_drive_alias(alias_id: int):
        alias = db.session.get(DriveDocumentMapping, alias_id)
        if not alias:
            abort(404)
        db.session.delete(alias)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/uploads/<path:filename>")
    def uploads_file(filename: str):
        upload_root = Path(app.config["UPLOADS_PATH"])
        return send_from_directory(upload_root, filename)

    @app.route("/admin/admins", methods=["POST"])
    @super_admin_required
    def admin_add_admin():
        email = normalize_email(request.form.get("email", ""))
        if not email:
            abort(400, description="Valid email required.")
        existing = Admin.query.filter_by(email=email).first()
        if not existing:
            db.session.add(Admin(email=email, is_super_admin=False, is_active=True))
            db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/admins/<int:admin_id>/toggle", methods=["POST"])
    @super_admin_required
    def admin_toggle_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if normalize_email(admin.email) == normalize_email(app.config["SUPER_ADMIN_EMAIL"]):
            return redirect(url_for("admin_dashboard"))
        admin.is_active = not admin.is_active
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/admins/<int:admin_id>/remove", methods=["POST"])
    @super_admin_required
    def admin_remove_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if admin.is_super_admin:
            return redirect(url_for("admin_dashboard"))
        db.session.delete(admin)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

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
            "blurb": "Need help from the society office? Email directly.",
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
    admin = Admin.query.filter_by(email=normalized).first()
    if not admin:
        admin = Admin(email=normalized, is_super_admin=True, is_active=True)
        db.session.add(admin)
    else:
        admin.is_super_admin = True
        admin.is_active = True
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


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "4273"))
    app.run(host="0.0.0.0", port=port)
