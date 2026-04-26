from datetime import datetime

from flask_login import UserMixin

from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Admin(UserMixin, TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_name = db.Column(db.String(255), default="", nullable=False)

    def get_id(self) -> str:
        return str(self.id)


class Notice(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Boolean, default=True, nullable=False)


class MCNotice(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False, index=True)


class Announcement(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)


class Event(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    event_date = db.Column(db.String(64), nullable=False)
    details = db.Column(db.Text, default="", nullable=False)


class Amenity(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    image_url = db.Column(db.Text, nullable=False, default="")
    cost = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    bookings = db.relationship("Booking", back_populates="amenity", cascade="all, delete-orphan")


class Booking(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resident_name = db.Column(db.String(255), nullable=False)
    resident_email = db.Column(db.String(255), nullable=False, index=True)
    booking_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    amenity_id = db.Column(db.Integer, db.ForeignKey("amenity.id"), nullable=False, index=True)

    amenity = db.relationship("Amenity", back_populates="bookings")


class RecipientConfig(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_requests_email = db.Column(db.String(255), default="", nullable=False)
    amenities_email = db.Column(db.String(255), default="", nullable=False)
    forms_email = db.Column(db.String(255), default="", nullable=False)
    office_email = db.Column(db.String(255), default="", nullable=False)


class UploadedFile(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    relative_path = db.Column(db.String(512), nullable=False)
    extension = db.Column(db.String(16), nullable=False)
    uploaded_by = db.Column(db.String(255), default="", nullable=False)


class DriveDocumentMapping(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drive_file_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)


class TileContent(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tile_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(128), nullable=False)
    blurb = db.Column(db.Text, nullable=False, default="")
