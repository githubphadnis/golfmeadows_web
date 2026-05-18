# Development Decisions, Issues, and Solutions

## Purpose
This file is the development ledger for key engineering decisions made in the project, major issues encountered, how they were solved, and what guardrails should be reused.

---

## 1) Core development decisions

## 1.1 Data evolution strategy
**Decision:** Use startup-time SQLite schema auto-patching instead of migrations tooling.  
**Why:** Project constraints favored zero-friction deployment and auto-healing schema on boot.  
**Implementation style:**
- inspect table/columns,
- add missing columns/tables/indexes with `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`,
- keep patches idempotent.

## 1.2 Access control architecture
**Decision:** Enforce authz in layers:
- route decorators (`admin_required`, `permission_required`),
- feature-flag decorator (`require_feature_flag`),
- template-level visibility checks.

**Why:** Prevent front-end-only hiding from becoming a security gap.

## 1.3 Feature-flag operating model
**Decision:** Use global booleans in settings as kill-switches for modules.  
**Why:** Required for staged rollouts, incident mitigation, and scoped deployments.

## 1.4 Testing strategy
**Decision:** Prefer targeted runtime checks (integration scripts + artifact logs) over exhaustive suites.  
**Why:** Repository has no mature unit/integration test infrastructure; targeted checks produce faster, higher-signal validation.

## 1.5 Branching and release policy
**Decision:** Use feature branches for implementation and keep release branch as stable deployment input.  
**Why:** Supports rollback and predictable CI/deploy behavior.

## 1.6 Roadmap governance
**Decision:** GitHub Project v2 + Issues + Milestones; then tighten active execution set (Top 8) and park remainder.  
**Why:** Reduces planning noise and controls token/cycle spend.

---

## 2) Issue register (problem -> cause -> solution)

## 2.1 OAuth and role mismatches
- **Problem:** inconsistent role checks across admin flows.
- **Cause:** mixed legacy checks and incomplete role normalization.
- **Solution:** consolidated permission model and route decorators; role-permission checks centralized.

## 2.2 Feature visibility vs API enforcement gaps
- **Problem:** disabled modules could still be reached through direct API calls.
- **Cause:** UI-only gating in some paths.
- **Solution:** feature-flag enforcement decorator applied to API/backend endpoints with consistent disabled response model.

## 2.3 Portainer `.env` deployment failures
- **Problem:** stack deployments failed with missing `.env` file errors.
- **Cause:** stack config assumed file-based env source unavailable in target deployment path.
- **Solution:** align stack/deploy flow so runtime vars can be provided in Portainer UI / stack config without required missing file.

## 2.4 SVG logo upload returning 400
- **Problem:** valid SVG uploads failed.
- **Cause:** raster image processing path attempted to parse SVG via PIL.
- **Solution:** explicit SVG branch that stores validated SVG bytes directly; raster formats continue via PIL pipeline.

## 2.5 Route endpoint naming drift
- **Problem:** template `url_for(...)` failures and conditional tile-gating mismatches.
- **Cause:** endpoint names changed (`admin_core_directory`) but some checks still referenced old names.
- **Solution:** align endpoint references in templates and dashboard gate logic to actual route function names.

## 2.6 Detached session behavior in tests
- **Problem:** intermittent SQLAlchemy detached-instance errors in scripted checks.
- **Cause:** stale ORM object access outside active session lifecycle.
- **Solution:** re-query by ID in active context and avoid carrying lazy relationships across commits/session boundaries.

## 2.7 Environment/module availability drift
- **Problem:** occasional `ModuleNotFoundError` and server startup failures.
- **Cause:** inconsistent Python env/venv usage across sessions.
- **Solution:** explicit env setup and deterministic interpreter usage for script runs.

## 2.8 Cross-repo push/access failures
- **Problem:** target repo returned “Repository not found”.
- **Cause:** private repo access/token scope mismatch.
- **Solution:** PAT-authenticated remote operations; where non-fast-forward existed, created sync commit using release tree + target main parent.

## 2.9 Non-fast-forward sync to target `main`
- **Problem:** direct push of release to target main rejected.
- **Cause:** target `main` had additional commits.
- **Solution:** construct commit with parent=`target/main` and tree=`release`, push new sync commit, verify tree equality.

## 2.10 PR tool branch visibility anomalies
- **Problem:** PR creation/update tooling intermittently reported branch missing despite successful pushes.
- **Cause:** likely remote/indexing lag or tool-side branch resolution inconsistency.
- **Solution:** continue with explicit git push verification and provide compare/PR URL manually when needed.

---

## 3) Feature-area decisions and practical notes

## 3.1 Visitor Management
- Added robust validation states and time windows.
- Security UI behavior explicitly modeled for pass/fail paths.
- Recommendation: keep “Expired” lifecycle management explicit and idempotent.

## 3.2 Branding
- Dynamic society name/logo in shared layout.
- Credentials/settings live in global settings UI.
- Recommendation: keep upload handling bifurcated (vector vs raster).

## 3.3 Directory and household
- Resident/staff modeling split into separate tables with flat-based linkage.
- Household limits configured in global settings.
- Recommendation: preserve strict role/occupancy validation boundaries.

## 3.4 Payments (Razorpay stream)
- Added checkout-order creation and webhook confirmation patterns where needed.
- Recommendation: keep webhook verification strict and idempotent, and never trust browser callback alone for final booking confirmation.

---

## 4) Cost and execution control decisions

## 4.1 Token spend reduction
- Keep context in repo docs (`project_context.md`, roadmap docs, this file) to avoid repeated long chat restatements.
- Work from a tight active issue list.
- Use one feature branch per issue and one focused prompt per scope.

## 4.2 API spend reduction
- Prefer caching for low-churn reads.
- Avoid duplicate bootstrap calls.
- Gate disabled modules at backend to prevent unnecessary calls.

## 4.3 Validation efficiency
- For non-trivial backend changes: run targeted integration scripts with deterministic fixtures.
- For docs-only changes: minimal verification (format/syntax + git status) is sufficient.

---

## 5) Recommended guardrails for future work
1. Always verify repo + branch + remote before implementation.
2. Keep schema changes backward-compatible and auto-patchable.
3. Never rely on UI-only controls for security boundaries.
4. Keep PR scope single-purpose (no mixed planning+feature code in one PR).
5. Attach proof artifacts for non-trivial behavior changes.
6. Rotate/remove temporary PAT usage after privileged operations.

---

## 6) Living-document policy
Update this file whenever:
- a major design decision changes,
- a production-impacting issue is found/fixed,
- branching/deployment policy changes,
- roadmap governance is altered.
