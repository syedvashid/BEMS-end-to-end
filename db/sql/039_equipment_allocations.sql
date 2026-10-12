begin;

create table if not exists equipment_allocations (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  department_id bigint,
  location_id bigint,
  source_module text not null default 'MANUAL',
  patient_reference text,
  encounter_reference text,
  practitioner_name text,
  purpose text,
  assigned_at timestamptz not null default now(),
  expected_release_at timestamptz,
  released_at timestamptz,
  released_by bigint references users (id),
  condition_on_release text,
  release_notes text,
  previous_location_id bigint,
  gate_override boolean not null default false,
  override_reason text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_allocations_public_id unique (public_id),
  constraint uq_equipment_allocations_facility_id unique (facility_id, id),
  constraint ck_equipment_allocations_rowver check (row_version >= 1),
  constraint fk_alloc_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_alloc_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint fk_alloc_location foreign key (facility_id, location_id) references locations (facility_id, id),
  constraint fk_alloc_prev_location foreign key (facility_id, previous_location_id) references locations (facility_id, id),
  constraint ck_alloc_target check (department_id is not null or location_id is not null),
  constraint ck_alloc_source check (source_module in ('IPD','OT','ICU','ER','RADIOLOGY','LAB','MANUAL')),
  constraint ck_alloc_patient_ref check (patient_reference is null or patient_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_alloc_encounter_ref check (encounter_reference is null or encounter_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_alloc_text_len check (
    coalesce(length(practitioner_name), 0) <= 200 and coalesce(length(purpose), 0) <= 1000
    and coalesce(length(release_notes), 0) <= 1000 and coalesce(length(override_reason), 0) <= 1000),
  constraint ck_alloc_expected check (expected_release_at is null or expected_release_at > assigned_at),
  constraint ck_alloc_condition check (condition_on_release is null
    or condition_on_release in ('GOOD','NEEDS_CLEANING','DAMAGED')),
  constraint ck_alloc_release_cond check (released_at is null or condition_on_release is not null),
  constraint ck_alloc_release_by check ((released_at is null) = (released_by is null)),
  constraint ck_alloc_release_after check (released_at is null or released_at >= assigned_at),
  constraint ck_alloc_override check (gate_override = (override_reason is not null)
    and (override_reason is null or length(btrim(override_reason)) > 0))
);

create unique index if not exists ux_equipment_allocations_equipment_active
  on equipment_allocations (facility_id, equipment_id) where released_at is null and is_active;
create index if not exists ix_alloc_equipment_assigned
  on equipment_allocations (facility_id, equipment_id, assigned_at desc);
create index if not exists ix_alloc_department_open
  on equipment_allocations (facility_id, department_id) where released_at is null and is_active;
create index if not exists ix_alloc_location_open
  on equipment_allocations (facility_id, location_id) where released_at is null and is_active;

drop trigger if exists trg_equipment_allocations_touch on equipment_allocations;
create trigger trg_equipment_allocations_touch before update on equipment_allocations
  for each row execute function touch_row();

grant select, insert, update on equipment_allocations to bems_app;

insert into schema_version (version, description)
  values ('039', 'equipment_allocations') on conflict (version) do nothing;
commit;