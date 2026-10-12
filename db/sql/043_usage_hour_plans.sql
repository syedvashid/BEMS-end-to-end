begin;

-- 1. frequency_type: find the existing CHECK by its definition, drop it, add the wider one
do $$
declare c record;
begin
  for c in
    select conname from pg_constraint
     where conrelid = 'maintenance_plans'::regclass and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%frequency_type%'
       and conname not in ('ck_maintenance_plans_freq_type', 'ck_maintenance_plans_next_due')
  loop
    raise notice 'dropping check % on maintenance_plans', c.conname;
    execute format('alter table maintenance_plans drop constraint %I', c.conname);
  end loop;
end $$;

alter table maintenance_plans drop constraint if exists ck_maintenance_plans_freq_type;
alter table maintenance_plans add constraint ck_maintenance_plans_freq_type
  check (frequency_type in ('DAYS', 'MONTHS', 'USAGE_HOURS'));

-- 2. new columns
alter table maintenance_plans add column if not exists last_performed_usage_hours numeric(12,2);
alter table maintenance_plans add column if not exists lead_usage_hours numeric(12,2) not null default 0;
alter table maintenance_plans drop constraint if exists ck_maintenance_plans_lead_usage;
alter table maintenance_plans add constraint ck_maintenance_plans_lead_usage check (lead_usage_hours >= 0);
alter table maintenance_plans drop constraint if exists ck_maintenance_plans_last_usage;
alter table maintenance_plans add constraint ck_maintenance_plans_last_usage
  check (last_performed_usage_hours is null or last_performed_usage_hours >= 0);

-- 3. next_due_date: nullable, and null exactly for usage-hour plans
alter table maintenance_plans alter column next_due_date drop not null;
do $$
declare c record;
begin
  for c in
    select conname from pg_constraint
     where conrelid = 'maintenance_plans'::regclass and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%next_due_date%'
       and conname <> 'ck_maintenance_plans_next_due'
  loop
    raise notice 'dropping check % on maintenance_plans', c.conname;
    execute format('alter table maintenance_plans drop constraint %I', c.conname);
  end loop;
end $$;
alter table maintenance_plans drop constraint if exists ck_maintenance_plans_next_due;
alter table maintenance_plans add constraint ck_maintenance_plans_next_due
  check ((frequency_type = 'USAGE_HOURS') = (next_due_date is null));

insert into schema_version (version, description)
  values ('043', 'usage-hour maintenance plans') on conflict (version) do nothing;
commit;