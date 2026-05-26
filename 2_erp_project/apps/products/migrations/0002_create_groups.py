from django.db import migrations

def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='System Admin')
    Group.objects.get_or_create(name='Production Operator')
    Group.objects.get_or_create(name='Logistics Supervisor')
    Group.objects.get_or_create(name='HR & Accounts Manager')

def remove_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=[
        'System Admin',
        'Production Operator',
        'Logistics Supervisor',
        'HR & Accounts Manager'
    ]).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
