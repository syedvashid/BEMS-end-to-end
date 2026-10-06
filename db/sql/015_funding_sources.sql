create table if not exists funding_sources (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  code varchar(30) not null,
  name varchar(200) not null,
  source_type varchar(20) not null,
  description varchar(500),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_funding_sources_public_id unique (public_id),
  constraint uq_funding_sources_facility_id_id unique (facility_id, id),
  constraint ck_funding_sources_type check (source_type in
    ('OWN_FUNDS','GRANT','DONATION','CSR','GOVERNMENT_SCHEME','LEASE_LOAN','OTHER')),
  constraint ck_funding_sources_rowver check (row_version >= 1)
);
create unique index if not exists ux_funding_sources_code_active
  on funding_sources (facility_id, lower(code)) where is_active;
drop trigger if exists trg_funding_sources_touch on funding_sources;
create trigger trg_funding_sources_touch before update on funding_sources
  for each row execute function touch_row();
grant select, insert, update on funding_sources to bems_app;
insert into schema_version (version, description)
  values ('015', 'funding_sources') on conflict (version) do nothing;