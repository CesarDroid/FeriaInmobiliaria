from django.shortcuts import render
from sales.models import Sale
from django.db.models import Sum, Count
from collections import Counter

def dashboard_view(request):
    # Estadísticas básicas
    total_sales = Sale.objects.count()
    total_amount = Sale.objects.aggregate(Sum('price'))['price__sum'] or 0
    total_commission = Sale.objects.aggregate(Sum('commission'))['commission__sum'] or 0
    
    # Rankings
    top_agents = Sale.objects.values('agent_name').annotate(
        sales_count=Count('id'),
        total_amount=Sum('price')
    ).order_by('-sales_count')[:10]
    
    top_companies = Sale.objects.values('company').annotate(
        sales_count=Count('id'),
        total_amount=Sum('price')
    ).order_by('-sales_count')[:5]
    
    context = {
        'total_sales': total_sales,
        'total_amount': total_amount,
        'total_commission': total_commission,
        'average_sale': total_amount / total_sales if total_sales > 0 else 0,
        'top_agents': top_agents,
        'top_companies': top_companies,
    }
    
    return render(request, 'dashboard/dashboard.html', context)