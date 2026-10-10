do $$
declare
  c record; n int := 0; found_name text;
begin
  -- 1. equipment_holds: allow CALIBRATION source
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'equipment_holds'::regclass and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%source_type%' and pg_get_constraintdef(oid) ilike '%CALIBRATION%'
  ) then
    for c in
      select conname, pg_get_constraintdef(oid) as def from pg_constraint
      where conrelid = 'equipment_holds'::regclass and contype = 'c'
        and pg_get_constraintdef(oid) ilike '%source_type%'
        and pg_get_constraintdef(oid) ilike '%MANUAL%'
        and pg_get_constraintdef(oid) not ilike '%work_order_id%'
    loop
      n := n + 1; found_name := c.conname;
    end loop;
    if n <> 1 then
      raise exception 'Expected exactly one source_type check on equipment_holds, found %. Definitions: %', n,
        (select string_agg(conname || ': ' || pg_get_constraintdef(oid), ' | ') from pg_constraint
         where conrelid = 'equipment_holds'::regclass and contype = 'c');
    end if;
    execute format('alter table equipment_holds drop constraint %I', found_name);
    alter table equipment_holds add constraint ck_equipment_holds_source_type
      check (source_type in ('WORK_ORDER','MANUAL','CALIBRATION'));
  end if;
end $$;

alter table equipment_holds add column if not exists calibration_record_id bigint;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'fk_equipment_holds_calibration_record') then
    alter table equipment_holds add constraint fk_equipment_holds_calibration_record
      foreign key (facility_id, calibration_record_id) references calibration_records (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'ck_equipment_holds_calibration_source') then
    alter table equipment_holds add constraint ck_equipment_holds_calibration_source
      check ((source_type = 'CALIBRATION') = (calibration_record_id is not null));
  end if;
end $$;
create index if not exists ix_equipment_holds_calibration_record
  on equipment_holds (facility_id, calibration_record_id) where calibration_record_id is not null;

-- 2. work_orders: calibration source and coverage links
alter table work_orders add column if not exists source_calibration_record_id bigint;
alter table work_orders add column if not exists warranty_id bigint;
alter table work_orders add column if not exists amc_contract_id bigint;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'fk_work_orders_calibration_record') then
    alter table work_orders add constraint fk_work_orders_calibration_record
      foreign key (facility_id, source_calibration_record_id) references calibration_records (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'fk_work_orders_warranty') then
    alter table work_orders add constraint fk_work_orders_warranty
      foreign key (facility_id, warranty_id) references warranties (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'fk_work_orders_amc_contract') then
    alter table work_orders add constraint fk_work_orders_amc_contract
      foreign key (facility_id, amc_contract_id) references amc_contracts (facility_id, id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'ck_work_orders_one_coverage_link') then
    alter table work_orders add constraint ck_work_orders_one_coverage_link
      check (warranty_id is null or amc_contract_id is null);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'ck_work_orders_warranty_source') then
    alter table work_orders add constraint ck_work_orders_warranty_source
      check (warranty_id is null or coverage_source = 'WARRANTY');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'ck_work_orders_amc_source') then
    alter table work_orders add constraint ck_work_orders_amc_source
      check (amc_contract_id is null or coverage_source = 'AMC');
  end if;
end $$;
create index if not exists ix_work_orders_warranty on work_orders (facility_id, warranty_id) where warranty_id is not null;
create index if not exists ix_work_orders_amc on work_orders (facility_id, amc_contract_id) where amc_contract_id is not null;
create index if not exists ix_work_orders_calibration_record
  on work_orders (facility_id, source_calibration_record_id) where source_calibration_record_id is not null;

insert into schema_version (version, description) values ('036', 'phase 5 links: calibration holds, work order coverage')
  on conflict (version) do nothing;