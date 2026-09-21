import os
import secrets
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_render_secret_env_files() -> None:
    """Load Render secret files without overriding explicit environment variables."""
    candidates = [
        Path("/etc/secrets/.env"),
        Path("/etc/secrets/env"),
        BASE_DIR / ".env",
        BASE_DIR.parent / ".env",
    ]
    secret_dir = Path("/etc/secrets")
    if secret_dir.is_dir():
        candidates.extend(sorted(secret_dir.glob(".env*")))
        candidates.extend(sorted(secret_dir.glob("*.env")))

        expected_markers = (
            "OPENAI_API_KEY=",
            "OPENAI_KEY=",
            "OPENAI_APIKEY=",
            "EMAIL_HOST_USER=",
            "EMAIL_HOST_PASSWORD=",
            "GMAIL_USER=",
            "GMAIL_EMAIL=",
            "GMAIL_APP_PASSWORD=",
            "DEFAULT_FROM_EMAIL=",
        )
        for secret_file in sorted(secret_dir.iterdir()):
            if not secret_file.is_file() or secret_file in candidates:
                continue
            try:
                preview = secret_file.read_text(encoding="utf-8", errors="ignore")[:8192]
            except OSError:
                continue
            if any(marker in preview for marker in expected_markers):
                candidates.append(secret_file)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen or not candidate.is_file():
            continue
        seen.add(resolved)
        load_dotenv(candidate, override=False)


_load_render_secret_env_files()


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SIGNING_KEY") or os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY and not DEBUG:
    raise RuntimeError(
        "DJANGO_SIGNING_KEY or DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false."
    )
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(64)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_prometheus",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "storages",
    "content",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "amaris_cms.middleware.CorrelationReferenceMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "amaris_cms.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "amaris_cms.wsgi.application"
ASGI_APPLICATION = "amaris_cms.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL and not DEBUG:
    raise RuntimeError(
        "DATABASE_URL must be set when DJANGO_DEBUG is false; "
        "refusing to fall back to ephemeral SQLite."
    )

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.getenv("DATABASE_CONN_MAX_AGE", "600")),
        conn_health_checks=True,
        ssl_require=env_bool("DATABASE_SSL_REQUIRED", False),
    )
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        {
            "connect_timeout": int(os.getenv("DATABASE_CONNECT_TIMEOUT", "5")),
            "options": " ".join(
                [
                    f"-c statement_timeout={int(os.getenv('DATABASE_STATEMENT_TIMEOUT_MS', '30000'))}",
                    (
                        "-c idle_in_transaction_session_timeout="
                        f"{int(os.getenv('DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS', '30000'))}"
                    ),
                ]
            ),
        }
    )

CACHES = {
    "default": {
        "BACKEND": "amaris_cms.cache.ResilientRedisCache",
        "LOCATION": os.getenv("DJANGO_CACHE_URL", "redis://redis_cache:6379/0"),
        "TIMEOUT": int(os.getenv("DJANGO_CACHE_DEFAULT_TIMEOUT", "300")),
        "KEY_PREFIX": os.getenv("DJANGO_CACHE_KEY_PREFIX", "amaris"),
        "OPTIONS": {
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "max_connections": int(os.getenv("DJANGO_CACHE_MAX_CONNECTIONS", "30")),
        },
    },
    "public_content": {
        "BACKEND": "amaris_cms.cache.ResilientRedisCache",
        "LOCATION": os.getenv("DJANGO_PUBLIC_CACHE_URL", "redis://redis_cache:6379/1"),
        "TIMEOUT": int(os.getenv("DJANGO_CACHE_DEFAULT_TIMEOUT", "300")),
        "KEY_PREFIX": os.getenv("DJANGO_PUBLIC_CACHE_KEY_PREFIX", "amaris-public"),
        "OPTIONS": {
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "max_connections": int(os.getenv("DJANGO_CACHE_MAX_CONNECTIONS", "30")),
        },
    },
}
PUBLIC_CONTENT_CACHE_SECONDS = int(os.getenv("PUBLIC_CONTENT_CACHE_SECONDS", "300"))
SITE_BOOTSTRAP_CACHE_SECONDS = int(os.getenv("SITE_BOOTSTRAP_CACHE_SECONDS", "60"))
PUBLIC_SITE_URL = os.getenv(
    "PUBLIC_SITE_URL",
    "https://amaris-mathematics-academy-live-students.onrender.com",
).rstrip("/")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_AUTH_TIMEOUT_SECONDS = float(os.getenv("SUPABASE_AUTH_TIMEOUT_SECONDS", "4"))
SUPABASE_AUTH_CACHE_SECONDS = int(os.getenv("SUPABASE_AUTH_CACHE_SECONDS", "15"))

ACCEPTANCE_GITHUB_OIDC_ENABLED = env_bool("ACCEPTANCE_GITHUB_OIDC_ENABLED", False)
ACCEPTANCE_GITHUB_AUDIENCE = os.getenv("ACCEPTANCE_GITHUB_AUDIENCE", "amaris-staging")
ACCEPTANCE_GITHUB_REPOSITORY = os.getenv(
    "ACCEPTANCE_GITHUB_REPOSITORY",
    "BETHUELTHIPE/Amaris-Mathematics-Academy",
)
ACCEPTANCE_GITHUB_ENVIRONMENT = os.getenv("ACCEPTANCE_GITHUB_ENVIRONMENT", "staging")
ACCEPTANCE_GITHUB_REF = os.getenv("ACCEPTANCE_GITHUB_REF", "refs/heads/main")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
if AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "region_name": os.getenv("AWS_S3_REGION_NAME", "af-south-1"),
                "default_acl": None,
                "querystring_auth": True,
                "file_overwrite": False,
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/hour", "user": "1000/hour", "enquiries": "5/hour"},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Amaris Mathematics Academy Content API",
    "DESCRIPTION": "Published website, course and learning-content API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
)
CORS_ALLOW_CREDENTIALS = False

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "500"))
CELERY_WORKER_MAX_MEMORY_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB", "350000"))
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_BROKER_POOL_LIMIT = int(os.getenv("CELERY_BROKER_POOL_LIMIT", "10"))
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES_SECONDS", "86400"))
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_PUBLISH_RETRY = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 5,
    "interval_start": 0,
    "interval_step": 1,
    "interval_max": 5,
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
    "socket_connect_timeout": 5,
    "socket_timeout": 10,
    "retry_on_timeout": True,
    "max_retries": 6,
}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "retry_policy": {
        "timeout": 5.0,
        "max_retries": 6,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 10,
    }
}
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_TASK_TIME_LIMIT = 30 * 60
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER") or os.getenv("GMAIL_USER") or os.getenv("GMAIL_EMAIL", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT_SECONDS", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Amaris Mathematics Academy <no-reply@example.invalid>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

AI_ENQUIRY_AUTOREPLY_ENABLED = env_bool("AI_ENQUIRY_AUTOREPLY_ENABLED", True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or os.getenv("OPENAI_APIKEY", "")
OPENAI_ENQUIRY_MODEL = os.getenv("OPENAI_ENQUIRY_MODEL", "gpt-5.6-luna")
OPENAI_ENQUIRY_TIMEOUT_SECONDS = float(os.getenv("OPENAI_ENQUIRY_TIMEOUT_SECONDS", "10"))

CELERY_BEAT_SCHEDULE = {
    "publish-scheduled-content": {
        "task": "content.tasks.publish_scheduled_content",
        "schedule": 60.0,
    },
    "reconcile-verified-payments": {
        "task": "content.tasks.reconcile_payments",
        "schedule": 300.0,
    },
    "deliver-transactional-email": {
        "task": "content.tasks.deliver_transactional_email",
        "schedule": 30.0,
        "options": {"queue": "notifications"},
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSRF_FAILURE_VIEW = "amaris_cms.error_views.error_403"
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

JAZZMIN_SETTINGS = {
    "site_title": "Amaris Academy Admin",
    "site_header": "Amaris Mathematics Academy",
    "site_brand": "Amaris Academy",
    "welcome_sign": "Content and learning operations",
    "copyright": "Amaris Mathematics Academy",
    "search_model": ["content.Course", "content.Lesson", "content.ContactEnquiry"],
    "topmenu_links": [
        {
            "name": "View website",
            "url": "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
            "new_window": True,
        },
        {"model": "content.course"},
        {"model": "content.contactenquiry"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "content",
        "content.sitesettings",
        "content.navigationitem",
        "content.page",
        "content.pagesection",
        "content.coursecategory",
        "content.course",
        "content.coursemodule",
        "content.lesson",
        "content.videoasset",
        "content.resourceasset",
        "content.pricingplan",
        "content.testimonial",
        "content.faq",
        "content.announcement",
        "content.contactenquiry",
        "content.studentrecord",
        "content.enrollment",
        "content.payment",
        "content.paymentreconciliationrun",
    ],
    "icons": {
        "content.SiteSettings": "fas fa-sliders-h",
        "content.NavigationItem": "fas fa-bars",
        "content.Page": "fas fa-file-alt",
        "content.PageSection": "fas fa-layer-group",
        "content.CourseCategory": "fas fa-folder-open",
        "content.Course": "fas fa-graduation-cap",
        "content.CourseModule": "fas fa-list-ol",
        "content.Lesson": "fas fa-chalkboard-teacher",
        "content.VideoAsset": "fas fa-video",
        "content.ResourceAsset": "fas fa-file-download",
        "content.PricingPlan": "fas fa-tags",
        "content.Testimonial": "fas fa-comment-dots",
        "content.FAQ": "fas fa-question-circle",
        "content.Announcement": "fas fa-bullhorn",
        "content.ContactEnquiry": "fas fa-inbox",
        "content.StudentRecord": "fas fa-user-graduate",
        "content.Enrollment": "fas fa-user-check",
        "content.Payment": "fas fa-credit-card",
        "content.PaymentReconciliationRun": "fas fa-sync-alt",
    },
    "related_modal_active": True,
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": True,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-navy",
    "accent": "accent-warning",
    "navbar": "navbar-navy navbar-dark",
    "sidebar": "sidebar-dark-navy",
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": True,
    "theme": "flatly",
    "dark_mode_theme": "darkly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}
