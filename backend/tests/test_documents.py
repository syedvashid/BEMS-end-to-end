"""Phase 3 documents tests. Run: python -m pytest -q tests/test_documents.py"""
import io
import zipfile
from dataclasses import replace

import pytest
from django.conf import settings
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from rest_framework.test import APIClient

from apps.documents import registry, tokens
from apps.documents.models import DocumentVersion
from apps.foundation.models import Facility, User, UserFacilityRole
from apps.masters.models import Vendor

try:  # mirror whatever DB marker your Phase 2 tests use
    import pytest_django  # noqa: F401
    pytestmark = pytest.mark.django_db
except ImportError:
    pass

BASE = "/api/v1/documents/"
PDF = b"%PDF-1.4\n%bems test\n"
PDF2 = b"%PDF-1.4\n%second version\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _uname(u):
    return getattr(u, "username", u)


def _user(u):
    return u if hasattr(u, "id") else User.objects.get(username=u)


def _fac(f):
    return f if isinstance(f, Facility) else Facility.objects.get(public_id=f)


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    root = tmp_path / "files"
    monkeypatch.setattr(settings, "BEMS_STORAGE_ROOT", str(root))
    monkeypatch.setattr(settings, "BEMS_UPLOAD_MAX_MB", 1)
    return root


@pytest.fixture
def vendor(world):
    return Vendor.objects.create(facility=_fac(world.fa), name="Acme Medical")


@pytest.fixture
def sysa(api, world):
    return api(_uname(world.sys_a), world.fa)


def up(client, vendor, name="a.pdf", content=PDF, entity_type="vendor", **extra):
    data = {"entity_type": entity_type, "entity": str(vendor.public_id),
            "document_type": "MANUAL", "title": "Manual"}
    data.update(extra)
    data["file"] = SimpleUploadedFile(name, content, content_type="application/octet-stream")
    return client.post(BASE, data, format="multipart")


def add_version(client, pid, content=PDF2, name="b.pdf"):
    return client.post(f"{BASE}{pid}/versions/", {"file": SimpleUploadedFile(name, content)}, format="multipart")


def link(client, pid, n=1, inline=False):
    r = client.post(f"{BASE}{pid}/versions/{n}/download-link/" + ("?inline=true" if inline else ""), format="json")
    assert r.status_code == 200, r.content
    return r.json()["url"]


def audit_count(action, entity=None):
    sql, params = "select count(*) from audit_log where action = %s", [action]
    if entity:
        sql += " and entity_public_id::text = %s"
        params.append(str(entity))
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


# ---------------------------------------------------------------- upload rejects
REJECTS = [
    ("empty", "empty.pdf", b""),
    ("unknown_ext", "note.txt", b"hello"),
    ("text_named_pdf", "fake.pdf", b"just text, not a pdf"),
    ("png_named_pdf", "img.pdf", PNG),
    ("exec_double_ext", "evil.php.pdf", PDF),
    ("script_double_ext", "run.exe.png", PNG),
    ("no_extension", "noext", PDF),
    ("fake_docx", "fake.docx", b"PK-not-a-zip"),
    ("xlsx_inside_docx", "wrong.docx", _zip({"[Content_Types].xml": b"x", "xl/workbook.xml": b"x"})),
    ("dots_only", "..", PDF),
]


@pytest.mark.parametrize("name,content", [(n, c) for _, n, c in REJECTS], ids=[i for i, _, _ in REJECTS])
def test_upload_rejected(sysa, vendor, storage, name, content):
    r = up(sysa, vendor, name=name, content=content)
    assert r.status_code == 400, r.content
    assert r.json()["error"]["code"] == "validation_error"
    assert not [p for p in storage.rglob("*") if p.is_file()]   # nothing left behind (temp files included)


def test_oversize_rejected_streaming_and_early_gate(sysa, vendor, storage):
    assert up(sysa, vendor, content=PDF + b"0" * (1024 * 1024)).status_code == 400            # real size > 1 MB
    assert up(sysa, vendor, content=PDF + b"0" * (3 * 1024 * 1024)).status_code == 400        # Content-Length gate
    assert not [p for p in storage.rglob("*") if p.is_file()]


def test_valid_docx_and_path_traversal_name(sysa, vendor, storage):
    docx = _zip({"[Content_Types].xml": b"x", "word/document.xml": b"x"})
    assert up(sysa, vendor, name="ok.docx", content=docx).status_code == 201
    r = up(sysa, vendor, name="../../..\\evil.pdf")
    assert r.status_code == 201
    assert r.json()["versions"][0]["original_filename"] == "evil.pdf"
    root = storage.resolve()
    assert all(root in p.resolve().parents for p in storage.rglob("*") if p.is_file())


def test_storage_key_never_in_responses(sysa, vendor, storage):
    created = up(sysa, vendor)
    pid = created.json()["public_id"]
    bodies = [created.text, sysa.get(f"{BASE}{pid}/").text, sysa.get(BASE).text]
    names = [p.name for p in storage.rglob("*") if p.is_file()]
    assert names
    for body in bodies:
        assert "storage_key" not in body and str(storage) not in body
        assert not any(n in body for n in names)


# ---------------------------------------------------------------- isolation
def test_cross_facility_is_404(api, world, vendor, sysa):
    pid = up(sysa, vendor).json()["public_id"]
    other = api(_uname(world.sys_b), world.fb)
    assert other.get(f"{BASE}{pid}/").status_code == 404
    assert other.delete(f"{BASE}{pid}/").status_code == 404
    assert other.post(f"{BASE}{pid}/versions/1/download-link/", format="json").status_code == 404
    assert up(other, vendor).status_code == 404            # attaching to another facility's record


def test_unknown_entity_type_400_and_missing_target_404(sysa, vendor):
    assert up(sysa, vendor, entity_type="nope").status_code == 400
    import uuid
    ghost = type("G", (), {"public_id": uuid.uuid4()})()
    assert up(sysa, ghost).status_code == 404


# ---------------------------------------------------------------- permission layers
def test_add_needs_entity_attach_permission(api, world, vendor, monkeypatch):
    att = registry.get_attachable("vendor")
    monkeypatch.setitem(registry._REGISTRY, "t_locked",
                        replace(att, entity_type="t_locked", attach_permission="role.manage"))
    eng = api(_uname(world.mk("t_eng", world.fa, "BIOMED_ENGINEER")), world.fa)   # has document.add
    before = audit_count("ACCESS_DENIED")
    assert up(eng, vendor, entity_type="t_locked").status_code == 403
    assert audit_count("ACCESS_DENIED") == before + 1


def test_document_perm_missing_is_denied(api, world, vendor):
    dept = api(_uname(world.mk("t_dept", world.fa, "DEPARTMENT_USER")), world.fa)   # document.view only
    assert up(dept, vendor).status_code == 403


def test_list_excludes_entity_types_user_cannot_view(api, world, vendor, sysa, monkeypatch):
    att = registry.get_attachable("vendor")
    monkeypatch.setitem(registry._REGISTRY, "t_open",
                        replace(att, entity_type="t_open", view_permission="document.view", attach_permission="document.add"))
    monkeypatch.setitem(registry._REGISTRY, "t_hidden",
                        replace(att, entity_type="t_hidden", view_permission="audit.view", attach_permission="document.add"))
    open_id = up(sysa, vendor, entity_type="t_open").json()["public_id"]
    hidden_id = up(sysa, vendor, entity_type="t_hidden").json()["public_id"]
    dept = api(_uname(world.mk("t_dept2", world.fa, "DEPARTMENT_USER")), world.fa)
    ids = [d["public_id"] for d in dept.get(BASE).json()["results"]]
    assert open_id in ids and hidden_id not in ids
    assert dept.get(f"{BASE}{hidden_id}/").status_code == 403


# ---------------------------------------------------------------- versioning
def test_versions_increment_and_old_ones_stay_downloadable(sysa, vendor):
    pid = up(sysa, vendor).json()["public_id"]
    r = add_version(sysa, pid)
    assert r.status_code == 201 and r.json()["current_version_no"] == 2
    detail = sysa.get(f"{BASE}{pid}/").json()
    assert [v["version_no"] for v in detail["versions"]] == [2, 1]
    for n, body in ((1, PDF), (2, PDF2)):
        resp = APIClient().get(link(sysa, pid, n))
        assert resp.status_code == 200 and b"".join(resp.streaming_content) == body
    assert audit_count("DOCUMENT_VERSION_ADDED", pid) == 1


def test_metadata_update_needs_row_version(sysa, vendor):
    d = up(sysa, vendor).json()
    r = sysa.patch(f"{BASE}{d['public_id']}/", {"title": "New", "row_version": d["row_version"]}, format="json")
    assert r.status_code == 200 and r.json()["title"] == "New"
    r = sysa.patch(f"{BASE}{d['public_id']}/", {"title": "Again", "row_version": d["row_version"]}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_version"


# ---------------------------------------------------------------- download token
def test_download_ok_headers_and_audit(sysa, vendor):
    pid = up(sysa, vendor).json()["public_id"]
    resp = APIClient().get(link(sysa, pid))                       # no dev headers at all
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == PDF
    assert resp["Content-Disposition"].startswith("attachment")
    assert resp["X-Content-Type-Options"] == "nosniff" and "no-store" in resp["Cache-Control"]
    assert audit_count("DOCUMENT_DOWNLOAD", pid) == 1
    inline = APIClient().get(link(sysa, pid, inline=True))
    assert inline["Content-Disposition"].startswith("inline")
    assert "sandbox" in inline["Content-Security-Policy"]


def test_inline_refused_for_docx(sysa, vendor):
    docx = _zip({"[Content_Types].xml": b"x", "word/document.xml": b"x"})
    pid = up(sysa, vendor, name="a.docx", content=docx).json()["public_id"]
    assert sysa.post(f"{BASE}{pid}/versions/1/download-link/?inline=true", format="json").status_code == 400


def test_token_expired_and_tampered(sysa, vendor, monkeypatch):
    pid = up(sysa, vendor).json()["public_id"]
    url = link(sysa, pid)
    tampered = url[:-2] + ("A" if url[-2] != "A" else "B") + "/"
    assert APIClient().get(tampered).status_code == 404
    monkeypatch.setattr(settings, "BEMS_DOWNLOAD_LINK_TTL_SECONDS", -1)
    assert APIClient().get(url).status_code == 404


def test_token_wrong_facility(world, sysa, vendor):
    pid = up(sysa, vendor).json()["public_id"]
    ver = DocumentVersion.objects.get(document__public_id=pid, version_no=1)
    sys_a = _user(world.sys_a)
    token = signing.dumps({"v": str(ver.public_id), "f": str(_fac(world.fb).public_id),
                           "u": str(sys_a.public_id), "d": "attachment"}, salt=tokens.SALT)
    assert APIClient().get(f"{BASE}download/{token}/").status_code == 404


def test_token_dies_when_user_permission_removed(api, world, vendor, sysa, monkeypatch):
    att = registry.get_attachable("vendor")
    monkeypatch.setitem(registry._REGISTRY, "t_open",
                        replace(att, entity_type="t_open", view_permission="document.view", attach_permission="document.add"))
    pid = up(sysa, vendor, entity_type="t_open").json()["public_id"]
    dept_user = _user(world.mk("t_dl", world.fa, "DEPARTMENT_USER"))
    url = link(api(dept_user.username, world.fa), pid)
    assert APIClient().get(url).status_code == 200
    UserFacilityRole.objects.filter(user_id=dept_user.id).update(is_active=False)
    assert APIClient().get(url).status_code == 404


# ---------------------------------------------------------------- soft delete / immutability
def test_soft_delete_hides_document_but_keeps_file(sysa, vendor, storage):
    d = up(sysa, vendor).json()
    pid = d["public_id"]
    url = link(sysa, pid)
    assert sysa.delete(f"{BASE}{pid}/").status_code == 204
    assert sysa.get(f"{BASE}{pid}/").status_code == 404
    assert pid not in [x["public_id"] for x in sysa.get(BASE).json()["results"]]
    assert APIClient().get(url).status_code == 404            # token dies with the document
    assert [p for p in storage.rglob("*") if p.is_file()]      # file still on disk
    assert audit_count("SOFT_DELETE", pid) == 1


@pytest.mark.parametrize("sql", ["update document_versions set original_filename = 'x'", "delete from document_versions"])
def test_document_versions_immutable_for_app_role(sysa, vendor, sql):
    up(sysa, vendor)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(sql)