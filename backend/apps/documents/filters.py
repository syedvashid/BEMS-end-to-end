import django_filters as df

from .models import Document
from .validators import DOCUMENT_TYPES


class DocumentFilter(df.FilterSet):
    entity_type = df.CharFilter(field_name="entity_type", lookup_expr="exact")
    entity = df.UUIDFilter(field_name="entity_public_id")
    document_type = df.ChoiceFilter(choices=[(v, v) for v, _ in DOCUMENT_TYPES])
    expiry_before = df.DateFilter(field_name="expiry_date", lookup_expr="lte")   # on or before
    search = df.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = Document
        fields = []