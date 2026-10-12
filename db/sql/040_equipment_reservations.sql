begin;

create table if not exists equipment_reservations (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  department_id bigint not null,
  start_at timestamptz not null,
  end_at timestamptz not null,
  purpose text not null,
  procedure_reference text,
  status text not null default 'CONFIRMED',
  cancel_reason text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_reservations_public_id unique (public_id),
  constraint ck_equipment_reservations_rowver check (row_version >= 1),
  constraint fk_resv_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_resv_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint ck_resv_window check (end_at > start_at and end_at - start_at <= interval '7 days'),
  constraint ck_resv_purpose check (length(btrim(purpose)) > 0 and length(purpose) <= 1000),
  constraint ck_resv_text_len check (coalesce(length(procedure_reference), 0) <= 200
    and coalesce(length(cancel_reason), 0) <= 1000),
  constraint ck_resv_status check (status in ('CONFIRMED','CANCELLED','FULFILLED','NO_SHOW')),
  constraint ck_resv_cancel_reason check (status <> 'CANCELLED' or length(btrim(coalesce(cancel_reason, ''))) > 0),
  constraint ex_resv_no_overlap exclude using gist (
    facility_id with =, equipment_id with =, tstzrange(start_at, end_at, '[)') with &&)
    where (status in ('CONFIRMED','FULFILLED') and is_active)
);

create index if not exists ix_resv_facility_start on equipment_reservations (facility_id, start_at);
create index if not exists ix_resv_equipment_start on equipment_reservations (facility_id, equipment_id, start_at);

create or replace function trg_resv_status_guard() returns trigger language plpgsql as $$
begin
  if old.status <> 'CONFIRMED' and new.status is distinct from old.status then
    raise exception 'reservation status is final' using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists trg_equipment_reservations_status on equipment_reservations;
create trigger trg_equipment_reservations_status before update on equipment_reservations
  for each row execute function trg_resv_status_guard();

drop trigger if exists trg_equipment_reservations_touch on equipment_reservations;
create trigger trg_equipment_reservations_touch before update on equipment_reservations
  for each row execute function touch_row();

grant select, insert, update on equipment_reservations to bems_app;

insert into schema_version (version, description)
  values ('040', 'equipment_reservations') on conflict (version) do nothing;
commit;