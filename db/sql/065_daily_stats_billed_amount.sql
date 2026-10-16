-- 065: billed amount in the Phase 10 daily statistics (run as bems_owner)
alter table equipment_daily_stats add column if not exists billed_amount numeric(14,2) not null default 0;

insert into schema_version (version, description)
  values ('065', 'equipment_daily_stats.billed_amount') on conflict (version) do nothing;
