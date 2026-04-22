from django.contrib import admin

from .models import Interface, InterfaceLog


@admin.register(Interface)
class InterfaceAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'protocol', 'target_system', 'is_active', 'created_at')
    list_filter = ('protocol', 'is_active')
    search_fields = ('code', 'name', 'target_system')


@admin.register(InterfaceLog)
class InterfaceLogAdmin(admin.ModelAdmin):
    list_display = ('interface', 'status', 'latency_ms', 'executed_at')
    list_filter = ('status', 'interface__protocol')
    search_fields = ('interface__code',)
    date_hierarchy = 'executed_at'
