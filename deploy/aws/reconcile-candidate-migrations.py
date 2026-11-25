"""Rebase the unpublished payment migration and join reviewed feature leaves.

Only for the isolated combined release candidate. No database operations run here.
The normal Django migration graph, drift and PostgreSQL checks must still pass.
"""
from pathlib import Path
import subprocess

root = Path("backend/content/migrations")
old = root / "0009_payment_provider_choice.py"
new = root / "0030_payment_provider_choice.py"
merge = root / "0031_merge_aws_feature_workflows.py"
leaves = (
    "0019_private_chat",
    "0021_sponsor_payment_gateways",
    "0023_subscription_learning_reports",
    "0029_tutor_employment_contract",
    "0030_payment_provider_choice",
)
for name in (*leaves[:-1], "0018_tutor_document_categories"):
    if not (root / f"{name}.py").is_file():
        raise SystemExit(f"Missing reviewed migration: {name}")
if new.exists() or merge.exists():
    raise SystemExit("Candidate migration names already exist")
expected = subprocess.check_output(
    ["git", "show", "287dad8950f695e46818a355c00fc11ea820df63:backend/content/migrations/0009_payment_provider_choice.py"]
)
if old.read_bytes() != expected:
    raise SystemExit("Payment migration differs from reviewed unpublished revision")
source = expected.decode("utf-8")
anchor = 'dependencies = [("content", "0008_announcement_media")]'
if source.count(anchor) != 1:
    raise SystemExit("Unexpected payment dependency")
new.write_text(source.replace(anchor, 'dependencies = [("content", "0018_tutor_document_categories")]'))
old.unlink()
merge.write_text(
    "from django.db import migrations\n\n\n"
    "class Migration(migrations.Migration):\n"
    "    dependencies = [\n"
    + "".join(f'        ("content", "{name}"),\n' for name in leaves)
    + "    ]\n\n    operations = []\n"
)
print("Prepared candidate migration join; Django/PostgreSQL validation still required.")
