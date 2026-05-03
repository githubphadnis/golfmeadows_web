#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE_URL:-${BASE:-https://beta.golfmeadows.org}}"
SESSION_COOKIE="${SESSION_COOKIE:-}"

TMP_BODY="$(mktemp)"
cleanup() {
  rm -f "$TMP_BODY"
}
trap cleanup EXIT

check_disabled_json() {
  local name="$1"
  local method="$2"
  local url="$3"
  local content_type="${4:-}"
  local data="${5:-}"
  local cookie="${6:-}"

  local args=(-sS -o "$TMP_BODY" -w "%{http_code}" -X "$method" "$url")
  if [[ -n "$cookie" ]]; then
    args+=(-H "Cookie: session=$cookie")
  fi
  if [[ -n "$content_type" ]]; then
    args+=(-H "Content-Type: $content_type")
  fi
  if [[ -n "$data" ]]; then
    args+=(--data "$data")
  fi

  local code
  code="$(curl "${args[@]}")"
  local body
  body="$(cat "$TMP_BODY")"

  if [[ "$code" != "403" ]]; then
    echo "FAIL [$name] expected HTTP 403, got $code"
    echo "Body: $body"
    exit 1
  fi

  if ! grep -q '"status":"disabled"' "$TMP_BODY"; then
    echo "FAIL [$name] missing status=disabled"
    echo "Body: $body"
    exit 1
  fi

  if ! grep -q '"error":"This feature is currently disabled by the administrator."' "$TMP_BODY"; then
    echo "FAIL [$name] missing expected disabled error message"
    echo "Body: $body"
    exit 1
  fi

  echo "PASS [$name]"
}

echo "Running disabled-feature checks on $BASE"

check_disabled_json \
  "ticket-create-public" \
  "POST" \
  "$BASE/service-tickets" \
  "application/x-www-form-urlencoded" \
  "full_name=QA+Resident&flat_number=A-101&email=qa%40example.com&category=Plumber&description=Blocked+test"

check_disabled_json \
  "amenities-get-api" \
  "GET" \
  "$BASE/api/amenities/1/bookings"

check_disabled_json \
  "amenities-book-api" \
  "POST" \
  "$BASE/api/amenities/book" \
  "application/json" \
  '{"amenity_id":"1","resident_name":"QA Resident","resident_email":"qa@example.com","booking_date":"2030-01-10","start_time":"10:00","end_time":"11:00"}'

if [[ -n "$SESSION_COOKIE" ]]; then
  echo "SESSION_COOKIE detected. Running admin checks..."
  check_disabled_json \
    "admin-ticket-update" \
    "POST" \
    "$BASE/admin/manage-tickets/1/update" \
    "application/x-www-form-urlencoded" \
    "status=Open&admin_notes=Blocked+test" \
    "$SESSION_COOKIE"

  check_disabled_json \
    "admin-amenity-pricing-update" \
    "POST" \
    "$BASE/admin/amenities/pricing" \
    "application/x-www-form-urlencoded" \
    "amenity_id=1&cost=0" \
    "$SESSION_COOKIE"

  check_disabled_json \
    "admin-directory-create" \
    "POST" \
    "$BASE/admin/directory-items" \
    "application/x-www-form-urlencoded" \
    "category=services_directory&title=Curl+Vendor&description=Blocked+test" \
    "$SESSION_COOKIE"
else
  echo "INFO: SESSION_COOKIE not set; skipping admin endpoint checks."
fi

echo "PASS: All disabled-feature checks passed."
