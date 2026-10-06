create table if not exists locations (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  parent_location_id bigint,
  location_type varchar(20) not null,
  code varchar(30) not null,
  name varchar(200) not null,
  department_id bigint,
  description varchar(500),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_locations_public_id unique (public_id),
  constraint uq_locations_facility_id_id unique (facility_id, id),
  constraint fk_locations_parent foreign key (facility_id, parent_location_id)
    references locations (facility_id, id),
  constraint fk_locations_department foreign key (facility_id, department_id)
    references departments (facility_id, id),
  constraint ck_locations_type check (location_type in ('BUILDING','FLOOR','WARD','ROOM','BED','STORE','OTHER')),
  constraint ck_locations_parent_not_self check (parent_location_id is null or parent_location_id <> id),
  constraint ck_locations_rowver check (row_version >= 1)
);
create unique index if not exists ux_locations_code_active
  on locations (facility_id, lower(code)) where is_active;
create index if not exists ix_locations_parent on locations (facility_id, parent_location_id);
create index if not exists ix_locations_department on locations (facility_id, department_id)
  where department_id is not null;
drop trigger if exists trg_locations_touch on locations;
create trigger trg_locations_touch before update on locations
  for each row execute function touch_row();
grant select, insert, update on locations to bems_app;
insert into schema_version (version, description)
  values ('012', 'locations') on conflict (version) do nothing;