"""Isolated acceptance settings; never deployed or used with a remote database."""
import os
if os.environ.get("DATABASE_URL") != "postgresql://amaris_itn@127.0.0.1:5432/amaris_itn" or os.environ.get("PAYFAST_MODE") != "sandbox":
    raise RuntimeError("Refusing non-isolated booking acceptance settings")
from amaris_cms.settings import *  # noqa: F403
MIDDLEWARE = ["booking_callback_diagnostics.CallbackDiagnostics", *MIDDLEWARE]
CELERY_TASK_ALWAYS_EAGER = False

EMAIL_FILE_PATH = os.environ["EMAIL_FILE_PATH"]
if EMAIL_FILE_PATH != "/tmp/amaris-staging-mail":
    raise RuntimeError("Refusing an unexpected isolated mailbox directory")
