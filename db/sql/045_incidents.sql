-- 045 incidents. Run as bems_owner.
begin;

-- Composite-FK targets: unique (facility_id, id) where missing (idempotent guard).
do $$
declare t text;
begin
  foreach t in array array['equipment','departments','locations','vendors','equipment_models','work_orders'] loop
    if not exists (
      select 1 from pg_index i
       where i.indrelid = t::regclass and i.indisunique and i.indpred is null and i.indnatts = 2
         and (select array_agg(a.attname::text order by a.attname) from pg_attribute a
               where a.attrelid = i.indrelid and a.attnum = any (i.indkey)) = array['facility_id','id']
    ) then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id');
    end if;
  end loop;
end $$;

create table if not exists equipment_incidents (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  incident_number text not null,
  equipment_id bigint not null,
  incident_type text not null,
  severity text not null,
  occurred_at timestamptz not null,
  reported_by_name text,
  department_id bigint,
  location_id bigint,
  description text not null,
  immediate_action text,
  patient_reference text,
  encounter_reference text,
  patient_affected boolean not null default false,
  staff_affected boolean not null default false,
  status text not null default 'REPORTED',
  investigated_by bigint references users (id),
  root_cause text,
  corrective_action text,
  preventive_action text,
  investigation_notes text,
  reportable_to_regulator boolean not null default false,
  regulator_report_reference text,
  regulator_reported_on date,
  work_order_id bigint,
  closure_notes text,
  closed_at timestamptz,
  closed_by bigint references users (id),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_incidents_public_id unique (public_id),
  constraint uq_equipment_incidents_facility_id unique (facility_id, id),
  constraint uq_equipment_incidents_number unique (facility_id, incident_number),
  constraint ck_equipment_incidents_rowver check (row_version >= 1),
  constraint ck_equipment_incidents_number check (incident_number ~ '^INC-[0-9]{4}-[0-9]{6}$'),
  constraint ck_equipment_incidents_type check (incident_type in ('MALFUNCTION','USE_ERROR','NEAR_MISS','OTHER')),
  constraint ck_equipment_incidents_severity check (severity in ('NO_HARM','MINOR','MODERATE','SEVERE','DEATH')),
  constraint ck_equipment_incidents_status check (status in ('REPORTED','UNDER_INVESTIGATION','ACTION_TAKEN','CLOSED')),
  constraint ck_equipment_incidents_description check (btrim(description) <> ''),
  constraint ck_equipment_incidents_patient_ref
    check (patient_reference is null or patient_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_equipment_incidents_encounter_ref
    check (encounter_reference is null or encounter_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_equipment_incidents_regulator
    check ((regulator_report_reference is null) = (regulator_reported_on is null)
           and (regulator_report_reference is null or btrim(regulator_report_reference) <> '')),
  constraint ck_equipment_incidents_closed
    check (status <> 'CLOSED' or (closed_at is not null and closure_notes is not null and btrim(closure_notes) <> '')),
  constraint fk_equipment_incidents_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_equipment_incidents_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint fk_equipment_incidents_location foreign key (facility_id, location_id) references locations (facility_id, id),
  constraint fk_equipment_incidents_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id)
);
create index if not exists ix_equipment_incidents_status on equipment_incidents (facility_id, status);
create index if not exists ix_equipment_incidents_equipment on equipment_incidents (facility_id, equipment_id);
create index if not exists ix_equipment_incidents_occurred on equipment_incidents (facility_id, occurred_at desc);
drop trigger if exists trg_equipment_incidents_touch on equipment_incidents;
create trigger trg_equipment_incidents_touch before update on equipment_incidents
  for each row execute function touch_row();
grant select, insert, update on equipment_incidents to bems_app;

-- Status machine (global reference table + trigger)
create table if not exists incident_transitions (
  from_status text not null,
  to_status text not null,
  primary key (from_status, to_status),
  constraint ck_incident_transitions_from check (from_status in ('REPORTED','UNDER_INVESTIGATION','ACTION_TAKEN','CLOSED')),
  constraint ck_incident_transitions_to check (to_status in ('REPORTED','UNDER_INVESTIGATION','ACTION_TAKEN','CLOSED'))
);
insert into incident_transitions (from_status, to_status) values
  ('REPORTED','UNDER_INVESTIGATION'), ('REPORTED','CLOSED'),
  ('UNDER_INVESTIGATION','ACTION_TAKEN'), ('UNDER_INVESTIGATION','CLOSED'),
  ('ACTION_TAKEN','CLOSED')
on conflict do nothing;
grant select on incident_transitions to bems_app;

create or replace function enforce_incident_transition() returns trigger
language plpgsql as $$
begin
  if new.status is distinct from old.status
     and not exists (select 1 from incident_transitions t
                      where t.from_status = old.status and t.to_status = new.status) then
    raise exception 'Incident status change % -> % is not allowed', old.status, new.status
      using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists trg_equipment_incidents_status on equipment_incidents;
create trigger trg_equipment_incidents_status before update on equipment_incidents
  for each row execute function enforce_incident_transition();

-- Immutable event log
create table if not exists incident_events (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  incident_id bigint not null,
  event_type text not null,
  from_status text,
  to_status text,
  note text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_incident_events_public_id unique (public_id),
  constraint ck_incident_events_type check (event_type in (
    'CREATED','STATUS_CHANGED','NOTE','INVESTIGATION_UPDATED','QUARANTINE_PLACED','QUARANTINE_RELEASED',
    'WORK_ORDER_LINKED','REGULATOR_REPORTED')),
  constraint fk_incident_events_incident foreign key (facility_id, incident_id) references equipment_incidents (facility_id, id)
);
create index if not exists ix_incident_events_incident on incident_events (incident_id, created_at);
grant select, insert on incident_events to bems_app;

insert into schema_version (version, description) values ('045', 'equipment incidents') on conflict (version) do nothing;
commit;
