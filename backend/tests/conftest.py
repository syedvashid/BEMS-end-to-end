import os
from pathlib import Path

# import psycopg
import pytest
from psycopg import sql
from rest_framework.test import APIClient

SQL_DIR = Path(__file__).resolve().parents[2] / "db" / "sql"
API = "/api/v1"


def _params():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5433")),
        "name": os.environ.get("BEMS_TEST_DB_NAME", "bems_test"),
        "admin_user": os.environ.get("BEMS_TEST_ADMIN_USER", "postgres"),
        "admin_pw": os.environ["BEMS_TEST_ADMIN_PASSWORD"],
        "owner_user": os.environ.get("BEMS_TEST_OWNER_USER", "bems_owner"),
        "owner_pw": os.environ["BEMS_TEST_OWNER_PASSWORD"],
    }


def connect(p, dbname, user, password, autocommit=True):
    return psycopg.connect(host=p["host"], port=p["port"], dbname=dbname, user=user,
                           password=password, autocommit=autocommit)


@pytest.fixture(scope="session")
def bems_db_params():
    return _params()


@pytest.fixture(scope="session")
def django_db_setup(bems_db_params):
    """Build a fresh test database from db/sql (files below 900; never the dev seed)."""
    p = bems_db_params
    assert p["name"] != os.environ.get("DB_NAME"), "Test DB must differ from the dev DB."
    admin = connect(p, "postgres", p["admin_user"], p["admin_pw"])
    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(p["name"])))
    admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(p["name"]), sql.Identifier(p["owner_user"])))
    admin.close()
    ext = connect(p, p["name"], p["admin_user"], p["admin_pw"])
    ext.execute((SQL_DIR / "000_extensions.sql").read_text(encoding="utf-8"))
    ext.close()
    owner = connect(p, p["name"], p["owner_user"], p["owner_pw"])
    for f in sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        n = int(f.name[:3])
        if n == 0 or n >= 900:
            continue
        owner.execute(f.read_text(encoding="utf-8"))
    owner.close()
    yield
    from django.db import connections
    connections.close_all()
    admin = connect(p, "postgres", p["admin_user"], p["admin_pw"])
    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(p["name"])))
    admin.close()


@pytest.fixture(autouse=True)
def _dev_auth_on(settings):
    settings.DEBUG = True          # pytest-django forces DEBUG=False; dev auth needs it
    settings.BEMS_DEV_AUTH = True


class Api:
    def __init__(self, username=None, facility=None):
        self.client = APIClient()
        self.extra = {}
        if username:
            self.extra["HTTP_X_DEV_USER"] = username
        if facility is not None:
            self.extra["HTTP_X_FACILITY_ID"] = str(getattr(facility, "public_id", facility))

    def call(self, method, path, body=None):
        fn = getattr(self.client, method.lower())
        if method.upper() in ("POST", "PUT", "PATCH"):
            return fn(API + path, body or {}, format="json", **self.extra)
        return fn(API + path, **self.extra)

    def get(self, path, **params):
        return self.client.get(API + path, params, **self.extra)

    def post(self, path, body=None):
        return self.call("POST", path, body)

    def put(self, path, body=None):
        return self.call("PUT", path, body)

    def patch(self, path, body=None):
        return self.call("PATCH", path, body)

    def delete(self, path):
        return self.client.delete(API + path, **self.extra)


@pytest.fixture
def api():
    return lambda username=None, facility=None: Api(username, facility)


@pytest.fixture
def world(db):
    from apps.foundation.models import Facility, Role, User, UserFacilityRole

    class W:
        pass

    w = W()
    w.fa = Facility.objects.create(code="FACA", name="Facility A")
    w.fb = Facility.objects.create(code="FACB", name="Facility B")

    def mk(username, facility, role_code):
        u = User.objects.filter(username=username).first() or User.objects.create(username=username, full_name=username)
        UserFacilityRole.objects.create(user=u, facility=facility, role=Role.objects.get(code=role_code, is_active=True))
        return u

    w.mk = mk
    w.sys_a = mk("sys_a", w.fa, "SYSTEM_ADMIN")
    w.admin_a = mk("admin_a", w.fa, "BIOMED_ADMIN")
    w.sys_b = mk("sys_b", w.fb, "SYSTEM_ADMIN")
    w.dept_b = mk("dept_b", w.fb, "DEPARTMENT_USER")
    return w