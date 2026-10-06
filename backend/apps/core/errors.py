import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response
# from rest_framework.views import exception_handler as drf_exception_handler

log = logging.getLogger("bems.errors")


class StaleVersion(exceptions.APIException):
    status_code = 409
    default_code = "stale_version"
    default_detail = "This record was changed by someone else. Reload it and try again."

    def __init__(self, current_row_version=None, detail=None, code=None):
        super().__init__(detail, code)
        self.extra = {"current_row_version": current_row_version} if current_row_version is not None else {}


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "The request conflicts with the current state of the data."


class FacilityRequired(exceptions.APIException):
    status_code = 400
    default_code = "facility_required"
    default_detail = "Header X-Facility-Id is required."


_FIXED = {
    "not_authenticated": "Authentication required.",
    "permission_denied": "You do not have permission to perform this action.",
    "not_found": "Not found.",
    "method_not_allowed": "Method not allowed.",
    "parse_error": "Malformed request.",
    "unsupported_media_type": "Unsupported media type.",
    "not_acceptable": "Not acceptable.",
    "throttled": "Too many requests.",
}


def error_body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _plain(detail):
    if isinstance(detail, dict):
        return {k: _plain(v) for k, v in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_plain(v) for v in detail]
    return str(detail)


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_exception_handler  # lazy: avoids import cycle

    if isinstance(exc, IntegrityError):
        log.warning("IntegrityError: %s", exc)
        return Response(error_body("conflict", "The request conflicts with existing data."), status=409)
    if isinstance(exc, DjangoValidationError):
        return Response(error_body("validation_error", "Invalid input.", {"non_field_errors": exc.messages}), status=400)

    response = drf_exception_handler(exc, context)
    if response is None:
        log.exception("Unhandled error")
        return Response(error_body("internal_error", "An unexpected error occurred."), status=500)

    if isinstance(exc, exceptions.ValidationError):
        details = _plain(exc.detail)
        if not isinstance(details, dict):
            details = {"non_field_errors": details if isinstance(details, list) else [details]}
        body = error_body("validation_error", "Invalid input.", details)
    elif isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else "error"
        if code == "authentication_failed":
            code = "not_authenticated"
        own = isinstance(exc, (StaleVersion, Conflict, FacilityRequired))
        message = str(exc.detail) if own else _FIXED.get(code, "Request failed.")
        body = error_body(code, message, getattr(exc, "extra", {}))
    else:  # Django Http404 / PermissionDenied converted by DRF
        code = {404: "not_found", 403: "permission_denied"}.get(response.status_code, "error")
        body = error_body(code, _FIXED.get(code, "Request failed."))
    response.data = body
    return response


def not_found(request, exception=None):
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error(request):
    return JsonResponse(error_body("internal_error", "An unexpected error occurred."), status=500)