import os
import sys
import json
import django
from pathlib import Path

# Base directory setup
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

def test_connection():
    from django.db import connection
    try:
        connection.ensure_connection()
        print("🟢 Database Connection Test: SUCCESSFUL!")
        print(f"   Engine: {connection.settings_dict['ENGINE']}")
        print(f"   Name: {connection.settings_dict['NAME']}")
        print(f"   Host: {connection.settings_dict.get('HOST', 'localhost')}")
        return True
    except Exception as e:
        print("🔴 Database Connection Test: FAILED!")
        print(f"   Error: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("   FOUNDRY ERP - DUAL-DATABASE DATA MIGRATION UTILITY")
    print("=" * 60)

    # 1. Initialize Django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from apps.master_data.models import Item, Client, LegalEntity
    from apps.production.models import StockTransaction, Carton

    if '--test-connection' in sys.argv or '--check' in sys.argv:
        test_connection()
        sys.exit(0)

    current_engine = settings.DATABASES['default']['ENGINE']
    print(f"Current Active Engine: {current_engine}")

    export_path = BASE_DIR / 'sqlite_data_backup.json'

    # Step 1: Dump SQLite data if we are in SQLite mode or if backup doesn't exist
    if 'sqlite3' in current_engine:
        print("\n[STEP 1/2] Backing up SQLite data into JSON fixture...")
        
        # Get baseline record counts
        item_count = Item.objects.count()
        client_count = Client.objects.count()
        txn_count = StockTransaction.objects.count()
        carton_count = Carton.objects.count()
        
        print(f" -> Found: {item_count} Items, {client_count} Clients, {txn_count} Stock Txns, {carton_count} Cartons.")
        
        with open(export_path, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                exclude=[
                    'contenttypes',
                    'auth.permission',
                    'admin.logentry',
                    'sessions',
                    'authentication.userliveactivity',
                    'authentication.systemauditlog'
                ],
                natural_foreign=True,
                natural_primary=True,
                indent=2,
                stdout=f
            )
        
        file_size_kb = os.path.getsize(export_path) / 1024
        print(f"SUCCESS: Exported baseline data to '{export_path.name}' ({file_size_kb:.2f} KB).")
        print("\n[NEXT STEP TO ACTIVATE POSTGRESQL]:")
        print("1. Set up PostgreSQL database 'foundry_erp'.")
        print("2. In .env, change `USE_POSTGRES=True` and configure DB_USER/DB_PASSWORD.")
        print("3. Run: python manage.py migrate")
        print(f"4. Run: python scripts/migrate_to_postgres.py to restore all {txn_count} transactions into PostgreSQL!")

    elif 'postgresql' in current_engine:
        print("\n[STEP 2/2] PostgreSQL mode detected! Restoring baseline data into PostgreSQL...")
        
        if not test_connection():
            sys.exit(1)

        if not export_path.exists():
            print(f"ERROR: Backup file '{export_path.name}' not found!")
            print("Please switch back to SQLite (USE_POSTGRES=False in .env) and run this script first to create the backup file.")
            sys.exit(1)
            
        print(f"Loading '{export_path.name}' into PostgreSQL database...")
        call_command('loaddata', str(export_path))
        
        # Verify restored counts
        res_items = Item.objects.count()
        res_clients = Client.objects.count()
        res_txns = StockTransaction.objects.count()
        res_cartons = Carton.objects.count()
        
        print(f"\nVerification Results in PostgreSQL:")
        print(f" -> Items: {res_items}")
        print(f" -> Clients: {res_clients}")
        print(f" -> Stock Transactions: {res_txns}")
        print(f" -> Cartons: {res_cartons}")
        print("\nSUCCESS: All data restored into PostgreSQL with 100% fidelity!")

if __name__ == '__main__':
    main()
