from rest_framework import serializers

from apps.foundation.models import User
from apps.foundation.serializers import BlankToNullMixin

from .models import Document
from .registry import labels_for
from .validators import DOCUMENT_TYPES

TYPE_CHOICES = [v for v, _ in DOCUMENT_TYPES]


def _version_dict(v, names=None):
    return {
        "version_no": v.version_no, "original_filename": v.original_filename,
        "content_type": v.content_type, "size_bytes": v.size_bytes,
        "uploaded_at": v.created_at,
        "uploaded_by": (names or {}).get(v.created_by),
    }


class DocumentListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        items = list(data)
        ctx = getattr(self.context.get("request"), "bems", None)
        self.child._labels = labels_for(items, ctx.facility.id if ctx and ctx.facility else None)
        return [self.child.to_representation(i) for i in items]


class DocumentSerializer(BlankToNullMixin, serializers.ModelSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_null=True)
    document_type = serializers.ChoiceField(choices=TYPE_CHOICES)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    entity = serializers.UUIDField(source="entity_public_id", read_only=True)
    entity_label = serializers.SerializerMethodField()
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "public_id", "entity_type", "entity", "entity_label", "document_type", "title", "description",
            "expiry_date", "current_version_no", "current_version",
            "is_active", "row_version", "created_at", "updated_at",
        ]
        read_only_fields = ["public_id", "entity_type", "current_version_no", "is_active",
                            "row_version", "created_at", "updated_at"]
        list_serializer_class = DocumentListSerializer

    def get_entity_label(self, obj):
        labels = getattr(self, "_labels", None)
        if labels is None:
            ctx = getattr(self.context.get("request"), "bems", None)
            labels = labels_for([obj], ctx.facility.id if ctx and ctx.facility else None)
        return labels.get(str(obj.entity_public_id))

    def get_current_version(self, obj):
        for v in obj.versions.all():
            if v.version_no == obj.current_version_no:
                return _version_dict(v)
        return None


class DocumentDetailSerializer(DocumentSerializer):
    versions = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["versions"]

    def get_versions(self, obj):
        versions = list(obj.versions.all())
        ids = {v.created_by for v in versions if v.created_by}
        names = dict(User.objects.filter(id__in=ids).values_list("id", "full_name")) if ids else {}
        return [_version_dict(v, names) for v in versions]


class VersionUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True, use_url=False)


class DocumentCreateSerializer(BlankToNullMixin, VersionUploadSerializer):
    entity_type = serializers.RegexField(r"^[a-z][a-z0-9_]*$", max_length=50)
    entity = serializers.UUIDField()
    document_type = serializers.ChoiceField(choices=TYPE_CHOICES)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)