-- 053 condemnation requests (run as bems_owner)
begin;

create table if not exists condemnation_requests (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  request_number text not null,
  equipment_id bigint not null,
  reason_category text not null,
  justification text not null,
  technical_assessment text,
  technical_assessment_by_name text,
  book_value_at_request numeric(14,2),
  source_verification_item_id bigint,
  status text not null default 'REQUESTED',
  committee_reference text,
  committee_decision_date date,
  decided_by bigint references users (id),
  decided_at timestamptz,
  decision_note text,
  revoked boolean not null default false,
  cancel_reason text,
  completed_at timestamptz,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_condemnation_requests_public_id unique (public_id),
  constraint uq_condemnation_requests_facility_id_id unique (facility_id, id),
  constraint ck_condemnation_requests_rowver check (row_version >= 1),
  constraint fk_condemnation_requests_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_condemnation_requests_verification_item foreign key (facility_id, source_verification_item_id)
    references physical_verification_items (facility_id, id),
  constraint ck_condemnation_requests_reason check (reason_category in (
    'UNECONOMICAL_TO_REPAIR','BEYOND_ECONOMIC_LIFE','OBSOLETE','UNSAFE','DAMAGED_BEYOND_REPAIR','LOST_MISSING','OTHER')),
  constraint ck_condemnation_requests_justification check (length(btrim(justification)) > 0),
  constraint ck_condemnation_requests_status check (status in ('REQUESTED','APPROVED','REJECTED','CANCELLED','COMPLETED')),
  constraint ck_condemnation_requests_book_value check (book_value_at_request is null or book_value_at_request >= 0),
  constraint ck_condemnation_requests_reject_note check (
    status <> 'REJECTED' or (decision_note is not null and length(btrim(decision_note)) > 0)),
  constraint ck_condemnation_requests_approved check (
    status <> 'APPROVED' or (decided_by is not null and decided_at is not null))
);
create unique index if not exists ux_condemnation_requests_number_active
  on condemnation_requests (facility_id, request_number) where is_active;
create unique index if not exists ux_condemnation_requests_live_equipment_active
  on condemnation_requests (facility_id, equipment_id)
  where status in ('REQUESTED','APPROVED') and is_active;
create index if not exists ix_condemnation_requests_equipment on condemnation_requests (facility_id, equipment_id);
create index if not exists ix_condemnation_requests_status on condemnation_requests (facility_id, status, created_at desc);

create or replace function fn_condemnation_requests_status_guard() returns trigger
language plpgsql as $$
begin
  if new.status is distinct from old.status then
    if not ((old.status = 'REQUESTED' and new.status in ('APPROVED','REJECTED','CANCELLED'))
         or (old.status = 'APPROVED' and new.status in ('COMPLETED','CANCELLED'))) then
      raise exception 'Condemnation status change % -> % is not allowed', old.status, new.status
        using errcode = '23514';
    end if;
  end if;
  return new;
end $$;

drop trigger if exists trg_condemnation_requests_status on condemnation_requests;
create trigger trg_condemnation_requests_status before update on condemnation_requests
  for each row execute function fn_condemnation_requests_status_guard();
drop trigger if exists trg_condemnation_requests_touch on condemnation_requests;
create trigger trg_condemnation_requests_touch before update on condemnation_requests
  for each row execute function touch_row();
grant select, insert, update on condemnation_requests to bems_app;

insert into schema_version (version, description)
  values ('053', 'condemnation requests') on conflict (version) do nothing;
commit;
