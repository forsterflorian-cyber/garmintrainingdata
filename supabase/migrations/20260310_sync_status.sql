create table if not exists public.sync_status (
  user_id uuid primary key,
  sync_state text not null default 'never_synced',
  sync_mode text,
  status_reason text,
  last_successful_sync_at timestamptz,
  last_attempted_sync_at timestamptz,
  last_started_sync_at timestamptz,
  last_finished_sync_at timestamptz,
  last_error_category text,
  last_error_code text,
  last_error_message text,
  cooldown_until timestamptz,
  lock_token text,
  lock_acquired_at timestamptz,
  lock_expires_at timestamptz,
  lock_version bigint not null default 0,
  last_synced_day date,
  missing_days_count integer not null default 0,
  stale_score integer not null default 0,
  auto_sync_enabled boolean not null default true,
  backfill_recommended boolean not null default false,
  baseline_rebuild_recommended boolean not null default false,
  consecutive_failure_count integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.sync_runs (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  mode text not null,
  trigger_source text not null,
  started_at timestamptz not null default timezone('utc', now()),
  finished_at timestamptz,
  status text not null default 'started',
  records_imported integer not null default 0,
  days_synced integer not null default 0,
  error_code text,
  error_message text
);

create index if not exists sync_runs_user_started_idx on public.sync_runs (user_id, started_at desc);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'sync_status_sync_state_check'
  ) then
    alter table public.sync_status
      add constraint sync_status_sync_state_check
      check (
        sync_state in (
          'never_synced',
          'fresh',
          'stale',
          'syncing',
          'backfilling',
          'success',
          'partial_success',
          'error',
          'blocked'
        )
      );
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'sync_status_sync_mode_check'
  ) then
    alter table public.sync_status
      add constraint sync_status_sync_mode_check
      check (
        sync_mode is null or sync_mode in ('update', 'backfill', 'baseline_rebuild')
      );
  end if;
end
$$;
