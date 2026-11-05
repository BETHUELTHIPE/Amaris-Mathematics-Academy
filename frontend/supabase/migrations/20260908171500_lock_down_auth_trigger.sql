revoke all on function public.handle_new_student_profile() from public;
revoke execute on function public.handle_new_student_profile() from anon, authenticated;
grant execute on function public.handle_new_student_profile() to supabase_auth_admin;

revoke all on function public.set_student_profile_updated_at() from public;
revoke execute on function public.set_student_profile_updated_at() from anon, authenticated;
