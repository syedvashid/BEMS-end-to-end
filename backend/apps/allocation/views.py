from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.foundation.models import User, UserFacilityRole
from apps.foundation.viewsets import FacilityScopedViewSet
from apps.masters.models import Department

from . import services
from .filters import AllocationFilter, ReservationFilter, TransferFilter, UsageLogFilter
from .models import (
    EquipmentAllocation, EquipmentReservation, EquipmentTransferRequest, EquipmentUsageLog, UserDepartment,
)
from .serializers import (
    AllocationCreateSerializer, AllocationReleaseSerializer, ApproveSerializer, ReasonSerializer, RejectSerializer,
    ReservationCreateSerializer, TransferCreateSerializer, UsageLogWriteSerializer, UserDepartmentsInputSerializer,
    allocation_repr, reservation_repr, transfer_repr, usage_repr,
)


def usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


class NamedListMixin:
    """list/retrieve through plain representation functions; user names are fetched once per page."""
    render = None

    def user_ids(self, o):
        return [o.created_by]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        names = usernames(i for o in page for i in self.user_ids(o))
        return self.get_paginated_response([self.render(o, names, request.user.id) for o in page])

    def retrieve(self, request, *args, **kwargs):
        o = self.get_object()
        return Response(self.render(o, usernames(self.user_ids(o)), request.user.id))

    def out(self, o):
        return self.render(o, usernames(self.user_ids(o)), self.request.user.id)


# ================================================================== allocations
class AllocationViewSet(NamedListMixin, FacilityScopedViewSet):
    queryset = EquipmentAllocation.objects.select_related("equipment", "department", "location", "previous_location")
    serializer_class = AllocationCreateSerializer
    audit_entity_type = "EquipmentAllocation"
    http_method_names = ["get", "post", "head"]
    filterset_class = AllocationFilter
    ordering_fields = ["assigned_at", "released_at", "created_at"]
    ordering = ["-assigned_at", "-id"]
    required_permissions = {"list": "allocation.view", "retrieve": "allocation.view",
                            "create": "allocation.assign", "release": "allocation.assign"}
    render = staticmethod(allocation_repr)

    def user_ids(self, o):
        return [o.created_by, o.released_by]

    def create(self, request, *args, **kwargs):
        ser = AllocationCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        eq = d.pop("equipment")
        override, reason = d.pop("override"), d.pop("override_reason", None)
        alloc, warnings = services.allocate(request=request, equipment=eq, data=d, override=override,
                                            override_reason=reason)
        return Response({**self.out(alloc), "warnings": warnings}, status=201)

    @action(detail=True, methods=["post"])
    def release(self, request, public_id=None):
        ser = AllocationReleaseSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        res = services.release(request=request, allocation=self.get_object(), condition=d["condition_on_release"],
                               notes=d.get("release_notes"),
                               return_to_previous_location=d["return_to_previous_location"])
        return Response({**self.out(res["allocation"]), "suggest_breakdown": res["suggest_breakdown"],
                         "moved_back": res["moved_back"]})


# ================================================================== reservations
class ReservationViewSet(NamedListMixin, FacilityScopedViewSet):
    queryset = EquipmentReservation.objects.select_related("equipment", "department")
    serializer_class = ReservationCreateSerializer
    audit_entity_type = "EquipmentReservation"
    http_method_names = ["get", "post", "head"]
    filterset_class = ReservationFilter
    ordering_fields = ["start_at", "end_at", "created_at"]
    ordering = ["start_at", "id"]
    required_permissions = {"list": "reservation.view", "retrieve": "reservation.view", "create": "reservation.add",
                            "cancel": "reservation.view",            # the service allows only the creator or reservation.manage
                            "fulfil": "reservation.manage", "no_show": "reservation.manage"}
    render = staticmethod(reservation_repr)

    def create(self, request, *args, **kwargs):
        ser = ReservationCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        r, warnings = services.reserve(request=request, equipment=d.pop("equipment"), data=d)
        return Response({**self.out(r), "warnings": warnings}, status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        r = services.cancel_reservation(request=request, reservation=self.get_object(),
                                        reason=ser.validated_data["reason"])
        return Response(self.out(r))

    @action(detail=True, methods=["post"])
    def fulfil(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        return Response(self.out(services.mark_reservation(
            request=request, reservation=self.get_object(), status="FULFILLED")))

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        return Response(self.out(services.mark_reservation(
            request=request, reservation=self.get_object(), status="NO_SHOW")))


# ================================================================== usage logs
class UsageLogViewSet(NamedListMixin, FacilityScopedViewSet):
    queryset = EquipmentUsageLog.objects.select_related("equipment", "department", "allocation")
    serializer_class = UsageLogWriteSerializer
    audit_entity_type = "EquipmentUsageLog"
    filterset_class = UsageLogFilter
    ordering_fields = ["started_at", "ended_at", "created_at"]
    ordering = ["-started_at", "-id"]
    include_inactive_permission = "usage.delete"
    required_permissions = {"list": "usage.view", "retrieve": "usage.view", "create": "usage.add",
                            "update": "usage.change", "partial_update": "usage.change", "destroy": "usage.delete"}
    render = staticmethod(usage_repr)

    def create(self, request, *args, **kwargs):
        ser = UsageLogWriteSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        d.pop("row_version", None)
        eq = d.pop("equipment", None)
        if eq is None:
            raise ValidationError({"equipment": ["This field is required."]})
        u = services.save_usage_log(request=request, equipment=eq, data=d)
        return Response(self.out(u), status=201)

    def update(self, request, *args, **kwargs):          # PUT and PATCH are both partial
        kwargs.pop("partial", None)
        ser = UsageLogWriteSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        version = self.parse_row_version(d.pop("row_version", None))
        instance = self.get_object()
        eq = d.pop("equipment", None)
        if eq is not None and eq.pk != instance.equipment_id:
            raise ValidationError({"equipment": ["The equipment of a usage log cannot be changed."]})
        u = services.save_usage_log(request=request, equipment=instance.equipment, data=d, instance=instance,
                                    expected_version=version)
        return Response(self.out(u))


# ================================================================== transfers
class TransferRequestViewSet(NamedListMixin, FacilityScopedViewSet):
    queryset = EquipmentTransferRequest.objects.select_related(
        "equipment", "from_department", "from_location", "to_location", "to_department")
    serializer_class = TransferCreateSerializer
    audit_entity_type = "EquipmentTransferRequest"
    http_method_names = ["get", "post", "head"]
    filterset_class = TransferFilter
    ordering_fields = ["created_at", "decided_at", "status"]
    ordering = ["-created_at", "-id"]
    required_permissions = {"list": "transfer.view", "retrieve": "transfer.view", "create": "transfer.request",
                            "approve": "transfer.approve", "reject": "transfer.approve", "cancel": "transfer.request"}
    render = staticmethod(transfer_repr)

    def user_ids(self, o):
        return [o.created_by, o.decided_by]

    def create(self, request, *args, **kwargs):
        ser = TransferCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        t = services.request_transfer(request=request, equipment=d.pop("equipment"), data=d)
        return Response(self.out(t), status=201)

    @action(detail=True, methods=["post"])
    def approve(self, request, public_id=None):
        ser = ApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        t = services.approve_transfer(request=request, transfer=self.get_object(), note=ser.validated_data.get("note"))
        return Response(self.out(t))

    @action(detail=True, methods=["post"])
    def reject(self, request, public_id=None):
        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        t = services.reject_transfer(request=request, transfer=self.get_object(), note=ser.validated_data["note"])
        return Response(self.out(t))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        return Response(self.out(services.cancel_transfer(request=request, transfer=self.get_object())))


# ================================================================== user departments
def _dept(d):
    return {"public_id": str(d.public_id), "code": d.code, "name": d.name}


class UserDepartmentsView(APIView):
    required_permissions = {"get": "user.view", "put": "user.change"}

    def _user(self, request, public_id):
        u = User.objects.filter(public_id=public_id, is_active=True).first()
        fid = request.bems.facility.id
        if u is None or not UserFacilityRole.objects.filter(
                user_id=u.pk, facility_id=fid, is_active=True, role__is_active=True).exists():
            raise NotFound()
        return u

    def _current(self, fid, user):
        return Department.objects.filter(
            facility_id=fid, is_active=True,
            pk__in=UserDepartment.objects.filter(facility_id=fid, user_id=user.pk).values("department_id")
        ).order_by("name")

    def get(self, request, public_id):
        u = self._user(request, public_id)
        return Response({"departments": [_dept(d) for d in self._current(request.bems.facility.id, u)]})

    def put(self, request, public_id):
        u = self._user(request, public_id)
        ser = UserDepartmentsInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        fid = request.bems.facility.id
        wanted = list(dict.fromkeys(ser.validated_data["departments"]))
        deps = list(Department.objects.filter(facility_id=fid, is_active=True, public_id__in=wanted))
        if len(deps) != len(wanted):
            raise ValidationError({"departments": ["Unknown reference."]})
        services.set_user_departments(request=request, user=u, departments=deps)
        return Response({"departments": [_dept(d) for d in self._current(fid, u)]})


class MyDepartmentsView(APIView):
    required_permissions = {"get": ()}

    def get(self, request):
        ctx, fid = request.bems, request.bems.facility.id
        qs = Department.objects.filter(facility_id=fid, is_active=True)
        if not (ctx.has("reservation.manage") or ctx.has("transfer.approve")):
            qs = qs.filter(pk__in=UserDepartment.objects.filter(
                facility_id=fid, user_id=request.user.id).values("department_id"))
        rows = [_dept(d) for d in qs.order_by("name")]
        return Response({"count": len(rows), "next": None, "previous": None, "results": rows})