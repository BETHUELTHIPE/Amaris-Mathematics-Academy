import json
from dataclasses import asdict

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

from amaris_cms.trusted_advisor import collect_advisor_report


class Command(BaseCommand):
    help = "Report Amaris platform findings and evidence as JSON."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(asdict(collect_advisor_report()), cls=DjangoJSONEncoder, indent=2))
