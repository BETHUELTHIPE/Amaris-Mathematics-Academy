-- Dedicated staging project only. Django uses the postgres server role.
-- Browser API roles must reach application data through Django's permissions.
DO $$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT schemaname, tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename ~ '^(auth_|django_|content_)'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', item.schemaname, item.tablename);
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM PUBLIC, anon, authenticated', item.schemaname, item.tablename);
  END LOOP;
  FOR item IN
    SELECT sequence_schema, sequence_name FROM information_schema.sequences
    WHERE sequence_schema = 'public' AND sequence_name ~ '^(auth_|django_|content_)'
  LOOP
    EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %I.%I FROM PUBLIC, anon, authenticated', item.sequence_schema, item.sequence_name);
  END LOOP;
END $$;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC, anon, authenticated;
