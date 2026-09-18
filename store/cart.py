from decimal import Decimal

from .models import BundleOffer, Product

CART_SESSION_KEY = 'cart'


class Cart:
    """A simple session-backed shopping cart.

    Stored in the session as: {"<product_id>": {"quantity": int}}
    Keeping only quantity in the session (not price) means price changes
    on the product are always reflected live.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if cart is None:
            cart = self.session[CART_SESSION_KEY] = {}
        self.cart = cart

    def add(self, product, quantity=1, replace=False):
        product_id = str(product.id)
        if product_id not in self.cart:
            self.cart[product_id] = {'quantity': 0}
        if replace:
            self.cart[product_id]['quantity'] = quantity
        else:
            self.cart[product_id]['quantity'] += quantity
        self.save()

    def remove(self, product):
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    def save(self):
        self.session.modified = True

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.save()

    def _paid_lines(self):
        """The lines the customer actually chose to buy, at whatever unit
        price applies for the quantity (wholesale tier included)."""
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        products_map = {str(p.id): p for p in products}
        lines = []
        for product_id, item in self.cart.items():
            product = products_map.get(product_id)
            if not product:
                continue
            quantity = item['quantity']
            unit_price = product.unit_price_for_quantity(quantity)
            lines.append({
                'product': product,
                'quantity': quantity,
                'unit_price': unit_price,
                'subtotal': unit_price * quantity,
                'is_wholesale': product.has_wholesale_price and quantity >= product.wholesale_quantity_threshold,
                'is_bonus': False,
            })
        return lines

    def _bonus_lines(self, paid_lines):
        """Auto-applied "buy X get Y" bundle rewards — genuinely free line
        items added because the trigger condition was met, not just a
        marketing banner. Computed fresh every time so removing the
        trigger item removes the bonus automatically."""
        qty_by_product_id = {line['product'].id: line['quantity'] for line in paid_lines}
        bonus_lines = []
        for offer in BundleOffer.objects.filter(is_active=True).select_related('trigger_product', 'reward_product'):
            trigger_qty = qty_by_product_id.get(offer.trigger_product_id, 0)
            if trigger_qty < offer.trigger_quantity:
                continue
            # One "reward" per complete multiple of the trigger quantity.
            times_earned = trigger_qty // offer.trigger_quantity
            free_quantity = times_earned * offer.reward_quantity
            if free_quantity <= 0:
                continue
            bonus_lines.append({
                'product': offer.reward_product,
                'quantity': free_quantity,
                'unit_price': Decimal('0.00'),
                'subtotal': Decimal('0.00'),
                'is_wholesale': False,
                'is_bonus': True,
                'bundle_label': offer.label,
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
        return any(not line['product'].is_deliverable for line in self if not line['is_bonus'])
