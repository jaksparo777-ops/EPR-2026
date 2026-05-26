import os
import gzip
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.conf import settings
from io import StringIO

class Command(BaseCommand):
    help = "Creates a database-agnostic compressed backup of the ERP data"

    def handle(self, *args, **options):
        # 1. Ensure backups folder exists in project root
        backups_dir = os.path.join(settings.BASE_DIR, 'backups')
        if not os.path.exists(backups_dir):
            os.makedirs(backups_dir)
            self.stdout.write(self.style.SUCCESS(f"Created backups directory: {backups_dir}"))

        # 2. Generate filename with timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{timestamp}.json.gz"
        filepath = os.path.join(backups_dir, filename)

        self.stdout.write("Serializing active database models...")

        try:
            # 3. Call dumpdata via memory buffer to keep it database agnostic and clean
            buffer = StringIO()
            call_command(
                'dumpdata',
                exclude=['contenttypes', 'auth.Permission', 'sessions', 'monitoring.usersession'],
                indent=2,
                stdout=buffer
            )
            data = buffer.getvalue()
            
            # 4. Compress and write to file
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                f.write(data)

            self.stdout.write(self.style.SUCCESS(
                f"Successfully backed up active ERP database configuration to:\n{filepath}\n"
                f"Size: {os.path.getsize(filepath)} bytes."
            ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {str(e)}"))
