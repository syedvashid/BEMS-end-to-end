create table if not exists equipment_licences (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  licence_type text not null,
  licence_number text,
  issuing_authority text,
  issue_date date not null,
  expiry_date date not null,
  renewed_from_licence_id bigint,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_licences_public_id unique (public_id),
  constraint uq_equipment_licences_facility_id unique (facility_id, id),
  constraint ck_equipment_licences_rowver check (row_version >= 1),
  constraint ck_equipment_licences_type check (licence_type in
    ('AERB_LICENCE','AERB_QA_CERTIFICATE','PRESSURE_VESSEL_INSPECTION','ELECTRICAL_SAFETY_TEST','OTHER')),
  constraint ck_equipment_licences_dates check (expiry_date >= issue_date),
  constraint ck_equipment_licences_not_self check (renewed_from_licence_id is null or renewed_from_licence_id <> id),
  constraint fk_equipment_licences_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_equipment_licences_renewed foreign key (facility_id, renewed_from_licence_id)
    references equipment_licences (facility_id, id)
);
create index if not exists ix_equipment_licences_expiry on equipment_licences (facility_id, expiry_date);
create index if not exists ix_equipment_licences_equipment on equipment_licences (facility_id, equipment_id);
drop trigger if exists trg_equipment_licences_touch on equipment_licences;
create trigger trg_equipment_licences_touch before update on equipment_licences
  for each row execute function touch_row();
grant select, insert, update on equipment_licences to bems_app;

insert into schema_version (version, description) values ('035', 'equipment licences')
  on conflict (version) do nothing;