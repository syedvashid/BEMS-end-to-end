-- 046 recalls and field safety notices. Run as bems_owner.
begin;

create table if not exists recall_notices (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  notice_number text not null,
  reference_number text,
  title text not null,
  notice_type text not null,
  source text not null,
  issued_by_vendor_id bigint,
  issued_date date,
  received_date date,
  urgency text not null,
  action_type text not null,
  stop_use boolean not null default false,
  description text not null,
  required_action text,
  affected_serials_note text,
  status text not null default 'OPEN',
  closed_at timestamptz,
  closed_by bigint references users (id),
  close_notes text,
  cancel_reason text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_recall_notices_public_id unique (public_id),
  constraint uq_recall_notices_facility_id unique (facility_id, id),
  constraint uq_recall_notices_number unique (facility_id, notice_number),
  constraint ck_recall_notices_rowver check (row_version >= 1),
  constraint ck_recall_notices_number check (notice_number ~ '^RCL-[0-9]{4}-[0-9]{6}$'),
  constraint ck_recall_notices_title check (btrim(title) <> ''),
  constraint ck_recall_notices_description check (btrim(description) <> ''),
  constraint ck_recall_notices_reference check (reference_number is null or btrim(reference_number) <> ''),
  constraint ck_recall_notices_type check (notice_type in ('RECALL','FIELD_SAFETY_NOTICE','SAFETY_ALERT','ADVISORY')),
  constraint ck_recall_notices_source check (source in ('MANUFACTURER','REGULATOR','INTERNAL')),
  constraint ck_recall_notices_urgency check (urgency in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_recall_notices_action check (action_type in ('STOP_USE','INSPECT','UPDATE_SOFTWARE','MODIFY','RETURN','INFORM_ONLY')),
  constraint ck_recall_notices_stop_use check (action_type <> 'STOP_USE' or stop_use),
  constraint ck_recall_notices_dates check (issued_date is null or received_date is null or received_date >= issued_date),
  constraint ck_recall_notices_status check (status in ('OPEN','CLOSED','CANCELLED')),
  constraint ck_recall_notices_closed
    check (status <> 'CLOSED' or (closed_at is not null and close_notes is not null and btrim(close_notes) <> '')),
  constraint ck_recall_notices_cancelled
    check (status <> 'CANCELLED' or (cancel_reason is not null and btrim(cancel_reason) <> '')),
  constraint fk_recall_notices_vendor foreign key (facility_id, issued_by_vendor_id) references vendors (facility_id, id)
);
create unique index if not exists ux_recall_notices_reference_active
  on recall_notices (facility_id, lower(reference_number)) where is_active and reference_number is not null;
create index if not exists ix_recall_notices_status on recall_notices (facility_id, status);
drop trigger if exists trg_recall_notices_touch on recall_notices;
create trigger trg_recall_notices_touch before update on recall_notices
  for each row execute function touch_row();
grant select, insert, update on recall_notices to bems_app;

-- Child collection (replaced as a set)
create table if not exists recall_notice_models (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  recall_notice_id bigint not null,
  equipment_model_id bigint not null,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_recall_notice_models_public_id unique (public_id),
  constraint uq_recall_notice_models_pair unique (recall_notice_id, equipment_model_id),
  constraint fk_recall_notice_models_notice foreign key (facility_id, recall_notice_id) references recall_notices (facility_id, id),
  constraint fk_recall_notice_models_model foreign key (facility_id, equipment_model_id) references equipment_models (facility_id, id)
);
create index if not exists ix_recall_notice_models_model on recall_notice_models (facility_id, equipment_model_id);
grant select, insert, delete on recall_notice_models to bems_app;

create table if not exists recall_affected_units (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  recall_notice_id bigint not null,
  equipment_id bigint not null,
  status text not null default 'PENDING',
  identified_by text not null,
  resolved_at timestamptz,
  resolved_by bigint references users (id),
  resolution_notes text,
  vendor_reference text,
  work_order_id bigint,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_recall_affected_units_public_id unique (public_id),
  constraint uq_recall_affected_units_facility_id unique (facility_id, id),
  constraint ck_recall_affected_units_rowver check (row_version >= 1),
  constraint ck_recall_affected_units_status check (status in ('PENDING','ACTION_COMPLETED','NOT_APPLICABLE')),
  constraint ck_recall_affected_units_identified check (identified_by in ('ALL_OF_MODELS','SERIAL_LIST','MANUAL')),
  constraint ck_recall_affected_units_resolved check ((resolved_at is not null) = (status <> 'PENDING')),
  constraint fk_recall_affected_units_notice foreign key (facility_id, recall_notice_id) references recall_notices (facility_id, id),
  constraint fk_recall_affected_units_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_recall_affected_units_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id)
);
create unique index if not exists ux_recall_affected_units_pair_active
  on recall_affected_units (recall_notice_id, equipment_id) where is_active;
create index if not exists ix_recall_affected_units_notice on recall_affected_units (recall_notice_id, status);
create index if not exists ix_recall_affected_units_pending
  on recall_affected_units (facility_id, equipment_id) where status = 'PENDING';

create or replace function enforce_recall_unit_final() returns trigger
language plpgsql as $$
begin
  if old.status <> 'PENDING' and new.status is distinct from old.status then
    raise exception 'A resolved recall unit is final' using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists trg_recall_affected_units_final on recall_affected_units;
create trigger trg_recall_affected_units_final before update on recall_affected_units
  for each row execute function enforce_recall_unit_final();
drop trigger if exists trg_recall_affected_units_touch on recall_affected_units;
create trigger trg_recall_affected_units_touch before update on recall_affected_units
  for each row execute function touch_row();
grant select, insert, update on recall_affected_units to bems_app;

insert into schema_version (version, description) values ('046', 'recall notices') on conflict (version) do nothing;
commit;
