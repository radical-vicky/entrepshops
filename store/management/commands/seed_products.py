from django.core.management.base import BaseCommand
from django.utils.text import slugify

from store.models import Category, DeliveryZone, Department, Product, Promotion

SAMPLE_ZONES = [
    # Nairobi estates — same-day, short-haul
    ('Kilimani', 100, 30),
    ('Westlands', 120, 35),
    ('Lavington', 120, 35),
    ('Kileleshwa', 100, 30),
    ('South B', 150, 45),
    ('South C', 150, 45),
    # Other major towns — we deliver Kenya-wide via courier partners,
    # so these carry a higher fee and longer ETA than in-city Nairobi drops.
    ('Mombasa', 350, 1440),
    ('Kisumu', 350, 1440),
    ('Nakuru', 300, 720),
    ('Eldoret', 350, 1440),
    ('Thika', 200, 180),
]

# Each product tuple is (name, price, volume_ml_or_None, wholesale_qty_or_None, wholesale_price_or_None)
DEPARTMENTS = [
    {
        'name': 'Drinks', 'slug': 'drinks', 'theme': Department.Theme.GREEN, 'icon_kind': 'bottle',
        'tagline': 'Sodas, juices, water & more, delivered cold.', 'sort_order': 0,
        'categories': {
            'Sodas': [
                ('Coca-Cola 500ml', 80, 500, 24, 65),
                ('Fanta Orange 500ml', 80, 500, None, None),
                ('Sprite 500ml', 80, 500, None, None),
            ],
            'Juices': [
                ('Del Monte Mango 1L', 220, 1000, None, None),
                ('Minute Maid Pulpy Orange 1L', 210, 1000, None, None),
            ],
            'Water': [
                ('Dasani Water 500ml', 50, 500, None, None),
                ('Keringet Water 1L', 90, 1000, None, None),
            ],
            'Energy Drinks': [
                ('Red Bull 250ml', 250, 250, None, None),
                ('Monster Energy 500ml', 300, 500, None, None),
            ],
        },
        'featured': {
            'Coca-Cola 500ml': ('20% off today', 'Chilled sodas, at your door', ''),
            'Del Monte Mango 1L': ('New arrivals', 'Real fruit juices, restocked weekly', ''),
            'Red Bull 250ml': ('Weekend pick', 'Fuel your night out', ''),
        },
    },
    {
        'name': 'Electronics', 'slug': 'electronics', 'theme': Department.Theme.BLUE, 'icon_kind': 'truck',
        'tagline': 'Smart TVs, sound systems, radios, smart watches — wholesale or single unit.', 'sort_order': 1,
        'categories': {
            'Smart TVs': [
                ('43" Smart TV', 28000, None, None, None),
                ('55" Smart TV', 42000, None, None, None),
            ],
            'Sound Systems': [
                ('Home Theatre System 5.1', 15000, None, None, None),
                ('Bluetooth Speaker', 3500, None, 10, 2800),
            ],
            'Radios': [
                ('Portable FM Radio', 1800, None, 12, 1400),
            ],
            'Smart Watches': [
                ('Fitness Smart Watch', 4500, None, None, None),
                ('Kids GPS Smart Watch', 3200, None, None, None),
            ],
        },
        'featured': {
            '55" Smart TV': ('New arrivals', 'Bigger screen, sharper picture', ''),
            'Bluetooth Speaker': ('Bulk deal', 'Buy 10+ at wholesale price', ''),
        },
    },
    {
        'name': 'Vehicles', 'slug': 'vehicles', 'theme': Department.Theme.CRIMSON, 'icon_kind': 'truck',
        'tagline': 'Cars and motorbikes, inspected and delivered to your door.', 'sort_order': 2,
        'categories': {
            'Motorbikes': [
                ('Boda Boda 150cc', 145000, None, None, None),
                ('Off-road Motorbike 200cc', 210000, None, None, None),
            ],
            'Cars': [
                ('Compact Sedan (used, inspected)', 850000, None, None, None),
            ],
        },
        'featured': {
            'Boda Boda 150cc': ('Best seller', 'Start earning from day one', ''),
        },
    },
    {
        'name': 'Fashion', 'slug': 'fashion', 'theme': Department.Theme.VIOLET, 'icon_kind': 'gift',
        'tagline': 'Shoes and more — wholesale cartons or a single pair.', 'sort_order': 3,
        'categories': {
            'Shoes': [
                ("Men's Sneakers", 2500, None, None, None),
                ("Women's Heels", 2200, None, None, None),
                ('Kids School Shoes', 1200, None, 12, 950),
            ],
        },
        'featured': {
            'Kids School Shoes': ('Back to school', 'Wholesale cartons of 12+', ''),
        },
    },
]

SAMPLE_PROMOTIONS = [
    {
        'kicker': 'First order', 'title': '20% off your first cart',
        'description': 'New customers save on any order over KES 1,000. Applies to non-alcoholic drinks.',
        'voucher_code': 'WELCOME20', 'tone': Promotion.Tone.GREEN, 'sort_order': 1,
    },
    {
        'kicker': 'This week', 'title': 'Free delivery over KES 2,000',
        'description': 'Stock up on juices and sodas — delivery fee waived automatically at that cart size.',
        'voucher_code': 'FREESHIP', 'tone': Promotion.Tone.ORANGE, 'sort_order': 2,
    },
    {
        'kicker': 'Gifting', 'title': "Send a drinks hamper",
        'description': "Pick a friend's saved address and we deliver the crate with a gift note attached.",
        'voucher_code': 'GIFTIT', 'tone': Promotion.Tone.GOLD, 'sort_order': 3,
    },
]


class Command(BaseCommand):
    help = 'Seed the database with sample products across every department (drinks, electronics, vehicles, fashion).'

    def handle(self, *args, **options):
        for zone_name, fee, minutes in SAMPLE_ZONES:
            DeliveryZone.objects.get_or_create(
                name=zone_name,
                defaults={'delivery_fee': fee, 'estimated_minutes': minutes},
            )

        for dept_data in DEPARTMENTS:
            department, _ = Department.objects.get_or_create(
                slug=dept_data['slug'],
                defaults={
                    'name': dept_data['name'],
                    'theme': dept_data['theme'],
                    'icon_kind': dept_data['icon_kind'],
                    'tagline': dept_data['tagline'],
                    'sort_order': dept_data['sort_order'],
                },
            )
            featured = dept_data.get('featured', {})

            for category_name, products in dept_data['categories'].items():
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'slug': slugify(category_name), 'department': department},
                )
                if category.department_id != department.id:
                    category.department = department
                    category.save(update_fields=['department'])

                for name, price, volume_ml, wholesale_qty, wholesale_price in products:
                    tagline, headline, description = featured.get(name, ('', '', ''))
                    Product.objects.get_or_create(
                        name=name,
                        defaults={
                            'category': category,
                            'slug': slugify(name),
                            'price': price,
                            'volume_ml': volume_ml,
                            'wholesale_quantity_threshold': wholesale_qty,
                            'wholesale_price': wholesale_price,
                            'stock': 100,
                            'is_alcoholic': False,
                            'is_active': True,
                            'is_featured': name in featured,
                            'hero_tagline': tagline,
                            'hero_headline': headline,
                            'hero_description': description,
                        },
                    )

        for promo_data in SAMPLE_PROMOTIONS:
            Promotion.objects.get_or_create(
                title=promo_data['title'],
                defaults={**promo_data, 'is_active': True},
            )

        self.stdout.write(self.style.SUCCESS('Sample products seeded across all departments.'))
