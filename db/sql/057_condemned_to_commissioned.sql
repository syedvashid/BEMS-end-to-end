-- 057 allow revoking a condemnation: CONDEMNED -> COMMISSIONED (run as bems_owner)
-- ASSUMES the columns are named from_stage / to_stage. Check first with:  \d equipment_lifecycle_transitions
begin;
insert into equipment_lifecycle_transitions (from_stage, to_stage)
values ('CONDEMNED', 'COMMISSIONED')
on conflict do nothing;
insert into schema_version (version, description)
  values ('057', 'lifecycle transition condemned to commissioned') on conflict (version) do nothing;
commit;
