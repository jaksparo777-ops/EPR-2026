from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from apps.client_orders.models import LegalEntity, ClientPO, InterCompanyChallan
from apps.products.models import Item, Client, Warehouse
from apps.production.models import StockTransaction
from apps.logistics.models import Carton

@login_required
def unified_dashboard(request):
    companies = LegalEntity.objects.all().order_by('name')
    active_company_id = request.GET.get('company', 'consolidated')
    
    active_company = None
    if active_company_id and active_company_id != 'consolidated':
        active_company = LegalEntity.objects.filter(id=active_company_id).first()
        
    context = {
        'companies': companies,
        'active_company_id': active_company_id,
        'active_company': active_company,
    }
    
    if active_company_id == 'consolidated':
        # Compile global metrics across the entire pipeline
        total_castings = StockTransaction.objects.filter(
            transaction_type='casting_entry'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        total_dispatches = StockTransaction.objects.filter(
            transaction_type='dispatch_out'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        total_challans = InterCompanyChallan.objects.count()
        total_cartons = Carton.objects.count()
        
        # Calculate shared item flow data for the Sankey flow visualizer
        shared_items = Item.objects.filter(companies__isnull=True).order_by('code')[:10]
        flow_data = []
        
        for item in shared_items:
            # Stage 1: Castings made in C1
            c1_cast = StockTransaction.objects.filter(
                item=item, transaction_type='casting_entry'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Stage 2: Issued to Jobworkers (C3)
            c3_wip = StockTransaction.objects.filter(
                item=item, transaction_type='machining_out', job_worker__isnull=False
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Stage 3: Received back at C2
            c2_machined = StockTransaction.objects.filter(
                item=item, transaction_type='machining_in'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Stage 4: Finished and Packed in Cartons
            c2_packed = StockTransaction.objects.filter(
                item=item, transaction_type='packaging_in'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Stage 5: Dispatched
            dispatched = StockTransaction.objects.filter(
                item=item, transaction_type='dispatch_out'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            flow_data.append({
                'item_code': item.code,
                'item_name': item.name,
                'c1_cast': c1_cast,
                'c3_wip': c3_wip,
                'c2_machined': c2_machined,
                'c2_packed': c2_packed,
                'dispatched': dispatched
            })
            
        context.update({
            'total_castings': total_castings,
            'total_dispatches': total_dispatches,
            'total_challans': total_challans,
            'total_cartons': total_cartons,
            'flow_data': flow_data,
        })
        
    else:
        # Compile company-specific metrics
        private_items = Item.objects.filter(companies=active_company)
        private_clients = Client.objects.filter(companies=active_company)
        private_pos = ClientPO.objects.filter(legal_entity=active_company)
        
        # Local warehouse stock calculation for active company
        warehouses = Warehouse.objects.all()
        warehouse_stats = []
        for wh in warehouses:
            # Simple in/out aggregation for safety
            in_qty = StockTransaction.objects.filter(
                to_warehouse=wh, item__in=Item.objects.filter(Q(companies=active_company) | Q(companies__isnull=True))
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            out_qty = StockTransaction.objects.filter(
                from_warehouse=wh, item__in=Item.objects.filter(Q(companies=active_company) | Q(companies__isnull=True))
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            balance = in_qty - out_qty
            if balance > 0:
                warehouse_stats.append({
                    'name': wh.name,
                    'balance': balance
                })
                
        context.update({
            'item_count': private_items.count(),
            'client_count': private_clients.count(),
            'po_count': private_pos.count(),
            'po_open_count': private_pos.filter(status='OPEN').count(),
            'warehouse_stats': warehouse_stats,
            'private_items': private_items[:10],
            'private_clients': private_clients[:10],
            'private_pos': private_pos[:10],
        })
        
    return render(request, 'unified_dashboard.html', context)
