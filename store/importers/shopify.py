import logging
from decimal import Decimal, InvalidOperation

import requests
from django.utils.text import slugify

from .base import BaseImporter, ImportedImage, ImportedProduct, ImportedVariant

log = logging.getLogger(__name__)


class ShopifyImporter(BaseImporter):
    """Fetches products from a Shopify store's REST Admin API.

    Docs: https://shopify.dev/docs/api/admin-rest/latest/resources/product

    Note: this uses the REST Admin API. Shopify has marked it as legacy
    as of October 2024 in favour of GraphQL, but for a single private
    store read-only sync it remains fully functional and much simpler
    to debug. If your store uses products with more than 100 variants,
    REST will truncate them and you'd need to migrate to GraphQL.
    """

    PAGE_SIZE = 250  # Shopify's max for REST product listing

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
        """Return a list of ImportedProduct. Shopify paginates with
        Link headers; we follow them until done or until we hit `limit`."""
        raw = self._fetch_raw(limit=limit)
        return [self._normalise(item) for item in raw]

    # ------------------------------------------------------------------
    # Raw fetch
    # ------------------------------------------------------------------
    def _fetch_raw(self, limit=None):
        results = []
        params = {'limit': self.PAGE_SIZE}

        while True:
            response = requests.get(
                f'{self.base_url}products.json',
                headers=self.headers,
                params=params,
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
                results = results[:limit]
                break

            # Shopify paginates via the Link header. If there's no
            # rel="next", we're done.
            next_url = self._parse_next_link(response.headers.get('Link', ''))
            if not next_url:
                break

            # The next URL contains the page_info cursor; drop our params.
            response = requests.get(
                next_url, headers=self.headers, timeout=30,
            )
            response.raise_for_status()
            products = response.json().get('products', [])
            results.extend(products)
            if limit and len(results) >= limit:
                results = results[:limit]
                break
            if not products:
                break

        return results

    @staticmethod
    def _parse_next_link(link_header):
        if not link_header:
            return None
        for part in link_header.split(','):
            if 'rel="next"' in part:
                url = part.split(';')[0].strip()
                return url.strip('<>')
        return None

    # ------------------------------------------------------------------
    # Normalise
    # ------------------------------------------------------------------
    def _normalise(self, item):
        variants = []
        for v in item.get('variants', []):
            title = v.get('title') or ''
            # Shopify's default variant title is "Default Title" — treat
            # that as a variant-less product by using the option1 value.
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
    from store.models import Category, Department, Product, ProductImage, ProductVariant

    from django.db import transaction

    imported = self.fetch(limit=limit)
    created = updated = skipped = 0

    default_dept = self.source.default_department

    for item in imported:
        if not item.name or not item.slug:
            skipped += 1
            continue

        # Category: match by name, else create under default_dept.
        category = None
        if item.category_name:
            category = Category.objects.filter(name__iexact=item.category_name).first()
            if category is None:
                category = Category.objects.create(
                    name=item.category_name[:100],
                    slug=slugify(item.category_name)[:110] or 'uncategorised',
                    department=default_dept,
                )

        if category is None:
            skipped += 1
            continue

        # Product: match by slug.
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

        # Variants — delete and recreate for simplicity. In production
        # you'd want a more careful merge.
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
                # Legacy fallback price = cheapest variant.
                product.price = min(v.price for v in item.variants if v.price)
                product.save(update_fields=['price'])
            elif product.price is None:
                product.price = Decimal('0.00')
                product.save(update_fields=['price'])

            if item.images:
                product.images.all().delete()
                for i, img in enumerate(item.images):
                    ProductImage.objects.create(
                        product=product,
                        image=img.url,  # ImageField accepts a URL string
                        alt_text=img.alt_text,
                        sort_order=i,
                    )

        if is_new:
            created += 1
        else:
            updated += 1

    return {'created': created, 'updated': updated, 'skipped': skipped}
