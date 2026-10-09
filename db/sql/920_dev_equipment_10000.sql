-- 920 (DEV ONLY, not applied automatically): 10,000 equipment rows for facility MAIN to time the list endpoint.
-- Needs at least one active equipment model, department and location in MAIN. Run as bems_owner.
do $$
declare
  n constant int := 10000;
  f bigint; yr int; end_val int; start_val int;
  models bigint[]; locs bigint[]; depts bigint[];
begin
  select id into f from facilities where code = 'MAIN';
  select array_agg(id) into models from equipment_models where facility_id = f and is_active;
  select array_agg(id) into locs from locations where facility_id = f and is_active;
  select array_agg(id) into depts from departments where facility_id = f and is_active;
  if f is null or models is null or locs is null or depts is null then
    raise exception 'Create at least one equipment model, location and department in MAIN first.';
  end if;
  yr := extract(year from (now() at time zone 'Asia/Kolkata'))::int;

  insert into asset_tag_counters (facility_id, year, last_value) values (f, yr, n)
  on conflict (facility_id, year) do update set last_value = asset_tag_counters.last_value + excluded.last_value
  returning last_value into end_val;
  start_val := end_val - n;

  insert into equipment (facility_id, asset_tag, qr_code_value, equipment_model_id, name, serial_number,
                         lifecycle_stage, operational_state, owning_department_id, current_location_id,
                         criticality, is_legacy_entry, purchase_cost, invoice_date)
  select f,
         'EQ-' || yr || '-' || lpad((start_val + g)::text, 6, '0'),
         'BEMS-' || upper(substr(md5(random()::text || g::text || clock_timestamp()::text), 1, 12)),
         models[1 + (g % array_length(models, 1))],
         'Dev equipment ' || g,
         'DEVSN-' || (start_val + g),
         case when g % 10 = 0 then 'RECEIVED' else 'COMMISSIONED' end,
         case when g % 10 = 0 then null when g % 7 = 0 then 'UNDER_MAINTENANCE' when g % 11 = 0 then 'OUT_OF_SERVICE' else 'IN_SERVICE' end,
         case when g % 10 = 0 then null else depts[1 + (g % array_length(depts, 1))] end,
         case when g % 10 = 0 then null else locs[1 + (g % array_length(locs, 1))] end,
         (array['LOW','MEDIUM','HIGH','CRITICAL'])[1 + (g % 4)],
         g % 10 <> 0,
         (10000 + (g % 500) * 1000)::numeric(14,2),
         current_date - (g % 1500)
  from generate_series(1, n) g;
end $$;
