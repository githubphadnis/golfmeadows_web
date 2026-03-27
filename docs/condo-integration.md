# CONDO Integration Blueprint (Open Source Ready)

This portal is structured as a modular service that can be merged into the larger **CONDO** housing society management application.

## Integration approach

1. **API contracts first**
   - Keep all endpoints under `/api/v1/*`.
   - Maintain typed request/response schemas in `app/schemas.py`.
   - This allows CONDO clients (web/mobile) to consume the same service contracts.

2. **Domain boundaries**
   - `service_requests`: resident issue workflows and lifecycle timeline.
   - `announcements`, `events`, `resources`: content management domains.
   - `messages`: resident communication inbox.
   - `carousel_images`: media domain, independently reusable in CONDO modules.

3. **Storage portability**
   - Use `GOLFMEADOWS_DATA_DIR` to externalize storage.
   - In CONDO deployments, mount this path to persistent cloud volumes.
   - Replace local filesystem adapter with object storage (S3/MinIO) via service abstraction when needed.

4. **Authentication and authorization**
   - Current admin routes are functionally open for rapid MVP delivery.
   - For CONDO integration, insert auth middleware and role checks:
     - resident role: create/read own service requests, submit messages
     - admin role: full CRUD on content, request operations, message triage

5. **Data model migration**
   - Current SQLite schema can be migrated to PostgreSQL in CONDO.
   - Recommended next step: add Alembic migrations and repository layer.

6. **Open-source alignment**
   - Keep framework-agnostic API naming and predictable status values.
   - Document all enum values and lifecycle transitions.
   - Add OpenAPI examples and automated tests for API regression safety.

## Recommended next CONDO-oriented enhancements

- Introduce token-based auth and tenant scoping (multi-society support).
- Add attachment support for service requests.
- Add notifications (email/WhatsApp/push) on status changes.
- Add audit log and export capabilities for admin actions.
- Add background tasks for image derivatives and cleanup jobs.
