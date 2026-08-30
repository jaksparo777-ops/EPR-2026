import os
import sys
import sqlite3
import django

# Set up Django environment
sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.master_data.models import LegalEntity, Category, Material, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, CustomUser, WorkerType
from apps.production.models import (
    StockTransaction, ItemWorkerAllocation, Attendance, Loan,
    LaborPayment, Carton, CartonItem, TransactionType
)

def main():
    print("Starting data migration...")
    
    # 1. Clear existing data in 3_erp_project (to make it repeatable)
    print("Clearing existing data...")
    CartonItem.objects.all().delete()
    Carton.objects.all().delete()
    LaborPayment.objects.all().delete()
    Loan.objects.all().delete()
    Attendance.objects.all().delete()
    ItemWorkerAllocation.objects.all().delete()
    StockTransaction.objects.all().delete()
    ItemComposition.objects.all().delete()
    Item.objects.all().delete()
    Warehouse.objects.all().delete()
    Client.objects.all().delete()
    Worker.objects.all().delete()
    Category.objects.all().delete()
    Material.objects.all().delete()
    LegalEntity.objects.all().delete()

    # Connect to the old database
    conn = sqlite3.connect("../core/db.sqlite3")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2. Create Legal Entities
    print("Creating Legal Entities...")
    c1 = LegalEntity.objects.create(
        id=1,
        name="Casting Foundry",
        gst_number="27AAAAA1111A1Z1",
        phone="9876543210",
        address="Foundry Zone, Industrial Area Phase 1",
        letterhead_title="CASTING FOUNDRY LTD."
    )
    c2 = LegalEntity.objects.create(
        id=2,
        name="Finishing Processor",
        gst_number="27BBBBB2222B2Z2",
        phone="9876543211",
        address="Finishing Complex, Industrial Area Phase 2",
        letterhead_title="FINISHING & LOGISTICS CORP."
    )

    # Associate superuser (admin) with all-company access (None)
    admin_user = CustomUser.objects.filter(username="admin").first()
    if admin_user:
        admin_user.role = "ADMIN"
        admin_user.company = None
        admin_user.save()
        print("Superuser 'admin' configured as global ADMIN.")

    # 3. Migrate Categories
    print("Migrating Categories...")
    cursor.execute("SELECT * FROM inventory_category")
    for r in cursor.fetchall():
        Category.objects.create(id=r['id'], name=r['name'])

    # 4. Migrate Materials
    print("Migrating Materials...")
    cursor.execute("SELECT * FROM inventory_material")
    for r in cursor.fetchall():
        Material.objects.create(id=r['id'], name=r['name'])

    # 5. Migrate Clients
    print("Migrating Clients...")
    client_mapping_c2 = {}
    cursor.execute("SELECT * FROM inventory_client")
    for r in cursor.fetchall():
        # Create client for Company 1 (Casting Foundry) with original ID
        Client.objects.create(
            id=r['id'],
            client_code=f"CL-{1000 + r['id']}",
            name=r['name'],
            active=r['active'],
            city=r['city'],
            phone=r['phone'],
            address=r['address'],
            email=r['email'],
            gst_number=r['gst_number'],
            company=c1
        )
        # Create client for Company 2 (Finishing Processor) with explicit non-colliding ID
        c2_client = Client.objects.create(
            id=r['id'] + 1000,
            client_code=f"CL-{2000 + r['id']}",
            name=r['name'],
            active=r['active'],
            city=r['city'],
            phone=r['phone'],
            address=r['address'],
            email=r['email'],
            gst_number=r['gst_number'],
            company=c2
        )
        client_mapping_c2[r['id']] = c2_client.id

    # 6. Migrate Warehouses
    print("Migrating Warehouses...")
    cursor.execute("SELECT * FROM inventory_warehouse")
    for r in cursor.fetchall():
        # Scoping warehouses to appropriate companies
        comp = c1 if r['code'] == 'CASTING' else c2
        Warehouse.objects.create(
            id=r['id'],
            name=r['name'],
            code=r['code'],
            created_at=r['created_at'],
            company=comp
        )

    # 7. Migrate Workers
    print("Migrating Workers...")
    cursor.execute("SELECT * FROM inventory_worker")
    for r in cursor.fetchall():
        Worker.objects.create(
            id=r['id'],
            name=r['name'],
            process=r['process'],
            phone=r['phone'],
            active=r['active'],
            created_at=r['created_at'],
            daily_rate=r['daily_rate'],
            monthly_fixed_salary=r['monthly_fixed_salary'],
            overtime_rate=r['overtime_rate'],
            salary_model=r['salary_model'],
            blood_group=r['blood_group'],
            designation=r['designation'],
            emergency_contact_name=r['emergency_contact_name'],
            emergency_contact_phone=r['emergency_contact_phone'],
            employee_id=r['employee_id'],
            identity_number=r['identity_number'],
            joining_date=r['joining_date'] if r['joining_date'] else None,
            standard_shift_hours=r['standard_shift_hours'],
            monthly_allowance=r['monthly_allowance'],
            company=c2  # All old workers belong to finishing/packaging
        )

    # 8. Migrate JobWorkers into unified Worker model
    print("Migrating JobWorkers...")
    jw_map = {}
    cursor.execute("SELECT * FROM inventory_jobworker")
    for r in cursor.fetchall():
        w_obj = Worker.objects.create(
            worker_type=WorkerType.JOB_WORKER,
            name=r['name'],
            process=r['process'],
            phone=r['phone'],
            address=r['address'],
            active=r['active'],
            created_at=r['created_at'],
            email=r['email'],
            gst_number=r['gst_number'],
            jw_code=r['jw_code'],
            company=c2  # All old job workers belong to finishing (machining/polishing)
        )
        jw_map[r['id']] = w_obj.id

    # 9. Migrate Items
    print("Migrating Items...")
    cursor.execute("SELECT * FROM inventory_item")
    for r in cursor.fetchall():
        # Scoping item company
        item_company = c1 if r['casting_required'] and not (r['machining_required'] or r['polishing_required']) else None
        
        Item.objects.create(
            id=r['id'],
            code=r['code'],
            name=r['name'],
            category=r['category'].upper() if r['category'] else 'OTHER',
            sub_category=r['sub_category'],
            material=r['material'].upper() if r['material'] else 'OTHER',
            variant=r['variant'],
            item_type=r['item_type'] if r['item_type'] else 'REGULAR',
            notes=r['notes'],
            casting_required=r['casting_required'],
            machining_required=r['machining_required'],
            polishing_required=r['polishing_required'],
            packing_required=r['packing_required'],
            casting_weight=r['casting_weight'] if r['casting_weight'] else 0.0,
            machining_weight=r['machining_weight'] if r['machining_weight'] else 0.0,
            lot_size=r['lot_size'] if r['lot_size'] else 1,
            lot_with_box=r['lot_with_box'] if r['lot_with_box'] else 1,
            rate_per_piece=r['rate_per_piece'] if r['rate_per_piece'] else 0.0,
            active=r['active'],
            created_at=r['created_at'],
            company=item_company,
            client_id=r['client_id']  # Maps to Company 1 client (id matches)
        )

    # 10. Migrate ItemCompositions (BOM)
    print("Migrating ItemCompositions...")
    cursor.execute("SELECT * FROM inventory_itemcomposition")
    for r in cursor.fetchall():
        ItemComposition.objects.create(
            id=r['id'],
            quantity=r['quantity'],
            component_item_id=r['component_item_id'],
            parent_item_id=r['parent_item_id']
        )

    # 11. Migrate StockTransactions
    print("Migrating StockTransactions...")
    cursor.execute("SELECT * FROM inventory_stocktransaction")
    for r in cursor.fetchall():
        w_id = r['worker_id'] or (jw_map.get(r['job_worker_id']) if r['job_worker_id'] else None)
        StockTransaction.objects.create(
            id=r['id'],
            quantity=r['quantity'],
            item_id=r['item_id'],
            created_at=r['created_at'],
            weight=r['weight'] if r['weight'] else 0.0,
            client_id=r['client_id'],  # Maps to Company 1 client
            heat_no=r['heat_no'],
            notes=r['notes'],
            worker_id=w_id,
            lot_quantity=r['lot_quantity'] if r['lot_quantity'] else 0,
            transaction_type=r['transaction_type'],
            from_warehouse_id=r['from_warehouse_id'],
            to_warehouse_id=r['to_warehouse_id'],
            rejection_quantity=r['rejection_quantity'] if r['rejection_quantity'] else 0
        )

    # 12. Migrate ItemWorkerAllocations
    print("Migrating ItemWorkerAllocations...")
    cursor.execute("SELECT * FROM inventory_itemworkerallocation")
    for r in cursor.fetchall():
        w_id = r['worker_id'] or (jw_map.get(r['job_worker_id']) if r['job_worker_id'] else None)
        ItemWorkerAllocation.objects.create(
            id=r['id'],
            rate_per_piece=r['rate_per_piece'] if r['rate_per_piece'] else 0.0,
            item_id=r['item_id'],
            worker_id=w_id
        )

    # 13. Migrate Attendance
    print("Migrating Attendance...")
    cursor.execute("SELECT * FROM inventory_attendance")
    for r in cursor.fetchall():
        Attendance.objects.create(
            id=r['id'],
            date=r['date'],
            status=r['status'],
            overtime_hours=r['overtime_hours'] if r['overtime_hours'] else 0.0,
            notes=r['notes'],
            worker_id=r['worker_id']
        )

    # 14. Migrate Loans
    print("Migrating Loans...")
    cursor.execute("SELECT * FROM inventory_loan")
    for r in cursor.fetchall():
        w_id = r['worker_id'] or (jw_map.get(r['job_worker_id']) if r['job_worker_id'] else None)
        Loan.objects.create(
            id=r['id'],
            total_amount=r['total_amount'],
            emi_amount=r['emi_amount'],
            remaining_balance=r['remaining_balance'],
            issued_date=r['issued_date'],
            is_active=r['is_active'],
            description=r['description'],
            worker_id=w_id
        )

    # 15. Migrate LaborPayments
    print("Migrating LaborPayments...")
    cursor.execute("SELECT * FROM inventory_laborpayment")
    for r in cursor.fetchall():
        w_id = r['worker_id'] or (jw_map.get(r['job_worker_id']) if r['job_worker_id'] else None)
        LaborPayment.objects.create(
            id=r['id'],
            amount=r['amount'],
            date=r['date'],
            payment_type=r['payment_type'],
            payment_mode=r['payment_mode'],
            reference_no=r['reference_no'],
            notes=r['notes'],
            worker_id=w_id
        )

    # 16. Migrate Cartons
    print("Migrating Cartons...")
    cursor.execute("SELECT * FROM inventory_carton")
    for r in cursor.fetchall():
        old_client_id = r['client_id']
        # Map carton client to Company 2 client
        new_client_id = client_mapping_c2.get(old_client_id) if old_client_id else None
        
        Carton.objects.create(
            id=r['id'],
            carton_number=r['carton_number'],
            carton_type=r['carton_type'],
            carton_label=r['carton_label'],
            cleaning=r['cleaning'],
            labeling=r['labeling'],
            packing=r['packing'],
            total_quantity=r['total_quantity'],
            total_weight=r['total_weight'],
            status=r['status'],
            dispatched_at=r['dispatched_at'],
            created_at=r['created_at'],
            client_id=new_client_id
        )

    # 17. Migrate CartonItems
    print("Migrating CartonItems...")
    cursor.execute("SELECT * FROM inventory_cartonitem")
    for r in cursor.fetchall():
        CartonItem.objects.create(
            id=r['id'],
            quantity=r['quantity'],
            weight=r['weight'] if r['weight'] else 0.0,
            carton_id=r['carton_id'],
            item_id=r['item_id']
        )

    conn.close()
    print("All data successfully migrated and fully functional!")

if __name__ == "__main__":
    main()
