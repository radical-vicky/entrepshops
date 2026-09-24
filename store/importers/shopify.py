import logging
from decimal import Decimal, InvalidOperation

import requests
from django.utils.text import slugify

from .base import BaseImporter, ImportedImage, ImportedProduct, ImportedVariant

log = logging.getLogger(__name__)


class ShopifyImporter(BaseImporter):
    """Fetches products from a Shopify store's REST Admin API.

    Docs: https://shopify.dev/docs/api/admin-rest/latest/resources/product
    """

    PAGE_SIZE = 250  # Shopify max for REST product listing

    def __init__(self, source):
        super().__init__(source)
        if not source.store_domain:
            raise ValueError('store_domain is empty — set it in admin.')
        if not source.access_token:
            raise ValueError('access_token is empty — set it in admin.')

        self.base_url = (
            f'https://{source.store_domain}/admin/api/'
            f'{source.api_version}/'
        )
        self.headers = {
            'X-Shopify-Access-Token': source.access_token,
            'Content-Type': 'application/json',
        }

    def fetch(self, limit=None):
        raw = self._fetch_raw(limit=limit)
        return [self._normalise(item) for item in raw]

    def _fetch_raw(self, limit=None):
        results = []
        url = f'{self.base_url}products.json'
        params = {'limit': self.PAGE_SIZE}

        while url:
            response = requests.get(
                url, headers=self.headers,
                params=params if url == f'{self.base_url}products.json' else None,
                timeout=30,
            )

            if response.status_code == 401:
                raise PermissionError(
                    'Shopify rejected the access token (401). '
                    'Confirm the token has read_products scope.'
                )
            if response.status_code == 404:
                raise LookupError(
                    'Shopify returned 404 — check the store domain '
                    '(it must be your-store.myshopify.com).'
                )
            response.raise_for_status()

            products = response.json().get('products', [])
            if not products:
                break

            results.extend(products)
            if limit and len(results) >= limit:
                return results[:limit]

            # Shopify paginates via the Link header with rel="next".
            url = self._parse_next_link(response.headers.get('Link', ''))

        return results

    @staticmethod
    def _parse_next_link(link_header):
        if not link_header:
            return None
        for part in link_header.split(','):
            if 'rel="next"' in part:
                return part.split(';')[0].strip().strip('<>')
        return None

    def _normalise(self, item):
        variants = []
        for v in item.get('variants', []):
            title = v.get('title') or ''
            if title.lower() == 'default title':
                title = v.get('option1') or 'Default'
            variants.append(ImportedVariant(
                external_id=str(v.get('id')),
                size_label=title[:40],
                price=self._to_decimal(v.get('price')),
                compare_at_price=self._to_decimal(v.get('compare_at_price')),
                stock=int(v.get('inventory_quantity') or 0),
                sku=(v.get('sku') or '')[:64],
                weight_grams=v.get('grams'),
            ))

        images = []
        for img in item.get('images', []):
            images.append(ImportedImage(
                external_id=str(img.get('id')),
                url=img.get('src') or '',
                alt_text=(img.get('alt') or '')[:150],
            ))

        return ImportedProduct(
            external_id=str(item.get('id')),
            name=(item.get('title') or '')[:150],
            description=item.get('body_html') or '',
            slug=slugify(item.get('title') or ''),
            category_name=item.get('product_type') or '',
            product_type=item.get('product_type') or '',
            tags=item.get('tags') or [],
            variants=variants,
            images=images,
            status=item.get('status') or 'active',
        )

    @staticmethod
    def _to_decimal(value):
        if value in (None, ''):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None

    def run(self, limit=None):
        """Persist imported products. Returns counts."""
        from django.db import transaction
        from store.models import (
            Category, Product, ProductImage, ProductVariant,
        )

        imported = self.fetch(limit=limit)
        created = updated = skipped = 0
        default_dept = self.source.default_department

        for item in imported:
            if not item.name or not item.slug:
                skipped += 1
                continue

            # Category: match by name; create if missing.
            category = None
            if item.category_name:
                category = Category.objects.filter(
                    name__iexact=item.category_name
                ).first()
                if category is None:
                    base_slug = slugify(item.category_name)[:110] or 'uncategorised'
                    slug = base_slug
                    n = 1
                    while Category.objects.filter(slug=slug).exists():
                        n += 1
                        slug = f'{base_slug}-{n}'[:110]
                    category = Category.objects.create(
                        name=item.category_name[:100],
                        slug=slug,
                        department=default_dept,
                    )

            if category is None:
                skipped += 1
                continue

            product = Product.objects.filter(slug=item.slug).first()
            is_new = product is None
            if is_new:
                product = Product(
                    slug=item.slug,
                    category=category,
                    department=category.department or default_dept,
                    name=item.name,
                    description=item.description,
                    is_active=(item.status == 'active'),
                    is_approved=self.source.auto_approve,
                )
            else:
                product.name = item.name
                product.description = item.description
                product.category = category
                if not product.department_id:
                    product.department = category.department or default_dept

            with transaction.atomic():
                product.save()

                if item.variants:
                    product.variants.all().delete()
                    for v in item.variants:
                        ProductVariant.objects.create(
                            product=product,
                            size_label=v.size_label,
                            price=v.price or Decimal('0.00'),
                            compare_at_price=v.compare_at_price,
                            stock=v.stock,
                            sku=v.sku,
                        )
                    prices = [v.price for v in item.variants if v.price]
                    if prices:
                        product.price = min(prices)
                        product.save(update_fields=['price'])
                elif product.price is None:
                    product.price = Decimal('0.00')
                    product.save(update_fields=['price'])

                if item.images:
                    product.images.all().delete()
                    for i, img in enumerate(item.images):
                        ProductImage.objects.create(
                            product=product,
                            image=img.url,
                            alt_text=img.alt_text,
                            sort_order=i,
                        )

            if is_new:
                created += 1
            else:
                updated += 1

        return {'created': created, 'updated': updated, 'skipped': skipped}
