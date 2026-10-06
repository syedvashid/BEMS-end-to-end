import psycopg
import pytest
from django.db import DatabaseError, connection, transaction

from apps.core import audit
from apps.foundation.models import AuditLog

from conftest import connect


def test_redact_is_central_and_deep():
    out = audit.redact({"password_hash": "x", "ok": 1, "n": {"Token": "y", "list": [{"secret": "z"}]}})
    assert out["password_hash"] == audit.REDACTED and out["ok"] == 1
    assert out["n"]["Token"] == audit.REDACTED and out["n"]["list"][0]["secret"] == audit.REDACTED


def test_record_redacts_secrets_in_stored_values(db):
    audit.record(action="TEST_EVENT", entity_type="T", previous={"password_hash": "old"}, new={"password_hash": "new", "a": 1})
    row = AuditLog.objects.filter(action="TEST_EVENT").latest("chain_seq")
    assert row.new_value == {"password_hash": "[REDACTED]", "a": 1}
    assert row.previous_value == {"password_hash": "[REDACTED]"}


def test_action_name_is_validated(db):
    with pytest.raises(ValueError):
        audit.record(action="bad action")


def test_chain_verifies(db):
    for i in range(3):
        audit.record(action="TEST_EVENT", new={"i": i})
    with connection.cursor() as cur:
        cur.execute("SELECT verify_audit_chain()")
        assert cur.fetchone()[0] is None
    seqs = list(AuditLog.objects.order_by("chain_seq").values_list("chain_seq", flat=True))
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


@pytest.mark.parametrize("stmt", ["UPDATE audit_log SET action = 'HACK'", "DELETE FROM audit_log", "TRUNCATE audit_log"])
def test_runtime_role_cannot_modify_audit(db, stmt):
    audit.record(action="TEST_EVENT")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(stmt)


def test_trigger_blocks_update_and_delete_even_for_owner(django_db_setup, bems_db_params):
    p = bems_db_params
    conn = connect(p, p["name"], p["owner_user"], p["owner_pw"], autocommit=False)
    try:
        for stmt in ("UPDATE audit_log SET action = 'HACK' WHERE action = 'TRIGGER_TEST'",
                     "DELETE FROM audit_log WHERE action = 'TRIGGER_TEST'"):
            cur = conn.cursor()
            cur.execute("INSERT INTO audit_log (action, entity_type) VALUES ('TRIGGER_TEST', 't')")
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
                cur.execute(stmt)
            conn.rollback()
    finally:
        conn.rollback()
        conn.close()


def test_tampering_is_detected_by_verify(django_db_setup, bems_db_params):
    p = bems_db_params
    conn = connect(p, p["name"], p["owner_user"], p["owner_pw"], autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO audit_log (action, entity_type) VALUES ('TAMPER_A', 't')")
        cur.execute("INSERT INTO audit_log (action, entity_type) VALUES ('TAMPER_B', 't')")
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_immutable")
        cur.execute("UPDATE audit_log SET action = 'HACKED' WHERE action = 'TAMPER_A'")
        cur.execute("SELECT verify_audit_chain()")
        assert cur.fetchone()[0] is not None
    finally:
        conn.rollback()   # DDL is transactional: trigger is restored, rows gone
        conn.close()