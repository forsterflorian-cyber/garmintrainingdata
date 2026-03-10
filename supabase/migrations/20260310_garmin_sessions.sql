alter table public.user_garmin_accounts
  add column if not exists garmin_session_enc text,
  add column if not exists garmin_session_version bigint not null default 0,
  add column if not exists garmin_session_updated_at timestamptz;

alter table public.user_garmin_accounts
  alter column garmin_session_version set default 0;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_garmin_accounts_garmin_session_version_nonnegative'
  ) then
    alter table public.user_garmin_accounts
      add constraint user_garmin_accounts_garmin_session_version_nonnegative
      check (garmin_session_version >= 0);
  end if;
end
$$;
