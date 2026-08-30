import json
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.utils import timezone

from apps.master_data.models import LegalEntity, Category, Material, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel, WorkerType
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem, Holiday

from apps.production.forms import ItemForm, ClientForm, WorkerForm, JobWorkerForm

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
    
    casting_req = False
    machining_req = False
    polishing_req = False
    packing_req = False
    
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
    Automatically maps worker allocations from components of a parent Set/BOM
    to the parent Set item itself, aggregating (summing) rates per piece multiplied by quantity.
    """
    worker_rates = {}
    
    compositions = ItemComposition.objects.filter(parent_item=parent_item)
    for comp in compositions:
        qty = comp.quantity
        comp_item = comp.component_item
        allocs = ItemWorkerAllocation.objects.filter(item=comp_item)
        for alloc in allocs:
            contrib = float(alloc.rate_per_piece or 0.0) * qty
            if alloc.worker:
                worker_rates[alloc.worker] = worker_rates.get(alloc.worker, 0.0) + contrib

    ItemWorkerAllocation.objects.filter(item=parent_item).delete()

    for worker, rate in worker_rates.items():
        ItemWorkerAllocation.objects.create(
            item=parent_item,
            worker=worker,
            rate_per_piece=rate
        )

# =====================================================
# MASTER DATA
# =====================================================

@staff_member_required
def master_data(request):
    def to_float(val, default_val=0.0):
        if val is None or str(val).strip() == "":
            return default_val
        try:
            return float(val)
        except ValueError:
            return default_val

    active_tab = request.GET.get("tab", "items")
    
    # Handle GET/POST data for editing
    edit_id = request.POST.get("edit_id") or request.GET.get("edit")
    edit_item = Item.objects.filter(id=edit_id).first() if edit_id else None
    
    edit_client = Client.objects.filter(id=request.GET.get("edit_client")).first()
    edit_worker = Worker.objects.filter(id=request.GET.get("edit_worker")).first()
    edit_job_worker = Worker.objects.filter(id=request.GET.get("edit_job_worker"), worker_type=WorkerType.JOB_WORKER).first()
    edit_holiday = Holiday.objects.filter(id=request.GET.get("edit_holiday")).first()

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "company":
            company_id = request.POST.get("company_id")
            if company_id:
                comp_instance = LegalEntity.objects.filter(id=company_id).first()
            else:
                comp_instance = LegalEntity()
            
            if comp_instance:
                comp_instance.name = request.POST.get("company_name", comp_instance.name or "").strip()
                comp_instance.gst_number = request.POST.get("company_gst", comp_instance.gst_number or "").strip()
                comp_instance.phone = request.POST.get("company_phone", comp_instance.phone or "").strip()
                comp_instance.address = request.POST.get("company_address", comp_instance.address or "").strip()
                comp_instance.letterhead_title = request.POST.get("company_letterhead", comp_instance.letterhead_title or "").strip()
                
                # Save workflow flags
                comp_instance.handles_casting = "handles_casting" in request.POST
                comp_instance.handles_machining = "handles_machining" in request.POST
                comp_instance.handles_polishing = "handles_polishing" in request.POST
                comp_instance.handles_packaging = "handles_packaging" in request.POST
                
                # Save weekly off settings
                comp_instance.weekly_off = int(request.POST.get("weekly_off", 6))
                comp_instance.is_weekly_off_paid = "is_weekly_off_paid" in request.POST
                
                comp_instance.save()
                if company_id:
                    messages.success(request, f"Company Profile for '{comp_instance.name}' updated successfully.")
                else:
                    messages.success(request, f"Company '{comp_instance.name}' created successfully.")
            else:
                messages.error(request, "Company could not be found.")
            return redirect(f"{reverse('master_data')}?tab=companies")
            
        elif form_type == "item":
            data = request.POST.copy()
            data['item_type'] = request.POST.get('item_type', 'REGULAR')
            
            # Default empty numeric fields to 0
            if not data.get('casting_weight'): data['casting_weight'] = 0
            if not data.get('machining_weight'): data['machining_weight'] = 0
            if not data.get('lot_size'): data['lot_size'] = 0
            if not data.get('lot_with_box'): data['lot_with_box'] = 0
            if not data.get('min_casting_stock'): data['min_casting_stock'] = 0
            if not data.get('min_machining_stock'): data['min_machining_stock'] = 0
            if not data.get('min_polishing_stock'): data['min_polishing_stock'] = 0
            if not data.get('min_ready_stock'): data['min_ready_stock'] = 0
            
            if not data.get('yield_pcs_per_unit'): data['yield_pcs_per_unit'] = 1.0
            if not data.get('uom'): data['uom'] = 'PCS'
            data['is_raw_material'] = 'is_raw_material' in request.POST
            
            custom_client = data.get('custom_client', '').strip()
            if custom_client:
                client = Client.objects.filter(name__iexact=custom_client).first() or Client.objects.filter(client_code__iexact=custom_client).first()
                if client:
                    data['client'] = client.id
            else:
                data['client'] = ''
            if data.get('custom_material'):
                data['material'] = data.get('custom_material')
            
            # Checkboxes handle False state
            data['casting_required'] = 'casting_required' in request.POST
            data['machining_required'] = 'machining_required' in request.POST
            data['polishing_required'] = 'polishing_required' in request.POST
            data['packing_required'] = 'packing_required' in request.POST
            
            form = ItemForm(data, instance=edit_item)
            if form.is_valid():
                item = form.save(commit=False)
                if item.client:
                    item.company = item.client.company
                elif request.company:
                    item.company = request.company
                item.save()

                
                # Only modify worker allocations directly if it is NOT a Set/BOM item
                if item.item_type != 'SET':
                    ItemWorkerAllocation.objects.filter(item=item).delete()
                    worker_ids = request.POST.getlist('worker_id[]')
                    worker_rates = request.POST.getlist('worker_rate[]')
                    
                    for wid, rate in zip(worker_ids, worker_rates):
                        if wid and wid.strip():
                            try:
                                r_val = float(rate) if rate and rate.strip() else 0.0
                            except ValueError:
                                r_val = 0.0
                            try:
                                # Handle prefixes for Internal vs Job Worker
                                clean_wid = wid.replace('w_', '').replace('jw_', '')
                                w_obj = Worker.objects.filter(id=clean_wid).first()
                                if w_obj:
                                    ItemWorkerAllocation.objects.create(
                                        item=item,
                                        worker=w_obj,
                                        rate_per_piece=r_val
                                    )
                            except Exception:
                                pass

                # Only modify compositions if it is NOT a Set/BOM item (managed inside BOM drawer instead)
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

                # Sync details and allocations from components if it is a SET
                if item.item_type == 'SET':
                    merge_bom_component_details(item)
                    sync_bom_worker_allocations(item)
                            
                messages.success(request, f"Item {'updated' if edit_item else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=items")
            else:
                print("ITEM FORM ERRORS:", form.errors)
                messages.error(request, f"Error saving item: {format_form_errors(form)}")

        elif form_type == "client":
            data = request.POST.copy()
            data['name'] = data.get('client_name')
            data['phone'] = data.get('client_phone')
            data['email'] = data.get('client_email')
            data['city'] = data.get('client_city')
            data['address'] = data.get('client_address')
            data['gst_number'] = data.get('client_gst')
            data['company'] = data.get('client_company')
            
            # Prioritize hidden ID from POST for edits
            client_id = request.POST.get('client_id')
            instance = None
            if client_id:
                instance = Client.objects.filter(id=client_id).first()
            elif edit_client:
                instance = edit_client
                
            form = ClientForm(data, instance=instance)
            if form.is_valid():
                client = form.save(commit=False)
                if not client.company and request.company:
                    client.company = request.company
                client.save()
                messages.success(request, f"Client {'updated' if edit_client else 'created'} successfully.")
                return redirect(f"{reverse('master_data')}?tab=clients")
            else:
                print("CLIENT FORM ERRORS:", form.errors)
                messages.error(request, f"Error saving client: {form.errors}")

        elif form_type == "worker":
            data = request.POST.copy()
            data['name'] = data.get('worker_name')
            data['process'] = data.get('worker_process')
            data['phone'] = data.get('worker_phone')
            
            data['daily_rate'] = to_float(data.get('worker_daily_rate'), 0.0)
            
            # Professional HR Fields
            emp_id = data.get('worker_employee_id', '').strip()
            if emp_id:
                data['employee_id'] = emp_id
            else:
                data['employee_id'] = None
                
            data['designation'] = data.get('worker_designation')
            data['joining_date'] = data.get('worker_joining_date') or None
            data['standard_shift_hours'] = to_float(data.get('worker_shift_hours'), 8.0)
            data['identity_number'] = data.get('worker_identity_no')
            data['emergency_contact_name'] = data.get('worker_emergency_name')
            data['emergency_contact_phone'] = data.get('worker_emergency_phone')
            data['blood_group'] = data.get('worker_blood_group')
            
            # Salary Fields
            data['salary_model'] = data.get('worker_salary_model', 'DAILY')
            data['monthly_fixed_salary'] = to_float(data.get('worker_fixed_salary'), 0.0)
            data['fixed_salary_calc_mode'] = data.get('worker_fixed_salary_calc_mode', 'PRO_RATA')
            data['monthly_allowance'] = to_float(data.get('worker_monthly_allowance'), 0.0)
            data['allowance_calc_mode'] = data.get('worker_allowance_calc_mode', 'FIXED')
            data['overtime_rate'] = to_float(data.get('worker_ot_rate'), 0.0)
            data['casting_rate_per_kg'] = to_float(data.get('worker_casting_rate_per_kg'), 0.0)
            data['company'] = data.get('worker_company')
            data['active'] = 'active' in request.POST
            
            # Prioritize hidden ID from POST for edits
            worker_id = request.POST.get('worker_id')
            instance = None
            if worker_id:
                instance = Worker.objects.filter(id=worker_id).first()
            elif edit_worker:
                instance = edit_worker
                
            form = WorkerForm(data, instance=instance)
            if form.is_valid():
                worker = form.save(commit=False)
                if not worker.company and request.company:
                    worker.company = request.company
                worker.save()
                
                # Log Worker Rate History if rates changed
                last_hist = worker.rate_history.order_by('-effective_from', '-created_at').first()
                if not last_hist or last_hist.daily_rate != worker.daily_rate or last_hist.monthly_fixed_salary != worker.monthly_fixed_salary or last_hist.overtime_rate != worker.overtime_rate or last_hist.monthly_allowance != worker.monthly_allowance:
                    from apps.authentication.models import WorkerRateHistory
                    eff_date = (worker.joining_date or timezone.now().date()) if not last_hist else timezone.now().date()
                    WorkerRateHistory.objects.create(
                        worker=worker,
                        daily_rate=worker.daily_rate,
                        monthly_fixed_salary=worker.monthly_fixed_salary,
                        overtime_rate=worker.overtime_rate,
                        monthly_allowance=worker.monthly_allowance,
                        effective_from=eff_date
                    )
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
            data['casting_rate_per_kg'] = to_float(data.get('jw_casting_rate_per_kg'), 0.0)
            data['company'] = data.get('jw_company')
            data['active'] = 'active' in request.POST
            
            # Prioritize hidden ID over GET param for edits
            jw_id = request.POST.get('jw_id')
            instance = None
            if jw_id:
                instance = Worker.objects.filter(id=jw_id, worker_type=WorkerType.JOB_WORKER).first()
            elif edit_job_worker:
                instance = edit_job_worker

            form = JobWorkerForm(data, instance=instance)
            if form.is_valid():
                instance = form.save(commit=False)
                instance.worker_type = WorkerType.JOB_WORKER
                if not instance.company and request.company:
                    instance.company = request.company
                instance.save()

                # Process Item Allocations
                item_ids = request.POST.getlist('assigned_item_id[]')
                item_rates = request.POST.getlist('assigned_item_rate[]')
                
                if item_ids:
                    ItemWorkerAllocation.objects.filter(worker=instance).delete()
                    from apps.production.models import ItemWorkerRateHistory
                    for i_id, i_rate in zip(item_ids, item_rates):
                        if i_id and i_id.strip():
                            try:
                                r_val = float(i_rate) if i_rate and i_rate.strip() else 0.0
                            except ValueError:
                                r_val = 0.0
                            alloc = ItemWorkerAllocation.objects.create(
                                worker=instance,
                                item_id=i_id,
                                rate_per_piece=r_val
                            )
                            # Log Item Worker Rate History
                            last_rh = ItemWorkerRateHistory.objects.filter(worker=instance, item_id=i_id).order_by('-effective_from', '-created_at').first()
                            if not last_rh or last_rh.rate_per_piece != r_val:
                                ItemWorkerRateHistory.objects.create(
                                    allocation=alloc,
                                    worker=instance,
                                    item_id=i_id,
                                    rate_per_piece=r_val,
                                    effective_from=timezone.now().date()
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
                    
                    # Create a NEW Item for the Set with custom process requirements
                    parent_item = Item.objects.create(
                        name=new_set_name,
                        code=code,
                        category=request.POST.get('category', 'OTHER'),
                        sub_category=request.POST.get('sub_category', ''),
                        variant=request.POST.get('variant', ''),
                        item_type='SET',
                        company=request.company,
                        casting_required=request.POST.get('casting_required') == 'on',
                        machining_required=request.POST.get('machining_required') == 'on',
                        polishing_required=request.POST.get('polishing_required') == 'on',
                        packing_required=request.POST.get('packing_required') == 'on'
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
                        parent_item.category = request.POST.get('category', parent_item.category)
                    parent_item.sub_category = request.POST.get('sub_category', parent_item.sub_category)
                    parent_item.variant = request.POST.get('variant', parent_item.variant)
                    
                    parent_item.casting_required = request.POST.get('casting_required') == 'on'
                    parent_item.machining_required = request.POST.get('machining_required') == 'on'
                    parent_item.polishing_required = request.POST.get('polishing_required') == 'on'
                    parent_item.packing_required = request.POST.get('packing_required') == 'on'

                # Match and set Client & Company robustly for BOTH new and updated sets
                custom_client = request.POST.get('custom_client', '').strip()
                if custom_client:
                    client = Client.objects.filter(name__iexact=custom_client).first() or Client.objects.filter(client_code__iexact=custom_client).first()
                    if client:
                        parent_item.client = client
                        parent_item.company = client.company
                else:
                    parent_item.client = None
                    if request.company:
                        parent_item.company = request.company
                    else:
                        parent_item.company = None

                custom_material = request.POST.get('custom_material')
                if custom_material:
                    parent_item.material = custom_material

                parent_item.save()


                ItemComposition.objects.filter(parent_item=parent_item).delete()
                
                # Ensure it's marked as SET
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
                
                # Auto-merge component details and map worker allocations
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
                parent_item.delete()  # This also deletes ItemComposition via CASCADE
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

        elif form_type == "holiday":
            holiday_id = request.POST.get('holiday_id')
            date_val = request.POST.get('holiday_date')
            name_val = request.POST.get('holiday_name', '').strip()
            company_id = request.POST.get('holiday_company')
            is_paid_val = 'holiday_is_paid' in request.POST
            is_working_day_override_val = 'holiday_is_working_day_override' in request.POST

            if not date_val or not name_val:
                messages.error(request, "Holiday date and name are required.")
                return redirect(f"{reverse('master_data')}?tab=holidays")

            try:
                # Resolve company
                comp = None
                if company_id and company_id.strip():
                    comp = LegalEntity.objects.get(id=company_id)

                if holiday_id:
                    holiday = Holiday.objects.get(id=holiday_id)
                    holiday.date = date_val
                    holiday.name = name_val
                    holiday.company = comp
                    holiday.is_paid = is_paid_val
                    holiday.is_working_day_override = is_working_day_override_val
                    holiday.save()
                    messages.success(request, f"Holiday '{name_val}' updated successfully.")
                else:
                    Holiday.objects.create(
                        date=date_val,
                        name=name_val,
                        company=comp,
                        is_paid=is_paid_val,
                        is_working_day_override=is_working_day_override_val
                    )
                    messages.success(request, f"Holiday '{name_val}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error saving holiday: {str(e)}")

            return redirect(f"{reverse('master_data')}?tab=holidays")

    show_inactive = request.GET.get('show_inactive') == 'true'

    active_company = request.company
    if active_company:
        if active_company.id == 1: # NC (Casting Foundry)
            # NC needs to manage casting weights & rates for all cast components, but hides non-casting finished SET items
            all_items = Item.objects.filter(
                Q(company=active_company) | Q(casting_required=True)
            ).exclude(item_type='SET').order_by('code').prefetch_related('worker_allocations__worker')
        else: # OM (Finishing, Packaging, Sales)
            all_items = Item.objects.filter(
                Q(company=active_company) | Q(company__isnull=True)
            ).order_by('code').prefetch_related('worker_allocations__worker')
        recent_assemblies = StockTransaction.objects.filter(transaction_type='kitting_produce', item__company=active_company).order_by('-created_at')[:20]
        client_list = Client.objects.filter(company=active_company).annotate(
            item_count=Count('items')
        ).order_by('name')
        workers = Worker.objects.filter(company=active_company, active=True, worker_type=WorkerType.IN_HOUSE)
        job_workers = Worker.objects.filter(company=active_company, active=True, worker_type=WorkerType.JOB_WORKER)
        holidays = Holiday.objects.filter(Q(company=active_company) | Q(company__isnull=True)).order_by('-date')
    else:
        all_items = Item.objects.all().prefetch_related('worker_allocations__worker')
        recent_assemblies = StockTransaction.objects.filter(transaction_type='kitting_produce').order_by('-created_at')[:20]
        client_list = Client.objects.all().annotate(
            item_count=Count('items')
        ).order_by('name')
        workers = Worker.objects.filter(active=True, worker_type=WorkerType.IN_HOUSE)
        job_workers = Worker.objects.filter(active=True, worker_type=WorkerType.JOB_WORKER)
        holidays = Holiday.objects.all().order_by('-date')
    
    # Filter items by client if requested
    client_filter_id = request.GET.get('client_filter')
    items_to_display = all_items
    if client_filter_id and client_filter_id.strip():
        items_to_display = all_items.filter(client_id=client_filter_id)
    
    # Items for the BOM tab (show all SET items so empty/new ones can be configured too)
    bom_items = all_items.filter(item_type='SET').distinct().prefetch_related(
        'components__component_item',
        'worker_allocations__worker'
    )


    # Assembly / Kitting support inside Master Data BOM tab
    assembly_items = all_items.filter(components__isnull=False, active=True).distinct().order_by('code')

    # Client Stats for the dashboard
    c1_clients = client_list.filter(company_id=1)
    c2_clients = client_list.filter(company_id=2)
    
    client_stats = {
         'total': client_list.count(),
         'cities': client_list.values('city').distinct().count(),
         'active': client_list.filter(active=True).count(),
    }

    if show_inactive:
        c1_workers = Worker.objects.filter(company_id=1, worker_type=WorkerType.IN_HOUSE)
        c2_workers = Worker.objects.filter(company_id=2, worker_type=WorkerType.IN_HOUSE)
        c1_job_workers = Worker.objects.filter(company_id=1, worker_type=WorkerType.JOB_WORKER)
        c2_job_workers = Worker.objects.filter(company_id=2, worker_type=WorkerType.JOB_WORKER)
    else:
        c1_workers = Worker.objects.filter(company_id=1, active=True, worker_type=WorkerType.IN_HOUSE)
        c2_workers = Worker.objects.filter(company_id=2, active=True, worker_type=WorkerType.IN_HOUSE)
        c1_job_workers = Worker.objects.filter(company_id=1, active=True, worker_type=WorkerType.JOB_WORKER)
        c2_job_workers = Worker.objects.filter(company_id=2, active=True, worker_type=WorkerType.JOB_WORKER)

    company1 = LegalEntity.objects.filter(id=1).first()
    company2 = LegalEntity.objects.filter(id=2).first()

    context = {
        "companies": LegalEntity.objects.all(),
        "company1": company1,
        "company2": company2,
        "clients": client_list,
        "c1_clients": c1_clients,
        "c2_clients": c2_clients,
        "client_stats": client_stats,
        "items": items_to_display,             # Show filtered or all items
        "bom_items": bom_items,         # Only actual sets in the BOM tab
        "all_items": all_items,         # For the Quick Set Creator
        "assembly_items": assembly_items,  # For the Kitting Assemble dropdown
        "recent_assemblies": recent_assemblies,  # For the Kitting logs history
        "workers": workers,
        "c1_workers": c1_workers,
        "c2_workers": c2_workers,
        "job_workers": job_workers,
        "c1_job_workers": c1_job_workers,
        "c2_job_workers": c2_job_workers,
        "edit_item_data": edit_item,
        "edit_client_data": edit_client,
        "edit_worker_data": edit_worker,
        "edit_job_worker_data": edit_job_worker,
        "edit_holiday_data": edit_holiday,
        "holidays": holidays,
        "active_tab": active_tab,
        "active_client_filter": client_filter_id,
        "categories": Category.objects.all().order_by('name'),
        "materials": Material.objects.all().order_by('name'),
        "show_inactive": show_inactive,
    }

    # Fetch Automated Maintenance configuration and history logs for the new tab
    try:
        from apps.production.views.import_export_hub import run_automatic_maintenance_checks, run_financial_audit
        run_automatic_maintenance_checks()
        is_clear, blockers = run_financial_audit()
    except Exception:
        is_clear, blockers = True, []

    from apps.master_data.models import MaintenanceSettings, MaintenanceLog
    maintenance_settings, _ = MaintenanceSettings.objects.get_or_create(id=1)
    maintenance_logs = MaintenanceLog.objects.all()[:15]

    context.update({
        "maintenance_settings": maintenance_settings,
        "maintenance_logs": maintenance_logs,
        "is_clear": is_clear,
        "blockers": blockers
    })

    return render(request, "master_data.html", context)

@staff_member_required
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

@staff_member_required
def delete_items_bulk(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('item_ids[]') or request.POST.get('item_ids', '').split(',')
        # Clean up empty strings
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

@staff_member_required

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

@staff_member_required
def delete_worker(request, worker_id):
    try:
        worker = Worker.objects.get(id=worker_id)
        worker_name = worker.name
        worker.delete()
        messages.success(request, f"Worker '{worker_name}' deleted successfully.")
    except Worker.DoesNotExist:
        messages.error(request, "Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=internal")

@staff_member_required
def delete_job_worker(request, job_worker_id):
    try:
        jw = Worker.objects.filter(id=job_worker_id, worker_type=WorkerType.JOB_WORKER).first()
        if jw:
            jw_name = jw.name
            jw.delete()
            messages.success(request, f"Job Worker '{jw_name}' deleted successfully.")
        else:
            messages.error(request, "Job Worker could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting job worker: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=workers&sub=job")


@staff_member_required
def delete_holiday(request, holiday_id):
    try:
        holiday = Holiday.objects.get(id=holiday_id)
        name = holiday.name
        holiday.delete()
        messages.success(request, f"Holiday '{name}' deleted successfully.")
    except Holiday.DoesNotExist:
        messages.error(request, "Holiday could not be found.")
    except Exception as e:
        messages.error(request, f"Error deleting holiday: {str(e)}")
    
    return redirect(f"{reverse('master_data')}?tab=holidays")

@staff_member_required
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
            messages.success(
                request,
                "Item updated successfully."
            )
        except Exception:
            messages.error(
                request,
                "Item could not be updated. Please try again."
            )

        return redirect("master_data")

    context = {
        "item": item
    }

    return render(
        request,
        "inventory/edit_item.html",
        context
    )

@staff_member_required
def toggle_worker_active(request, worker_id):
    try:
        worker = Worker.objects.get(id=worker_id)
        worker.active = not worker.active
        worker.save()
        status_str = "Activated" if worker.active else "Deactivated"
        messages.success(request, f"Worker '{worker.name}' status has been set to {status_str}.")
    except Worker.DoesNotExist:
        messages.error(request, "Worker not found.")
    
    sub_tab = request.GET.get('sub', 'internal')
    return redirect(f"{reverse('master_data')}?tab=workers&sub={sub_tab}")

@staff_member_required
def toggle_job_worker_active(request, job_worker_id):
    jw = Worker.objects.filter(id=job_worker_id, worker_type=WorkerType.JOB_WORKER).first()
    if jw:
        jw.active = not jw.active
        jw.save()
        status_str = "Activated" if jw.active else "Deactivated"
        messages.success(request, f"Job Worker '{jw.name}' status has been set to {status_str}.")
    else:
        messages.error(request, "Job Worker not found.")
        
    sub_tab = request.GET.get('sub', 'job')
    return redirect(f"{reverse('master_data')}?tab=workers&sub={sub_tab}")

