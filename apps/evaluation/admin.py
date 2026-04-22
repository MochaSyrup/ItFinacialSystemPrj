from django.contrib import admin

from .models import FinancialProduct, Portfolio


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'base_currency', 'created_at')
    search_fields = ('name',)


@admin.register(FinancialProduct)
class FinancialProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'portfolio', 'kind', 'notional')
    list_filter = ('kind', 'portfolio')
    search_fields = ('code', 'name')
