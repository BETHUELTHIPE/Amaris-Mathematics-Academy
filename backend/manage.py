#!/usr/bin/env python
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    from django.core.management import execute_from_command_line

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        # Render runs pre-deploy migrations before starting the web process.
        # Check the resolved Django connection before touching any schema.
        from django.conf import settings

        from amaris_cms.database_guard import validate_migration_database

        validate_migration_database(
            settings.DATABASES["default"],
            service_name=os.getenv("RENDER_SERVICE_NAME", ""),
            deployment_environment=os.getenv("AMARIS_DEPLOY_ENV", ""),
            on_render=bool(
                os.getenv("RENDER_SERVICE_ID")
                or os.getenv("RENDER_SERVICE_NAME")
                or os.getenv("RENDER", "").lower() == "true"
            ),
        )

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
