import logging
from decimal import Decimal, InvalidOperation

import requests
from django.core.cache import cache
from django.utils.text import slugify

from .base import BaseImporter, ImportedImage, ImportedProduct, ImportedVariant

log = logging.getLogger(__name__)


class ShopifyAuthError(Exception):
    """Raised when Shopify rejects our credentials or the token request fails."""


class ShopifyImporter(BaseImporter):
    """Fetches products from a Shopify store's REST Admin API.

    Uses the Client Credentials Grant:
      - We store client_id + client_secret on the SupplierSource.
      - On every import, we POST them to /admin/oauth/access_token and get
        back an access_token valid for ~24 hours.
      - The token is cached in Django's cache for 23 hours so subsequent
        imports the same day don't re-authenticate.

    Docs:
      https://shopify.dev/docs/apps/auth/get-access-tokens
      https://shopify.dev/docs/api/admin-rest/latest/resources/product
    """

    PAGE_SIZE = 250
    TOKEN_CACHE_SECONDS = 60 * 60 * 23  # 23 hours — 1h safety margin

    def __init__(self, source):
        super().__init__(source)
        if not source.store_domain:
            raise ShopifyAuthError('store_domain is empty — set it in admin.')
        if not source.client_id or not source.client_secret:
            raise ShopifyAuthError(
                'client_id and client_secret are required. Get them from the '
                'Shopify Dev Dashboard → your app → App settings.'
            )

        self.domain = source.store_domain.strip().rstrip('/')
        self.base_url = (
            f'https://{self.domain}/admin/api/{source.api_version}/'
        )
        self._access_token = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    @property
    def access_token(self):
        if self._access_token:
            return self._access_token

        cache_key = f'shopify_token_{self.source.pk}'
        cached = cache.get(cache_key)
        if cached:
            self._access_token = cached
            return cached

        token = self._fetch_token()
        cache.set(cache_key, token, self.TOKEN_CACHE_SECONDS)
        self._access_token = token
        return token

    def _fetch_token(self):
        """Exchange client_id + client_secret for an access token."""
        url = f'https://{self.domain}/admin/oauth/access_token'
        body = {
            'client_id': self.source.client_id,
            'client_secret': self.source.client_secret,
            'grant_type': 'client_credentials',
        }
        try:
            response = requests.post(url, json=body, timeout=30)
        except requests.RequestException as exc:
            raise ShopifyAuthError(f'Could not reach Shopify: {exc}') from exc

        if response.status_code == 401:
            raise ShopifyAuthError(
                'Shopify rejected the client credentials (401). '
                'Confirm the Client ID and Client Secret, and that the app '
                'has the read_products scope enabled.'
            )
        if response.status_code == 404:
            raise ShopifyAuthError(
                f'Shopify returned 404 for {self.domain}. '
                'The store domain must be your-store.myshopify.com '
                '(no https://, no trailing slash).'
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise ShopifyAuthError(
                f'Shopify token endpoint returned {response.status_code}: '
                f'{response.text[:300]}'
            ) from exc

        payload = response.json()
        token = payload.get('access_token')
        if not token:
            raise ShopifyAuthError(
                f'Shopify did not return an access_token. Response: {payload}'
            )
        return token

    @property
    def headers(self):
        return {
            'X-Shopify-Access-Token': self.access_token,
            'Content-Type': 'application/json',
        }

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------
    def fetch(self, limit=None):
        raw = self._fetch_raw(limit=limit)
        return [self._normalise(item) for item in raw]

    def _fetch_raw(self, limit=None):
        results = []
        url = f'{self.base_url}products.json'
        params = {'limit': self.PAGE_SIZE}

        while url:
            try:
                response = requests.get(
                    url, headers=self.headers,
                    params=params if url == f'{self.base_url}products.json' else None,
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise ShopifyAuthError(f'Request to Shopify failed: {exc}') from exc

            if response.status_code == 401:
                # Cached token expired mid-run. Clear cache and retry once.
                cache.delete(f'shopify_token_{self.source.pk}')
                self._access_token = None
                response = requests.get(
                    url, headers=self.headers,
                    params=params if url == f'{self.base_url}products.json' else None,
                    timeout=30,
                )
            if response.status_code == 404:
                raise ShopifyAuthError(
                    f'Shopify returned 404 for {self.domain}. '
                    'Check the store domain.'
                )
            response.raise_for_status()

            products = response.json().get('products', [])
            if not products:
                break

            results.extend(products)
            if limit and len(results) >= limit:
                return results[:limit]

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

    # ------------------------------------------------------------------
    # Normalise
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    def run(self, limit=None):
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
