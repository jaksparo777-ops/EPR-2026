import os, sys, django
sys.path.append('/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.production.models import LaborPayment

payments = LaborPayment.objects.all().order_by('id')
print(f"Total LaborPayment records in DB: {payments.count()}\n")

for p in payments:
    target = p.job_worker.name if p.job_worker else (p.worker.name if p.worker else "Unknown")
    print(f"ID: {p.id} | Target: {target} | Date: {p.date} | Amount: {p.amount} | Type: {p.payment_type} | Mode: {p.payment_mode}")
