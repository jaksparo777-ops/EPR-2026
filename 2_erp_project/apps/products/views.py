import json
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from core.security import require_role
from django.db.models import Count, Sum
from django.utils import timezone

from apps.products.models import Client, Item, Category, Material, Warehouse, ItemComposition
from apps.products.forms import ItemForm, ClientForm
from apps.workforce.models import Worker, JobWorker, Attendance
from apps.workforce.forms import WorkerForm, JobWorkerForm
from apps.ledger_pay.models import ItemWorkerAllocation, Loan, LaborPayment
from apps.production.models import StockTransaction
from apps.production.services import get_stock_by_item, get_overall_stock

def format_form_errors(form):
    error_messages = []
    for field, errors in form.errors.items():
        field_name = form.fields[field].label if field in form.fields else field.replace('_', ' ').title()
        for error in errors:
            error_messages.append(f"{field_name}: {error}")
    return " | ".join(error_messages)


def merge_bom_component_details(parent_item):
    """
    Merges and synchronizes Item details (Category, Material, Weights, Process Requirements)
    from all BOM component items to the parent Set/BOM item.
    """
    compositions = list(ItemComposition.objects.filter(parent_item=parent_item).select_related('component_item'))
    if not compositions:
        return

    categories = []
    materials = []
    clients = []
    
    total_casting_weight = 0.0
    total_machining_weight = 0.0
    
    first_comp = compositions[0].component_item
    
    for comp in compositions:
        item = comp.component_item
        qty = comp.quantity
        
        if item.category and item.category != 'OTHER' and item.category not in categories:
            categories.append(item.category)
        if item.material and item.material != 'OTHER' and item.material not in materials:
            materials.append(item.material)
            
        if item.client and item.client not in clients:
            clients.append(item.client)
            
        total_casting_weight += float(item.casting_weight or 0.0) * qty
        total_machining_weight += float(item.machining_weight or 0.0) * qty

    if categories:
        parent_item.category = " + ".join(categories)
    else:
        parent_item.category = first_comp.category
        
    if materials:
        parent_item.material = " + ".join(materials)
    else:
        parent_item.material = first_comp.material
        
    if clients:
        parent_item.client = clients[0]
    elif first_comp.client:
        parent_item.client = first_comp.client
        
    parent_item.casting_weight = total_casting_weight
    parent_item.machining_weight = total_machining_weight
    
    parent_item.lot_size = first_comp.lot_size
    parent_item.lot_with_box = first_comp.lot_with_box

    parent_item.save()


def sync_bom_worker_allocations(parent_item):
    """
    Automatically maps worker and job worker allocations from components of a parent Set/BOM
    to the parent Set item itself, aggregating (summing) rates per piece multiplied by quantity.
    """
    worker_rates = {}
    job_worker_rates = {}
    
    compositions = ItemComposition.objects.filter(parent_item=parent_item)
    for comp in compositions:
        qty = comp.quantity
        comp_item = comp.component_item
        allocs = ItemWorkerAllocation.objects.filter(item=comp_item)
        for alloc in allocs:
            contrib = float(alloc.rate_per_piece or 0.0) * qty
            if alloc.worker:
                worker_rates[alloc.worker] = worker_rates.get(alloc.worker, 0.0) + contrib
            if alloc.job_worker:
                job_worker_rates[alloc.job_worker] = job_worker_rates.get(alloc.job_worker, 0.0) + contrib

    ItemWorkerAllocation.objects.filter(item=parent_item).delete()

    for worker, rate in worker_rates.items():
        ItemWorkerAllocation.objects.create(
            item=parent_item,
            worker=worker,
            rate_per_piece=rate
        )
    for job_worker, rate in job_worker_rates.items():
        ItemWorkerAllocation.objects.create(
            item=parent_item,
            job_worker=job_worker,
            rate_per_piece=rate
        )


@login_required
def dashboard(request):
    """
    Dashboard view showing overall stock levels and today's metrics.
    """
    # Import inside function to avoid circular import loops
    from apps.production.views import create_default_warehouses
    create_default_warehouses()

    stock = get_overall_stock()
    items = Item.objects.all()
    stock_rows = []

    # Optimize N+1 queries by using bulk stock getter
    from apps.production.services import get_stock_for_all_items
    bulk_stocks = get_stock_for_all_items()

    for item in items:
        item_stock = bulk_stocks.get(item.id, {'ready': 0})
        ready_qty = item_stock.get('ready', 0)

        if ready_qty > 0:
            cartons, loose_pieces = item.calculate_cartons_and_loose(ready_qty)
            stock_rows.append({
                "code": item.code,
                "item": item,
                "cartons": cartons,
                "loose_pieces": loose_pieces,
                "total_pieces": ready_qty,
                "weight": round(ready_qty * float(item.machining_weight or 0), 3)
            })

    today = timezone.now().date()
    today_casting = StockTransaction.objects.filter(
        transaction_type='casting_entry',
        created_at__date=today
    )

    today_heats = today_casting.values("heat_no").distinct().count()
    today_pieces = today_casting.aggregate(total=Sum("quantity"))["total"] or 0
    today_weight = today_casting.aggregate(total=Sum("weight"))["total"] or 0

    today_dispatch = StockTransaction.objects.filter(
        transaction_type='dispatch_out',
        created_at__date=today
    ).select_related("item")
    
    dispatch_pieces = 0
    dispatch_cartons = 0
    dispatch_weight = 0

    for tx in today_dispatch:
        dispatch_pieces += tx.quantity or 0
        dispatch_weight += float(tx.weight or 0)
        if tx.item and tx.item.lot_with_box and tx.item.lot_with_box > 0:
            dispatch_cartons += (tx.quantity or 0) // tx.item.lot_with_box

    casting_avg_weight = round(float(today_weight) / today_pieces, 3) if today_pieces > 0 else 0.0
    casting_avg_heat_pcs = round(float(today_pieces) / today_heats, 1) if today_heats > 0 else 0.0
    casting_unique_items = today_casting.values("item").distinct().count()

    dispatch_avg_weight = round(float(dispatch_weight) / dispatch_pieces, 3) if dispatch_pieces > 0 else 0.0
    dispatch_unique_clients = today_dispatch.values("client").distinct().count()
    dispatch_unique_items = today_dispatch.values("item").distinct().count()

    context = {
        "casting_stock": stock['casting_qty'],
        "casting_weight": stock['casting_weight'],
        "machining_stock": stock['machining_qty'],
        "machining_weight": stock['machining_weight'],
        "polishing_stock": stock['polishing_qty'],
        "polishing_weight": stock['polishing_weight'],
        "ready_stock": stock['ready_qty'],
        "ready_weight": stock['ready_weight'],

        "today_heats": today_heats,
        "today_pieces": today_pieces,
        "today_weight": today_weight,
        "casting_avg_weight": casting_avg_weight,
        "casting_avg_heat_pcs": casting_avg_heat_pcs,
        "casting_unique_items": casting_unique_items,

        "dispatch_cartons": dispatch_cartons,
        "dispatch_pieces": dispatch_pieces,
        "dispatch_weight": dispatch_weight,
        "dispatch_avg_weight": dispatch_avg_weight,
        "dispatch_unique_clients": dispatch_unique_clients,
        "dispatch_unique_items": dispatch_unique_items,

        "stock_rows": stock_rows,
    }

    return render(request, "dashboard.html", context)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def master_data(request):
    from django.db.models import Q
    from apps.client_orders.models import LegalEntity

    # Resolve Active Company
    companies = LegalEntity.objects.all().order_by('name')
    if not companies.exists():
        # Auto-seed the 3 default companies
        LegalEntity.objects.create(
            name="C1 Casting Foundry",
            address="Plot A-1, Metal Casting Zone, Industrial Area",
            gst_number="24AAAAA1111A1Z1",
            phone="+91 98765 43210",
            letterhead_title="C1 CASTING FOUNDRY - Quality Castings Since 2010",
            processes="CASTING,PACKAGING,DISPATCH"
        )
        LegalEntity.objects.create(
            name="C2 Finishing Processor",
            address="Plot B-4, Machine Tools Sector, Phase 2",
            gst_number="24BBBBB2222B2Z2",
            phone="+91 87654 32109",
            letterhead_title="C2 FINISHING PROCESSORS - Precision Engineering",
            processes="MACHINING,POLISHING"
        )
        LegalEntity.objects.create(
            name="C3 Jobwork Supplier",
            address="Plot C-12, Ancillary Hub, Sector 4",
            gst_number="24CCCCC3333C3Z3",
            phone="+91 76543 21098",
            letterhead_title="C3 JOBWORK SERVICES - Industrial Vendor & Jobwork",
            processes="MACHINING,POLISHING"
        )
        companies = LegalEntity.objects.all().order_by('name')

    active_company_id = request.GET.get('active_company')
    if active_company_id is not None:
        if active_company_id == 'global':
            request.session['active_company_id'] = 'global'
        else:
            request.session['active_company_id'] = active_company_id
    
    session_company_id = request.session.get('active_company_id')
    
    active_company = None
    if session_company_id and session_company_id != 'global':
        active_company = LegalEntity.objects.filter(id=session_company_id).first()
        
    if session_company_id is None and companies.exists():
        active_company = companies.first()
        request.session['active_company_id'] = active_company.id

    active_tab = request.GET.get("tab", "items")
    edit_id = request.POST.get("edit_id") or request.GET.get("edit")
    edit_item = Item.objects.filter(id=edit_id).first() if edit_id else None
    
    edit_client = Client.objects.filter(id=request.GET.get("edit_client")).first()
    edit_worker = Worker.objects.filter(id=request.GET.get("edit_worker")).first()
    edit_job_worker = JobWorker.objects.filter(id=request.GET.get("edit_job_worker")).first()

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "item":
            data = request.POST.copy()
            data['item_type'] = request.POST.get('item_type', 'REGULAR')
            
            if not data.get('casting_weight'): data['casting_weight'] = 0
            if not data.get('machining_weight'): data['machining_weight'] = 0
            if not data.get('lot_size'): data['lot_size'] = 0
            if not data.get('lot_with_box'): data['lot_with_box'] = 0
            
            if data.get('custom_client'):
                client = Client.objects.filter(name=data.get('custom_client')).first()
                if client:
                    data['client'] = client.id
            if data.get('custom_material'):
                data['material'] = data.get('custom_material')
            
            data['casting_required'] = 'casting_required' in request.POST
            data['machining_required'] = 'machining_required' in request.POST
            data['polishing_required'] = 'polishing_required' in request.POST
            data['packing_required'] = 'packing_required' in request.POST
            
            form = ItemForm(data, instance=edit_item)
            if form.is_valid():
                item = form.save(commit=False)
                item.save()
                
                # Update Organizational Scope
                is_global = request.POST.get('scope_global') == 'true' or 'scope_global' in request.POST
                if is_global:
                    item.companies.clear()
                else:
                    scope_companies = request.POST.getlist('scope_companies')
                    if scope_companies:
                        item.companies.set(scope_companies)
                    elif active_company:
                        item.companies.set([active_company])
                    else:
                        item.companies.clear()
                
                if item.item_type != 'SET':
                    ItemWorkerAllocation.objects.filter(item=item).delete()
                    worker_ids = request.POST.getlist('worker_id[]')
                    worker_rates = request.POST.getlist('worker_rate[]')
                    
                    for wid, rate in zip(worker_ids, worker_rates):
                        if wid and rate:
                            try:
                                if wid.startswith('w_'):
                                    ItemWorkerAllocation.objects.create(
                                        item=item,
                                        worker_id=wid.replace('w_', ''),
                                        rate_per_piece=float(rate)
                                    )
                                elif wid.startswith('jw_'):
                                    ItemWorkerAllocation.objects.create(
                                        item=item,
                                        job_worker_id=wid.replace('jw_', ''),
                                        rate_per_piece=float(rate)
                                    )
                                else:
                                    ItemWorkerAllocation.objects.create(
                                        item=item,
                                        job_worker_id=wid,
                                        rate_per_piece=float(rate)
                                    )
                            except Exception:
                                pass

                if item.item_type != 'SET':
                    ItemComposition.objects.filter(parent_item=item).delete()
                    comp_ids = request.POST.getlist('component_id[]')
                    comp_qtys = request.POST.getlist('component_qty[]')
                    for cid, qty in zip(comp_ids, comp_qtys):
                        if cid and qty:
                            try:
                                ItemComposition.objects.create(
                                    parent_item=item,
                                    component_item_id=cid,
                                    quantity=int(qty)
                                )
                            except Exception:
                                pass

                if item.item_type == 'SET':
                    merge_bom_component_details(item)
                    sync_bom_worker_allocations(item)
                            
                messages.success(request, f"Item {'updated' if edit_item else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=items")
            else:
                messages.error(request, f"Error saving item: {format_form_errors(form)}")

        elif form_type == "client":
            client_id = request.POST.get('client_id')
            instance = None
            if client_id:
                instance = Client.all_objects.filter(id=client_id).first()
            elif edit_client:
                instance = edit_client
                
            form = ClientForm(request.POST, instance=instance)
            if form.is_valid():
                client = form.save(commit=False)
                client.save()
                
                # Update Organizational Scope
                is_global = request.POST.get('scope_global') == 'true' or 'scope_global' in request.POST
                if is_global:
                    client.companies.clear()
                else:
                    scope_companies = request.POST.getlist('scope_companies')
                    if scope_companies:
                        client.companies.set(scope_companies)
                    elif active_company:
                        client.companies.set([active_company])
                    else:
                        client.companies.clear()
                
                messages.success(request, f"Client {'updated' if edit_client else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=clients")
            else:
                messages.error(request, "Error saving client.")

        elif form_type == "worker":
            data = request.POST.copy()
            data['name'] = data.get('worker_name')
            data['process'] = data.get('worker_process')
            data['phone'] = data.get('worker_phone')
            data['employee_id'] = data.get('worker_employee_id')
            data['designation'] = data.get('worker_designation')
            data['joining_date'] = data.get('worker_joining_date') or None
            
            data['identity_number'] = data.get('worker_identity_number')
            data['emergency_contact_name'] = data.get('worker_emergency_name')
            data['emergency_contact_phone'] = data.get('worker_emergency_phone')
            data['blood_group'] = data.get('worker_blood_group')
            
            data['salary_model'] = data.get('worker_salary_model', 'DAILY')
            
            def to_float(val, default_val=0.0):
                if val is None or str(val).strip() == "":
                    return default_val
                try:
                    return float(val)
                except ValueError:
                    return default_val

            data['daily_rate'] = to_float(data.get('worker_daily_rate'), 0.0)
            data['standard_shift_hours'] = to_float(data.get('worker_shift_hours'), 8.0)
            data['monthly_fixed_salary'] = to_float(data.get('worker_fixed_salary'), 0.0)
            data['monthly_allowance'] = to_float(data.get('worker_monthly_allowance'), 0.0)
            data['overtime_rate'] = to_float(data.get('worker_ot_rate'), 0.0)
            
            worker_id = request.POST.get('worker_id')
            instance = None
            if worker_id:
                instance = Worker.objects.filter(id=worker_id).first()
            elif edit_worker:
                instance = edit_worker
                
            form = WorkerForm(data, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, f"Worker {'updated' if edit_worker else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=workers&sub=internal")
            else:
                messages.error(request, f"Error saving worker: {format_form_errors(form)}")

        elif form_type == "job_worker":
            data = request.POST.copy()
            data['name'] = data.get('jw_name')
            data['process'] = data.get('jw_process')
            data['jw_code'] = data.get('jw_code')
            data['phone'] = data.get('jw_phone')
            data['email'] = data.get('jw_email')
            data['address'] = data.get('jw_address')
            data['gst_number'] = data.get('jw_gst')
            
            jw_id = request.POST.get('jw_id')
            instance = None
            if jw_id:
                instance = JobWorker.objects.filter(id=jw_id).first()
            elif edit_job_worker:
                instance = edit_job_worker

            form = JobWorkerForm(data, instance=instance)
            if form.is_valid():
                instance = form.save()
                
                item_ids = request.POST.getlist('assigned_item_id[]')
                item_rates = request.POST.getlist('assigned_item_rate[]')
                
                if item_ids:
                    ItemWorkerAllocation.objects.filter(job_worker=instance).delete()
                    for i_id, i_rate in zip(item_ids, item_rates):
                        if i_id and i_rate:
                            ItemWorkerAllocation.objects.create(
                                job_worker=instance,
                                item_id=i_id,
                                rate_per_piece=float(i_rate)
                            )

                msg = f"Job Worker {'updated' if jw_id else 'created'} successfully."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'message': msg})
                messages.success(request, msg)
                return redirect(f"{reverse('master_data')}?tab=workers&sub=job")
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'errors': form.errors.as_json()}, status=400)
                messages.error(request, "Error saving job worker.")

        elif form_type == "bom":
            parent_id = request.POST.get('parent_item_id')
            new_set_name = request.POST.get('new_set_name')
            
            try:
                if new_set_name:
                    code = request.POST.get('new_set_code', '').strip()
                    if Item.objects.filter(code=code).exists():
                        messages.error(request, f"Error saving BOM: An item with code '{code}' already exists in the Item Master. Please choose a unique code.")
                        return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
                    
                    parent_item = Item.objects.create(
                        name=new_set_name,
                        code=code,
                        category=request.POST.get('category', 'OTHER'),
                        sub_category=request.POST.get('sub_category', ''),
                        variant=request.POST.get('variant', ''),
                        item_type='SET',
                        casting_required=request.POST.get('casting_required') == 'on',
                        machining_required=request.POST.get('machining_required') == 'on',
                        polishing_required=request.POST.get('polishing_required') == 'on',
                        packing_required=request.POST.get('packing_required') == 'on',
                        company=active_company
                    )
                else:
                    parent_item = Item.objects.get(id=parent_id)
                    parent_item.name = request.POST.get('parent_item_name', parent_item.name).strip()
                    code = request.POST.get('parent_item_code', '').strip()
                    if code and code != parent_item.code:
                        if Item.objects.filter(code=code).exists():
                            messages.error(request, f"Error updating BOM: An item with code '{code}' already exists in the Item Master. Please choose a unique code.")
                            return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
                        parent_item.code = code
                    
                    parent_item.category = request.POST.get('category', parent_item.category)
                    parent_item.sub_category = request.POST.get('sub_category', parent_item.sub_category)
                    parent_item.variant = request.POST.get('variant', parent_item.variant)
                    
                    custom_material = request.POST.get('custom_material')
                    if custom_material:
                        parent_item.material = custom_material
                        
                    custom_client = request.POST.get('custom_client')
                    if custom_client:
                        client = Client.objects.filter(name=custom_client).first()
                        if client:
                            parent_item.client = client
                            
                    parent_item.casting_required = request.POST.get('casting_required') == 'on'
                    parent_item.machining_required = request.POST.get('machining_required') == 'on'
                    parent_item.polishing_required = request.POST.get('polishing_required') == 'on'
                    parent_item.packing_required = request.POST.get('packing_required') == 'on'

                ItemComposition.objects.filter(parent_item=parent_item).delete()
                parent_item.item_type = 'SET'
                parent_item.save()

                comp_ids = request.POST.getlist('component_id[]')
                comp_qtys = request.POST.getlist('component_qty[]')
                
                total_weight = 0
                for cid, qty in zip(comp_ids, comp_qtys):
                    if cid and qty:
                        comp_obj = Item.objects.get(id=cid)
                        qty_int = int(qty)
                        total_weight += (comp_obj.machining_weight * qty_int)
                        
                        ItemComposition.objects.create(
                            parent_item=parent_item,
                            component_item=comp_obj,
                            quantity=qty_int
                        )
                
                merge_bom_component_details(parent_item)
                sync_bom_worker_allocations(parent_item)
                
                messages.success(request, f"BOM for {parent_item.name} saved successfully.")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")
            except Exception as e:
                messages.error(request, f"Error saving BOM: {str(e)}")
                return redirect(f"{reverse('master_data')}?tab=items&sub=bom")

        elif form_type == "delete_bom":
            parent_id = request.POST.get('parent_item_id')
            try:
                parent_item = Item.objects.get(id=parent_id)
                item_name = parent_item.name
                parent_item.delete()
                messages.success(request, f"Set '{item_name}' and its BOM deleted successfully.")
            except Exception as e:
                messages.error(request, f"CRITICAL ERROR: Could not delete Set. Details: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=bom")

        elif form_type == "category":
            name = request.POST.get('category_name', '').strip()
            if name:
                try:
                    Category.objects.get_or_create(name=name)
                    messages.success(request, f"Category '{name}' saved successfully.")
                except Exception as e:
                    messages.error(request, f"Error saving category: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=category")

        elif form_type == "delete_category":
            cat_id = request.POST.get('category_id')
            try:
                cat = Category.objects.get(id=cat_id)
                name = cat.name
                cat.delete()
                messages.success(request, f"Category '{name}' deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting category: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=category")

        elif form_type == "material":
            name = request.POST.get('material_name', '').strip()
            if name:
                try:
                    Material.objects.get_or_create(name=name)
                    messages.success(request, f"Material '{name}' saved successfully.")
                except Exception as e:
                    messages.error(request, f"Error saving material: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=material")

        elif form_type == "delete_material":
            mat_id = request.POST.get('material_id')
            try:
                mat = Material.objects.get(id=mat_id)
                name = mat.name
                mat.delete()
                messages.success(request, f"Material '{name}' deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting material: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=items&sub=material")

        elif form_type == "company":
            company_id = request.POST.get('company_id')
            try:
                if company_id:
                    company = LegalEntity.objects.get(id=company_id)
                    action = "updated"
                else:
                    company = LegalEntity()
                    action = "created"
                
                company.name = request.POST.get('company_name').strip()
                company.address = request.POST.get('company_address').strip()
                company.gst_number = request.POST.get('company_gst', '').strip() or None
                company.phone = request.POST.get('company_phone', '').strip() or None
                company.letterhead_title = request.POST.get('company_letterhead', '').strip() or None
                company.processes = request.POST.get('company_processes', '').strip()
                company.save()
                messages.success(request, f"Company '{company.name}' {action} successfully.")
            except Exception as e:
                messages.error(request, f"Error saving company details: {str(e)}")
            return redirect(f"{reverse('master_data')}?tab=company")


    # Scope all queries by active company
    all_items = Item.objects.all().prefetch_related('worker_allocations__worker', 'worker_allocations__job_worker')
    if active_company:
        all_items = all_items.filter(Q(companies=active_company) | Q(companies__isnull=True)).distinct()
    else:
        all_items = all_items.filter(companies__isnull=True).distinct()
        
    client_filter_id = request.GET.get('client_filter')
    items_to_display = all_items
    if client_filter_id and client_filter_id.strip():
        items_to_display = all_items.filter(client_id=client_filter_id)
    
    bom_items = all_items.filter(item_type='SET').distinct().prefetch_related(
        'components__component_item',
        'worker_allocations__worker',
        'worker_allocations__job_worker'
    )

    assembly_items = all_items.filter(components__isnull=False, active=True).distinct().order_by('code')
    recent_assemblies = StockTransaction.objects.filter(
        transaction_type='kitting_produce',
        item__in=all_items
    ).order_by('-created_at')[:20]

    client_list = Client.objects.all()
    if active_company:
        client_list = client_list.filter(Q(companies=active_company) | Q(companies__isnull=True)).distinct()
    else:
        client_list = client_list.filter(companies__isnull=True).distinct()
        
    client_list = client_list.annotate(
        item_count=Count('item')
    ).order_by('name')
    
    client_stats = {
        'total': client_list.count(),
        'cities': client_list.values('city').distinct().count(),
        'active': client_list.filter(active=True).count(),
    }

    context = {
        "companies": companies,
        "active_company": active_company,
        "clients": client_list,
        "client_stats": client_stats,
        "items": items_to_display,
        "bom_items": bom_items,
        "all_items": all_items,
        "assembly_items": assembly_items,
        "recent_assemblies": recent_assemblies,
        "workers": Worker.objects.all(),
        "job_workers": JobWorker.objects.all(),
        "edit_item_data": edit_item,
        "edit_client_data": edit_client,
        "edit_worker_data": edit_worker,
        "edit_job_worker_data": edit_job_worker,
        "active_tab": active_tab,
        "active_client_filter": client_filter_id,
        "categories": Category.objects.all().order_by('name'),
        "materials": Material.objects.all().order_by('name'),
        "deleted_items": Item.all_objects.filter(is_deleted=True).filter(Q(companies=active_company) | Q(companies__isnull=True)).distinct() if active_company else Item.all_objects.filter(is_deleted=True, companies__isnull=True).distinct(),
        "deleted_clients": Client.all_objects.filter(is_deleted=True).filter(Q(companies=active_company) | Q(companies__isnull=True)).distinct() if active_company else Client.all_objects.filter(is_deleted=True, companies__isnull=True).distinct(),
        "deleted_workers": Worker.all_objects.filter(is_deleted=True),
        "deleted_job_workers": JobWorker.all_objects.filter(is_deleted=True),
    }
    return render(request, "master_data.html", context)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def delete_item(request, item_id):
    try:
        item = Item.objects.get(id=item_id)
        item.delete()
        messages.success(request, "Item deleted successfully.")
    except Item.DoesNotExist:
        messages.error(request, "Item could not be found for deletion.")

    next_url = request.GET.get('next', 'master_data')
    if next_url == 'bom':
        target = f"{reverse('master_data')}?tab=items&sub=bom"
    elif next_url == 'assembly':
        target = f"{reverse('assembly')}?tab=bom"
    else:
        target = reverse('master_data')

    return redirect(target)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def delete_items_bulk(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('item_ids[]') or request.POST.get('item_ids', '').split(',')
        item_ids = [id_str.strip() for id_str in item_ids if id_str.strip()]
        
        if not item_ids:
            messages.warning(request, "No items were selected for deletion.")
            return redirect(reverse('master_data'))
            
        try:
            items_to_delete = Item.objects.filter(id__in=item_ids)
            count = items_to_delete.count()
            items_to_delete.delete()
            messages.success(request, f"Successfully deleted {count} items.")
        except Exception as e:
            messages.error(request, f"Error deleting items: {str(e)}")
            
    return redirect(reverse('master_data'))


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def delete_client(request, client_id):
    try:
        client = Client.objects.get(id=client_id)
        client_name = client.name
        client.delete()
        messages.success(request, f"Client '{client_name}' deleted successfully.")
    except Client.DoesNotExist:
        messages.error(request, "Client could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting client: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=clients")


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def recover_deleted_record(request, model_type, record_id):
    model_map = {
        'item': Item,
        'client': Client,
        'worker': Worker,
        'job_worker': JobWorker,
    }
    
    model = model_map.get(model_type)
    if not model:
        messages.error(request, "Invalid model type.")
        return redirect(f"{reverse('master_data')}?tab=trash")
        
    try:
        record = model.all_objects.get(id=record_id)
        record.is_deleted = False
        if hasattr(record, 'active'):
            record.active = True
        record.save()
        messages.success(request, f"Successfully restored {model_type.replace('_', ' ').title()}: '{record.name if hasattr(record, 'name') else record.code}'.")
    except model.DoesNotExist:
        messages.error(request, f"Could not find the deleted {model_type.replace('_', ' ')}.")
    except Exception as e:
        messages.error(request, f"Error recovering record: {str(e)}")
        
    return redirect(f"{reverse('master_data')}?tab=trash")


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def permanent_delete_record(request, model_type, record_id):
    model_map = {
        'item': Item,
        'client': Client,
        'worker': Worker,
        'job_worker': JobWorker,
    }
    
    model = model_map.get(model_type)
    if not model:
        messages.error(request, "Invalid model type.")
        return redirect(f"{reverse('master_data')}?tab=trash")
        
    try:
        record = model.all_objects.get(id=record_id)
        name_str = record.name if hasattr(record, 'name') else record.code
        record.hard_delete()
        messages.success(request, f"Permanently deleted {model_type.replace('_', ' ').title()}: '{name_str}'.")
    except model.DoesNotExist:
        messages.error(request, f"Could not find the deleted {model_type.replace('_', ' ')}.")
    except Exception as e:
        messages.error(request, f"Error permanently deleting record: {str(e)}")
        
    return redirect(f"{reverse('master_data')}?tab=trash")



@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def edit_item(request, item_id):
    item = Item.objects.get(id=item_id)

    if request.method == "POST":
        item.name = request.POST.get("item_name")
        item.code = request.POST.get("item_code")
        item.category = request.POST.get("category")
        item.casting_weight = float(request.POST.get("casting_weight") or 0)
        item.machining_weight = float(request.POST.get("machining_weight") or 0)

        try:
            item.save()
            messages.success(request, "Item updated successfully.")
        except Exception:
            messages.error(request, "Item could not be updated. Please try again.")

        return redirect("master_data")

    context = {
        "item": item
    }

    return render(request, "inventory/edit_item.html", context)


@login_required
@require_GET
def get_item_composition(request, item_id):
    try:
        item = Item.objects.get(id=item_id)
        compositions = item.components.all()
        data = []
        for comp in compositions:
            stock = get_stock_by_item(comp.component_item)
            data.append({
                'id': comp.component_item.id,
                'name': comp.component_item.name,
                'code': comp.component_item.code,
                'quantity': comp.quantity,
                'available': stock['polishing']
            })
        return JsonResponse({
            'name': item.name,
            'code': item.code,
            'category': item.category,
            'sub_category': item.sub_category or '',
            'variant': item.variant or '',
            'material': item.material or '',
            'client_name': item.client.name if item.client else '',
            'casting_required': item.casting_required,
            'machining_required': item.machining_required,
            'polishing_required': item.polishing_required,
            'packing_required': item.packing_required,
            'components': data
        })
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found'}, status=404)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def download_item_template(request):
    from apps.products.bulk_import import generate_csv_template, generate_xlsx_template, ITEM_HEADERS
    fmt = request.GET.get('format', 'xlsx')
    if fmt == 'csv':
        return generate_csv_template(ITEM_HEADERS, 'item_import_template')
    return generate_xlsx_template(ITEM_HEADERS, 'item_import_template')


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def download_worker_template(request):
    from apps.products.bulk_import import generate_csv_template, generate_xlsx_template, WORKER_HEADERS
    fmt = request.GET.get('format', 'xlsx')
    if fmt == 'csv':
        return generate_csv_template(WORKER_HEADERS, 'worker_import_template')
    return generate_xlsx_template(WORKER_HEADERS, 'worker_import_template')


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
def download_job_worker_template(request):
    from apps.products.bulk_import import generate_csv_template, generate_xlsx_template, JOB_WORKER_HEADERS
    fmt = request.GET.get('format', 'xlsx')
    if fmt == 'csv':
        return generate_csv_template(JOB_WORKER_HEADERS, 'job_worker_import_template')
    return generate_xlsx_template(JOB_WORKER_HEADERS, 'job_worker_import_template')


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_POST
def preview_import_data(request):
    from apps.products.bulk_import import parse_uploaded_file, validate_items_data, validate_workers_data, validate_job_workers_data
    
    import_type = request.POST.get('type')
    uploaded_file = request.FILES.get('file')
    
    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'}, status=400)
    
    if import_type not in ('items', 'workers', 'job_workers'):
        return JsonResponse({'status': 'error', 'message': 'Invalid import type.'}, status=400)
    
    try:
        headers, rows = parse_uploaded_file(uploaded_file)
        if not rows:
            return JsonResponse({'status': 'error', 'message': 'The uploaded file is empty.'}, status=400)
            
        if import_type == 'items':
            validated_rows = validate_items_data(rows)
        elif import_type == 'workers':
            validated_rows = validate_workers_data(rows)
        else:
            validated_rows = validate_job_workers_data(rows)
            
        # Check counts
        total = len(validated_rows)
        errors = sum(1 for r in validated_rows if r['action'] == 'ERROR')
        inserts = sum(1 for r in validated_rows if r['action'] == 'INSERT')
        updates = sum(1 for r in validated_rows if r['action'] == 'UPDATE')
        
        # Store in session for confirm step
        request.session['bulk_import_data'] = {
            'type': import_type,
            'rows': validated_rows
        }
        request.session.modified = True
        
        return JsonResponse({
            'status': 'success',
            'type': import_type,
            'total': total,
            'errors_count': errors,
            'inserts_count': inserts,
            'updates_count': updates,
            'rows': validated_rows
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Failed to parse file: {str(e)}'}, status=500)


@login_required
@require_role(['HR & Accounts Manager', 'System Admin'])
@require_POST
def confirm_import_data(request):
    from apps.products.bulk_import import commit_items_import, commit_workers_import, commit_job_workers_import
    
    import_data = request.session.get('bulk_import_data')
    if not import_data:
        return JsonResponse({
            'status': 'error', 
            'message': 'No import session found. Please upload and preview the file again.'
        }, status=400)
        
    import_type = import_data.get('type')
    validated_rows = import_data.get('rows')
    
    # Double check no errors exist
    has_errors = any(r['action'] == 'ERROR' for r in validated_rows)
    if has_errors:
        return JsonResponse({
            'status': 'error', 
            'message': 'Cannot confirm import because some rows contain errors.'
        }, status=400)
        
    try:
        if import_type == 'items':
            created, updated = commit_items_import(validated_rows)
        elif import_type == 'workers':
            created, updated = commit_workers_import(validated_rows)
        else:
            created, updated = commit_job_workers_import(validated_rows)
            
        # Clean up session
        if 'bulk_import_data' in request.session:
            del request.session['bulk_import_data']
        request.session.modified = True
        
        msg = f"Successfully imported data: Created {created} records, Updated {updated} records."
        messages.success(request, msg)
        
        return JsonResponse({
            'status': 'success',
            'message': msg
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error', 
            'message': f'Database save failed: {str(e)}'
        }, status=500)

