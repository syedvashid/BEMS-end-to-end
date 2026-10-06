from .settings import *  # noqa: F401,F403
from .settings import DATABASES, env

_name = env("BEMS_TEST_DB_NAME", "bems_test")
if _name == DATABASES["default"]["NAME"]:
    raise RuntimeError("BEMS_TEST_DB_NAME must differ from DB_NAME.")
DATABASES["default"]["NAME"] = _name