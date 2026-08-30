import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
target_dir = BASE_DIR / "apps" / "production" / "views"

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            deleted_count = 0
            for idx, line in enumerate(lines):
                # If it's a global import (first 25 lines of the file), keep it!
                if idx < 25:
                    new_lines.append(line)
                    continue
                
                # Check if it is an inner import statement that got replaced
                stripped = line.strip()
                if (stripped.startswith("from apps.master_data.models import") or 
                    stripped.startswith("from apps.authentication.models import") or 
                    stripped.startswith("from apps.production.models import") or
                    stripped.startswith("from inventory.models import")):
                    deleted_count += 1
                    continue
                
                new_lines.append(line)
            
            if deleted_count > 0:
                with open(filepath, "w") as f:
                    f.writelines(new_lines)
                print(f"Deleted {deleted_count} inner imports in {filepath}")
