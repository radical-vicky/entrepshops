from django.core.management.base import BaseCommand

from marketing.views import process_due_proofs


class Command(BaseCommand):
    help = (
        'Credit every pending marketing proof whose 24-hour hold has expired, '
        'and send the congratulations email to the user.'
    )

    def handle(self, *args, **options):
        result = process_due_proofs()
        self.stdout.write(self.style.SUCCESS(
            f'Processed {result["processed"]} proof(s); '
            f'credited KES {result["credits"]}.'
        ))