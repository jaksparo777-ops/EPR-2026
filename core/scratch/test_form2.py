import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from inventory.forms import ItemForm

data = {
    "code": "TEST2",
    "name": "Test Item 2",
    "category": "OTHER",
    "casting_weight": 0,
    "machining_weight": 0,
    "lot_size": 0,
    "lot_with_box": 0,
    "client": "",
    "material": "",
    "variant": "",
    "notes": ""
}

form = ItemForm(data)
if not form.is_valid():
    print("ERRORS:", form.errors)
else:
    print("VALID!")
