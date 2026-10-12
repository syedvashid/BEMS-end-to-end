-- 047 physical verification. Run as bems_owner.
begin;

create table if not exists physical_verifications (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  verification_number text not null,
  title text not null,
  scope_type text not null,
  department_id bigint,
  location_id bigint,
  planned_date date,
  started_at timestamptz,
  completed_at timestamptz,
  status text not null default 'PLANNED',
  conducted_by_name text,
  notes text,
  expected_count integer,
  found_count integer,
  elsewhere_count integer,
  missing_count integer,
  unexpected_count integer,
  cancel_reason text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_physical_verifications_public_id unique (public_id),
  constraint uq_physical_verifications_facility_id unique (facility_id, id),
  constraint uq_physical_verifications_number unique (facility_id, verification_number),
  constraint ck_physical_verifications_rowver check (row_version >= 1),
  constraint ck_physical_verifications_number check (verification_number ~ '^VER-[0-9]{4}-[0-9]{6}$'),
  constraint ck_physical_verifications_title check (btrim(title) <> ''),
  constraint ck_physical_verifications_scope_type check (scope_type in ('FACILITY','DEPARTMENT','LOCATION')),
  constraint ck_physical_verifications_scope check (
    (scope_type = 'FACILITY' and department_id is null and location_id is null)
    or (scope_type = 'DEPARTMENT' and department_id is not null and location_id is null)
    or (scope_type = 'LOCATION' and location_id is not null and department_id is null)),
  constraint ck_physical_verifications_status check (status in ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')),
  constraint ck_physical_verifications_counts check (
    coalesce(expected_count, 0) >= 0 and coalesce(found_count, 0) >= 0 and coalesce(elsewhere_count, 0) >= 0
    and coalesce(missing_count, 0) >= 0 and coalesce(unexpected_count, 0) >= 0),
  constraint ck_physical_verifications_started check (status not in ('IN_PROGRESS','COMPLETED') or started_at is not null),
  constraint ck_physical_verifications_completed check (status <> 'COMPLETED' or (completed_at is not null and expected_count is not null)),
  constraint ck_physical_verifications_cancelled check (status <> 'CANCELLED' or (cancel_reason is not null and btrim(cancel_reason) <> '')),
  constraint fk_physical_verifications_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint fk_physical_verifications_location foreign key (facility_id, location_id) references locations (facility_id, id)
);
create index if not exists ix_physical_verifications_status on physical_verifications (facility_id, status);

create or replace function enforce_verification_transition() returns trigger
language plpgsql as $$
begin
  if new.status is distinct from old.status and (old.status, new.status) not in (
       ('PLANNED','IN_PROGRESS'), ('PLANNED','CANCELLED'), ('IN_PROGRESS','COMPLETED'), ('IN_PROGRESS','CANCELLED')) then
    raise exception 'Verification status change % -> % is not allowed', old.status, new.status
      using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists trg_physical_verifications_status on physical_verifications;
create trigger trg_physical_verifications_status before update on physical_verifications
  for each row execute function enforce_verification_transition();
drop trigger if exists trg_physical_verifications_touch on physical_verifications;
create trigger trg_physical_verifications_touch before update on physical_verifications
  for each row execute function touch_row();
grant select, insert, update on physical_verifications to bems_app;

create table if not exists physical_verification_items (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  verification_id bigint not null,
  equipment_id bigint not null,
  expected_location_id bigint,
  expected_department_id bigint,
  result text not null default 'PENDING',
  found_location_id bigint,
  scanned_at timestamptz,
  scanned_by bigint references users (id),
  tag_status text not null default 'OK',
  notes text,
  resolution text not null default 'NONE',
  resolution_notes text,
  resolved_by bigint references users (id),
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_physical_verification_items_public_id unique (public_id),
  constraint uq_physical_verification_items_pair unique (verification_id, equipment_id),
  constraint ck_physical_verification_items_rowver check (row_version >= 1),
  constraint ck_physical_verification_items_result check (result in ('PENDING','FOUND','FOUND_ELSEWHERE','MISSING','UNEXPECTED')),
  constraint ck_physical_verification_items_tag check (tag_status in ('OK','DAMAGED','UNREADABLE')),
  constraint ck_physical_verification_items_resolution check (resolution in ('NONE','LOCATION_UPDATED','CONFIRMED_MISSING','FOUND_LATER','IGNORED')),
  constraint ck_physical_verification_items_scanned check (
    result not in ('FOUND','FOUND_ELSEWHERE','UNEXPECTED') or (scanned_at is not null and found_location_id is not null)),
  constraint ck_physical_verification_items_resolved check (
    (resolution = 'NONE') = (resolved_at is null)
    and (resolution = 'NONE' or result in ('FOUND_ELSEWHERE','MISSING','UNEXPECTED'))),
  constraint fk_physical_verification_items_verification foreign key (facility_id, verification_id) references physical_verifications (facility_id, id),
  constraint fk_physical_verification_items_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_physical_verification_items_exp_location foreign key (facility_id, expected_location_id) references locations (facility_id, id),
  constraint fk_physical_verification_items_exp_department foreign key (facility_id, expected_department_id) references departments (facility_id, id),
  constraint fk_physical_verification_items_found_location foreign key (facility_id, found_location_id) references locations (facility_id, id)
);
create index if not exists ix_physical_verification_items_result on physical_verification_items (verification_id, result);
drop trigger if exists trg_physical_verification_items_touch on physical_verification_items;
create trigger trg_physical_verification_items_touch before update on physical_verification_items
  for each row execute function touch_row();
grant select, insert, update on physical_verification_items to bems_app;

insert into schema_version (version, description) values ('047', 'physical verifications') on conflict (version) do nothing;
commit;
