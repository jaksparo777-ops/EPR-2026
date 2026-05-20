import os
import sys
import sqlite3
import django

# Setup Django environment
sys.path.append('/Users/kizzzz/erp_project/core')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from inventory.models import Item, ItemWorkerAllocation, Worker, JobWorker
from django.db import transaction

def restore_corrupted_sets():
    backup_db_path = '/Users/kizzzz/erp_project/core/scratch/db_workspace_backup.sqlite3'
    if not os.path.exists(backup_db_path):
        print(f"Error: Backup database not found at {backup_db_path}")
        return

    print("Connecting to backup database...")
    conn = sqlite3.connect(backup_db_path)
    cursor = conn.cursor()

    target_ids = [12, 13, 14, 16, 19, 20, 22, 23]
    
    print("\n--- Phase 1: Restoring Item Types to REGULAR ---")
    with transaction.atomic():
        for item_id in target_ids:
            try:
                item = Item.objects.get(id=item_id)
                if item.item_type == 'SET':
                    print(f"Updating Item ID {item_id} ({item.name}) from SET to REGULAR...")
                    item.item_type = 'REGULAR'
                    item.save()
            except Item.DoesNotExist:
                print(f"Item ID {item_id} does not exist in the active database.")

    print("\n--- Phase 2: Restoring Labor Allocations from Backup ---")
    with transaction.atomic():
        for item_id in target_ids:
            try:
                item = Item.objects.get(id=item_id)
                # Clear existing allocations first to avoid duplicates
                deleted_count, _ = ItemWorkerAllocation.objects.filter(item=item).delete()
                if deleted_count > 0:
                    print(f"Cleared {deleted_count} active allocations for {item.name}")

                # Query allocations in backup for this item
                cursor.execute("""
                    SELECT worker_id, job_worker_id, rate_per_piece
                    FROM inventory_itemworkerallocation
                    WHERE item_id = ?
                """, (item_id,))
                
                rows = cursor.fetchall()
                for w_id, jw_id, rate in rows:
                    worker_obj = None
                    job_worker_obj = None
                    
                    if w_id:
                        # Find worker by ID in active database
                        worker_obj = Worker.objects.filter(id=w_id).first()
                        if not worker_obj:
                            # Try to find by name from backup
                            cursor.execute("SELECT name FROM inventory_worker WHERE id = ?", (w_id,))
                            name_row = cursor.fetchone()
                            if name_row:
                                worker_obj = Worker.objects.filter(name=name_row[0]).first()
                    
                    if jw_id:
                        # Find job worker by ID in active database
                        job_worker_obj = JobWorker.objects.filter(id=jw_id).first()
                        if not job_worker_obj:
                            # Try to find by name from backup
                            cursor.execute("SELECT name FROM inventory_jobworker WHERE id = ?", (jw_id,))
                            name_row = cursor.fetchone()
                            if name_row:
                                job_worker_obj = JobWorker.objects.filter(name=name_row[0]).first()

                    if worker_obj or job_worker_obj:
                        alloc = ItemWorkerAllocation.objects.create(
                            item=item,
                            worker=worker_obj,
                            job_worker=job_worker_obj,
                            rate_per_piece=rate
                        )
                        label = worker_obj.name if worker_obj else job_worker_obj.name
                        print(f" -> Restored Allocation for {item.name}: {label} @ ₹{rate}")
                    else:
                        print(f" -> Warning: Could not find matching worker for backup allocation (worker_id={w_id}, job_worker_id={jw_id})")

            except Item.DoesNotExist:
                pass

    print("\nRestore completed successfully!")
    conn.close()

if __name__ == '__main__':
    restore_corrupted_sets()
