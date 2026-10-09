-- 023: immutable history tables (select + insert only). Run as bems_owner.
create table if not exists equipment_state_history (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  change_type text not null,
  from_value text,
  to_value text not null,
  reason text not null,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_equipment_state_history_public_id unique (public_id),
  constraint ck_esh_type check (change_type in ('LIFECYCLE','OPERATIONAL')),
  constraint ck_esh_reason check (btrim(reason) <> '' and char_length(reason) <= 1000),
  constraint fk_esh_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id)
);
create index if not exists ix_esh_equipment on equipment_state_history (equipment_id, created_at desc);
grant select, insert on equipment_state_history to bems_app;

create table if not exists equipment_movements (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  from_location_id bigint,
  to_location_id bigint not null,
  from_department_id bigint,
  to_department_id bigint,
  reason text not null,
  moved_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_equipment_movements_public_id unique (public_id),
  constraint ck_em_reason check (btrim(reason) <> '' and char_length(reason) <= 1000),
  constraint fk_em_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_em_from_location foreign key (facility_id, from_location_id) references locations (facility_id, id),
  constraint fk_em_to_location foreign key (facility_id, to_location_id) references locations (facility_id, id),
  constraint fk_em_from_dept foreign key (facility_id, from_department_id) references departments (facility_id, id),
  constraint fk_em_to_dept foreign key (facility_id, to_department_id) references departments (facility_id, id)
);
create index if not exists ix_em_equipment on equipment_movements (equipment_id, moved_at desc);
grant select, insert on equipment_movements to bems_app;

insert into schema_version (version, description)
  values ('023', 'equipment_state_history, equipment_movements') on conflict (version) do nothing;
