"""The only module that touches the file system. Files are never deleted by normal operations."""
import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from . import validators

KEY_RE = re.compile(r"^[0-9a-f-]{36}/[0-9]{4}/[0-9a-f-]{36}$")
CL_OVERHEAD = 1024 * 1024   # multipart envelope allowance for the early Content-Length gate


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    sha256: str
    content_type: str
    original_filename: str


def max_bytes():
    return int(settings.BEMS_UPLOAD_MAX_MB) * 1024 * 1024


def _too_large():
    return validators.bad(f"File is too large. Maximum size is {int(settings.BEMS_UPLOAD_MAX_MB)} MB.")


def storage_root() -> Path:
    raw = getattr(settings, "BEMS_STORAGE_ROOT", "") or ""
    if not raw:
        raise ImproperlyConfigured("BEMS_STORAGE_ROOT is not set (see backend/.env.example).")
    root = Path(raw)
    if not root.is_absolute():
        raise ImproperlyConfigured("BEMS_STORAGE_ROOT must be an absolute path.")
    root = root.resolve()
    project = Path(settings.BASE_DIR).parent.resolve()
    if root == project or project in root.parents:
        raise ImproperlyConfigured("BEMS_STORAGE_ROOT must be outside the project folder.")
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_path(key) -> Path:
    """Real path of a storage key; anything outside the storage root is refused."""
    if not KEY_RE.match(key or ""):
        raise FileNotFoundError("bad key")
    root = storage_root()
    path = (root / key).resolve()
    if root not in path.parents:
        raise FileNotFoundError("outside storage root")
    return path


def check_request_size(request):
    """Early gate on Content-Length, before the body is parsed."""
    raw = request.META.get("CONTENT_LENGTH") or ""
    if raw.isdigit() and int(raw) > max_bytes() + CL_OVERHEAD:
        raise _too_large()


def store_upload(uploaded, facility_public_id) -> StoredFile:
    """Validate, stream to a temp file (size + sha256 on the fly), verify content, atomic move."""
    name, ext = validators.check_filename(uploaded.name)
    limit = max_bytes()
    if uploaded.size == 0:
        raise validators.bad("The file is empty.")
    if uploaded.size is not None and uploaded.size > limit:
        raise _too_large()

    root = storage_root()
    tmp_dir = root / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / uuid.uuid4().hex
    digest, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as out:
            for chunk in uploaded.chunks():
                size += len(chunk)
                if size > limit:
                    raise _too_large()
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise validators.bad("The file is empty.")
        validators.verify_content(tmp, ext)
        key = f"{facility_public_id}/{timezone.now():%Y}/{uuid.uuid4()}"
        final = resolve_path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return StoredFile(key, size, digest.hexdigest(), validators.ALLOWED_TYPES[ext], name)


def delete_stored(key):
    """Only used to undo a store when the DB step failed."""
    try:
        resolve_path(key).unlink(missing_ok=True)
    except (FileNotFoundError, OSError):
        pass


def open_for_read(key):
    return open(resolve_path(key), "rb")