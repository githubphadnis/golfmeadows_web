@echo off
setlocal enabledelayedexpansion

REM ===============================
REM Config
REM ===============================
set "BASE=https://beta.golfmeadows.org"
if defined BASE_URL set "BASE=%BASE_URL%"

REM Optional: set this for admin route checks.
REM set "SESSION_COOKIE=PASTE_SESSION_COOKIE_HERE"

set "TMP_BODY=%TEMP%\ff_check_body_%RANDOM%.txt"

echo Running disabled-feature checks on %BASE%
echo.

call :CHECK "ticket-create-public" "POST" "%BASE%/service-tickets" "FORM" "full_name=QA+Resident^&flat_number=A-101^&email=qa%%40example.com^&category=Plumber^&description=Blocked+test" ""
if errorlevel 1 goto :FAIL

call :CHECK "amenities-get-api" "GET" "%BASE%/api/amenities/1/bookings" "NONE" "" ""
if errorlevel 1 goto :FAIL

call :CHECK "amenities-book-api" "POST" "%BASE%/api/amenities/book" "JSON" "{\"amenity_id\":\"1\",\"resident_name\":\"QA Resident\",\"resident_email\":\"qa@example.com\",\"booking_date\":\"2030-01-10\",\"start_time\":\"10:00\",\"end_time\":\"11:00\"}" ""
if errorlevel 1 goto :FAIL

if defined SESSION_COOKIE (
  echo SESSION_COOKIE detected. Running admin checks...
  call :CHECK "admin-ticket-update" "POST" "%BASE%/admin/manage-tickets/1/update" "FORM" "status=Open^&admin_notes=Blocked+test" "%SESSION_COOKIE%"
  if errorlevel 1 goto :FAIL

  call :CHECK "admin-amenity-pricing-update" "POST" "%BASE%/admin/amenities/pricing" "FORM" "amenity_id=1^&cost=0" "%SESSION_COOKIE%"
  if errorlevel 1 goto :FAIL

  call :CHECK "admin-directory-create" "POST" "%BASE%/admin/directory-items" "FORM" "category=services_directory^&title=Curl+Vendor^&description=Blocked+test" "%SESSION_COOKIE%"
  if errorlevel 1 goto :FAIL
) else (
  echo INFO: SESSION_COOKIE not set; skipping admin endpoint checks.
)

echo.
echo PASS: All disabled-feature checks passed.
if exist "%TMP_BODY%" del /q "%TMP_BODY%" >nul 2>nul
exit /b 0

:CHECK
set "NAME=%~1"
set "METHOD=%~2"
set "URL=%~3"
set "PAYLOAD_TYPE=%~4"
set "DATA=%~5"
set "COOKIE=%~6"

if exist "%TMP_BODY%" del /q "%TMP_BODY%" >nul 2>nul

set "CURL_CMD=curl -sS -o "%TMP_BODY%" -w %%{http_code} -X %METHOD% "%URL%""

if /I "%PAYLOAD_TYPE%"=="JSON" (
  set "CURL_CMD=!CURL_CMD! -H "Content-Type: application/json" --data "%DATA%""
) else if /I "%PAYLOAD_TYPE%"=="FORM" (
  set "CURL_CMD=!CURL_CMD! -H "Content-Type: application/x-www-form-urlencoded" --data "%DATA%""
)

if defined COOKIE (
  set "CURL_CMD=!CURL_CMD! -H "Cookie: session=%COOKIE%""
)

for /f "delims=" %%H in ('cmd /v:on /c !CURL_CMD!') do set "HTTP_CODE=%%H"

if not "!HTTP_CODE!"=="403" (
  echo FAIL [!NAME!]: expected HTTP 403, got !HTTP_CODE!
  echo ---- response body ----
  type "%TMP_BODY%"
  echo -----------------------
  exit /b 1
)

findstr /C:"\"status\":\"disabled\"" "%TMP_BODY%" >nul
if errorlevel 1 (
  echo FAIL [!NAME!]: missing status=disabled
  echo ---- response body ----
  type "%TMP_BODY%"
  echo -----------------------
  exit /b 1
)

findstr /C:"\"error\":\"This feature is currently disabled by the administrator.\"" "%TMP_BODY%" >nul
if errorlevel 1 (
  echo FAIL [!NAME!]: missing expected error message
  echo ---- response body ----
  type "%TMP_BODY%"
  echo -----------------------
  exit /b 1
)

echo PASS [!NAME!]
exit /b 0

:FAIL
echo.
echo FAILED: One or more checks failed.
if exist "%TMP_BODY%" del /q "%TMP_BODY%" >nul 2>nul
exit /b 1
