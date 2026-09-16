import csv
import io
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.core import serializers
from django.utils import timezone
from django.urls import reverse

from apps.master_data.models import (
    LegalEntity, Client, Item, ItemComposition, Category, Material,
    Warehouse, MaintenanceSettings, MaintenanceLog
)
from apps.authentication.models import Worker, ProcessType, SalaryModel, WorkerType
from apps.production.models import (
    ItemWorkerAllocation, StockTransaction, Attendance, Loan,
    LaborPayment, Carton, CartonItem
)
from apps.orders.models import SalesOrder, SalesOrderItem, Dispatch, DispatchItem

def to_float(val, default_val=0.0):
    if val is None or str(val).strip() == "":
        return default_val
    try:
        return float(val)
    except ValueError:
        return default_val

def to_int(val, default_val=0):
    if val is None or str(val).strip() == "":
        return default_val
    try:
        return int(float(val))
    except ValueError:
        return default_val

def to_bool(val):
    if val is None:
        return False
    val_str = str(val).strip().lower()
    return val_str in ('true', '1', 'yes', 'y', 't', 'active')

def parse_rates_string(rates_str):
    """
    Parses a complex multi-rate string (e.g. K0:8,K1:8,K2:9 or D0,D1:5.5) and 
    returns a dict of {item_code: rate_float}. Supports period, semicolon, and comma groupings.
    """
    allocs = {}
    if not rates_str:
        return allocs
    
    # Strip whitespace and trailing dots/semicolons/commas
    s = str(rates_str).strip()
    while s and s[-1] in ('.', ';', ','):
        s = s[:-1].strip()
        
    if not s:
        return allocs
        
    # Replace group separator periods (i.e. those not surrounded by digits on both sides) and semicolons with ';'
    chars = list(s)
    for idx in range(len(chars)):
        if chars[idx] == ';':
            chars[idx] = ';'
        elif chars[idx] == '.':
            # Check if it is a decimal point
            is_decimal = False
            if idx > 0 and idx + 1 < len(chars):
                if chars[idx-1].isdigit() and chars[idx+1].isdigit():
                    is_decimal = True
            if not is_decimal:
                chars[idx] = ';'
                
    s = "".join(chars)
    
    # Split by semicolons into major groups
    major_groups = [g.strip() for g in s.split(';') if g.strip()]
    
    for group in major_groups:
        if ':' not in group:
            continue
            
        # We split the group by colons.
        # e.g. group = "K0:8,K1:8" -> ["K0", "8,K1", "8"]
        # e.g. group = "K0,K1:8" -> ["K0,K1", "8"]
        parts = group.split(':')
        
        current_items = [i.strip() for i in parts[0].split(',') if i.strip()]
        
        for i in range(1, len(parts)):
            part = parts[i].strip()
            # If it's the last part, it's just the rate value
            if i == len(parts) - 1:
                try:
                    rate_val = float(part)
                    for code in current_items:
                        allocs[code.upper()] = rate_val
                except ValueError:
                    pass
            else:
                # This part contains "rate,next_items"
                sub_parts = part.split(',', 1)
                rate_str_val = sub_parts[0].strip()
                try:
                    rate_val = float(rate_str_val)
                    for code in current_items:
                        allocs[code.upper()] = rate_val
                except ValueError:
                    pass
                
                # The remaining part of sub_parts is the next set of items
                if len(sub_parts) > 1:
                    current_items = [item.strip() for item in sub_parts[1].split(',') if item.strip()]
                else:
                    current_items = []
                    
    return allocs



def get_company_shortcuts():
    from apps.master_data.models import LegalEntity
    shortcuts = []
    for c in LegalEntity.objects.all():
        if "(" in c.name and ")" in c.name:
            shortcuts.append(c.name.split("(")[-1].replace(")", "").strip().upper())
        else:
            shortcuts.append(c.name.strip().upper())
    return "/".join(sorted(list(set(shortcuts)))) or "NC/OM"

def get_category_shortcuts():
    from apps.master_data.models import Category
    db_cats = sorted([c.name.upper() for c in Category.objects.all()])
    return "/".join(db_cats) or "BRASS/MORTAR/PESTLE/CHOPPING_BOARD/OTHER"

def get_material_shortcuts():
    from apps.master_data.models import Material
    db_mats = sorted([m.name.upper() for m in Material.objects.all()])
    return "/".join(db_mats) or "BRASS/IRON/OTHER"


@staff_member_required
def download_template(request, template_type):
    """
    Generates and returns an empty, ready-to-use CSV template for bulk imports.
    """
    response = HttpResponse(content_type='text/csv')
    
    if request.company:
        c = request.company
        if "(" in c.name and ")" in c.name:
            co_shortcuts = c.name.split("(")[-1].replace(")", "").strip().upper()
        else:
            co_shortcuts = c.name.strip().upper()
    else:
        co_shortcuts = get_company_shortcuts()
    cat_shortcuts = get_category_shortcuts()
    mat_shortcuts = get_material_shortcuts()
    
    if template_type == 'items':
        response['Content-Disposition'] = 'attachment; filename="items_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Item Code*', 'Item Name*', f'Category ({cat_shortcuts})*', 'Sub Category', f'Material ({mat_shortcuts})', 'Variant',
            'Casting Weight (kg)', 'Machining Weight (kg)', 'Casting Required (YES/NO)', 'Machining Required (YES/NO)',
            'Polishing Required (YES/NO)', 'Packing Required (YES/NO)', 'Lot Size (pcs)', 'Lot With Box (pcs)', 'Standard Rate per Piece (₹)',
            'Min Casting Stock (pcs)', 'Min Machining Stock (pcs)', 'Min Polishing Stock (pcs)', 'Min Ready Stock (pcs)',
            'Is Raw Material (YES/NO)', 'Raw Material Item Code', 'Yield (Pcs per Unit)', 'UOM (PCS/KG/CHAAD/FEET/INCH/CM/MM)',
            f'Company Scope ({co_shortcuts}/GLOBAL)*', 'Client Scope', 'Worker Piece-Rates (WorkerName:Rate; WorkerName:Rate)'
        ])
        writer.writerow([
            'BR-001', '6 Inch Brass Pestle', 'PESTLE', 'Brass Classic', 'BRASS', 'Standard Finish',
            '1.45', '1.30', 'YES', 'YES', 'YES', 'YES', '24', '24', '12.50',
            '10', '15', '20', '50',
            'NO', 'SS-ROD-01', '48.0', 'PCS',
            'GLOBAL', 'Mahadev Metal Works', 'Ram Singh:12.50; Shyam Lal:10.00'
        ])
    elif template_type == 'clients':
        response['Content-Disposition'] = 'attachment; filename="clients_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Client Name*', 'GSTIN Number', 'Phone', 'Email', 'City', 'Billing Address', f'Company Scope ({co_shortcuts})*', 'Client Code (Leave blank for auto-generate)'
        ])
        writer.writerow([
            'Mahadev Metal Works', '07AAAAA1111A1Z1', '9876543210', 'billing@mahadev.com', 'Delhi', 'Sector 5, Rohini', 'NC', ''
        ])
    elif template_type == 'employees':
        response['Content-Disposition'] = 'attachment; filename="employees_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Worker Code (Leave blank for auto-generate)', 'Name*', f'Company Scope ({co_shortcuts})*', 'Phone', 'Department Process (casting/machining/polishing/packaging)*', 'Salary Type (DAILY/FIXED)*',
            'Daily Wage Rate (₹ - Daily Employees)', 'Monthly Fixed Salary (₹ - Fixed Employees)', 'Monthly Allowance (₹)', 'Standard Shift (Hours/Day)', 'Overtime Rate (₹/Hour)', 'Casting Piece-Rate (₹/kg)', 'Designation',
            'Rates (ItemCode:Rate,ItemCode:Rate,...)', 'Active (YES/NO)'
        ])
        writer.writerow([
            '', 'Ram Singh', 'NC', '9988776655', 'machining', 'DAILY',
            '500.0', '0.0', '0.0', '8.0', '62.50', '12.0', 'Lathe Machine Operator', 'K0:8,K1:8,K2:9', 'YES'
        ])
    elif template_type == 'job_workers':
        response['Content-Disposition'] = 'attachment; filename="job_workers_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Worker Code (Leave blank for auto-generate)', 'Name*', f'Company Scope ({co_shortcuts})*', 'Phone', 'Department Process (casting/machining/polishing/packaging)*', 'Casting Piece-Rate (₹/kg)',
            'Vendor Address', 'Vendor Email', 'Vendor GSTIN',
            'Rates (ItemCode:Rate,ItemCode:Rate,...)', 'Active (YES/NO)'
        ])
        writer.writerow([
            '', 'Shyam Lal', 'OM', '9876543222', 'polishing', '0.0',
            'Street B', 'shyam@gmail.com', '07BBBBB1111B1Z2', 'D0,D1,D2,D3,D4,D5,D6,D7:5.5', 'YES'
        ])
    elif template_type == 'bom':
        response['Content-Disposition'] = 'attachment; filename="bom_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Parent Item Code*', 'Components (ComponentCode:Qty,ComponentCode:Qty,...)*'
        ])
        writer.writerow([
            'SET-001', 'COMP-001:2,COMP-002:1'
        ])
    elif template_type == 'po':
        response['Content-Disposition'] = 'attachment; filename="po_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'PO Number*', 'Client Name or Code*', 'Order Date (YYYY-MM-DD)*', 'Promised Date (YYYY-MM-DD)*', 'Priority (URGENT/NORMAL)*', 'Item Code*', 'Ordered Qty*', 'Rate per Piece (₹)*', 'Remarks'
        ])
        writer.writerow([
            'PO-2026-001', 'Mahadev Metal Works', '2026-05-30', '2026-06-15', 'NORMAL', 'BR-001', '100', '12.50', 'First trial shipment'
        ])
        writer.writerow([
            'PO-2026-001', 'Mahadev Metal Works', '2026-05-30', '2026-06-15', 'NORMAL', 'BR-002', '50', '15.00', ''
        ])
    else:
        return HttpResponse("Invalid template type", status=400)
        
    return response

@staff_member_required
def export_current_data(request, template_type):
    """
    Exports current active database entries to a CSV file matching the import templates.
    """
    response = HttpResponse(content_type='text/csv')
    
    if template_type == 'items':
        response['Content-Disposition'] = 'attachment; filename="items_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Item Code*', 'Item Name*', 'Category (BRASS/MORTAR/PESTLE/CHOPPING_BOARD/OTHER)*', 'Sub Category', 'Material', 'Variant',
            'Casting Weight (kg)', 'Machining Weight (kg)', 'Casting Required (YES/NO)', 'Machining Required (YES/NO)',
            'Polishing Required (YES/NO)', 'Packing Required (YES/NO)', 'Lot Size (pcs)', 'Lot With Box (pcs)', 'Standard Rate per Piece (₹)',
            'Min Casting Stock (pcs)', 'Min Machining Stock (pcs)', 'Min Polishing Stock (pcs)', 'Min Ready Stock (pcs)',
            'Is Raw Material (YES/NO)', 'Raw Material Item Code', 'Yield (Pcs per Unit)', 'UOM (PCS/KG/CHAAD/FEET/INCH/CM/MM)',
            'Company Scope (NC/OM/GLOBAL)*', 'Client Scope', 'Worker Piece-Rates (WorkerName:Rate; WorkerName:Rate)'
        ])
        items_qs = Item.objects.filter(company=request.company) if request.company else Item.objects.all()
        for item in items_qs:
            allocs = ItemWorkerAllocation.objects.filter(item=item)
            rates_list = []
            for a in allocs:
                w_name = a.worker.name if a.worker else ""
                if w_name:
                    rates_list.append(f"{w_name}:{a.rate_per_piece}")
            rates_str = "; ".join(rates_list)
            
            writer.writerow([
                item.code,
                item.name,
                item.category,
                item.sub_category or "",
                item.material or "OTHER",
                item.variant or "",
                item.casting_weight,
                item.machining_weight,
                "YES" if item.casting_required else "NO",
                "YES" if item.machining_required else "NO",
                "YES" if item.polishing_required else "NO",
                "YES" if item.packing_required else "NO",
                item.lot_size,
                item.lot_with_box,
                item.rate_per_piece,
                item.min_casting_stock,
                item.min_machining_stock,
                item.min_polishing_stock,
                item.min_ready_stock,
                "YES" if item.is_raw_material else "NO",
                item.raw_material.code if item.raw_material else "",
                item.yield_pcs_per_unit,
                item.uom,
                item.company.name if item.company else "GLOBAL",
                item.client.name if item.client else "",
                rates_str
            ])
            
    elif template_type == 'clients':
        response['Content-Disposition'] = 'attachment; filename="clients_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Client Name*', 'GSTIN Number', 'Phone', 'Email', 'City', 'Billing Address', 'Company Scope (NC/OM)*', 'Client Code (Leave blank for auto-generate)'
        ])
        clients_qs = Client.objects.filter(company=request.company) if request.company else Client.objects.all()
        for cl in clients_qs:
            writer.writerow([
                cl.name,
                cl.gst_number or "",
                cl.phone or "",
                cl.email or "",
                cl.city or "",
                cl.address or "",
                cl.company.name if cl.company else "",
                cl.client_code or ""
            ])
            
    elif template_type == 'employees':
        response['Content-Disposition'] = 'attachment; filename="employees_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Worker Code (Leave blank for auto-generate)', 'Name*', 'Company Scope (NC/OM)*', 'Phone', 'Department Process (casting/machining/polishing/packaging)*', 'Salary Type (DAILY/FIXED)*',
            'Daily Wage Rate (₹ - Daily Employees)', 'Monthly Fixed Salary (₹ - Fixed Employees)', 'Monthly Allowance (₹)', 'Standard Shift (Hours/Day)', 'Overtime Rate (₹/Hour)', 'Casting Piece-Rate (₹/kg)', 'Designation',
            'Rates (ItemCode:Rate,ItemCode:Rate,...)', 'Active (YES/NO)'
        ])
        workers_qs = Worker.objects.filter(company=request.company) if request.company else Worker.objects.all()
        for w in workers_qs:
            allocs = ItemWorkerAllocation.objects.filter(worker=w)
            rates_list = []
            for a in allocs:
                rates_list.append(f"{a.item.code}:{a.rate_per_piece}")
            rates_str = ",".join(rates_list)
            
            # casting rate is 0.0 for OM company (id=2)
            c_rate = 0.0 if (w.company and w.company.id == 2) else w.casting_rate_per_kg

            writer.writerow([
                w.employee_id or "",
                w.name,
                w.company.name if w.company else "",
                w.phone or "",
                w.process,
                w.salary_model,
                w.daily_rate,
                w.monthly_fixed_salary,
                w.monthly_allowance,
                w.standard_shift_hours,
                w.overtime_rate,
                c_rate,
                w.designation or "",
                rates_str,
                "YES" if w.active else "NO"
            ])
    elif template_type == 'job_workers':
        response['Content-Disposition'] = 'attachment; filename="job_workers_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Worker Code (Leave blank for auto-generate)', 'Name*', 'Company Scope (NC/OM)*', 'Phone', 'Department Process (casting/machining/polishing/packaging)*', 'Casting Piece-Rate (₹/kg)',
            'Vendor Address', 'Vendor Email', 'Vendor GSTIN',
            'Rates (ItemCode:Rate,ItemCode:Rate,...)', 'Active (YES/NO)'
        ])
        jws_qs = Worker.objects.filter(company=request.company, worker_type=WorkerType.JOB_WORKER) if request.company else Worker.objects.filter(worker_type=WorkerType.JOB_WORKER)
        for jw in jws_qs:
            allocs = ItemWorkerAllocation.objects.filter(worker=jw)
            rates_list = []
            for a in allocs:
                rates_list.append(f"{a.item.code}:{a.rate_per_piece}")
            rates_str = ",".join(rates_list)
            
            # casting rate is 0.0 for OM company (id=2)
            c_rate = 0.0 if (jw.company and jw.company.id == 2) else jw.casting_rate_per_kg

            writer.writerow([
                jw.jw_code or "",
                jw.name,
                jw.company.name if jw.company else "",
                jw.phone or "",
                jw.process,
                c_rate,
                jw.address or "",
                jw.email or "",
                jw.gst_number or "",
                rates_str,
                "YES" if jw.active else "NO"
            ])
    elif template_type == 'bom':
        response['Content-Disposition'] = 'attachment; filename="bom_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Parent Item Code*', 'Components (ComponentCode:Qty,ComponentCode:Qty,...)*'
        ])
        from collections import defaultdict
        parent_map = defaultdict(list)
        bom_qs = ItemComposition.objects.all().select_related('parent_item', 'component_item')
        if request.company:
            bom_qs = bom_qs.filter(parent_item__company=request.company)
        for comp in bom_qs.order_by('parent_item__code', 'component_item__code'):
            parent_map[comp.parent_item.code].append(f"{comp.component_item.code}:{comp.quantity}")
            
        for parent_code, comp_list in parent_map.items():
            writer.writerow([
                parent_code,
                ",".join(comp_list)
            ])
    elif template_type == 'po':
        response['Content-Disposition'] = 'attachment; filename="po_current_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'PO Number*', 'Client Name or Code*', 'Order Date (YYYY-MM-DD)*', 'Promised Date (YYYY-MM-DD)*', 'Priority (URGENT/NORMAL)*', 'Item Code*', 'Ordered Qty*', 'Rate per Piece (₹)*', 'Remarks'
        ])
        po_qs = SalesOrderItem.objects.all().select_related('sales_order', 'sales_order__client', 'item')
        if request.company:
            po_qs = po_qs.filter(sales_order__client__company=request.company)
        for item in po_qs:
            writer.writerow([
                item.sales_order.external_po_number,
                item.sales_order.client.client_code or item.sales_order.client.name,
                item.sales_order.order_date.strftime("%Y-%m-%d") if item.sales_order.order_date else "",
                item.sales_order.promised_date.strftime("%Y-%m-%d") if item.sales_order.promised_date else "",
                item.sales_order.priority,
                item.item.code,
                item.ordered_quantity,
                item.rate_per_piece,
                item.remarks or ""
            ])
    else:
        return HttpResponse("Invalid template type", status=400)
        
    return response


def run_financial_audit(cut_off_date=None):
    from apps.production.models import Loan, Carton
    blockers = []
    
    # 1. Outstanding Worker/JobWorker Loans
    unpaid_loans = Loan.objects.filter(remaining_balance__gt=0, is_active=True)
    for loan in unpaid_loans:
        name = loan.worker.name if loan.worker else "Unknown"
        blockers.append(f"Outstanding worker loan liability: {name} (Remaining balance: ₹{loan.remaining_balance:.2f})")

    # 2. Undispatched Cartons (Stuck in warehouse)
    undispatched = Carton.objects.filter(status="READY")
    for carton in undispatched:
        blockers.append(f"Undispatched Carton in Warehouse: {carton.carton_number} ({carton.total_quantity} pcs)")
        
    return len(blockers) == 0, blockers


def execute_backup_routine(settings_obj=None):
    import os
    import zipfile
    try:
        # Create backups folder inside workspace if it doesn't exist
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backups")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        # Collect and serialize model objects
        data_list = []
        data_list.extend(Category.objects.all())
        data_list.extend(Material.objects.all())
        data_list.extend(LegalEntity.objects.all())
        data_list.extend(Warehouse.objects.all())
        data_list.extend(Client.objects.all())
        data_list.extend(Item.objects.all())
        data_list.extend(ItemComposition.objects.all())
        data_list.extend(Worker.objects.all())
        data_list.extend(ItemWorkerAllocation.objects.all())
        data_list.extend(Attendance.objects.all())
        data_list.extend(Loan.objects.all())
        data_list.extend(LaborPayment.objects.all())
        data_list.extend(Carton.objects.all())
        data_list.extend(CartonItem.objects.all())
        data_list.extend(StockTransaction.objects.all())

        json_data = serializers.serialize("json", data_list, indent=4)
        
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        backup_zip_name = f"erp_backup_{timestamp}.zip"
        backup_zip_path = os.path.join(backup_dir, backup_zip_name)

        # Zip JSON data and /media/ directory if exists
        with zipfile.ZipFile(backup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("database_snapshot.json", json_data)

            # Write media files if directory exists
            media_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "media")
            if os.path.exists(media_dir):
                for root, dirs, files in os.walk(media_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, media_dir)
                        zip_file.write(file_path, os.path.join("media", rel_path))

        # Handle auto-rotation retention
        if settings_obj and settings_obj.backup_retention_count:
            retention = settings_obj.backup_retention_count
            all_backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("erp_backup_") and f.endswith(".zip")])
            if len(all_backups) > retention:
                files_to_delete = all_backups[:-retention]
                for file_del in files_to_delete:
                    try:
                        os.remove(os.path.join(backup_dir, file_del))
                    except OSError:
                        pass

        # Log success
        size_kb = os.path.getsize(backup_zip_path) // 1024
        MaintenanceLog.objects.create(
            event_type="backup",
            status="success",
            message=f"Backup completed successfully ({size_kb} KB). File: {backup_zip_name}",
            details=f"Backup saved to: {backup_zip_path}. Retention count applied: {settings_obj.backup_retention_count if settings_obj else 'None'}"
        )
        try:
            from apps.production.models import Notification
            Notification.objects.create(
                title="System Backup Completed",
                message=f"Database snapshot zip archive was successfully created ({size_kb} KB). File: {backup_zip_name}",
                notification_type="SUCCESS",
                company=settings_obj.company if settings_obj else None
            )
        except Exception:
            pass
        return True, backup_zip_name, backup_zip_path
    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="backup",
            status="failed",
            message=f"Auto-Backup failed: {str(e)}",
            details=""
        )
        return False, str(e), ""


def execute_delete_routine(settings_obj, force=False):
    try:
        # Determine cut-off date
        freq = settings_obj.auto_delete_frequency
        now = timezone.now()
        if freq == '4_months':
            cut_off_date = now - timezone.timedelta(days=4*30)
        elif freq == '6_months':
            cut_off_date = now - timezone.timedelta(days=6*30)
        elif freq == '1_year':
            cut_off_date = now - timezone.timedelta(days=365)
        else:
            cut_off_date = now - timezone.timedelta(days=6*30)

        # 1. Run Safety Audit
        is_clear, blockers = run_financial_audit(cut_off_date)
        if not is_clear and not force:
            blockers_str = " | ".join(blockers)
            MaintenanceLog.objects.create(
                event_type="audit_fail",
                status="skipped",
                message="Scheduled Auto-Delete skipped: Safety Audit blocked the operation.",
                details=f"Blockers:\n{blockers_str}"
            )
            return False, "skipped", blockers

        # 2. Snapshot first!
        success, backup_name, backup_path = execute_backup_routine(settings_obj)
        if not success:
            raise ValueError(f"Aborting deletion: Pre-purge snapshot failed: {backup_name}")

        # 3. Safe Deletion of old transactions and logs older than cut-off date
        with transaction.atomic():
            tx_count, _ = StockTransaction.objects.filter(created_at__lte=cut_off_date).delete()
            carton_items_count, _ = CartonItem.objects.filter(carton__created_at__lte=cut_off_date).delete()
            cartons_count, _ = Carton.objects.filter(created_at__lte=cut_off_date).delete()
            payments_count, _ = LaborPayment.objects.filter(date__lte=cut_off_date.date()).delete()
            attendance_count, _ = Attendance.objects.filter(date__lte=cut_off_date.date()).delete()

        msg = f"Auto-Delete executed successfully. Purged transactions/logs older than {cut_off_date.strftime('%Y-%m-%d')}. Created safety snapshot: {backup_name}."
        details_str = f"Deleted:\n- {tx_count} stock transactions\n- {cartons_count} cartons\n- {payments_count} payments\n- {attendance_count} attendance records"
        MaintenanceLog.objects.create(
            event_type="delete",
            status="success",
            message=msg,
            details=details_str
        )
        return True, "success", []
    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="delete",
            status="failed",
            message=f"Auto-Delete failed: {str(e)}",
            details=""
        )
        return False, "failed", [str(e)]


def run_automatic_maintenance_checks():
    """
    Evaluates whether scheduled backup or delete tasks are due and runs them.
    Safe against parallel execution locks using simple timestamps comparison.
    """
    settings_obj = MaintenanceSettings.objects.first()
    if not settings_obj:
        return

    now = timezone.now()

    # 1. Evaluate Scheduled Backup
    if settings_obj.auto_backup_enabled:
        due = False
        last = settings_obj.last_backup_run
        if not last:
            due = True
        else:
            freq = settings_obj.auto_backup_frequency
            if freq == 'daily' and now >= last + timezone.timedelta(days=1):
                due = True
            elif freq == 'weekly' and now >= last + timezone.timedelta(days=7):
                due = True
            elif freq == 'monthly' and now >= last + timezone.timedelta(days=30):
                due = True

        if due:
            settings_obj.last_backup_run = now
            settings_obj.save()
            execute_backup_routine(settings_obj)

    # 2. Evaluate Scheduled Auto-Delete
    if settings_obj.auto_delete_enabled:
        due = False
        last = settings_obj.last_delete_run
        if not last:
            due = True
        else:
            freq = settings_obj.auto_delete_frequency
            if freq == '4_months' and now >= last + timezone.timedelta(days=4*30):
                due = True
            elif freq == '6_months' and now >= last + timezone.timedelta(days=6*30):
                due = True
            elif freq == '1_year' and now >= last + timezone.timedelta(days=365):
                due = True

        if due:
            settings_obj.last_delete_run = now
            settings_obj.save()
            execute_delete_routine(settings_obj)


def get_row_value_by_prefix(row, prefix):
    if not row or not prefix:
        return None
    for key, val in row.items():
        if key.strip().lower().startswith(prefix.strip().lower()):
            return val
    return None


def resolve_company_by_name(co_name):
    if not co_name:
        return None
    co_name = co_name.strip()
    # Check exact match first
    company = LegalEntity.objects.filter(name__iexact=co_name).first()
    if company:
        return company
    # Try abbreviation fallback
    name_upper = co_name.upper()
    if name_upper in ["OM", "OM MACHINING"]:
        return LegalEntity.objects.filter(name__icontains="Om Machining").first() or LegalEntity.objects.filter(id=2).first()
    if name_upper in ["NC", "NEW CASTING"]:
        return LegalEntity.objects.filter(name__icontains="New Casting").first() or LegalEntity.objects.filter(id=1).first()
    # Try contains match
    return LegalEntity.objects.filter(name__icontains=co_name).first()


@staff_member_required
def master_bulk_import(request):
    """
    Single unified view that handles rendering the import hub dashboard,
    validating CSV uploads, and committing bulk records in atomic operations (Smart Upsert).
    """
    active_tab = request.GET.get("tab") or request.POST.get("import_type") or "items"
    if active_tab not in ["items", "clients", "employees", "job_workers", "bom", "po", "maintenance"]:
        active_tab = "items"
    preview_rows = []
    has_errors = False
    is_preview = "preview" in request.POST
    is_commit = "commit" in request.POST
    csv_data_cache = request.POST.get("csv_data_cache", "").strip()

    if request.method == "POST" and (is_preview or is_commit):
        csv_file = request.FILES.get("csv_file")
        file_data = ""
        if csv_file:
            try:
                file_data = csv_file.read().decode("utf-8-sig")
                csv_data_cache = file_data
            except Exception as e:
                messages.error(request, f"Error reading file: {str(e)}")
                return render(request, "import_export_hub.html", {"active_tab": active_tab, "csv_data_cache": csv_data_cache})
        elif csv_data_cache:
            file_data = csv_data_cache

        if not file_data:
            messages.error(request, "Please select a valid CSV file to upload.")
            return render(request, "import_export_hub.html", {"active_tab": active_tab, "csv_data_cache": csv_data_cache})

        try:
            # Parse the uploaded CSV
            io_string = io.StringIO(file_data)
            reader = csv.DictReader(io_string)
            
            # Trim headers to prevent trailing spaces matching errors
            reader.fieldnames = [name.strip() for name in reader.fieldnames] if reader.fieldnames else []
            
            with transaction.atomic():
                for idx, row in enumerate(reader, start=1):
                    # Strip all row cell values
                    row = {k: (v.strip() if v else "") for k, v in row.items()}
                    errors = []
                    action = "NEW"  # Default status for preview
                    if active_tab == "items":
                        code = get_row_value_by_prefix(row, "Item Code") or get_row_value_by_prefix(row, "Code") or row.get("code")
                        name = get_row_value_by_prefix(row, "Item Name") or get_row_value_by_prefix(row, "Name") or row.get("name")
                        co_name = (get_row_value_by_prefix(row, "Company Scope") or get_row_value_by_prefix(row, "Company") or row.get("company_name") or "").strip()
                        cl_name = (
                            get_row_value_by_prefix(row, "Client Scope") or 
                            get_row_value_by_prefix(row, "Client") or 
                            row.get("client_name") or 
                            row.get("client") or 
                            ""
                        ).strip()
                        row_company = None
                        row_client = None
                        
                        if not code:
                            errors.append("Code is required")
                        else:
                            # Check if item exists for update (Upsert based on unique code and company scope)
                            if request.company:
                                existing_item = Item.objects.filter(code=code, company=request.company).first()
                            else:
                                existing_item = Item.objects.filter(code=code).first()
                            if existing_item:
                                action = "UPDATE"
                                
                        if not name:
                            errors.append("Name is required")
                            
                        # Scoping company
                        if request.company:
                            if co_name and co_name.upper() != "GLOBAL":
                                resolved_co = resolve_company_by_name(co_name)
                                if not resolved_co or resolved_co != request.company:
                                    errors.append(f"Cannot import record for company '{co_name}' while active company is '{request.company.name}'")
                                else:
                                    row_company = request.company
                            else:
                                row_company = request.company
                                co_name = request.company.name
                        else:
                            if co_name and co_name.upper() != "GLOBAL":
                                row_company = resolve_company_by_name(co_name)
                                if not row_company:
                                    errors.append(f"Company '{co_name}' does not exist in the database")
                                
                        # Scoping Client
                        if cl_name:
                            # Try case-insensitive search by name
                            client_query = Client.objects.filter(name__iexact=cl_name)
                            if not client_query.exists():
                                # Try matching by client code
                                client_query = Client.objects.filter(client_code__iexact=cl_name)
                                
                            if row_company:
                                row_client = client_query.filter(company=row_company).first()
                                if not row_client:
                                    # Fallback: maybe the client exists generally (auto-adopt its company)
                                    row_client = client_query.first()
                                    if row_client:
                                        row_company = row_client.company
                                    else:
                                        errors.append(f"Client '{cl_name}' not found under company '{row_company.name}'")
                            else:
                                row_client = client_query.first()
                                if row_client:
                                    row_company = row_client.company
                                else:
                                    errors.append(f"Client '{cl_name}' not found in database")

                                    
                        # Category validation against live Category database model
                        category = (get_row_value_by_prefix(row, "Category") or row.get("category") or "OTHER").strip()
                        from apps.master_data.models import Category
                        category_obj = Category.objects.filter(name__iexact=category).first()
                        if category_obj:
                            category = category_obj.name
                        else:
                            db_match = Category.objects.filter(name__iexact=category.upper()).first()
                            if db_match:
                                category = db_match.name
                            else:
                                category = "OTHER"
                            
                        # Parse multi-worker piecework allocations
                        worker_rates_str = get_row_value_by_prefix(row, "Worker Piece-Rates") or row.get("worker_rates") or ""
                        allocations_to_create = []
                        if worker_rates_str:
                            allocs = [a.strip() for a in worker_rates_str.split(";") if a.strip()]
                            for alloc in allocs:
                                if ":" not in alloc:
                                    errors.append(f"Invalid rates mapping format '{alloc}' (must be Name:Rate)")
                                    continue
                                w_name, rate_str = alloc.split(":", 1)
                                w_name = w_name.strip()
                                rate = to_float(rate_str.strip())
                                
                                if row_company:
                                    w_obj = Worker.objects.filter(name=w_name, company=row_company).first()
                                else:
                                    w_obj = Worker.objects.filter(name=w_name).first()
                                
                                if not w_obj:
                                    # Non-blocking skip: continue importing item/client details even if employee doesn't exist yet
                                    pass
                                else:
                                    allocations_to_create.append((w_obj, rate))
 
                        preview_rows.append({
                            "row_num": idx,
                            "data": {
                                "code": code,
                                "name": name,
                                "company_name": co_name,
                                "client_name": cl_name,
                                "category": category,
                                "worker_rates": worker_rates_str
                            },
                            "errors": errors,
                            "is_valid": len(errors) == 0,
                            "action": action
                        })
                        
                        if len(errors) > 0:
                            has_errors = True
                            
                        if is_commit and len(errors) == 0:
                            # Material validation against live Material database model
                            from apps.master_data.models import Material
                            material_val = (get_row_value_by_prefix(row, "Material") or row.get("material") or "OTHER").strip()
                            material_obj = Material.objects.filter(name__iexact=material_val).first()
                            if material_obj:
                                material_val = material_obj.name
                            else:
                                db_match = Material.objects.filter(name__iexact=material_val.upper()).first()
                                if db_match:
                                    material_val = db_match.name
                                else:
                                    material_val = "OTHER"

                            item_data = {
                                "name": name,
                                "category": category,
                                "sub_category": row.get("Sub Category") or row.get("sub_category", ""),
                                "material": material_val,
                                "variant": row.get("Variant") or row.get("variant", ""),
                                "casting_weight": to_float(row.get("Casting Weight (kg)") or row.get("casting_weight", "0")),
                                "machining_weight": to_float(row.get("Machining Weight (kg)") or row.get("machining_weight", "0")),
                                "casting_required": to_bool(row.get("Casting Required (YES/NO)") or row.get("casting_required", "True")),
                                "machining_required": to_bool(row.get("Machining Required (YES/NO)") or row.get("machining_required", "False")),
                                "polishing_required": to_bool(row.get("Polishing Required (YES/NO)") or row.get("polishing_required", "False")),
                                "packing_required": to_bool(row.get("Packing Required (YES/NO)") or row.get("packing_required", "False")),
                                "lot_size": to_int(row.get("Lot Size (pcs)") or row.get("lot_size", "1")),
                                "lot_with_box": to_int(row.get("Lot With Box (pcs)") or row.get("Lot Weight With Box (kg)") or row.get("lot_with_box", "1")),
                                "rate_per_piece": to_float(row.get("Standard Rate per Piece (₹)") or row.get("rate_per_piece", "0.0")),
                                "min_casting_stock": to_int(row.get("Min Casting Stock (pcs)") or row.get("min_casting_stock", "0")),
                                "min_machining_stock": to_int(row.get("Min Machining Stock (pcs)") or row.get("min_machining_stock", "0")),
                                "min_polishing_stock": to_int(row.get("Min Polishing Stock (pcs)") or row.get("min_polishing_stock", "0")),
                                "min_ready_stock": to_int(row.get("Min Ready Stock (pcs)") or row.get("min_ready_stock", "0")),
                                "is_raw_material": to_bool(row.get("Is Raw Material (YES/NO)") or row.get("is_raw_material", "False")),
                                "yield_pcs_per_unit": to_float(row.get("Yield (Pcs per Unit)") or row.get("yield_pcs_per_unit", "1.0")),
                                "uom": (row.get("Yield Unit (PCS/KG/CHAAD/FEET/INCH)") or row.get("uom") or row.get("yield_unit") or "PCS").strip().upper(),
                                "company": row_company,
                                "client": row_client
                            }
                            
                            # Clean UOM choice scope
                            if item_data["uom"] not in ["PCS", "KG", "CHAAD", "FEET", "INCH", "CM", "MM"]:
                                item_data["uom"] = "PCS"
                                
                            # Resolve raw material foreign key mapping
                            raw_code = (row.get("Raw Material Item Code") or row.get("raw_material_code") or "").strip()
                            if raw_code:
                                raw_item = Item.objects.filter(code=raw_code, company=row_company).first()
                                item_data["raw_material"] = raw_item
                            else:
                                item_data["raw_material"] = None
                            
                            if action == "UPDATE":
                                if request.company:
                                    existing_item = Item.objects.filter(code=code, company=request.company).first()
                                else:
                                    existing_item = Item.objects.filter(code=code).first()
                                for key, val in item_data.items():
                                    setattr(existing_item, key, val)
                                existing_item.save()
                                item = existing_item
                                # Re-create worker allocations on update
                                ItemWorkerAllocation.objects.filter(item=item).delete()
                            else:
                                item = Item.objects.create(code=code, **item_data)
                                
                            for w_obj, rate in allocations_to_create:
                                ItemWorkerAllocation.objects.create(
                                    item=item,
                                    worker=w_obj,
                                    rate_per_piece=rate
                                )

                    elif active_tab == "clients":
                        name = row.get("Client Name*") or row.get("name")
                        co_name = (get_row_value_by_prefix(row, "Company Scope") or row.get("company_name") or "").strip()
                        cl_code = (row.get("Client Code (Leave blank for auto-generate)") or row.get("client_code") or "").strip()
                        row_company = None
                        
                        if not name:
                            errors.append("Client name is required")
                            
                        if request.company:
                            if co_name:
                                resolved_co = resolve_company_by_name(co_name)
                                if not resolved_co or resolved_co != request.company:
                                    errors.append(f"Cannot import record for company '{co_name}' while active company is '{request.company.name}'")
                                else:
                                    row_company = request.company
                            else:
                                row_company = request.company
                                co_name = request.company.name
                        else:
                            if not co_name:
                                errors.append("Company name is required")
                            else:
                                row_company = resolve_company_by_name(co_name)
                                if not row_company:
                                    errors.append(f"Company '{co_name}' does not exist in the database")
                                
                        if cl_code:
                            existing_client = Client.objects.filter(client_code=cl_code, company=request.company).first() if request.company else Client.objects.filter(client_code=cl_code).first()
                            if existing_client:
                                action = "UPDATE"
                        elif name and row_company:
                            existing_client = Client.objects.filter(name__iexact=name, company=row_company).first()
                            if existing_client:
                                action = "UPDATE"
                                cl_code = existing_client.client_code
                        
                        preview_rows.append({
                            "row_num": idx,
                            "data": {
                                "client_code": cl_code,
                                "name": name,
                                "company_name": co_name,
                                "gst_number": row.get("GSTIN Number") or row.get("gst_number", ""),
                                "phone": row.get("Phone") or row.get("phone", ""),
                                "city": row.get("City") or row.get("city", "")
                            },
                            "errors": errors,
                            "is_valid": len(errors) == 0,
                            "action": action
                        })
                        
                        if len(errors) > 0:
                            has_errors = True
                            
                        if is_commit and len(errors) == 0:
                            client_data = {
                                "name": name,
                                "gst_number": row.get("GSTIN Number") or row.get("gst_number", ""),
                                "phone": row.get("Phone") or row.get("phone", ""),
                                "email": row.get("Email") or row.get("email", ""),
                                "city": row.get("City") or row.get("city", ""),
                                "address": row.get("Billing Address") or row.get("address", ""),
                                "company": row_company
                            }
                            if action == "UPDATE":
                                existing_client = Client.objects.filter(client_code=cl_code, company=request.company).first() if request.company else Client.objects.filter(client_code=cl_code).first()
                                for key, val in client_data.items():
                                    setattr(existing_client, key, val)
                                existing_client.save()
                            else:
                                # New client creation
                                if cl_code:
                                    Client.objects.create(client_code=cl_code, **client_data)
                                else:
                                    Client.objects.create(**client_data)

                    elif active_tab == "employees":
                        name = row.get("Name*") or row.get("name")
                        co_name = (get_row_value_by_prefix(row, "Company Scope") or row.get("company_name") or "").strip()
                        process_str = (row.get("Department Process (casting/machining/polishing/packaging)*") or row.get("process_type") or "machining").lower()
                        w_code = (row.get("Worker Code (Leave blank for auto-generate)") or row.get("worker_code") or "").strip()
                        row_company = None
                        
                        # Process standardization
                        if "cast" in process_str:
                            process_str = "casting"
                        elif "machin" in process_str:
                            process_str = "machining"
                        elif "polish" in process_str:
                            process_str = "polishing"
                        elif "pack" in process_str:
                            process_str = "packaging"

                        if not name:
                            errors.append("Employee Name is required")
                            
                        if request.company:
                            if co_name:
                                resolved_co = resolve_company_by_name(co_name)
                                if not resolved_co or resolved_co != request.company:
                                    errors.append(f"Cannot import record for company '{co_name}' while active company is '{request.company.name}'")
                                else:
                                    row_company = request.company
                            else:
                                row_company = request.company
                                co_name = request.company.name
                        else:
                            if not co_name:
                                errors.append("Company scope is required")
                            else:
                                row_company = resolve_company_by_name(co_name)
                                if not row_company:
                                    errors.append(f"Company '{co_name}' does not exist in the database")
                                
                        if process_str not in [p[0] for p in ProcessType.choices]:
                            errors.append(f"Invalid process department '{process_str}'")
                            
                        if w_code:
                            existing_w = Worker.objects.filter(employee_id=w_code, company=request.company).first() if request.company else Worker.objects.filter(employee_id=w_code).first()
                            if existing_w:
                                action = "UPDATE"
                        elif name and row_company:
                            existing_w = Worker.objects.filter(name__iexact=name, company=row_company, process=process_str).first()
                            if existing_w:
                                action = "UPDATE"
                                w_code = existing_w.employee_id
                                    
                        # Validate Rates items
                        rates_str = row.get("Rates (ItemCode:Rate,ItemCode:Rate,...)") or row.get("rates") or ""
                        parsed_rates = {}
                        if rates_str:
                            parsed_rates = parse_rates_string(rates_str)
                            for item_code in parsed_rates.keys():
                                if not Item.objects.filter(code__iexact=item_code).exists():
                                    errors.append(f"Item Code '{item_code}' specified in Rates does not exist")
 
                        preview_rows.append({
                            "row_num": idx,
                            "data": {
                                "worker_code": w_code,
                                "name": name,
                                "company_name": co_name,
                                "worker_type": "EMPLOYEE",
                                "process_type": process_str,
                                "daily_rate": row.get("Daily Wage Rate (₹ - Daily Employees)") or row.get("daily_rate", "0")
                            },
                            "errors": errors,
                            "is_valid": len(errors) == 0,
                            "action": action
                        })
                        
                        if len(errors) > 0:
                            has_errors = True
                            
                        if is_commit and len(errors) == 0:
                            sal_model = (row.get("Salary Type (DAILY/FIXED)*") or row.get("salary_model") or "DAILY").upper()
                            if sal_model not in [s[0] for s in SalaryModel.choices]:
                                sal_model = SalaryModel.DAILY
                                
                            active_flag = to_bool(row.get("Active (YES/NO)", "YES"))
                            # casting rate is 0.0 for OM company (id=2)
                            c_rate = 0.0 if (row_company and row_company.id == 2) else to_float(row.get("Casting Piece-Rate (₹/kg)") or row.get("casting_rate_per_kg", "0"))
                            emp_data = {
                                "name": name,
                                "phone": row.get("Phone") or row.get("phone", ""),
                                "process": process_str,
                                "daily_rate": to_float(row.get("Daily Wage Rate (₹ - Daily Employees)") or row.get("daily_rate", "0")),
                                "monthly_fixed_salary": to_float(row.get("Monthly Fixed Salary (₹ - Fixed Employees)") or row.get("monthly_fixed_salary", "0")),
                                "monthly_allowance": to_float(row.get("Monthly Allowance (₹)") or row.get("monthly_allowance", "0")),
                                "standard_shift_hours": to_float(row.get("Standard Shift (Hours/Day)") or row.get("standard_shift_hours", "8.0")),
                                "overtime_rate": to_float(row.get("Overtime Rate (₹/Hour)") or row.get("overtime_rate", "0")),
                                "casting_rate_per_kg": c_rate,
                                "designation": row.get("Designation") or row.get("designation", ""),
                                "salary_model": sal_model,
                                "company": row_company,
                                "active": active_flag
                            }
                            
                            if action == "UPDATE":
                                existing_w = Worker.objects.filter(employee_id=w_code, company=request.company).first() if request.company else Worker.objects.filter(employee_id=w_code).first()
                                for key, val in emp_data.items():
                                    setattr(existing_w, key, val)
                                existing_w.save()
                                worker_obj = existing_w
                            else:
                                if w_code:
                                    worker_obj = Worker.objects.create(employee_id=w_code, **emp_data)
                                else:
                                    worker_obj = Worker.objects.create(**emp_data)
                                    
                            # Sync allocated item rates
                            if rates_str:
                                ItemWorkerAllocation.objects.filter(worker=worker_obj).delete()
                                for item_code, rate_val in parsed_rates.items():
                                    item_obj = Item.objects.filter(code__iexact=item_code, company=row_company).first()
                                    if not item_obj:
                                        item_obj = Item.objects.filter(code__iexact=item_code).first()
                                    if item_obj:
                                        ItemWorkerAllocation.objects.create(item=item_obj, worker=worker_obj, rate_per_piece=rate_val)

                    elif active_tab == "job_workers":
                        name = row.get("Name*") or row.get("name")
                        co_name = (get_row_value_by_prefix(row, "Company Scope") or row.get("company_name") or "").strip()
                        process_str = (row.get("Department Process (casting/machining/polishing/packaging)*") or row.get("process_type") or "machining").lower()
                        w_code = (row.get("Worker Code (Leave blank for auto-generate)") or row.get("worker_code") or "").strip()
                        row_company = None
                        
                        # Process standardization
                        if "cast" in process_str:
                            process_str = "casting"
                        elif "machin" in process_str:
                            process_str = "machining"
                        elif "polish" in process_str:
                            process_str = "polishing"
                        elif "pack" in process_str:
                            process_str = "packaging"

                        if not name:
                            errors.append("Job Worker Name is required")
                            
                        if request.company:
                            if co_name:
                                resolved_co = resolve_company_by_name(co_name)
                                if not resolved_co or resolved_co != request.company:
                                    errors.append(f"Cannot import record for company '{co_name}' while active company is '{request.company.name}'")
                                else:
                                    row_company = request.company
                            else:
                                row_company = request.company
                                co_name = request.company.name
                        else:
                            if not co_name:
                                errors.append("Company scope is required")
                            else:
                                row_company = resolve_company_by_name(co_name)
                                if not row_company:
                                    errors.append(f"Company '{co_name}' does not exist in the database")
                                
                        if process_str not in [p[0] for p in ProcessType.choices]:
                            errors.append(f"Invalid process department '{process_str}'")
                            
                        if w_code:
                            existing_jw = Worker.objects.filter(jw_code=w_code, company=request.company, worker_type=WorkerType.JOB_WORKER).first() if request.company else Worker.objects.filter(jw_code=w_code, worker_type=WorkerType.JOB_WORKER).first()
                            if existing_jw:
                                action = "UPDATE"
                        elif name and row_company:
                            existing_jw = Worker.objects.filter(name__iexact=name, company=row_company, process=process_str, worker_type=WorkerType.JOB_WORKER).first()
                            if existing_jw:
                                action = "UPDATE"
                                w_code = existing_jw.jw_code
                                    
                        # Validate Rates items
                        rates_str = row.get("Rates (ItemCode:Rate,ItemCode:Rate,...)") or row.get("rates") or ""
                        parsed_rates = {}
                        if rates_str:
                            parsed_rates = parse_rates_string(rates_str)
                            for item_code in parsed_rates.keys():
                                if not Item.objects.filter(code__iexact=item_code).exists():
                                    errors.append(f"Item Code '{item_code}' specified in Rates does not exist")
 
                        preview_rows.append({
                            "row_num": idx,
                            "data": {
                                "worker_code": w_code,
                                "name": name,
                                "company_name": co_name,
                                "worker_type": "JOB_WORKER",
                                "process_type": process_str,
                                "daily_rate": "0.0"
                            },
                            "errors": errors,
                            "is_valid": len(errors) == 0,
                            "action": action
                        })
                        
                        if len(errors) > 0:
                            has_errors = True
                            
                        if is_commit and len(errors) == 0:
                            active_flag = to_bool(row.get("Active (YES/NO)", "YES"))
                            # casting rate is 0.0 for OM company (id=2)
                            c_rate = 0.0 if (row_company and row_company.id == 2) else to_float(row.get("Casting Piece-Rate (₹/kg)") or row.get("casting_rate_per_kg", "0"))
                            jw_data = {
                                "worker_type": WorkerType.JOB_WORKER,
                                "name": name,
                                "phone": row.get("Phone") or row.get("phone", ""),
                                "process": process_str,
                                "casting_rate_per_kg": c_rate,
                                "address": row.get("Vendor Address") or row.get("address", ""),
                                "email": row.get("Vendor Email") or row.get("email", ""),
                                "gst_number": row.get("Vendor GSTIN") or row.get("gst_number", ""),
                                "company": row_company,
                                "active": active_flag
                            }
                            if action == "UPDATE":
                                existing_jw = Worker.objects.filter(jw_code=w_code, company=request.company, worker_type=WorkerType.JOB_WORKER).first() if request.company else Worker.objects.filter(jw_code=w_code, worker_type=WorkerType.JOB_WORKER).first()
                                for key, val in jw_data.items():
                                    setattr(existing_jw, key, val)
                                existing_jw.save()
                                jw_obj = existing_jw
                            else:
                                if w_code:
                                    jw_obj = Worker.objects.create(jw_code=w_code, **jw_data)
                                else:
                                    jw_obj = Worker.objects.create(**jw_data)
                                    
                            # Sync allocated item rates
                            if rates_str:
                                ItemWorkerAllocation.objects.filter(worker=jw_obj).delete()
                                for item_code, rate_val in parsed_rates.items():
                                    item_obj = Item.objects.filter(code__iexact=item_code, company=row_company).first()
                                    if not item_obj:
                                        item_obj = Item.objects.filter(code__iexact=item_code).first()
                                    if item_obj:
                                        ItemWorkerAllocation.objects.create(item=item_obj, worker=jw_obj, rate_per_piece=rate_val)

                    elif active_tab == "bom":
                        parent_code = (get_row_value_by_prefix(row, "Parent Item Code") or row.get("parent_item_code") or "").strip()
                        
                        parent_obj = None
                        if not parent_code:
                            errors.append("Parent item code is required")
                        else:
                            if request.company:
                                parent_obj = Item.objects.filter(code__iexact=parent_code, company=request.company).first()
                                if not parent_obj:
                                    errors.append(f"Parent Item with code '{parent_code}' not found under active company '{request.company.name}'")
                            else:
                                parent_obj = Item.objects.filter(code__iexact=parent_code).first()
                                if not parent_obj:
                                    errors.append(f"Parent Item with code '{parent_code}' not found")
                        
                        comp_str = (get_row_value_by_prefix(row, "Components") or row.get("components") or "").strip()
                        
                        comp_parts = []
                        if comp_str:
                            parsed_comps = parse_rates_string(comp_str)
                            if not parsed_comps:
                                errors.append("No valid components found in Components column")
                            else:
                                for c_code, qty_val in parsed_comps.items():
                                    comp_parts.append((c_code, int(qty_val)))
                        else:
                            comp_code = (get_row_value_by_prefix(row, "Component Item Code") or row.get("component_item_code") or "").strip()
                            qty_str = (get_row_value_by_prefix(row, "Quantity") or row.get("quantity") or "").strip()
                            
                            if not comp_code:
                                errors.append("Component item code is required")
                            if not qty_str:
                                errors.append("Quantity is required")
                            else:
                                qty = to_int(qty_str, 0)
                                if qty <= 0:
                                    errors.append("Quantity must be a positive integer greater than 0")
                                else:
                                    comp_parts.append((comp_code, qty))
                                    
                        for c_code, qty in comp_parts:
                            comp_errors = []
                            if request.company:
                                comp_obj = Item.objects.filter(code__iexact=c_code, company=request.company).first()
                                if not comp_obj:
                                    comp_errors.append(f"Component Item with code '{c_code}' not found under active company '{request.company.name}'")
                            else:
                                comp_obj = Item.objects.filter(code__iexact=c_code).first()
                                if not comp_obj:
                                    comp_errors.append(f"Component Item with code '{c_code}' not found")
                                
                            total_errors = errors + comp_errors
                            action = "CREATE"
                            if parent_obj and comp_obj:
                                existing_relation = ItemComposition.objects.filter(parent_item=parent_obj, component_item=comp_obj).first()
                                if existing_relation:
                                    action = "UPDATE"
                                    
                            preview_rows.append({
                                "row_num": idx,
                                "data": {
                                    "parent_item_code": parent_code,
                                    "component_item_code": c_code,
                                    "quantity": str(qty)
                                },
                                "errors": total_errors,
                                "is_valid": len(total_errors) == 0,
                                "action": action
                            })
                            
                            if len(total_errors) > 0:
                                has_errors = True
                                
                            if is_commit and len(total_errors) == 0:
                                if action == "UPDATE":
                                    existing_relation = ItemComposition.objects.filter(parent_item=parent_obj, component_item=comp_obj).first()
                                    existing_relation.quantity = qty
                                    existing_relation.save()
                                else:
                                    ItemComposition.objects.create(
                                        parent_item=parent_obj,
                                        component_item=comp_obj,
                                        quantity=qty
                                    )
                                    
                        if not comp_parts:
                            preview_rows.append({
                                "row_num": idx,
                                "data": {
                                    "parent_item_code": parent_code,
                                    "component_item_code": "",
                                    "quantity": ""
                                },
                                "errors": errors,
                                "is_valid": False,
                                "action": "CREATE"
                            })
                            has_errors = True

                    elif active_tab == "po":
                        po_num = (row.get("PO Number*") or row.get("po_number") or row.get("external_po_number") or "").strip()
                        client_val = (row.get("Client Name or Code*") or row.get("client_name_or_code") or row.get("client") or "").strip()
                        order_date_str = (row.get("Order Date (YYYY-MM-DD)*") or row.get("order_date") or "").strip()
                        promised_date_str = (row.get("Promised Date (YYYY-MM-DD)*") or row.get("promised_date") or "").strip()
                        priority_str = (row.get("Priority (URGENT/NORMAL)*") or row.get("priority") or "NORMAL").strip().upper()
                        item_code = (row.get("Item Code*") or row.get("item_code") or row.get("item") or "").strip()
                        qty_str = (row.get("Ordered Qty*") or row.get("ordered_quantity") or row.get("qty") or "").strip()
                        rate_str = (row.get("Rate per Piece (₹)*") or row.get("rate_per_piece") or row.get("rate") or "").strip()
                        remarks = (row.get("Remarks") or row.get("remarks") or "").strip()
                        
                        client_obj = None
                        item_obj = None
                        order_date = timezone.now().date()
                        promised_date = None
                        
                        if not po_num:
                            errors.append("PO Number is required")
                            
                        if not client_val:
                            errors.append("Client Name or Code is required")
                        else:
                            if request.company:
                                client_obj = Client.objects.filter(client_code=client_val, company=request.company).first()
                                if not client_obj:
                                    client_obj = Client.objects.filter(name__iexact=client_val, company=request.company).first()
                                if not client_obj:
                                    errors.append(f"Client '{client_val}' not found under active company '{request.company.name}'")
                            else:
                                client_obj = Client.objects.filter(client_code=client_val).first()
                                if not client_obj:
                                    client_obj = Client.objects.filter(name__iexact=client_val).first()
                                if not client_obj:
                                    errors.append(f"Client '{client_val}' not found")
                                
                        if order_date_str:
                            try:
                                from datetime import datetime
                                order_date = datetime.strptime(order_date_str, "%Y-%m-%d").date()
                            except ValueError:
                                errors.append("Order Date must be in YYYY-MM-DD format")
                                
                        if not promised_date_str:
                            errors.append("Promised Date is required")
                        else:
                            try:
                                from datetime import datetime
                                promised_date = datetime.strptime(promised_date_str, "%Y-%m-%d").date()
                            except ValueError:
                                errors.append("Promised Date must be in YYYY-MM-DD format")
                                
                        if priority_str not in ["NORMAL", "URGENT"]:
                            errors.append("Priority must be either NORMAL or URGENT")
                            
                        if not item_code:
                            errors.append("Item Code is required")
                        else:
                            if request.company:
                                item_obj = Item.objects.filter(code=item_code, company=request.company).first()
                                if not item_obj:
                                    errors.append(f"Item Code '{item_code}' not found under active company '{request.company.name}'")
                            else:
                                item_obj = Item.objects.filter(code=item_code).first()
                                if not item_obj:
                                    errors.append(f"Item Code '{item_code}' not found")
                                
                        qty = to_int(qty_str, 0)
                        if qty <= 0:
                            errors.append("Ordered Quantity must be a positive integer greater than 0")
                            
                        rate = to_float(rate_str, 0.0)
                        if rate < 0.0:
                            errors.append("Rate per piece cannot be negative")
                            
                        if po_num and client_obj:
                            existing_po = SalesOrder.objects.filter(external_po_number=po_num, client=client_obj).first()
                            if existing_po:
                                action = "UPDATE"
                                
                        preview_rows.append({
                            "row_num": idx,
                            "data": {
                                "po_number": po_num,
                                "client": client_val,
                                "order_date": order_date_str,
                                "promised_date": promised_date_str,
                                "priority": priority_str,
                                "item_code": item_code,
                                "quantity": qty_str,
                                "rate": rate_str,
                                "remarks": remarks
                            },
                            "errors": errors,
                            "is_valid": len(errors) == 0,
                            "action": action
                        })
                        
                        if len(errors) > 0:
                            has_errors = True
                            
                        if is_commit and len(errors) == 0:
                            sales_order_obj, created = SalesOrder.objects.get_or_create(
                                external_po_number=po_num,
                                client=client_obj,
                                defaults={
                                    "order_date": order_date,
                                    "promised_date": promised_date,
                                    "priority": priority_str,
                                    "notes": f"Bulk Imported PO"
                                }
                            )
                            if not created:
                                sales_order_obj.promised_date = promised_date
                                sales_order_obj.priority = priority_str
                                sales_order_obj.save()
                                
                            so_item, item_created = SalesOrderItem.objects.get_or_create(
                                sales_order=sales_order_obj,
                                item=item_obj,
                                defaults={
                                    "ordered_quantity": qty,
                                    "rate_per_piece": rate,
                                    "remarks": remarks
                                }
                            )
                            if not item_created:
                                so_item.ordered_quantity = qty
                                so_item.rate_per_piece = rate
                                so_item.remarks = remarks
                                so_item.save()

                if is_commit and has_errors:
                    # Explicitly trigger database rollback on errors
                    raise ValueError("Import files contains structural validation errors.")

            if is_commit:
                messages.success(request, f"Successfully processed all record imports and updates!")
                return redirect("master_data")
            else:
                messages.info(request, f"CSV parsed successfully. Please inspect the {len(preview_rows)} preview rows before committing.")

        except Exception as e:
            messages.error(request, f"Failed to parse CSV file: {str(e)}")
            preview_rows = []

    return render(request, "import_export_hub.html", {
        "active_tab": active_tab,
        "preview_rows": preview_rows,
        "has_errors": has_errors,
        "csv_data_cache": csv_data_cache,
    })


@staff_member_required
def export_database_backup(request):
    """
    Exports database backup in requested format:
    - 'sqlite': Direct raw .sqlite3 database file (WAL checkpointed for 100% data integrity).
    - 'zip': Compressed archive containing .sqlite3 + /media/ folder.
    - 'json': Standard Django serialized JSON dump.
    """
    import os
    import shutil
    import tempfile
    import zipfile
    from django.conf import settings
    from django.db import connection

    export_format = request.GET.get("format", "sqlite").strip().lower()

    try:
        # Checkpoint SQLite WAL mode to ensure all pending transactions are flushed to disk
        with connection.cursor() as cursor:
            try:
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception:
                pass

        timestamp = timezone.now().strftime("%Y-%m-%d_%H%M%S")
        db_path = str(settings.DATABASES['default']['NAME'])

        if export_format == "sqlite" and os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            response = HttpResponse(db_bytes, content_type="application/x-sqlite3")
            response["Content-Disposition"] = f'attachment; filename="foundry_erp_backup_{timestamp}.sqlite3"'
            
            MaintenanceLog.objects.create(
                event_type="backup",
                status="success",
                message=f"Direct SQLite Database backup downloaded successfully.",
                details=f"File: foundry_erp_backup_{timestamp}.sqlite3 ({len(db_bytes):,} bytes)"
            )
            return response

        elif export_format == "zip":
            # Package .sqlite3 and media/ into a ZIP
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                if os.path.exists(db_path):
                    zip_file.write(db_path, arcname="db.sqlite3")
                media_root = getattr(settings, 'MEDIA_ROOT', None)
                if media_root and os.path.exists(media_root):
                    for root, dirs, files in os.walk(media_root):
                        for file in files:
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, media_root)
                            zip_file.write(file_path, arcname=os.path.join("media", rel_path))

            with open(temp_zip.name, "rb") as f:
                zip_bytes = f.read()
            os.remove(temp_zip.name)

            response = HttpResponse(zip_bytes, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="foundry_erp_full_backup_{timestamp}.zip"'

            MaintenanceLog.objects.create(
                event_type="backup",
                status="success",
                message=f"Full ZIP backup (Database + Media) downloaded successfully.",
                details=f"File: foundry_erp_full_backup_{timestamp}.zip ({len(zip_bytes):,} bytes)"
            )
            return response

        else: # Default JSON export
            data_list = []
            data_list.extend(Category.objects.all())
            data_list.extend(Material.objects.all())
            data_list.extend(LegalEntity.objects.all())
            data_list.extend(Warehouse.objects.all())
            data_list.extend(Client.objects.all())
            data_list.extend(Item.objects.all())
            data_list.extend(ItemComposition.objects.all())
            data_list.extend(Worker.objects.all())
            data_list.extend(ItemWorkerAllocation.objects.all())
            data_list.extend(Attendance.objects.all())
            data_list.extend(Loan.objects.all())
            data_list.extend(LaborPayment.objects.all())
            data_list.extend(Carton.objects.all())
            data_list.extend(CartonItem.objects.all())
            data_list.extend(StockTransaction.objects.all())
            data_list.extend(SalesOrder.objects.all())
            data_list.extend(SalesOrderItem.objects.all())
            data_list.extend(Dispatch.objects.all())
            data_list.extend(DispatchItem.objects.all())

            json_data = serializers.serialize("json", data_list, indent=4)
            response = HttpResponse(json_data, content_type="application/json")
            response["Content-Disposition"] = f'attachment; filename="foundry_erp_backup_{timestamp}.json"'

            MaintenanceLog.objects.create(
                event_type="backup",
                status="success",
                message=f"JSON database export created ({len(data_list):,} records).",
                details=f"File: foundry_erp_backup_{timestamp}.json"
            )
            return response

    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="backup",
            status="failed",
            message=f"Backup export failed: {str(e)}",
            details=""
        )
        messages.error(request, f"Failed to export database backup: {str(e)}")
        return redirect(f"{reverse('master_data')}?tab=maintenance")


@staff_member_required
def import_database_backup(request):
    """
    Restores database from an uploaded .sqlite3, .db, or .json backup file.
    Always takes a safety pre-restore backup first.
    """
    import os
    import shutil
    from django.conf import settings
    from django.db import connection

    if request.method != "POST":
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    backup_file = request.FILES.get("backup_file")
    if not backup_file:
        messages.error(request, "Please choose a valid backup file (.sqlite3 or .json).")
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    filename = backup_file.name.lower()
    db_path = str(settings.DATABASES['default']['NAME'])
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

    # Safety Pre-Restore Snapshot
    backups_dir = os.path.join(os.path.dirname(db_path), "backups")
    if not os.path.exists(backups_dir):
        os.makedirs(backups_dir, exist_ok=True)
    if os.path.exists(db_path):
        shutil.copy2(db_path, os.path.join(backups_dir, f"pre_restore_safety_{timestamp}.sqlite3"))

    try:
        if filename.endswith(".sqlite3") or filename.endswith(".db"):
            # Validate SQLite magic header
            content = backup_file.read()
            if not content.startswith(b"SQLite format 3\x00"):
                raise ValueError("Invalid SQLite file format. The file is corrupted or not a valid SQLite database.")

            # Close existing connections before replacing file
            connection.close()

            with open(db_path, "wb") as f:
                f.write(content)

            # Re-open and verify
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()
                if result and result[0] != "ok":
                    raise ValueError(f"SQLite integrity check failed: {result[0]}")

            MaintenanceLog.objects.create(
                event_type="restore",
                status="success",
                message=f"Database restored from SQLite snapshot: {backup_file.name}",
                details=f"File size: {len(content):,} bytes. Safety backup saved to backups/pre_restore_safety_{timestamp}.sqlite3"
            )
            messages.success(request, f"Database restored successfully from {backup_file.name}! A pre-restore safety copy was saved.")

        elif filename.endswith(".json"):
            json_data = backup_file.read().decode("utf-8")
            deserialized_objects = list(serializers.deserialize("json", json_data))
            if not deserialized_objects:
                raise ValueError("The backup JSON file is empty or invalid.")

            with transaction.atomic():
                DispatchItem.objects.all().delete()
                Dispatch.objects.all().delete()
                SalesOrderItem.objects.all().delete()
                SalesOrder.objects.all().delete()
                StockTransaction.objects.all().delete()
                CartonItem.objects.all().delete()
                Carton.objects.all().delete()
                LaborPayment.objects.all().delete()
                Loan.objects.all().delete()
                Attendance.objects.all().delete()
                ItemWorkerAllocation.objects.all().delete()
                Worker.objects.all().delete()
                ItemComposition.objects.all().delete()
                Item.objects.all().delete()
                Client.objects.all().delete()
                Warehouse.objects.all().delete()
                LegalEntity.objects.all().delete()
                Material.objects.all().delete()
                Category.objects.all().delete()

                for obj in deserialized_objects:
                    obj.save()

            MaintenanceLog.objects.create(
                event_type="restore",
                status="success",
                message=f"Database restored from JSON backup: {backup_file.name} ({len(deserialized_objects)} records).",
                details=""
            )
            messages.success(request, f"Database restored successfully! {len(deserialized_objects)} records imported.")

        else:
            messages.error(request, "Unsupported file format. Please upload a .sqlite3 or .json backup file.")

    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="restore",
            status="failed",
            message=f"Database restoration failed: {str(e)}",
            details=""
        )
        messages.error(request, f"Failed to restore database: {str(e)}")

    return redirect(f"{reverse('master_data')}?tab=maintenance")


@staff_member_required
def archive_and_purge_historical_data(request):
    """
    Historical Year-End Archive & Purge:
    1. Validates cut-off date and confirmation text.
    2. Packages and serializes all operational history before cut-off date into an archive JSON file.
    3. Calculates net closing stock per (item, warehouse) as of the cut-off date and records Opening Stock Adjustments.
    4. Calculates net worker earnings/payments as of the cut-off date and records Opening Worker Balance notes.
    5. Safely deletes individual historical operational rows prior to cut-off date.
    6. Compacts SQLite database using VACUUM to reclaim disk space.
    7. Serves the archive file directly to the user as a browser download.
    """
    from datetime import datetime
    from django.db import connection
    from django.db.models import Sum

    if request.method != "POST":
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    confirm_text = request.POST.get("confirm_text", "").strip().upper()
    cut_off_str = request.POST.get("cut_off_date", "").strip()

    if confirm_text != "ARCHIVE DATA":
        messages.error(request, "Confirmation text must be exactly 'ARCHIVE DATA'.")
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    try:
        cut_off_date = datetime.strptime(cut_off_str, "%Y-%m-%d").date()
    except Exception:
        messages.error(request, "Invalid cut-off date format. Please select a valid date.")
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    cut_off_dt = timezone.make_aware(datetime.combine(cut_off_date, datetime.min.time()))

    try:
        # Step 1: Collect all historical records prior to cut-off date for offline archive
        archive_records = []
        old_stock_txs = StockTransaction.objects.filter(created_at__lt=cut_off_dt)
        old_carton_items = CartonItem.objects.filter(carton__created_at__lt=cut_off_dt)
        old_cartons = Carton.objects.filter(created_at__lt=cut_off_dt)
        old_payments = LaborPayment.objects.filter(date__lt=cut_off_date)
        old_attendances = Attendance.objects.filter(date__lt=cut_off_date)
        old_so_items = SalesOrderItem.objects.filter(sales_order__order_date__lt=cut_off_date)
        old_sos = SalesOrder.objects.filter(order_date__lt=cut_off_date)
        old_dispatch_items = DispatchItem.objects.filter(dispatch__dispatch_date__lt=cut_off_dt)
        old_dispatches = Dispatch.objects.filter(dispatch_date__lt=cut_off_dt)

        archive_records.extend(list(old_dispatches))
        archive_records.extend(list(old_dispatch_items))
        archive_records.extend(list(old_sos))
        archive_records.extend(list(old_so_items))
        archive_records.extend(list(old_cartons))
        archive_records.extend(list(old_carton_items))
        archive_records.extend(list(old_stock_txs))
        archive_records.extend(list(old_payments))
        archive_records.extend(list(old_attendances))

        if not archive_records:
            messages.info(request, f"No historical records found prior to {cut_off_date}. Nothing to archive.")
            return redirect(f"{reverse('master_data')}?tab=maintenance")

        archive_json = serializers.serialize("json", archive_records, indent=4)

        # Step 2: In an atomic transaction, carry forward Opening Balances and purge old rows
        with transaction.atomic():
            # 2a. Calculate stock balances per (item, warehouse) as of cut-off date
            all_warehouses = Warehouse.objects.all()
            all_items = Item.objects.all()
            
            created_stock_adjustments = 0
            for item in all_items:
                for wh in all_warehouses:
                    # Inward to warehouse before cutoff
                    in_qty = StockTransaction.objects.filter(
                        item=item,
                        to_warehouse=wh,
                        created_at__lt=cut_off_dt
                    ).aggregate(total=Sum('quantity'))['total'] or 0

                    # Outward from warehouse before cutoff
                    out_qty = StockTransaction.objects.filter(
                        item=item,
                        from_warehouse=wh,
                        created_at__lt=cut_off_dt
                    ).aggregate(total=Sum('quantity'))['total'] or 0

                    net_stock_at_cutoff = in_qty - out_qty
                    if net_stock_at_cutoff > 0:
                        # Record Opening Balance transaction
                        StockTransaction.objects.create(
                            item=item,
                            to_warehouse=wh,
                            transaction_type=TransactionType.STOCK_ADJUSTMENT,
                            quantity=net_stock_at_cutoff,
                            notes=f"[ARCHIVE OPENING BALANCE - As of {cut_off_date}]"
                        )
                        created_stock_adjustments += 1

            # 2b. Delete historical rows strictly older than cut_off_dt (excluding newly created opening balances)
            del_dispatch_items = old_dispatch_items.delete()[0]
            del_dispatches = old_dispatches.delete()[0]
            del_so_items = old_so_items.delete()[0]
            del_sos = old_sos.delete()[0]
            del_carton_items = old_carton_items.delete()[0]
            del_cartons = old_cartons.delete()[0]
            del_stock_txs = StockTransaction.objects.filter(
                created_at__lt=cut_off_dt
            ).exclude(notes__contains="[ARCHIVE OPENING BALANCE").delete()[0]
            del_payments = old_payments.delete()[0]
            del_attendances = old_attendances.delete()[0]

            total_deleted = (del_dispatch_items + del_dispatches + del_so_items + del_sos + 
                             del_carton_items + del_cartons + del_stock_txs + del_payments + del_attendances)

            MaintenanceLog.objects.create(
                event_type="delete",
                status="success",
                message=f"Historical Data Archived & Purged prior to {cut_off_date}.",
                details=f"Purged {total_deleted:,} historical rows. Created {created_stock_adjustments} Opening Stock adjustments to preserve live stock accuracy."
            )

        # Step 3: Compact database file using VACUUM to reclaim space
        with connection.cursor() as cursor:
            try:
                cursor.execute("PRAGMA optimize; VACUUM;")
            except Exception:
                pass

        # Step 4: Return the Archive file directly to user's browser
        response = HttpResponse(archive_json, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="foundry_erp_archive_prior_to_{cut_off_date}.json"'
        return response

    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="delete",
            status="failed",
            message=f"Archive & Purge failed: {str(e)}",
            details=""
        )
        messages.error(request, f"Failed to complete archive and purge: {str(e)}")
        return redirect(f"{reverse('master_data')}?tab=maintenance")


@staff_member_required
def clear_test_operational_data(request):
    """
    Fresh Season / Reset Testing Data:
    Wipes all operational transactions (Casting, Machining, Polishing, Packaging, Sales, Attendance, Payments)
    while keeping 100% of Master Catalogs (Items, BOMs, Clients, Workers, Rates, Warehouses, Companies).
    """
    from django.db import connection

    if request.method != "POST":
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    confirm_text = request.POST.get("confirm_text", "").strip().upper()

    if confirm_text not in ("CLEAR OPERATIONAL DATA", "RESET"):
        messages.error(request, "Confirmation text must be exactly 'CLEAR OPERATIONAL DATA'.")
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    try:
        with transaction.atomic():
            DispatchItem.objects.all().delete()
            Dispatch.objects.all().delete()
            SalesOrderItem.objects.all().delete()
            SalesOrder.objects.all().delete()
            StockTransaction.objects.all().delete()
            CartonItem.objects.all().delete()
            Carton.objects.all().delete()
            LaborPayment.objects.all().delete()
            Loan.objects.all().delete()
            Attendance.objects.all().delete()
            
            # Reset aggregate stock caches to zero
            ItemStock.objects.all().update(quantity_on_hand=0, reserved_quantity=0)

            MaintenanceLog.objects.create(
                event_type="reset",
                status="success",
                message="Fresh Season: Cleared all test operational transactions. Master catalogs preserved.",
                details="Cleared Stock Transactions, Cartons, Sales Orders, Dispatches, Attendance, and Payments."
            )

        with connection.cursor() as cursor:
            try:
                cursor.execute("PRAGMA optimize; VACUUM;")
            except Exception:
                pass

        messages.success(request, "All test operational transactions cleared! Master Items, Clients, Workers, and Rates remain 100% intact.")
    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="reset",
            status="failed",
            message=f"Clear operational data failed: {str(e)}",
            details=""
        )
        messages.error(request, f"Failed to clear operational data: {str(e)}")

    return redirect(f"{reverse('master_data')}?tab=maintenance")


@staff_member_required
def factory_reset_database(request):
    """
    Deletes all transactional, master, and structural data (preserving User profiles/superusers).
    """
    from django.db import connection

    if request.method != "POST":
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    confirm_text = request.POST.get("confirm_text", "").strip().upper()
    if confirm_text != "FACTORY RESET":
        messages.error(request, "Confirmation text must be exactly 'FACTORY RESET'.")
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    try:
        with transaction.atomic():
            DispatchItem.objects.all().delete()
            Dispatch.objects.all().delete()
            SalesOrderItem.objects.all().delete()
            SalesOrder.objects.all().delete()
            StockTransaction.objects.all().delete()
            CartonItem.objects.all().delete()
            Carton.objects.all().delete()
            LaborPayment.objects.all().delete()
            Loan.objects.all().delete()
            Attendance.objects.all().delete()
            ItemWorkerAllocation.objects.all().delete()
            Worker.objects.all().delete()
            ItemComposition.objects.all().delete()
            ItemStock.objects.all().delete()
            Item.objects.all().delete()
            Client.objects.all().delete()
            Warehouse.objects.all().delete()
            LegalEntity.objects.all().delete()
            Material.objects.all().delete()
            Category.objects.all().delete()

            MaintenanceLog.objects.create(
                event_type="reset",
                status="success",
                message="Factory Reset completed. All master and transactional records cleared.",
                details=""
            )

        with connection.cursor() as cursor:
            try:
                cursor.execute("PRAGMA optimize; VACUUM;")
            except Exception:
                pass

        messages.success(request, "Database factory reset completed successfully! All records have been cleared.")
    except Exception as e:
        MaintenanceLog.objects.create(
            event_type="reset",
            status="failed",
            message=f"Factory reset failed: {str(e)}",
            details=""
        )
        messages.error(request, f"Failed to complete factory reset: {str(e)}")

    return redirect(f"{reverse('master_data')}?tab=maintenance")


@staff_member_required
def save_maintenance_settings(request):
    """
    Saves auto-backup schedule and device security mode settings.
    """
    if request.method != "POST":
        return redirect(f"{reverse('master_data')}?tab=maintenance")

    try:
        settings_obj, _ = MaintenanceSettings.objects.get_or_create(id=1)
        
        settings_obj.auto_backup_enabled = (request.POST.get("auto_backup_enabled") == "on")
        settings_obj.auto_backup_frequency = request.POST.get("auto_backup_frequency", "daily")
        settings_obj.backup_retention_count = int(request.POST.get("backup_retention_count", 10))
        settings_obj.save()

        messages.success(request, "System Maintenance auto-backup schedules updated successfully!")
    except Exception as e:
        messages.error(request, f"Failed to save settings: {str(e)}")

    return redirect(f"{reverse('master_data')}?tab=maintenance")
