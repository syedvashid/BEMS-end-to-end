-- 020: Phase 4 prerequisites. Run as bems_owner.
-- Adds unique (facility_id, id) where missing (needed by composite FKs) and asset_tag_counters.
do $$
declare
  t text; fid smallint; iid smallint; has_it boolean;
begin
  foreach t in array array['departments','locations','vendors','equipment_models','funding_sources'] loop
    select attnum into fid from pg_attribute where attrelid = t::regclass and attname = 'facility_id' and not attisdropped;
    select attnum into iid from pg_attribute where attrelid = t::regclass and attname = 'id' and not attisdropped;
    select exists (
      select 1 from pg_constraint
       where conrelid = t::regclass and contype in ('u','p') and conkey = array[fid, iid]
    ) into has_it;
    if not has_it then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id_id');
    end if;
  end loop;
end $$;

create table if not exists asset_tag_counters (
  facility_id bigint not null references facilities (id),
  year integer not null,
  last_value integer not null default 0,
  primary key (facility_id, year),
  constraint ck_asset_tag_counters_year check (year between 2000 and 9999),
  constraint ck_asset_tag_counters_value check (last_value between 0 and 999999)
);
grant select, insert, update on asset_tag_counters to bems_app;

insert into schema_version (version, description)
  values ('020', 'equipment prerequisites: facility_id+id uniques, asset_tag_counters') on conflict (version) do nothing;
