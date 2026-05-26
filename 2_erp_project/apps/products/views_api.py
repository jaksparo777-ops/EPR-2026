from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.client_orders.models import LegalEntity
from apps.products.models import Item, Client
from apps.ledger_pay.models import ItemWorkerAllocation

@login_required
def company_details_api(request, company_id):
    try:
        company = LegalEntity.objects.get(id=company_id)
    except LegalEntity.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)
        
    # 1. Fetch Mapped Items (direct scoped OR global)
    items = Item.objects.filter(Q(companies=company) | Q(companies__isnull=True)).distinct().order_by('code')
    items_data = []
    for item in items:
        # If it doesn't have this company explicitly, it's global/shared
        is_global = not item.companies.filter(id=company.id).exists()
        items_data.append({
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "category": item.category,
            "material": item.material or "OTHER",
            "is_global": is_global
        })
        
    # 2. Fetch Mapped Clients (direct scoped OR global)
    clients = Client.objects.filter(Q(companies=company) | Q(companies__isnull=True)).distinct().order_by('name')
    clients_data = []
    for client in clients:
        is_global = not client.companies.filter(id=company.id).exists()
        clients_data.append({
            "id": client.id,
            "name": client.name,
            "city": client.city or "---",
            "gst_number": client.gst_number or "N/A",
            "is_global": is_global
        })
        
    # 3. Fetch Labor Rate Allocations
    allocations = ItemWorkerAllocation.objects.filter(
        item__in=items
    ).select_related('worker', 'job_worker', 'item').order_by('item__code')
    
    alloc_data = []
    for alloc in allocations:
        worker_name = alloc.worker.name if alloc.worker else (alloc.job_worker.name if alloc.job_worker else "---")
        worker_type = "Employee" if alloc.worker else "Job Worker"
        process = alloc.worker.process if alloc.worker else (alloc.job_worker.process if alloc.job_worker else "---")
        
        alloc_data.append({
            "item_code": alloc.item.code,
            "item_name": alloc.item.name,
            "worker_name": worker_name,
            "worker_type": worker_type,
            "process": process.capitalize(),
            "rate": alloc.rate_per_piece
        })
        
    return JsonResponse({
        "company": {
            "id": company.id,
            "name": company.name,
            "gst_number": company.gst_number or "Not Registered",
            "phone": company.phone or "Not Specified",
            "address": company.address,
            "letterhead": company.letterhead_title or "",
            "processes": [p.strip() for p in company.processes.split(',') if p.strip()] if company.processes else []
        },
        "items": items_data,
        "clients": clients_data,
        "allocations": alloc_data
    })
