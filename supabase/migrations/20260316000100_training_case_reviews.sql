create table if not exists public.training_case_reviews (
  user_id uuid not null,
  review_date date not null,
  mode text not null,
  case_payload jsonb not null,
  review_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, review_date, mode)
);

create index if not exists idx_training_case_reviews_user_date
  on public.training_case_reviews (user_id, review_date desc);