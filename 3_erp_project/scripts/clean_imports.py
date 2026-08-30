import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
target_dir = BASE_DIR / "apps" / "production" / "views"

pattern = re.compile(r"# Removed legacy import:\s*\(\s*.*?\s*\)", re.DOTALL)

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            original = content
            # Replace the pattern
            content = pattern.sub("", content)
            
            if content != original:
                with open(filepath, "w") as f:
                    f.write(content)
                print(f"Cleaned legacy block in {filepath}")
