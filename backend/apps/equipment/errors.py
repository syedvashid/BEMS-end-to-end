from rest_framework import status
from rest_framework.exceptions import APIException

try:  # reuse the project's own 409 class if it already has one
    from apps.core.errors import Conflict  # noqa: F401
except ImportError:
    class Conflict(APIException):
        status_code = status.HTTP_409_CONFLICT
        default_code = "conflict"
        default_detail = "This action conflicts with the current state of the record."
