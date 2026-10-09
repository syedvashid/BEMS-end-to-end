from apps.core.errors import Conflict


class InsufficientStock(Conflict):
    """409 with code insufficient_stock and details.available (the core handler passes `extra` as details)."""
    default_code = "insufficient_stock"

    def __init__(self, available):
        super().__init__("Not enough stock. Available: %s." % format(available, "f"))
        self.extra = {"available": format(available, "f")}
