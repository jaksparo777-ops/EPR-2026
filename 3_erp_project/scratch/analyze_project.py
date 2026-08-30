import os
import django
from django.conf import settings
from django.apps import apps
import sys

# Set up Django environment
sys.path.insert(0, '/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def analyze_project():
    print("Project Analysis:")
    print("=================\n")
    
    total_models = 0
    total_views = 0 # this is hard to count dynamically, but we can try
    
    for app_config in apps.get_app_configs():
        # Only analyze our custom apps
        if app_config.path.startswith('/Users/kizzzz/erp_project/3_erp_project/apps'):
            print(f"App: {app_config.name}")
            models = app_config.get_models()
            model_count = len(list(models))
            total_models += model_count
            print(f"  Models: {model_count}")
            for model in app_config.get_models():
                print(f"    - {model.__name__} ({model._meta.db_table})")
                
            # Try to list view files
            views_dir = os.path.join(app_config.path, 'views')
            if os.path.exists(views_dir) and os.path.isdir(views_dir):
                view_files = [f for f in os.listdir(views_dir) if f.endswith('.py') and f != '__init__.py']
                print(f"  Views files: {len(view_files)}")
                for view_file in view_files:
                    print(f"    - {view_file}")
            else:
                view_file_path = os.path.join(app_config.path, 'views.py')
                if os.path.exists(view_file_path):
                    print(f"  Views file: views.py")
            print()

    print(f"Total Models in custom apps: {total_models}")

if __name__ == '__main__':
    analyze_project()
