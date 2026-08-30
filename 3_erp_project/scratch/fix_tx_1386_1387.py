import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import StockTransaction
from apps.authentication.models import Worker, JobWorker, WorkerType

# Delete auto-generated surplus transaction #1386
deleted_auto = StockTransaction.objects.filter(id=1386).delete()
print(f"Deleted auto-surplus transaction #1386: {deleted_auto}")

# Update transaction #1387 to point to Ramesh bhai's Worker record
tx_1387 = StockTransaction.objects.filter(id=1387).first()
if tx_1387:
    ramesh_worker = Worker.objects.filter(name__iexact="Ramesh bhai").first()
    ramesh_jw = JobWorker.objects.filter(name__iexact="Ramesh bhai").first()
    
    tx_1387.worker = ramesh_worker
    tx_1387.job_worker = ramesh_jw
    tx_1387.save()
    print(f"Updated tx #1387 worker to {ramesh_worker} and job_worker to {ramesh_jw}")

print("Done.")
