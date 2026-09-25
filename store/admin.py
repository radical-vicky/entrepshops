from django.contrib import admin, messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    BackgroundImage, BundleOffer, Category, DeliveryAddress, DeliveryZone,
    Department, Product, ProductImage, ProductOffer, ProductVariant,
    Promotion, SiteLogo, SupplierSource,
)


# ======================================================================
# Catalog
# ======================================================================

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'theme', 'unit_kind', 'is_active', 'sort_order')
    list_filter = ('theme', 'unit_kind', 'is_active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'slug')
    list_filter = ('department',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('size_label', 'size_value', 'size_unit', 'sku', 'price',
              'compare_at_price', 'stock', 'is_active', 'sort_order')
    ordering = ('sort_order', 'price')


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'sort_order')


class ProductOfferInline(admin.TabularInline):
    model = ProductOffer
    extra = 1
    fields = ('text', 'url', 'sort_order', 'is_active')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'department', 'category', 'vendor', 'price_range_display',
        'stock', 'availability', 'is_active', 'is_approved', 'is_featured',
    )
    list_filter = (
        'department', 'category', 'vendor', 'availability', 'is_alcoholic',
        'is_active', 'is_approved', 'is_featured',
    )
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    actions = ['approve_products']
    inlines = [ProductVariantInline, ProductImageInline, ProductOfferInline]
    fieldsets = (
        (None, {
            'fields': (
                'department', 'category', 'vendor', 'is_approved',
                'name', 'slug', 'description', 'image',
            )
        }),
        ('Availability', {
            'fields': ('availability', 'is_active'),
            'description': 'Controls the badge and whether customers can add to cart.',
        }),
        ('Fallback pricing & stock — overridden by variants', {
            'fields': ('price', 'compare_at_price', 'volume_ml', 'stock', 'is_alcoholic'),
            'description': 'Only used if this product has no variants. Add variants below to set per-size pricing.',
        }),
        ('Wholesale / bulk pricing', {
            'fields': ('wholesale_quantity_threshold', 'wholesale_price'),
            'classes': ('collapse',),
        }),
        ('Homepage hero slider', {
            'fields': ('is_featured', 'hero_tagline', 'hero_headline', 'hero_description'),
            'classes': ('collapse',),
        }),
    )

    def price_range_display(self, obj):
        lo, hi = obj.price_range
        if lo is None or hi is None:
            return '—'
        return f'KES {lo}' if lo == hi else f'KES {lo}–{hi}'
    price_range_display.short_description = 'Price'

    @admin.action(description='Approve selected products (make visible in the shop)')
    def approve_products(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} product(s) approved.')


@admin.register(BundleOffer)
class BundleOfferAdmin(admin.ModelAdmin):
    list_display = ('label', 'trigger_product', 'trigger_quantity',
                    'reward_product', 'reward_quantity', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label',)


# ======================================================================
# Site chrome
# ======================================================================

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'kicker', 'tone', 'media_type', 'is_active', 'sort_order')
    list_filter = ('tone', 'media_type', 'is_active')
    search_fields = ('title', 'kicker')


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'uploaded_at')
    list_filter = ('is_active',)


@admin.register(BackgroundImage)
class BackgroundImageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'uploaded_at')
    list_filter = ('is_active',)


# ======================================================================
# Delivery
# ======================================================================

@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'delivery_fee', 'estimated_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'building_name', 'area', 'city', 'is_default')
    list_filter = ('is_default', 'city')
    search_fields = ('user__username', 'building_name', 'area', 'phone_number')
    raw_id_fields = ('user',)


# ======================================================================
# Supplier sources (Shopify import)
# ======================================================================

@admin.register(SupplierSource)
class SupplierSourceAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'provider', 'store_domain',
        'is_active', 'auto_approve',
        'last_status', 'last_synced_at',
        'preview_button',
    )
    list_filter = ('provider', 'is_active', 'last_status')
    search_fields = ('name', 'store_domain')
    readonly_fields = ('last_synced_at', 'last_status', 'last_error')
    fieldsets = (
        (None, {'fields': ('name', 'provider', 'is_active')}),
        ('Shopify connection', {
            'fields': ('store_domain', 'api_version', 'client_id', 'client_secret'),
            'description': (
                'Get Client ID and Client Secret from the Shopify Dev Dashboard → '
                'your app → App settings. The importer exchanges them for a '
                'short-lived access token automatically.'
            ),
        }),
        ('Mapping', {
            'fields': ('default_department',),
            'description': 'Where imported products land if they don\'t match an existing category.'
        }),
        ('Behaviour', {'fields': ('auto_approve',)}),
        ('Status', {'fields': ('last_synced_at', 'last_status', 'last_error')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                '<int:pk>/preview/',
                self.admin_site.admin_view(self.preview_view),
                name='store_suppliersource_preview',
            ),
            path(
                '<int:pk>/run-import/',
                self.admin_site.admin_view(self.run_import_view),
                name='store_suppliersource_run_import',
            ),
        ]
        return extra + urls

    def preview_button(self, obj):
        url = reverse('admin:store_suppliersource_preview', args=[obj.pk])
        return format_html('<a class="button" href="{}">Preview</a>', url)
    preview_button.short_description = 'Actions'

    def preview_view(self, request, pk):
        from .importers.shopify import ShopifyImporter
        source = get_object_or_404(SupplierSource, pk=pk)
        try:
            importer = ShopifyImporter(source)
            preview = importer.preview(limit=50)
            return render(request, 'admin/store/suppliersource/preview.html', {
                'source': source,
                'preview': preview,
                'title': f'Preview: {source.name}',
                **self.admin_site.each_context(request),
            })
        except Exception as exc:
            messages.error(request, f'Preview failed: {exc}')
            return redirect('admin:store_suppliersource_changelist')

    def run_import_view(self, request, pk):
        from .importers.shopify import ShopifyImporter
        source = get_object_or_404(SupplierSource, pk=pk)
        try:
            importer = ShopifyImporter(source)
            result = importer.run(limit=None)
            source.last_synced_at = timezone.now()
            source.last_status = 'ok'
            source.last_error = ''
            source.save(update_fields=['last_synced_at', 'last_status', 'last_error'])
            messages.success(
                request,
                f'Imported {result["created"]} new, updated {result["updated"]}, '
                f'skipped {result["skipped"]}.'
            )
        except Exception as exc:
            source.last_status = 'error'
            source.last_error = str(exc)[:2000]
            source.save(update_fields=['last_status', 'last_error'])
            messages.error(request, f'Import failed: {exc}')
        return redirect('admin:store_suppliersource_changelist')