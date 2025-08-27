from django.contrib import admin
from .models import Sale

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['agent_name', 'company', 'property_type', 'price', 'sale_date']
    list_filter = ['company', 'property_type', 'sale_date']
    search_fields = ['agent_name', 'company', 'location']