# Project Context

## Purpose of this document
This file captures the running context of the AI-assisted development stream for the Cooperative Housing Society / GolfMeadows portal project, including architecture direction, major implementation waves, repository/branch operations, and current working assumptions.

## Product and technical baseline
- Product: cooperative housing society portal with resident-facing and admin/security-facing workflows.
- Runtime: Python + Flask + SQLAlchemy + SQLite + server-rendered Jinja templates.
- Frontend: Tailwind (CDN) + vanilla JavaScript.
- Deployment model: Docker image build/publish + Portainer deployment flow.
- Authentication/authorization: Google OAuth for admin + role-based permissions.
- Data approach: SQLite auto-patch schema evolution (no migrations framework).

## Repository context and operating mode
- Main repository in this workspace: `githubphadnis/golfmeadows_web`.
- Collaboration involved syncing work to another repo (`raksha-io/griham`) during parts of the conversation.
- Branching pattern used heavily: `cursor/<feature>-d05e`.
- PRs generally created as draft first, then merged/promoted.

## High-level development timeline (conversation stream)

### Phase A: Foundational full-platform expansion
Large multi-module feature wave was requested and implemented incrementally:
1. RBAC + OAuth hardening:
   - role model normalization,
   - admin role assignment and permission checks,
   - domain-safe OAuth callback behavior.
2. Admin dashboard restoration:
   - role/admin management cards and associated views.
3. Amenities/calendar engine upgrades:
   - booking windows,
   - booking management,
   - confirmation email support.
4. Email UX/template fixes:
   - anti-spam safe link construction,
   - Gmail compose URL handling,
   - directory email-template support.
5. UI consistency/polish:
   - reusable search,
   - banner clean-up,
   - consistent “Back” navigation placement.

### Phase B: Release and deployment pipeline hardening
- The user requested that `release` be the clean deploy source and “latest” image source.
- Work included actions/workflow checks and Portainer deployment troubleshooting.
- Portainer `.env` file dependency errors were addressed by adjusting stack/deploy assumptions so DevOps can provide runtime variables in Portainer UI.

### Phase C: Media and UI stabilization
- Google Drive image/document behavior, rendering reliability, and fallback logic were iterated.
- Hero/media presentation and section/card composition were repeatedly refined.
- Shared-drive/referrer issues were addressed.
- Several UI refactor passes were done to satisfy explicit visual structure requirements.

### Phase D: Global feature flags and API hardening
- Site-wide module toggles were added (ticketing, amenities, directory, visitors).
- Feature flags were enforced at:
  - template/UI visibility level,
  - route gating level,
  - API level via decorator (`require_feature_flag`).
- Cross-platform test scripts were generated (Windows/Linux/macOS variants).

### Phase E: Visitor Management v2
- Visitor pre-approval and guard validation were expanded with:
  - time windows,
  - code validation API,
  - QR generation/scanning flow,
  - security UI success/failure states.

### Phase F: Dynamic branding and logo pipeline
- Global branding fields were added (society name + logo path).
- Logo upload flow supported SVG and raster paths with normalization.
- Navbar/footer branding became data-driven.
- SVG upload failure path was diagnosed and corrected.

### Phase G: Core resident and staff directory
- New resident household and service staff models/routes/templates were added.
- Directory limits were made configurable in settings.
- Resident and admin directory screens were introduced.
- Feature flag and RBAC integration was enforced for directory surfaces.

### Phase H: Roadmap/planning operating system
- GitHub-native roadmap scaffolding was requested and built:
  - roadmap guide,
  - issue backlog,
  - import-friendly CSV,
  - issue creation helper script.
- Gemini-proposed prompt items were evaluated and merged selectively.
- Scope was tightened to a Top-8 execution set with parking-lot deferrals.

### Phase I: Cross-repo sync and access constraints
- The user requested syncing `release` to `raksha-io/griham:main`.
- Initial pushes failed due to private-repo access/token visibility.
- With PAT-based authenticated remote operations:
  - push conflict (non-fast-forward) was resolved via a sync commit based on release tree and target main parent,
  - target `main` tree was confirmed aligned to release content.

### Phase J: Razorpay Phase 2 request context
- User requested checkout UI + webhook hardening.
- During inspection, branch mismatch/context drift surfaced in some runs:
  - expected Phase-1 routes/models were not always present in the currently checked-out branch/repo state.
- Work proceeded by implementing missing pieces directly where absent.

## Recurring engineering patterns established in this project
- Prefer additive schema patching in startup auto-patcher for SQLite compatibility.
- Keep feature gates enforceable in both UI and API layers.
- Favor targeted integration scripts over broad test suites (repo has no formal pytest/lint baseline).
- Use artifact logs/screenshots/videos as proof of execution when testing non-trivial changes.

## Notable operational constraints observed
- Environment path drift between sessions/branches can happen; always re-verify cwd/repo/branch before coding.
- Some tool flows reported stale PR branch visibility intermittently even after successful push.
- Private repo access and PAT scope frequently impacted cross-repo Git operations.
- Some environments lacked pre-created writable `/app` paths, requiring `DATABASE_PATH`/`UPLOADS_PATH` overrides for test scripts.

## Current context snapshot (at time of writing)
- Active branch in this workspace: `cursor/flask-coop-portal-d05e`.
- Repository remote: `githubphadnis/golfmeadows_web`.
- This document and `dev_doc.md` are being added as requested to preserve project memory and execution rationale.

## How to use this context
- Read this file first to understand historical intent and feature layering.
- Use `dev_doc.md` for concrete decisions, incident patterns, and fixes.
- Before any new implementation:
  1. confirm repo + branch,
  2. confirm target milestone/scope,
  3. run focused verification scripts tied to changed modules.
