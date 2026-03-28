from __future__ import annotations

from email.message import EmailMessage
import smtplib
from typing import Iterable

from app.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_TLS, SMTP_USER
from app import models


def _normalize_recipients(recipients: Iterable[str]) -> list[str]:
    seen = set()
    normalized = []
    for entry in recipients:
        cleaned = entry.strip()
        if not cleaned or "@" not in cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _send_email(subject: str, body: str, recipients: list[str]) -> tuple[str, str]:
    cleaned = _normalize_recipients(recipients)
    if not cleaned:
        return "skipped", "No valid recipients configured."
    if not SMTP_HOST:
        return "skipped", "SMTP_HOST is not configured."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(cleaned)
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        return "failed", str(exc)
    return "sent", "Notification delivered."


def send_service_request_email(
    service_request: models.ServiceRequest,
    recipients: list[str],
    event: str,
) -> tuple[str, str, str]:
    subject = f"[GolfMeadows] Service Request {service_request.ticket_ref} - {service_request.status}"
    body = (
        f"Event: {event}\n"
        f"Ticket: {service_request.ticket_ref}\n"
        f"Resident: {service_request.resident_name}\n"
        f"Flat: {service_request.flat_number}\n"
        f"Category: {service_request.category}\n"
        f"Priority: {service_request.priority}\n"
        f"Status: {service_request.status}\n"
        f"Response SLA: {service_request.response_due_at}\n"
        f"Resolution SLA: {service_request.resolve_due_at}\n"
        f"Description: {service_request.description}\n"
    )
    status, detail = _send_email(subject, body, recipients)
    return status, detail, subject


def send_feedback_email(
    message: models.Message,
    recipients: list[str],
) -> tuple[str, str, str]:
    subject = f"[GolfMeadows] Resident feedback: {message.subject}"
    body = (
        "A new resident feedback message was submitted.\n\n"
        f"Resident: {message.resident_name}\n"
        f"Contact: {message.contact}\n"
        f"Subject: {message.subject}\n"
        f"Message:\n{message.message}\n"
    )
    status, detail = _send_email(subject, body, recipients)
    return status, detail, subject
