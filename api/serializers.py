from rest_framework import serializers

from store.models import (
    Category, Department, Product, ProductImage, ProductOffer, ProductVariant,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ('id', 'name', 'slug', 'tagline', 'theme', 'unit_kind', 'icon_kind')


class CategorySerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'department')


class ProductVariantSerializer(serializers.ModelSerializer):
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            'id', 'size_label', 'size_value', 'size_unit',
            'price', 'compare_at_price', 'stock',
            'is_active', 'sort_order', 'discount_percent',
        )


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source='image', read_only=True)

    class Meta:
        model = ProductImage
        fields = ('id', 'url', 'alt_text', 'sort_order')


class ProductOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductOffer
        fields = ('id', 'text', 'url', 'sort_order')


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight — used for the grid. No variants, no offers."""
    department = serializers.StringRelatedField()
    category = serializers.StringRelatedField()
    image = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            'id', 'slug', 'name', 'department', 'category',
            'image', 'price', 'compare_at_price', 'price_range',
            'in_stock', 'discount_percent',
        )

    def get_image(self, obj):
        img = obj.primary_image
        return img.url if img else None

    def get_price_range(self, obj):
        lo, hi = obj.price_range
        return [str(lo), str(hi)]


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full detail — used for the product page or a mobile app."""
    department = DepartmentSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    offers = ProductOfferSerializer(many=True, read_only=True)
    price_range = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            'id', 'slug', 'name', 'description',
            'department', 'category',
            'price', 'compare_at_price', 'price_range',
            'stock', 'in_stock', 'is_available', 'is_alcoholic',
            'availability', 'discount_percent',
            'variants', 'images', 'offers',
            'created_at',
        )

    def get_price_range(self, obj):
        lo, hi = obj.price_range
        return [str(lo), str(hi)]
