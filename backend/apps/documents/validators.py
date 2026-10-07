"""Upload validation: extension AND magic bytes. The client Content-Type is never trusted."""
import unicodedata
import zipfile

from rest_framework.exceptions import ValidationError

DOCUMENT_TYPES = [
    ("MANUAL", "Manual"), ("INVOICE", "Invoice"), ("PURCHASE_ORDER", "Purchase order"), ("GRN", "GRN"),
    ("WARRANTY_CARD", "Warranty card"), ("INSTALLATION_REPORT", "Installation report"),
    ("ACCEPTANCE_REPORT", "Acceptance report"), ("SERVICE_REPORT", "Service report"),
    ("CALIBRATION_CERTIFICATE", "Calibration certificate"), ("CONTRACT", "Contract"),
    ("LICENSE", "Licence"), ("REGISTRATION_CERTIFICATE", "Registration certificate"),
    ("PHOTO", "Photo"), ("OTHER", "Other"),
]

CT_PDF = "application/pdf"
CT_PNG = "image/png"
CT_JPG = "image/jpeg"
CT_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CT_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ALLOWED_TYPES = {"pdf": CT_PDF, "jpg": CT_JPG, "jpeg": CT_JPG, "png": CT_PNG, "docx": CT_DOCX, "xlsx": CT_XLSX}
INLINE_TYPES = frozenset({CT_PDF, CT_PNG, CT_JPG})

BLOCKED_EXT = frozenset({
    "php", "php3", "php4", "php5", "php7", "phtml", "phar", "exe", "dll", "com", "bat", "cmd", "sh", "bash",
    "ps1", "psm1", "vbs", "vbe", "js", "jse", "mjs", "wsf", "wsh", "hta", "html", "htm", "xhtml", "svg",
    "jar", "msi", "scr", "py", "pl", "rb", "asp", "aspx", "jsp", "cgi", "lnk", "reg", "apk", "bin", "iso",
})

ALLOWED_MSG = "File type not allowed. Allowed: PDF, JPG, PNG, DOCX, XLSX."
MAX_NAME_LEN = 150


def bad(message):
    return ValidationError({"file": [message]})


def sanitize_filename(raw):
    """Basename only; control/format characters and path separators removed; length capped. Display only."""
    name = unicodedata.normalize("NFC", str(raw or ""))
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf") and ch not in '<>:"|?*')
    name = name.strip(" .")
    if len(name) > MAX_NAME_LEN:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: MAX_NAME_LEN - len(ext) - 1] + "." + ext) if dot else name[:MAX_NAME_LEN]
    return name


def check_filename(raw):
    """Returns (clean_name, ext). Raises ValidationError."""
    name = sanitize_filename(raw)
    if not name or "." not in name:
        raise bad(ALLOWED_MSG)
    parts = [p.strip().lower() for p in name.split(".")]
    ext = parts[-1]
    if ext not in ALLOWED_TYPES:
        raise bad(ALLOWED_MSG)
    if any(p in BLOCKED_EXT for p in parts[1:-1]):
        raise bad("This file name is not allowed.")
    return name, ext


def _zip_has(path, prefix):
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > 20000 or sum(i.file_size for i in infos) > 500 * 1024 * 1024:
                return False
            names = [i.filename for i in infos]
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
        return False
    return "[Content_Types].xml" in names and any(n.startswith(prefix) for n in names)


def verify_content(path, ext):
    with open(path, "rb") as fh:
        head = fh.read(16)
    if ext == "pdf":
        ok = head.startswith(b"%PDF-")
    elif ext in ("jpg", "jpeg"):
        ok = head.startswith(b"\xff\xd8\xff")
    elif ext == "png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext == "docx":
        ok = _zip_has(path, "word/")
    else:
        ok = _zip_has(path, "xl/")
    if not ok:
        raise bad("The file content does not match its type.")