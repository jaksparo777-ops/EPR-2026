import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
target_dir = BASE_DIR / "apps" / "production" / "views"

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            # Clean up duplicates at end of import lines
            content = content.replace("Carton, CartonItem ItemWorkerAllocation", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem ItemComposition", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem Warehouse", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem Client", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem Worker", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem Category", "Carton, CartonItem")
            content = content.replace("Carton, CartonItem Material", "Carton, CartonItem")
            
            with open(filepath, "w") as f:
                f.write(content)
            print(f"Cleaned syntax appends in {filepath}")
