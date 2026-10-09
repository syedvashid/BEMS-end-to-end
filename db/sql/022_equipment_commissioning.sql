-- 022: installation and acceptance record, one active row per equipment. Run as bems_owner.
create table if not exists equipment_commissioning (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,

  installation_date date,
  installation_engineer_name text,
  installation_vendor_id bigint,
  installation_notes text,

  acceptance_test_result text,
  acceptance_test_notes text,
  acceptance_date date,
  accepted_by bigint references users (id),
  handed_over_department_id bigint,
  handover_received_by_name text,
  training_conducted boolean not null default false,
  training_notes text,
  commissioning_date date,

  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,

  constraint uq_equipment_commissioning_public_id unique (public_id),
  constraint ck_equipment_commissioning_rowver check (row_version >= 1),
  constraint ck_equipment_commissioning_result check (acceptance_test_result is null or acceptance_test_result in ('PASS','CONDITIONAL','FAIL')),
  constraint ck_equipment_commissioning_accept check (acceptance_date is null or acceptance_test_result is not null),
  constraint ck_equipment_commissioning_text check (
    coalesce(char_length(installation_engineer_name),0) <= 200 and coalesce(char_length(handover_received_by_name),0) <= 200
    and coalesce(char_length(installation_notes),0) <= 2000 and coalesce(char_length(acceptance_test_notes),0) <= 2000
    and coalesce(char_length(training_notes),0) <= 2000),
  constraint fk_equipment_commissioning_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_equipment_commissioning_vendor foreign key (facility_id, installation_vendor_id) references vendors (facility_id, id),
  constraint fk_equipment_commissioning_dept foreign key (facility_id, handed_over_department_id) references departments (facility_id, id)
);
create unique index if not exists ux_equipment_commissioning_equipment_active
  on equipment_commissioning (equipment_id) where is_active;
create index if not exists ix_equipment_commissioning_vendor
  on equipment_commissioning (facility_id, installation_vendor_id) where installation_vendor_id is not null;

drop trigger if exists trg_equipment_commissioning_touch on equipment_commissioning;
create trigger trg_equipment_commissioning_touch before update on equipment_commissioning
  for each row execute function touch_row();
grant select, insert, update on equipment_commissioning to bems_app;

insert into schema_version (version, description)
  values ('022', 'equipment_commissioning') on conflict (version) do nothing;
