-- 050 finance settings and depreciation policies (run as bems_owner)
begin;

-- Idempotent guard: unique (facility_id, id) on tables referenced later by composite FKs.
do $$
declare t text;
begin
  foreach t in array array['equipment','equipment_categories','vendors','physical_verification_items'] loop
    if not exists (
      select 1 from pg_index i
       where i.indrelid = t::regclass and i.indisunique and i.indpred is null and i.indexprs is null
         and i.indnkeyatts = 2
         and (select array_agg(a.attname::text order by k.ord)
                from unnest(i.indkey::int2[]) with ordinality as k(attnum, ord)
                join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k.attnum)
             = array['facility_id','id']
    ) then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id_id');
    end if;
  end loop;
end $$;

create table if not exists finance_settings (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  maintenance_cost_threshold_percent numeric(6,2) not null default 60,
  committee_required_above_book_value numeric(14,2),
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_finance_settings_public_id unique (public_id),
  constraint ck_finance_settings_rowver check (row_version >= 1),
  constraint ck_finance_settings_threshold check (maintenance_cost_threshold_percent > 0),
  constraint ck_finance_settings_committee check (committee_required_above_book_value is null or committee_required_above_book_value >= 0)
);
create unique index if not exists ux_finance_settings_facility_active
  on finance_settings (facility_id) where is_active;
drop trigger if exists trg_finance_settings_touch on finance_settings;
create trigger trg_finance_settings_touch before update on finance_settings
  for each row execute function touch_row();
grant select, insert, update on finance_settings to bems_app;

create table if not exists depreciation_policies (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  category_id bigint,
  equipment_id bigint,
  method text not null,
  useful_life_years numeric(5,2),
  rate_percent numeric(6,3),
  salvage_percent numeric(5,2) not null default 5,
  start_rule text not null default 'COMMISSIONING_DATE',
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_depreciation_policies_public_id unique (public_id),
  constraint uq_depreciation_policies_facility_id_id unique (facility_id, id),
  constraint ck_depreciation_policies_rowver check (row_version >= 1),
  constraint fk_depreciation_policies_category foreign key (facility_id, category_id)
    references equipment_categories (facility_id, id),
  constraint fk_depreciation_policies_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint ck_depreciation_policies_one_scope check ((category_id is not null) <> (equipment_id is not null)),
  constraint ck_depreciation_policies_method check (method in ('STRAIGHT_LINE','WRITTEN_DOWN_VALUE')),
  constraint ck_depreciation_policies_life check (useful_life_years is null or useful_life_years > 0),
  constraint ck_depreciation_policies_rate check (rate_percent is null or (rate_percent > 0 and rate_percent <= 100)),
  constraint ck_depreciation_policies_method_inputs check (
    (method = 'STRAIGHT_LINE' and useful_life_years is not null)
    or (method = 'WRITTEN_DOWN_VALUE' and rate_percent is not null)),
  constraint ck_depreciation_policies_salvage check (salvage_percent between 0 and 100),
  constraint ck_depreciation_policies_start_rule check (start_rule in ('COMMISSIONING_DATE','INVOICE_DATE'))
);
create unique index if not exists ux_depreciation_policies_category_active
  on depreciation_policies (facility_id, category_id) where is_active and category_id is not null;
create unique index if not exists ux_depreciation_policies_equipment_active
  on depreciation_policies (facility_id, equipment_id) where is_active and equipment_id is not null;
drop trigger if exists trg_depreciation_policies_touch on depreciation_policies;
create trigger trg_depreciation_policies_touch before update on depreciation_policies
  for each row execute function touch_row();
grant select, insert, update on depreciation_policies to bems_app;

insert into schema_version (version, description)
  values ('050', 'finance settings and depreciation policies') on conflict (version) do nothing;
commit;
