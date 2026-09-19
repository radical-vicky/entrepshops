from decimal import Decimal

from .models import BundleOffer, Product, ProductVariant

CART_SESSION_KEY = 'cart'


def _line_key(product, variant=None):
    """Session dict key for a cart line. Products without a variant keep
    the legacy '<product_id>' key so existing carts survive a deploy.
    Variant lines use '<product_id>:<variant_id>'."""
    if variant is None:
        return str(product.id)
    return f'{product.id}:{variant.id}'


def _split_key(key):
    """Return (product_id, variant_id|None) from a session key."""
    if ':' in key:
        product_part, variant_part = key.split(':', 1)
        try:
            return int(product_part), int(variant_part)
        except ValueError:
            return None, None
    try:
        return int(key), None
    except ValueError:
        return None, None


class Cart:
    """Session-backed shopping cart with variant support.

    Session layout::

        {
          "<product_id>":          {"quantity": int},                    # legacy / no-variant
          "<product_id>:<var_id>": {"quantity": int, "variant_id": int}, # variant line
        }

    Only quantities are stored — prices are always looked up live so an
    admin price change is reflected the moment the cart is next read.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if cart is None:
            cart = self.session[CART_SESSION_KEY] = {}
        self.cart = cart

    # ------------------------------------------------------------ mutators

    def add(self, product, variant=None, quantity=1, replace=False):
        # If the caller didn't pass a variant but the product has variants,
        # default to the first active one so add-to-cart from the grid
        # (which has no variant selector) still produces a purchasable line.
        if variant is None and product.has_variants:
            variant = product.available_variants.first()

        key = _line_key(product, variant)
        if key not in self.cart:
            self.cart[key] = {'quantity': 0}
            if variant is not None:
                self.cart[key]['variant_id'] = variant.id

        if replace:
            self.cart[key]['quantity'] = quantity
        else:
            self.cart[key]['quantity'] += quantity
        self.save()

    def remove(self, product, variant=None):
        key = _line_key(product, variant)
        # If the caller didn't pass a variant and a legacy line exists,
        # remove that one.
        if key in self.cart:
            del self.cart[key]
            self.save()
            return
        # Fallback: remove every line for this product, variant or not.
        for k in list(self.cart.keys()):
            pid, _vid = _split_key(k)
            if pid == product.id:
                del self.cart[k]
        self.save()

    def update_quantity(self, product, variant, quantity):
        """Set an exact quantity for one specific line. Quantity 0 removes it."""
        key = _line_key(product, variant)
        if quantity <= 0:
            if key in self.cart:
                del self.cart[key]
        else:
            self.cart.setdefault(key, {'quantity': 0})
            if variant is not None:
                self.cart[key]['variant_id'] = variant.id
            self.cart[key]['quantity'] = quantity
        self.save()

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.save()

    def save(self):
        self.session.modified = True

    # ------------------------------------------------------------ readers

    def _load_lines(self):
        """Resolve every session entry to a (product, variant, quantity)
        triple, dropping entries whose product or variant no longer exists."""
        if not self.cart:
            return []

        product_ids = set()
        variant_ids = set()
        parsed = []
        for key, item in self.cart.items():
            pid, vid = _split_key(key)
            if pid is None:
                continue
            product_ids.add(pid)
            if vid is not None:
                variant_ids.add(vid)
            parsed.append((key, pid, vid, item.get('quantity', 0)))

        products = Product.objects.filter(id__in=product_ids).select_related(
            'category', 'department', 'vendor'
        )
        products_map = {p.id: p for p in products}

        variants_map = {}
        if variant_ids:
            variants = ProductVariant.objects.filter(id__in=variant_ids).select_related('product')
            variants_map = {v.id: v for v in variants}

        lines = []
        stale_keys = []
        for key, pid, vid, quantity in parsed:
            product = products_map.get(pid)
            if product is None:
                stale_keys.append(key)
                continue
            variant = variants_map.get(vid) if vid is not None else None
            if vid is not None and variant is None:
                stale_keys.append(key)
                continue
            lines.append({
                'key': key,
                'product': product,
                'variant': variant,
                'quantity': quantity,
            })

        if stale_keys:
            for k in stale_keys:
                self.cart.pop(k, None)
            self.save()

        return lines

    def _unit_price(self, product, variant, quantity):
        """Wholesale tier applies per-line: if the customer buys enough of
        the same product at the same size, use the wholesale price for
        that line. Variants carry their own price directly."""
        if variant is not None:
            return variant.price
        return product.unit_price_for_quantity(quantity)

    def _is_wholesale(self, product, variant, quantity):
        if variant is not None:
            return False
        return (
            product.has_wholesale_price
            and quantity >= product.wholesale_quantity_threshold
        )

    def _paid_lines(self):
        lines = []
        for entry in self._load_lines():
            product = entry['product']
            variant = entry['variant']
            quantity = entry['quantity']
            unit_price = self._unit_price(product, variant, quantity)
            lines.append({
                'key': entry['key'],
                'product': product,
                'variant': variant,
                'quantity': quantity,
                'unit_price': unit_price,
                'subtotal': unit_price * quantity,
                'is_wholesale': self._is_wholesale(product, variant, quantity),
                'is_bonus': False,
                'display_name': (
                    f'{product.name} — {variant.size_label}'
                    if variant else product.name
                ),
            })
        return lines

    def _bonus_lines(self, paid_lines):
        """Auto-applied "buy X get Y" bundle rewards. Triggered by total
        quantity of the trigger product across all its variants."""
        qty_by_product_id = {}
        for line in paid_lines:
            pid = line['product'].id
            qty_by_product_id[pid] = qty_by_product_id.get(pid, 0) + line['quantity']

        bonus_lines = []
        offers = BundleOffer.objects.filter(is_active=True).select_related(
            'trigger_product', 'reward_product'
        )
        for offer in offers:
            trigger_qty = qty_by_product_id.get(offer.trigger_product_id, 0)
            if trigger_qty < offer.trigger_quantity:
                continue
            times_earned = trigger_qty // offer.trigger_quantity
            free_quantity = times_earned * offer.reward_quantity
            if free_quantity <= 0:
                continue
            # Reward is added as the reward product's default variant if
            # it has any, otherwise variant-less.
            reward_variant = None
            if offer.reward_product.has_variants:
                reward_variant = offer.reward_product.available_variants.first()
            bonus_lines.append({
                'key': f'bonus:{offer.id}',
                'product': offer.reward_product,
                'variant': reward_variant,
                'quantity': free_quantity,
                'unit_price': Decimal('0.00'),
                'subtotal': Decimal('0.00'),
                'is_wholesale': False,
                'is_bonus': True,
                'bundle_label': offer.label,
                'display_name': (
                    f'{offer.reward_product.name} — {reward_variant.size_label}'
                    if reward_variant else offer.reward_product.name
                ),
            })
        return bonus_lines

    def __iter__(self):
        paid_lines = self._paid_lines()
        for line in paid_lines:
            yield line
        for line in self._bonus_lines(paid_lines):
            yield line

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    @property
    def subtotal(self):
        return sum((line['subtotal'] for line in self), Decimal('0.00'))

    def has_undeliverable_items(self):
        return any(
            not line['product'].is_deliverable
            for line in self
            if not line['is_bonus']
        )