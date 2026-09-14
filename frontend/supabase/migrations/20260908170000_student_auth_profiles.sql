create table if not exists public.student_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  first_name text not null,
  last_name text not null,
  mobile text not null,
  province text not null,
  institution text not null,
  academic_level text not null,
  terms_accepted_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint student_profiles_mobile_length check (char_length(mobile) between 7 and 24),
  constraint student_profiles_first_name_length check (char_length(first_name) between 2 and 80),
  constraint student_profiles_last_name_length check (char_length(last_name) between 2 and 80)
);

alter table public.student_profiles enable row level security;

revoke all on table public.student_profiles from anon;
grant select, insert, update on table public.student_profiles to authenticated;

drop policy if exists "Students can read their own profile" on public.student_profiles;
create policy "Students can read their own profile"
on public.student_profiles
for select
to authenticated
using ((select auth.uid()) = id);

drop policy if exists "Students can insert their own profile" on public.student_profiles;
create policy "Students can insert their own profile"
on public.student_profiles
for insert
to authenticated
with check ((select auth.uid()) = id);

drop policy if exists "Students can update their own profile" on public.student_profiles;
create policy "Students can update their own profile"
on public.student_profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

create or replace function public.handle_new_student_profile()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.student_profiles (
    id,
    email,
    first_name,
    last_name,
    mobile,
    province,
    institution,
    academic_level,
    terms_accepted_at
  ) values (
    new.id,
    lower(coalesce(new.email, '')),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'first_name'), ''), 'Student'),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'last_name'), ''), 'Learner'),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'mobile'), ''), 'Not provided'),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'province'), ''), 'Not provided'),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'institution'), ''), 'Not provided'),
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'academic_level'), ''), 'Not provided'),
    coalesce((new.raw_user_meta_data ->> 'terms_accepted_at')::timestamptz, timezone('utc', now()))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

revoke all on function public.handle_new_student_profile() from public;
revoke execute on function public.handle_new_student_profile() from anon, authenticated;
grant execute on function public.handle_new_student_profile() to supabase_auth_admin;

drop trigger if exists on_auth_user_created_student_profile on auth.users;
create trigger on_auth_user_created_student_profile
  after insert on auth.users
  for each row execute procedure public.handle_new_student_profile();

create or replace function public.set_student_profile_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

revoke all on function public.set_student_profile_updated_at() from public;
revoke execute on function public.set_student_profile_updated_at() from anon, authenticated;

drop trigger if exists set_student_profile_updated_at on public.student_profiles;
create trigger set_student_profile_updated_at
  before update on public.student_profiles
  for each row execute procedure public.set_student_profile_updated_at();
