import re
from datetime import date as _date
from typing import Optional, Tuple

PROJECT_LOG_NAME = "ULTRA_FAST_ZIP_BATCH_RENAMER_LOG.txt"

_TOKEN_CLEAN_RE = re.compile(r"[^A-Z0-9_]")
_MULTI_US_RE = re.compile(r"_+")

_DATE_CLEAN_RE = re.compile(r"[^A-Z0-9-]")
_MULTI_DASH_RE = re.compile(r"-+")


def sanitize_token(s: str) -> str:
    if s is None:
        return ""
    s = s.strip().upper()
    s = re.sub(r"\s+", "_", s)
    s = s.replace("-", "_")
    s = _TOKEN_CLEAN_RE.sub("", s)
    s = _MULTI_US_RE.sub("_", s)
    return s.strip("_")


def sanitize_date_token(s: str) -> str:
    if s is None:
        return ""
    s = s.strip().upper()
    s = s.replace("_", "-")
    s = _DATE_CLEAN_RE.sub("", s)
    s = _MULTI_DASH_RE.sub("-", s)
    return s.strip("-")


def sanitize_server_number(server_number: str) -> str:
    """
    STRICT: exactly 2 digits: 01..99
    """
    if server_number is None:
        raise ValueError("Server Number is required.")
    server_number = server_number.strip()
    if not re.fullmatch(r"\d{2}", server_number):
        raise ValueError("Server Number must be exactly 2 digits (01, 02, 03 ...).")

    n = int(server_number)
    if not (1 <= n <= 99):
        raise ValueError("Server Number must be between 01 and 99.")
    return f"{n:02d}"


def sanitize_date_format(fmt: str) -> str:
    fmt = (fmt or "").strip().upper()
    if fmt in ("DD-MM-YYYY", "MM-DD-YYYY"):
        return fmt
    raise ValueError("Invalid date format. Use DD-MM-YYYY or MM-DD-YYYY.")


def detect_server_kind(original_name: str) -> Tuple[Optional[str], str]:
    """
    Detect ONLY server kind from filename text:
      TCMAINSVR / TCMAIN   -> M
      TCBACKUPSVR / TCBACKUP -> B

    IMPORTANT: any digits like SVR02/SVR03 are ignored completely.
    """
    name = (original_name or "").upper()

    if "TCBACKUPSVR" in name or "TCBACKUP" in name:
        return "B", "kind-backup"
    if "TCMAINSVR" in name or "TCMAIN" in name:
        return "M", "kind-main"

    if "BACKUPSVR" in name:
        return "B", "kind-backup-fallback"
    if "MAINSVR" in name:
        return "M", "kind-main-fallback"

    return None, "kind-not-detected"


def extract_date_parts(original_name: str) -> Tuple[Optional[Tuple[int, int, int]], str]:
    """
    Detect date from: 17_04_2026 or 17-04-2026

    Returns (dd, mm, yyyy). If ambiguous, prefers DD_MM_YYYY, then fallback MM_DD_YYYY.
    """
    name = (original_name or "")

    m = re.search(r"(?<!\d)(\d{1,2})_(\d{1,2})_(\d{4})(?!\d)", name)
    if not m:
        m = re.search(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{4})(?!\d)", name)

    if not m:
        return None, "date-not-detected"

    a = int(m.group(1))
    b = int(m.group(2))
    yyyy = int(m.group(3))

    def valid(d: int, mo: int, y: int) -> bool:
        try:
            _date(y, mo, d)
            return True
        except Exception:
            return False

    # Prefer DD-MM-YYYY (a=DD, b=MM)
    if valid(a, b, yyyy):
        return (a, b, yyyy), "date-detected-dd-mm"

    # Fallback interpret as MM-DD-YYYY (a=MM, b=DD) then convert to (DD,MM,YYYY)
    if valid(b, a, yyyy):
        return (b, a, yyyy), "date-detected-mm-dd-fallback"

    return None, "date-invalid"


def format_date(dd: int, mm: int, yyyy: int, fmt: str) -> str:
    fmt = sanitize_date_format(fmt)
    if fmt == "DD-MM-YYYY":
        return f"{dd:02d}-{mm:02d}-{yyyy:04d}"
    return f"{mm:02d}-{dd:02d}-{yyyy:04d}"


def safe_inner_name(zip_entry_name: str) -> str:
    """
    Prevent path traversal: keep only basename.
    """
    if not zip_entry_name:
        return ""
    zip_entry_name = zip_entry_name.replace("\\", "/")
    return zip_entry_name.split("/")[-1]


def build_output_filename(
    exam: str,
    city: str,
    center: str,
    tech: str,
    server_code: str,
    date_str: str,
    suffix: Optional[int] = None,
) -> str:
    exam = sanitize_token(exam)
    city = sanitize_token(city)
    center = sanitize_token(center)
    tech = sanitize_token(tech)
    server_code = sanitize_token(server_code)
    date_str = sanitize_date_token(date_str)

    parts = [p for p in [exam, city, center, tech, server_code, date_str] if p]
    base = "_".join(parts) if parts else "RENAMED"

    if suffix is not None:
        base = f"{base}_{suffix}"

    if not base.lower().endswith(".zip"):
        base = f"{base}.zip"
    return base