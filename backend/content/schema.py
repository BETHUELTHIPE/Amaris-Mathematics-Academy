from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SupabaseStudentAuthenticationScheme(OpenApiAuthenticationExtension):
    """Describe the bearer token accepted by the student API."""

    target_class = "content.authentication.SupabaseStudentAuthentication"
    name = "SupabaseBearerAuth"

    def get_security_definition(self, auto_schema):
        del auto_schema
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Supabase student access token. Protected staging acceptance requests "
                "may use the repository's GitHub Actions OIDC token when explicitly enabled."
            ),
        }


class SupabaseTutorAuthenticationScheme(OpenApiAuthenticationExtension):
    """Document the restricted bearer token and tutor group requirement."""

    target_class = "content.tutor_views.SupabaseTutorAuthentication"
    name = "SupabaseTutorBearerAuth"

    def get_security_definition(self, auto_schema):
        del auto_schema
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Verified Supabase access token; the corresponding active Django user "
                "must be an approved member of the Tutors group. Student registration "
                "or a GitHub synthetic acceptance identity does not grant tutor access."
            ),
        }
