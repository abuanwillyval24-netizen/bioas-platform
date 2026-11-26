from django.core.management.base import BaseCommand
from citizens.models import CitizenSupportingDocument, CitizenProfile


class Command(BaseCommand):
    help = "Wipe redundant duplicate Base64 PDF blobs to keep Render RAM under 512MB"

    def handle(self, *args, **options):
        wiped = CitizenSupportingDocument.objects.exclude(file_data_uri="").update(file_data_uri="")
        self.stdout.write(f"Purged {wiped} duplicate repository Base64 PDF blobs.")
