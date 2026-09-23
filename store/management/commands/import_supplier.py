from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from store.importers.shopify import ShopifyImporter
from store.models import SupplierSource


class Command(BaseCommand):
    help = 'Import products from a configured SupplierSource.'

    def add_arguments(self, parser):
        parser.add_argument('slug', help='The SupplierSource.name to import.')
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Max products to fetch (for testing).'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Fetch and print what would happen without writing.'
        )

    def handle(self, *args, **options):
        name = options['slug']
        try:
            source = SupplierSource.objects.get(name=name)
        except SupplierSource.DoesNotExist:
            raise CommandError(f'No SupplierSource named "{name}".')

        importer = ShopifyImporter(source)
        limit = options['limit']

        if options['dry_run']:
            products = importer.preview(limit=limit)
            self.stdout.write(f'Fetched {len(products)} products (dry run).')
            for p in products[:10]:
                self.stdout.write(
                    f'  {p.external_id}  {p.name[:60]}  '
                    f'({len(p.variants)} variants, {len(p.images)} images)'
                )
            return

        result = importer.run(limit=limit)
        source.last_synced_at = timezone.now()
        source.last_status = 'ok'
        source.last_error = ''
        source.save(update_fields=['last_synced_at', 'last_status', 'last_error'])

        self.stdout.write(self.style.SUCCESS(
            f'Imported {result["created"]} new, '
            f'updated {result["updated"]}, '
            f'skipped {result["skipped"]}.'
        ))
