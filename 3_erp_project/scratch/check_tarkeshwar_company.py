import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.authentication.models import Worker, JobWorker
from apps.master_data.models import LegalEntity

print("=== Tarkeshwar bhai in Worker model ===")
workers = Worker.objects.filter(name__icontains='Tarkeshwar')
for w in workers:
    print(f"Worker id={w.id}, name='{w.name}', company_id={w.company_id}, type={w.worker_type}, proc={w.process}")

print("\n=== Tarkeshwar bhai in JobWorker model ===")
jws = JobWorker.objects.filter(name__icontains='Tarkeshwar')
for jw in jws:
    print(f"JobWorker id={jw.id}, name='{jw.name}', company_id={jw.company_id}, proc={jw.process}")
