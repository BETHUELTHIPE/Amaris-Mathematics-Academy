-- Source-of-truth for the live private student document bucket.
-- The live policies were applied directly to Supabase project epkcuseloinygkakxxdu.
-- Paths are: <auth.uid()>/<category>/<filename>.

drop policy if exists "Amaris students can read own files" on storage.objects;
drop policy if exists "Amaris students can upload own files" on storage.objects;
drop policy if exists "Amaris students can update own files" on storage.objects;
drop policy if exists "Amaris students can delete own files" on storage.objects;

create policy "Amaris students can read own files"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'Amaris Mathematics Academy'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy "Amaris students can upload own files"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'Amaris Mathematics Academy'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy "Amaris students can update own files"
on storage.objects
for update
to authenticated
using (
  bucket_id = 'Amaris Mathematics Academy'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
)
with check (
  bucket_id = 'Amaris Mathematics Academy'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy "Amaris students can delete own files"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'Amaris Mathematics Academy'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);
