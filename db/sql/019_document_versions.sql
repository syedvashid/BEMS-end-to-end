create table if not exists document_versions (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  document_id bigint not null,
  version_no integer not null,
  original_filename text not null,
  storage_key text not null,
  content_type text not null,
  size_bytes bigint not null,
  sha256 text not null,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_document_versions_public_id unique (public_id),
  constraint uq_document_versions_storage_key unique (storage_key),
  constraint uq_document_versions_doc_ver unique (document_id, version_no),
  constraint fk_document_versions_document foreign key (facility_id, document_id)
    references documents (facility_id, id),
  constraint ck_document_versions_ver check (version_no >= 1),
  constraint ck_document_versions_filename check (char_length(original_filename) between 1 and 255),
  constraint ck_document_versions_key check (storage_key ~ '^[0-9a-f-]{36}/[0-9]{4}/[0-9a-f-]{36}$'),
  constraint ck_document_versions_ctype check (content_type in (
    'application/pdf','image/jpeg','image/png',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')),
  constraint ck_document_versions_size check (size_bytes > 0),
  constraint ck_document_versions_sha check (sha256 ~ '^[0-9a-f]{64}$')
);
create index if not exists ix_document_versions_document on document_versions (facility_id, document_id);
-- immutable: select and insert only, no update/delete, no touch trigger
grant select, insert on document_versions to bems_app;
insert into schema_version (version, description)
  values ('019', 'document_versions') on conflict (version) do nothing;