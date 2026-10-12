-- 048 equipment_holds: INCIDENT and RECALL sources. Run as bems_owner AFTER 045 and 046.
begin;

alter table equipment_holds add column if not exists incident_id bigint;
alter table equipment_holds add column if not exists recall_unit_id bigint;

do $$
declare r record;
begin
  -- Find the source_type enumeration check by its definition (not by name), drop it, add the wider one.
  for r in select conname from pg_constraint
            where conrelid = 'equipment_holds'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) like '%source_type = ANY%'
  loop
    execute format('alter table equipment_holds drop constraint %I', r.conname);
  end loop;
  alter table equipment_holds add constraint ck_equipment_holds_source_type
    check (source_type in ('WORK_ORDER','MANUAL','CALIBRATION','INCIDENT','RECALL'));

  if not exists (select 1 from pg_constraint where conrelid = 'equipment_holds'::regclass
                  and conname = 'fk_equipment_holds_incident') then
    alter table equipment_holds add constraint fk_equipment_holds_incident
      foreign key (facility_id, incident_id) references equipment_incidents (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conrelid = 'equipment_holds'::regclass
                  and conname = 'fk_equipment_holds_recall_unit') then
    alter table equipment_holds add constraint fk_equipment_holds_recall_unit
      foreign key (facility_id, recall_unit_id) references recall_affected_units (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conrelid = 'equipment_holds'::regclass
                  and conname = 'ck_equipment_holds_incident_source') then
    alter table equipment_holds add constraint ck_equipment_holds_incident_source
      check ((source_type = 'INCIDENT') = (incident_id is not null));
  end if;
  if not exists (select 1 from pg_constraint where conrelid = 'equipment_holds'::regclass
                  and conname = 'ck_equipment_holds_recall_source') then
    alter table equipment_holds add constraint ck_equipment_holds_recall_source
      check ((source_type = 'RECALL') = (recall_unit_id is not null));
  end if;
end $$;

create unique index if not exists ux_equipment_holds_incident_open
  on equipment_holds (incident_id) where released_at is null and incident_id is not null;
create unique index if not exists ux_equipment_holds_recall_unit_open
  on equipment_holds (recall_unit_id) where released_at is null and recall_unit_id is not null;

insert into schema_version (version, description) values ('048', 'equipment holds: incident and recall sources') on conflict (version) do nothing;
commit;
