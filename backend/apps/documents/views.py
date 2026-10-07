import logging
import uuid

from django.core import signing
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.foundation.context import resolve_context
from apps.foundation.models import User
from apps.foundation.permissions import deny
from apps.foundation.viewsets import FacilityScopedViewSet

from . import tokens
from .filters import DocumentFilter
from .models import Document, DocumentVersion
from .registry import all_attachables, get_attachable, resolve_target
from .serializers import (
    DocumentCreateSerializer, DocumentDetailSerializer, DocumentSerializer, VersionUploadSerializer,
)
from .storage import check_request_size, delete_stored, open_for_read, store_upload
from .validators import INLINE_TYPES

log = logging.getLogger(__name__)
INLINE_CSP = "default-src 'none'; sandbox"
CREATE_FIELDS = {"entity_type", "entity", "document_type", "title", "description", "expiry_date", "file"}


def _reject_unknown(data, allowed):
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        raise ValidationError({name: ["Unknown field."] for name in unknown})


class DocumentViewSet(FacilityScopedViewSet):
    queryset = Document.objects.prefetch_related(
        Prefetch("versions", queryset=DocumentVersion.objects.order_by("-version_no")))
    serializer_class = DocumentSerializer
    audit_entity_type = "Document"
    required_permissions = {
        "list": "document.view", "retrieve": "document.view", "download_link": "document.view",
        "create": "document.add", "add_version": "document.change",
        "update": "document.change", "partial_update": "document.change", "destroy": "document.delete",
    }
    include_inactive_permission = "document.delete"
    filterset_class = DocumentFilter
    ordering_fields = ["title", "document_type", "expiry_date", "created_at"]
    ordering = ["-created_at"]

    # multipart only on POST /documents/ (the versions action sets its own parser_classes)
    def initialize_request(self, request, *args, **kwargs):
        req = super().initialize_request(request, *args, **kwargs)
        if self.action == "create":
            req.parsers = [MultiPartParser()]
        return req

    def get_serializer_class(self):
        if self.action in ("retrieve", "create", "add_version"):
            return DocumentDetailSerializer
        return DocumentSerializer

    def scope_queryset(self, queryset):
        qs = super().scope_queryset(queryset)
        if self.action == "list":   # layer 2 for lists: only entity types the user may view
            allowed = [t for t, a in all_attachables().items() if self.ctx.has(a.view_permission)]
            qs = qs.filter(entity_type__in=allowed)
        return qs

    def require_entity_permission(self, doc, kind):
        """Layer 2. Runs BEFORE any atomic block (deny() audits in autocommit)."""
        att = get_attachable(doc.entity_type)
        if att is None:
            raise NotFound()
        code = att.view_permission if kind == "view" else att.attach_permission
        if not self.ctx.has(code):
            deny(self.request, self, self.action, (code,), reason=f"entity_{kind}_permission")
        return att

    def fresh(self, doc):
        return DocumentDetailSerializer(Document.objects.get(pk=doc.pk), context=self.get_serializer_context()).data

    # ---- reads ----
    def retrieve(self, request, *args, **kwargs):
        doc = self.get_object()
        self.require_entity_permission(doc, "view")
        return Response(self.get_serializer(doc).data)

    # ---- upload: POST /documents/ ----
    def create(self, request, *args, **kwargs):
        check_request_size(request)
        _reject_unknown(request.data, CREATE_FIELDS)
        ser = DocumentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        att = get_attachable(v["entity_type"])
        if att is None:
            raise ValidationError({"entity_type": ["Unknown entity type."]})
        if not self.ctx.has(att.attach_permission):
            deny(request, self, "create", (att.attach_permission,), reason="entity_attach_permission")
        resolve_target(att, v["entity"], self.ctx.facility)            # 404 if missing/inactive/other facility
        stored = store_upload(v["file"], self.ctx.facility.public_id)  # validates, streams, moves
        uid = request.user.id
        try:
            with transaction.atomic():
                doc = Document.objects.create(
                    facility=self.ctx.facility, document_type=v["document_type"], title=v["title"],
                    description=v.get("description"), entity_type=v["entity_type"],
                    entity_public_id=v["entity"], expiry_date=v.get("expiry_date"),
                    current_version_no=1, created_by=uid, updated_by=uid,
                )
                DocumentVersion.objects.create(
                    facility=self.ctx.facility, document=doc, version_no=1,
                    original_filename=stored.original_filename, storage_key=stored.key,
                    content_type=stored.content_type, size_bytes=stored.size, sha256=stored.sha256,
                    created_by=uid,
                )
                self._audit("CREATE", doc, None, audit.snapshot(doc))
        except BaseException:
            delete_stored(stored.key)
            raise
        return Response(self.fresh(doc), status=201)

    # ---- add version: POST /documents/{id}/versions/ ----
    @action(detail=True, methods=["post"], url_path="versions", parser_classes=[MultiPartParser])
    def add_version(self, request, public_id=None):
        check_request_size(request)
        doc = self.get_object()
        att = self.require_entity_permission(doc, "attach")
        resolve_target(att, doc.entity_public_id, self.ctx.facility)
        _reject_unknown(request.data, {"file"})
        ser = VersionUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        stored = store_upload(ser.validated_data["file"], self.ctx.facility.public_id)
        uid = request.user.id
        try:
            with transaction.atomic():
                locked = self.get_object_for_update()          # row lock serialises concurrent uploads
                number = locked.current_version_no + 1
                DocumentVersion.objects.create(
                    facility=self.ctx.facility, document=locked, version_no=number,
                    original_filename=stored.original_filename, storage_key=stored.key,
                    content_type=stored.content_type, size_bytes=stored.size, sha256=stored.sha256,
                    created_by=uid,
                )
                locked.current_version_no = number
                locked.updated_by = uid
                locked.save(update_fields=["current_version_no", "updated_by"])
                audit.record(
                    request=request, action="DOCUMENT_VERSION_ADDED", facility_id=self.ctx.facility.id,
                    entity_type="Document", entity_public_id=locked.public_id,
                    new={"version_no": number, "filename": stored.original_filename,
                         "size_bytes": stored.size, "sha256": stored.sha256},
                )
        except BaseException:
            delete_stored(stored.key)
            raise
        return Response(self.fresh(doc), status=201)

    # ---- metadata edit / soft delete: layer 2 first, then the standard audited machinery ----
    def update(self, request, *args, **kwargs):
        self.require_entity_permission(self.get_object(), "attach")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.require_entity_permission(self.get_object(), "attach")
        return super().destroy(request, *args, **kwargs)

    # ---- POST /documents/{id}/versions/{n}/download-link/ ----
    @action(detail=True, methods=["post"], url_path=r"versions/(?P<version_no>[0-9]+)/download-link")
    def download_link(self, request, public_id=None, version_no=None):
        from django.urls import reverse
        doc = self.get_object()
        self.require_entity_permission(doc, "view")
        version = DocumentVersion.objects.filter(document=doc, version_no=int(version_no)).first()
        if version is None:
            raise NotFound()
        inline = str(request.query_params.get("inline", "")).lower() in ("1", "true")
        if inline and version.content_type not in INLINE_TYPES:
            raise ValidationError({"inline": ["Preview is not available for this file type."]})
        token, expires_at = tokens.issue(version.public_id, self.ctx.facility.public_id,
                                         request.user.public_id, inline)
        return Response({"url": reverse("document-download", kwargs={"token": token}),
                         "expires_at": expires_at.isoformat()})


class _CtxShim:
    """Lets the existing resolve_context() build a context without request headers."""
    def __init__(self, user, facility_public_id):
        self.user = user
        self.headers = {"X-Facility-Id": str(facility_public_id)}


class DocumentDownloadView(APIView):
    """The token is the credential. Every failure is the same generic 404."""
    authentication_classes = []
    permission_classes = []

    def perform_content_negotiation(self, request, force=False):
        return super().perform_content_negotiation(request, force=True)   # browsers send odd Accept headers

    def get(self, request, token):
        try:
            data = tokens.read(token)
            version_id, fac_id, user_id = (uuid.UUID(data[k]) for k in ("v", "f", "u"))
            disposition = data["d"]
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise NotFound()
        if disposition not in ("attachment", "inline"):
            raise NotFound()

        version = (DocumentVersion.objects.select_related("document")
                   .filter(public_id=version_id, facility__public_id=fac_id, document__is_active=True).first())
        user = User.objects.filter(public_id=user_id, is_active=True).first()
        if version is None or user is None:
            raise NotFound()
        ctx = resolve_context(_CtxShim(user, fac_id), True)     # NotFound if the user left the facility
        doc = version.document
        att = get_attachable(doc.entity_type)
        if (att is None or doc.facility_id != ctx.facility.id or version.facility_id != ctx.facility.id
                or not ctx.has("document.view") or not ctx.has(att.view_permission)):
            raise NotFound()

        inline = disposition == "inline" and version.content_type in INLINE_TYPES
        try:
            fh = open_for_read(version.storage_key)
        except (FileNotFoundError, OSError):
            log.error("document file missing for version %s", version.public_id)
            raise NotFound()
        try:
            with transaction.atomic():
                audit.record(
                    request=request, actor=user, action="DOCUMENT_DOWNLOAD", facility_id=ctx.facility.id,
                    entity_type="Document", entity_public_id=doc.public_id,
                    new={"target_entity_type": doc.entity_type, "target_entity": str(doc.entity_public_id),
                         "document": str(doc.public_id), "version_no": version.version_no,
                         "disposition": "inline" if inline else "attachment"},
                )
        except BaseException:
            fh.close()
            raise
        resp = FileResponse(fh, as_attachment=not inline, filename=version.original_filename,
                            content_type=version.content_type)
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "no-store"
        if inline:
            resp["Content-Security-Policy"] = INLINE_CSP
        return resp