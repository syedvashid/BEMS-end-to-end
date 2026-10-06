create table if not exists equipment_models (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  category_id bigint not null,
  manufacturer_id bigint not null,
  model_name varchar(200) not null,
  model_number varchar(100) not null,
  description varchar(500),
  risk_class varchar(10),
  default_pm_interval_days integer,
  default_calibration_interval_days integer,
  expected_life_years integer,
  cdsco_registration_number varchar(100),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_models_public_id unique (public_id),
  constraint uq_equipment_models_facility_id_id unique (facility_id, id),
  constraint fk_equipment_models_category foreign key (facility_id, category_id)
    references equipment_categories (facility_id, id),
  constraint fk_equipment_models_manufacturer foreign key (facility_id, manufacturer_id)
    references vendors (facility_id, id),
  constraint ck_equipment_models_risk check (risk_class is null or risk_class in ('LOW','MEDIUM','HIGH')),
  constraint ck_equipment_models_pm check (default_pm_interval_days is null or default_pm_interval_days > 0),
  constraint ck_equipment_models_cal check (default_calibration_interval_days is null or default_calibration_interval_days > 0),
  constraint ck_equipment_models_life check (expected_life_years is null or expected_life_years > 0),
  constraint ck_equipment_models_rowver check (row_version >= 1)
);
create unique index if not exists ux_equipment_models_number_active
  on equipment_models (facility_id, manufacturer_id, lower(model_number)) where is_active;
create index if not exists ix_equipment_models_category on equipment_models (facility_id, category_id);
create index if not exists ix_equipment_models_manufacturer on equipment_models (facility_id, manufacturer_id);
drop trigger if exists trg_equipment_models_touch on equipment_models;
create trigger trg_equipment_models_touch before update on equipment_models
  for each row execute function touch_row();
grant select, insert, update on equipment_models to bems_app;
insert into schema_version (version, description)
  values ('016', 'equipment_models') on conflict (version) do nothing;