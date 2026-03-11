alter table public.user_garmin_accounts
  add column if not exists garmin_account_key text,
  add column if not exists garmin_account_key_source text,
  add column if not exists garmin_login_key text;

create unique index if not exists user_garmin_accounts_garmin_account_key_unique
  on public.user_garmin_accounts (garmin_account_key)
  where garmin_account_key is not null;

create unique index if not exists user_garmin_accounts_garmin_login_key_unique
  on public.user_garmin_accounts (garmin_login_key)
  where garmin_login_key is not null;
