import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction
from apps.authentication.models import Worker, JobWorker, WorkerType
from apps.production.models import StockTransaction, ItemWorkerAllocation, LaborPayment, Loan

@transaction.atomic
def run_migration():
    print("=== Starting Legacy JobWorker Migration into Worker ===")
    
    # 1. Migrate JobWorker entries into Worker model
    legacy_job_workers = JobWorker.objects.all()
    jw_to_worker_map = {} # JobWorker.id -> Worker instance
    
    for jw in legacy_job_workers:
        # Check if matching Worker already exists by jw_code or name
        worker = None
        if jw.jw_code:
            worker = Worker.objects.filter(jw_code=jw.jw_code).first()
        if not worker and jw.name:
            worker = Worker.objects.filter(name__iexact=jw.name, worker_type=WorkerType.JOB_WORKER).first()
        if not worker and jw.name:
            worker = Worker.objects.filter(name__iexact=jw.name).first()
            
        if not worker:
            worker = Worker.objects.create(
                worker_type=WorkerType.JOB_WORKER,
                name=jw.name,
                company=jw.company,
                process=jw.process or 'machining',
                phone=jw.phone,
                email=jw.email,
                address=jw.address,
                gst_number=jw.gst_number,
                jw_code=jw.jw_code or f"JW-{jw.id + 1000}",
                casting_rate_per_kg=jw.casting_rate_per_kg or 0.0,
                active=jw.active
            )
            print(f"Created new Worker record for JobWorker: {jw.name} (Worker ID {worker.id})")
        else:
            # Ensure worker_type is JOB_WORKER
            if worker.worker_type != WorkerType.JOB_WORKER:
                worker.worker_type = WorkerType.JOB_WORKER
            if not worker.jw_code and jw.jw_code:
                worker.jw_code = jw.jw_code
            worker.save()
            print(f"Found existing Worker for JobWorker {jw.name}: Worker ID {worker.id}")
            
        jw_to_worker_map[jw.id] = worker

    # 2. Update StockTransaction records where worker is NULL but job_worker is set
    txs_updated = 0
    for jw_id, worker in jw_to_worker_map.items():
        # Case A: job_worker set, worker NULL
        updated = StockTransaction.objects.filter(job_worker_id=jw_id, worker__isnull=True).update(worker=worker)
        txs_updated += updated
        # Case B: worker set, but update job_worker to match clean ID
        StockTransaction.objects.filter(job_worker_id=jw_id).update(job_worker=jw_id)
        
    print(f"Updated StockTransaction worker FK for {txs_updated} transactions.")

    # 3. Update ItemWorkerAllocation records
    allocs_updated = 0
    for jw_id, worker in jw_to_worker_map.items():
        updated = ItemWorkerAllocation.objects.filter(job_worker_id=jw_id, worker__isnull=True).update(worker=worker)
        allocs_updated += updated
    print(f"Updated ItemWorkerAllocation worker FK for {allocs_updated} allocations.")

    # 4. Update LaborPayment records
    payments_updated = 0
    for jw_id, worker in jw_to_worker_map.items():
        updated = LaborPayment.objects.filter(job_worker_id=jw_id, worker__isnull=True).update(worker=worker)
        payments_updated += updated
    print(f"Updated LaborPayment worker FK for {payments_updated} payments.")

    # 5. Update Loan records
    loans_updated = 0
    for jw_id, worker in jw_to_worker_map.items():
        updated = Loan.objects.filter(job_worker_id=jw_id, worker__isnull=True).update(worker=worker)
        loans_updated += updated
    print(f"Updated Loan worker FK for {loans_updated} loans.")

    print("=== Migration Completed Successfully ===")

if __name__ == "__main__":
    run_migration()
