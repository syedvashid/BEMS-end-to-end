create table if not exists equipment_categories (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  parent_category_id bigint,
  code varchar(50) not null,
  name varchar(200) not null,
  description varchar(500),
  default_pm_interval_days integer,
  default_calibration_interval_days integer,
  risk_class varchar(10) not null default 'MEDIUM',
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_categories_public_id unique (public_id),
  constraint uq_equipment_categories_facility_id_id unique (facility_id, id),
  constraint fk_equipment_categories_parent foreign key (facility_id, parent_category_id)
    references equipment_categories (facility_id, id),
  constraint ck_equipment_categories_code check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint ck_equipment_categories_parent_not_self check (parent_category_id is null or parent_category_id <> id),
  constraint ck_equipment_categories_pm check (default_pm_interval_days is null or default_pm_interval_days > 0),
  constraint ck_equipment_categories_cal check (default_calibration_interval_days is null or default_calibration_interval_days > 0),
  constraint ck_equipment_categories_risk check (risk_class in ('LOW','MEDIUM','HIGH')),
  constraint ck_equipment_categories_rowver check (row_version >= 1)
);
create unique index if not exists ux_equipment_categories_code_active
  on equipment_categories (facility_id, lower(code)) where is_active;
create unique index if not exists ux_equipment_categories_name_active
  on equipment_categories (facility_id, lower(name)) where is_active;
create index if not exists ix_equipment_categories_parent
  on equipment_categories (facility_id, parent_category_id);
drop trigger if exists trg_equipment_categories_touch on equipment_categories;
create trigger trg_equipment_categories_touch before update on equipment_categories
  for each row execute function touch_row();
grant select, insert, update on equipment_categories to bems_app;
insert into schema_version (version, description)
  values ('013', 'equipment_categories') on conflict (version) do nothing;