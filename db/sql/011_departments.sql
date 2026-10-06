create table if not exists departments (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  code varchar(30) not null,
  name varchar(200) not null,
  department_type varchar(20) not null,
  description varchar(500),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_departments_public_id unique (public_id),
  constraint uq_departments_facility_id_id unique (facility_id, id),
  constraint ck_departments_type check (department_type in ('CLINICAL','DIAGNOSTIC','SUPPORT','ADMINISTRATIVE')),
  constraint ck_departments_rowver check (row_version >= 1)
);
create unique index if not exists ux_departments_code_active
  on departments (facility_id, lower(code)) where is_active;
create unique index if not exists ux_departments_name_active
  on departments (facility_id, lower(name)) where is_active;
drop trigger if exists trg_departments_touch on departments;
create trigger trg_departments_touch before update on departments
  for each row execute function touch_row();
grant select, insert, update on departments to bems_app;
insert into schema_version (version, description)
  values ('011', 'departments') on conflict (version) do nothing;