create table if not exists audit_log (
    id                bigint generated always as identity primary key,
    chain_seq         bigint      not null,           -- assigned by trigger under lock
    occurred_at       timestamptz not null default now(),
    facility_id       bigint      references facilities (id),
    actor_user_id     bigint      references users (id),
    actor_username    text,
    action            text        not null,
    entity_type       text,
    entity_public_id  uuid,
    previous_value    jsonb,
    new_value         jsonb,
    changed_fields    text[],
    request_id        text,
    ip_address        inet,
    user_agent        text,
    http_method       text,
    request_path      text,
    prev_hash         text        not null,
    row_hash          text        not null,
    constraint uq_audit_chain_seq unique (chain_seq),
    constraint ck_audit_action check (action ~ '^[A-Z][A-Z0-9_]*$')
);

create index if not exists ix_audit_entity   on audit_log (entity_type, entity_public_id, occurred_at);
create index if not exists ix_audit_facility on audit_log (facility_id, occurred_at);
create index if not exists ix_audit_actor    on audit_log (actor_user_id, occurred_at);
create index if not exists ix_audit_action   on audit_log (action, occurred_at);

-- Hash over the row's key fields. %L quoting makes NULLs and separators unambiguous.
create or replace function audit_compute_hash(r audit_log, p_prev text) returns text
language sql immutable
set search_path = public, pg_catalog
as $$
    select encode(digest(
        format('%L|%L|%L|%L|%L|%L|%L|%L|%L|%L|%L|%L|%L|%L|%L',
            p_prev, r.chain_seq,
            to_char(r.occurred_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
            r.facility_id, r.actor_user_id, r.actor_username, r.action,
            r.entity_type, r.entity_public_id,
            r.previous_value::text, r.new_value::text, r.changed_fields::text,
            r.request_id, r.http_method, r.request_path
        ), 'sha256'), 'hex');
$$;

-- Chain on insert, serialised by a global advisory lock.
create or replace function audit_log_before_insert() returns trigger
language plpgsql
set search_path = public, pg_catalog
as $$
declare
    v_seq  bigint;
    v_hash text;
begin
    perform pg_advisory_xact_lock(7301001);          -- fixed key: audit chain
    select chain_seq, row_hash into v_seq, v_hash
      from audit_log order by chain_seq desc limit 1;
    new.chain_seq  := coalesce(v_seq, 0) + 1;
    new.prev_hash  := coalesce(v_hash, repeat('0', 64));
    new.user_agent := left(new.user_agent, 255);
    new.row_hash   := audit_compute_hash(new, new.prev_hash);
    return new;
end;
$$;

drop trigger if exists trg_audit_log_chain on audit_log;
create trigger trg_audit_log_chain before insert on audit_log
    for each row execute function audit_log_before_insert();

-- Immutability
create or replace function audit_log_block_change() returns trigger
language plpgsql as $$
begin
    raise exception 'audit_log is append-only (% blocked)', tg_op
        using errcode = 'insufficient_privilege';
end;
$$;

drop trigger if exists trg_audit_log_immutable on audit_log;
create trigger trg_audit_log_immutable before update or delete on audit_log
    for each row execute function audit_log_block_change();

drop trigger if exists trg_audit_log_no_truncate on audit_log;
create trigger trg_audit_log_no_truncate before truncate on audit_log
    for each statement execute function audit_log_block_change();

-- Returns id of the first broken row, or null if the chain is intact.
create or replace function verify_audit_chain() returns bigint
language plpgsql stable
set search_path = public, pg_catalog
as $$
declare
    r          audit_log;
    v_prev     text   := repeat('0', 64);
    v_expected bigint := 1;
begin
    for r in select * from audit_log order by chain_seq loop
        if r.chain_seq <> v_expected
           or r.prev_hash is distinct from v_prev
           or r.row_hash  is distinct from audit_compute_hash(r, v_prev) then
            return r.id;
        end if;
        v_prev := r.row_hash;
        v_expected := v_expected + 1;
    end loop;
    return null;
end;
$$;

insert into schema_version (version, description)
values ('006', 'audit_log: append-only, hash chain, verify_audit_chain()')
on conflict (version) do nothing;