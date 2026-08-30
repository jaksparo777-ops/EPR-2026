import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
target_dir = BASE_DIR / "apps" / "production" / "views"

replacements = {
    "from inventory.models import (": """from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem
# Removed legacy import: (""",
    "from inventory.models import": """from apps.master_data.models import LegalEntity, Client, Warehouse, Item, ItemComposition
from apps.authentication.models import Worker, ProcessType, SalaryModel
from apps.production.models import StockTransaction, TransactionType, ItemWorkerAllocation, Attendance, Loan, LaborPayment, Carton, CartonItem""",
    "from inventory import services": "from apps.production import services",
    "from inventory.forms import": "from apps.production.forms import",
}

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            original = content
            for old, new in replacements.items():
                content = content.replace(old, new)
            
            if content != original:
                with open(filepath, "w") as f:
                    f.write(content)
                print(f"Updated imports in {filepath}")
