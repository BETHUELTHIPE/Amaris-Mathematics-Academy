"""Regression tests for the migration-only Render database isolation guard."""

from unittest import TestCase

from amaris_cms.database_guard import validate_migration_database


class MigrationDatabaseIsolationTests(TestCase):
    def _db(self, host: str, user: str) -> dict[str, str]:
        return {"ENGINE": "django.db.backends.postgresql", "HOST": host, "USER": user}

    def test_staging_direct_project_is_accepted(self) -> None:
        self.assertIsNone(
            validate_migration_database(
                self._db("db.atyhhjwwxgzeurnwayay.supabase.co", "postgres"),
                service_name="amaris-mathematics-academy-staging",
                on_render=True,
            )
        )

    def test_staging_pooler_project_is_accepted(self) -> None:
        self.assertIsNone(
            validate_migration_database(
                self._db("aws-1-eu-west-1.pooler.supabase.com", "postgres.atyhhjwwxgzeurnwayay"),
                service_name="amaris-mathematics-academy-staging",
                on_render=True,
            )
        )

    def test_staging_rejects_production_direct_project(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "approved staging Supabase project"):
            validate_migration_database(
                self._db("db.epkcuseloinygkakxxdu.supabase.co", "postgres"),
                service_name="amaris-mathematics-academy-staging",
                on_render=True,
            )

    def test_staging_rejects_production_pooler_project(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "approved staging Supabase project"):
            validate_migration_database(
                self._db("aws-1-us-east-1.pooler.supabase.com", "postgres.epkcuseloinygkakxxdu"),
                service_name="amaris-mathematics-academy-staging",
                on_render=True,
            )

    def test_production_accepts_only_production_project(self) -> None:
        self.assertIsNone(
            validate_migration_database(
                self._db("aws-1-us-east-1.pooler.supabase.com", "postgres.epkcuseloinygkakxxdu"),
                service_name="amaris-production-web",
                on_render=True,
            )
        )
        with self.assertRaisesRegex(RuntimeError, "approved production Supabase project"):
            validate_migration_database(
                self._db("db.atyhhjwwxgzeurnwayay.supabase.co", "postgres"),
                service_name="amaris-production-web",
                on_render=True,
            )

    def test_hosted_unknown_environment_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown Render service"):
            validate_migration_database(
                self._db("db.atyhhjwwxgzeurnwayay.supabase.co", "postgres"),
                service_name="amaris-unknown-backend",
                on_render=True,
            )

    def test_explicit_conflicting_environment_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "conflicts with Render service"):
            validate_migration_database(
                self._db("db.epkcuseloinygkakxxdu.supabase.co", "postgres"),
                service_name="amaris-mathematics-academy-staging",
                deployment_environment="production",
                on_render=True,
            )

    def test_non_postgres_database_is_rejected_on_host(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "requires PostgreSQL"):
            validate_migration_database(
                {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
                deployment_environment="staging",
                on_render=True,
            )

    def test_local_django_migrations_are_not_changed(self) -> None:
        self.assertIsNone(validate_migration_database({"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}))

    def test_error_does_not_expose_credentials(self) -> None:
        secret = "sensitive-unprintable-test-secret"
        with self.assertRaises(RuntimeError) as error:
            validate_migration_database(
                self._db("db.epkcuseloinygkakxxdu.supabase.co", "postgres"),
                service_name="amaris-mathematics-academy-staging",
                on_render=True,
            )
        self.assertNotIn(secret, str(error.exception))
        self.assertNotIn("epkcuseloinygkakxxdu", str(error.exception))
