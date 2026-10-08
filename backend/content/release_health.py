"""OIDC-protected staging schema gate for a release candidate.

This endpoint is intentionally not a public health check. It provides no
database connection details or migration names and never applies migrations.
"""

import os

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication


class StagingSchemaReadinessView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        enabled = os.getenv("ACCEPTANCE_GITHUB_OIDC_ENABLED", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        auth = request.auth if isinstance(request.auth, dict) else {}
        if not enabled or auth.get("provider") != "github-actions-oidc":
            raise PermissionDenied("Staging schema checks require the configured GitHub Actions identity.")

        if connection.vendor != "postgresql":
            return Response(
                {"status": "unavailable", "database": "invalid", "pending_migrations": None},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("PostgreSQL connectivity check failed")
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception:
            # Do not expose database hosts, SQL, connection errors, or migration names.
            return Response(
                {"status": "unavailable", "database": "postgresql", "pending_migrations": None},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        count = len(pending)
        return Response(
            {
                "status": "ready" if count == 0 else "pending",
                "database": "postgresql",
                "pending_migrations": count,
            },
            status=status.HTTP_200_OK if count == 0 else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
