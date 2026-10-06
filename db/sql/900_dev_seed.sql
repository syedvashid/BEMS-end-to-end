-- DEV ONLY. Fictional data. Never apply to production.
do $$ begin
    if current_database() !~ '(dev|test)' then
        raise exception 'Refusing to apply dev seed to database %', current_database();
    end if;
end $$;

insert into facilities (code, name, facility_type, city, state, pin_code) values
    ('MAIN', 'Main Hospital', 'HOSPITAL', 'Kanpur', 'Uttar Pradesh', '208001'),
    ('CITY', 'City Clinic',   'CLINIC',   'Kanpur', 'Uttar Pradesh', '208002')
on conflict (lower(code)) where is_active do nothing;

insert into users (username, full_name, email, designation) values
    ('dev_sysadmin',        'Dev System Admin',     'sysadmin@example.test',        'System Administrator'),
    ('dev_biomed_admin',    'Dev Biomed Admin',     'biomed.admin@example.test',    'Biomedical Admin'),
    ('dev_biomed_engineer', 'Dev Biomed Engineer',  'biomed.eng@example.test',      'Biomedical Engineer'),
    ('dev_store_officer',   'Dev Store Officer',    'store@example.test',           'Store Officer'),
    ('dev_department_user', 'Dev Department User',  'dept@example.test',            'Ward In-charge'),
    ('dev_finance',         'Dev Finance User',     'finance@example.test',         'Accounts Officer'),
    ('dev_auditor',         'Dev Auditor',          'auditor@example.test',         'Internal Auditor')
on conflict (username) where is_active do nothing;

-- sysadmin: BOTH facilities; dept user + auditor: CITY only; the rest: MAIN only
insert into user_facility_roles (user_id, facility_id, role_id)
select u.id, f.id, r.id
  from (values
    ('dev_sysadmin',        'MAIN', 'SYSTEM_ADMIN'),
    ('dev_sysadmin',        'CITY', 'SYSTEM_ADMIN'),
    ('dev_biomed_admin',    'MAIN', 'BIOMED_ADMIN'),
    ('dev_biomed_engineer', 'MAIN', 'BIOMED_ENGINEER'),
    ('dev_store_officer',   'MAIN', 'STORE_OFFICER'),
    ('dev_department_user', 'CITY', 'DEPARTMENT_USER'),
    ('dev_finance',         'MAIN', 'FINANCE'),
    ('dev_auditor',         'CITY', 'AUDITOR')
  ) m (uname, fcode, rcode)
  join users u      on u.username = m.uname and u.is_active
  join facilities f on lower(f.code) = lower(m.fcode) and f.is_active
  join roles r      on r.code = m.rcode and r.is_active
 where not exists (
    select 1 from user_facility_roles x
     where x.user_id = u.id and x.facility_id = f.id and x.role_id = r.id and x.is_active);

insert into schema_version (version, description)
values ('900', 'DEV ONLY seed') on conflict (version) do nothing;