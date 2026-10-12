from apps.core.errors import Conflict


class DetailedConflict(Conflict):
    """409 whose `details` carry structured data (blocking items, the clashing booking, ...)."""

    def __init__(self, message=None, details=None, code=None):
        super().__init__(message, code)
        self.extra = details or {}


class AllocationBlocked(DetailedConflict):
    """A refused allocation. The caller audits ASSIGNMENT_BLOCKED outside the rolled-back atomic block."""