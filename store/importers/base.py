from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class ImportedVariant:
    """A normalised variant — one size/option of a product."""
    external_id: str
    size_label: str
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    stock: int = 0
    sku: str = ''
    weight_grams: Optional[int] = None


@dataclass
class ImportedImage:
    external_id: str
    url: str
    alt_text: str = ''


@dataclass
class ImportedProduct:
    """A normalised product from any supplier. Every importer returns
    a list of these — the writer code that persists them doesn't care
    which supplier they came from."""
    external_id: str
    name: str
    description: str = ''
    slug: str = ''
    category_name: str = ''
    product_type: str = ''
    tags: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    images: list = field(default_factory=list)
    status: str = 'active'


class BaseImporter:
    """Every supplier importer subclasses this and implements fetch()."""

    def __init__(self, source):
        self.source = source

    def fetch(self, limit=None):
        raise NotImplementedError

    def preview(self, limit=50):
        """Returns normalised products without writing anything to the DB."""
        return self.fetch(limit=limit)
