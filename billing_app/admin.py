from django.contrib import admin
from .models import WifiSession, PaymentPlan

@admin.register(WifiSession)
class WifiSessionAdmin(admin.ModelAdmin):
    list_display = ['mac_address', 'ip_address', 'is_paid', 'payment_amount', 'created_at', 'expires_at']
    list_filter = ['is_paid', 'is_active', 'created_at']
    search_fields = ['mac_address', 'ip_address']
    readonly_fields = ['session_id', 'created_at']

@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'duration_hours', 'is_active']
    list_filter = ['is_active']
