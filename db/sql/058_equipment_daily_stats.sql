-- Composite-FK target on equipment, added only if no unique (facility_id, id) exists yet
do $$
begin
  if not exists (
    select 1
      from pg_index i
     where i.indrelid = 'equipment'::regclass
       and i.indisunique and i.indpred is null and i.indnatts = 2
       and (select array_agg(a.attname::text order by k.ord)
              from unnest(i.indkey::int2[]) with ordinality k(attnum, ord)
              join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k.attnum)
           = array['facility_id', 'id']
  ) then
    create unique index ux_equipment_facility_id_p10 on equipment (facility_id, id);
  end if;
end $$;

create table if not exists equipment_daily_stats (
  id bigint generated always as identity primary key,
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  stat_date date not null,
  in_service_minutes integer not null default 0,
  downtime_planned_minutes integer not null default 0,
  downtime_unplanned_minutes integer not null default 0,
  available_minutes integer not null default 0,
  used_minutes integer not null default 0,
  allocated_minutes integer not null default 0,
  session_count integer not null default 0,
  breakdown_count integer not null default 0,
  computed_at timestamptz not null default now(),
  constraint fk_eds_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint uq_eds_equipment_date unique (equipment_id, stat_date),
  constraint ck_eds_in_service check (in_service_minutes between 0 and 1440),
  constraint ck_eds_planned check (downtime_planned_minutes between 0 and 1440),
  constraint ck_eds_unplanned check (downtime_unplanned_minutes between 0 and 1440),
  constraint ck_eds_available check (available_minutes between 0 and 1440),
  constraint ck_eds_used check (used_minutes between 0 and 1440),
  constraint ck_eds_allocated check (allocated_minutes between 0 and 1440),
  constraint ck_eds_counts check (session_count >= 0 and breakdown_count >= 0),
  constraint ck_eds_downtime_le_service
    check (downtime_planned_minutes + downtime_unplanned_minutes <= in_service_minutes),
  constraint ck_eds_available_formula
    check (available_minutes = in_service_minutes - downtime_planned_minutes - downtime_unplanned_minutes)
);
create index if not exists ix_eds_facility_date on equipment_daily_stats (facility_id, stat_date);
create index if not exists ix_eds_equipment_date on equipment_daily_stats (equipment_id, stat_date desc);

grant select, insert, update, delete on equipment_daily_stats to bems_app;

insert into schema_version (version, description)
  values ('058', 'equipment_daily_stats') on conflict (version) do nothing;