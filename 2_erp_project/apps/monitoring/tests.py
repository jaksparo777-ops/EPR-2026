from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils import timezone
from apps.monitoring.models import UserSession, AuditLog
from apps.workforce.models import Worker
from apps.products.models import Material

class MonitoringSystemTestCase(TestCase):
    def setUp(self):
        # Create standard test password
        self.password = "Foundry@2026"
        
        # Setup groups
        self.admin_group, _ = Group.objects.get_or_create(name='System Admin')
        self.operator_group, _ = Group.objects.get_or_create(name='Production Operator')
        
        # Create users
        self.admin_user = User.objects.create_user(
            username='admin_operator', 
            email='admin@foundry.com', 
            password=self.password
        )
        self.admin_user.groups.add(self.admin_group)
        
        self.operator_user = User.objects.create_user(
            username='standard_operator', 
            email='operator@foundry.com', 
            password=self.password
        )
        self.operator_user.groups.add(self.operator_group)
        
        # Set up a testing client
        self.client = Client()

    def test_login_creates_session_and_audit(self):
        """Verify that logging in registers a UserSession and logs an login audit entry."""
        # Clean existing sessions/logs to isolate test
        UserSession.objects.all().delete()
        AuditLog.objects.all().delete()
        
        # Authenticate Standard Operator
        login_success = self.client.login(username='standard_operator', password=self.password)
        self.assertTrue(login_success)
        
        # Make a dummy request to trigger session creation in middleware
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check active session created
        sessions = UserSession.objects.filter(user=self.operator_user, is_active=True)
        self.assertEqual(sessions.count(), 1)
        session = sessions.first()
        self.assertEqual(session.device_type, 'Desktop') # Default client is desktop user agent
        
        # Check audit log entry
        login_audits = AuditLog.objects.filter(user=self.operator_user, action='LOGIN')
        self.assertEqual(login_audits.count(), 1)
        self.assertIn("successfully authenticated", login_audits.first().details)

    def test_database_operation_auditing(self):
        """Verify that db insertions/modifications automatically generate detailed AuditLog entries."""
        # Log in standard operator
        self.client.login(username='standard_operator', password=self.password)
        
        # Perform request that saves a model to the DB.
        # To avoid UI form dependency, we trigger save inside a mock request block
        # Or let's trigger it directly. The middleware sets the contextvars thread-locals.
        # Let's test that when contextvars are set, saving a model records the user.
        from apps.monitoring.middleware import _user, _ip
        
        user_token = _user.set(self.operator_user)
        ip_token = _ip.set("127.0.0.1")
        
        try:
            # Create a Material
            material = Material.objects.create(name="Graphite Powder")
            
            # Verify AuditLog created
            material_audits = AuditLog.objects.filter(department='products', action='CREATE')
            self.assertEqual(material_audits.count(), 1)
            audit = material_audits.first()
            self.assertEqual(audit.user, self.operator_user)
            self.assertEqual(audit.ip_address, "127.0.0.1")
            self.assertIn("Graphite Powder", audit.object_repr)
            self.assertIn("Graphite Powder", audit.details)
            
            # Update the Material
            material.name = "Graphite Dust"
            material.save()
            
            update_audits = AuditLog.objects.filter(department='products', action='UPDATE')
            self.assertEqual(update_audits.count(), 1)
            self.assertIn("updated", update_audits.first().details)
            
            # Delete the Material
            material.delete()
            delete_audits = AuditLog.objects.filter(department='products', action='DELETE')
            self.assertEqual(delete_audits.count(), 1)
            self.assertIn("deleted", delete_audits.first().details)
            
        finally:
            _user.reset(user_token)
            _ip.reset(ip_token)

    def test_dashboard_access_restrictions(self):
        """Verify that only users with System Admin role can access the monitoring center."""
        # 1. Non-admin operator tries to access
        self.client.login(username='standard_operator', password=self.password)
        response = self.client.get(reverse('monitoring_dashboard'))
        # Should deny access and redirect to dashboard
        self.assertRedirects(response, reverse('dashboard'))
        
        # 2. Admin operator tries to access
        self.client.login(username='admin_operator', password=self.password)
        response = self.client.get(reverse('monitoring_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_session_termination_force_logout(self):
        """Verify that force-killing a session logs out the user on their next request."""
        # Log in standard operator
        self.client.login(username='standard_operator', password=self.password)
        
        # Visit page to register UserSession
        self.client.get(reverse('dashboard'))
        session_record = UserSession.objects.get(user=self.operator_user, is_active=True)
        
        # Simulate Admin force terminating standard operator session via POST
        self.client.login(username='admin_operator', password=self.password)
        response = self.client.post(reverse('terminate_session', args=[session_record.id]))
        self.assertRedirects(response, reverse('monitoring_dashboard'))
        
        # Verify custom session is inactive
        session_record.refresh_from_db()
        self.assertFalse(session_record.is_active)
        
        # Verify standard operator's client is force logged out on subsequent requests
        # We restore the standard operator's client session keys
        self.client.login(username='standard_operator', password=self.password)
        # Manually force set the terminated session key on client
        session = self.client.session
        session_record.session_key = session.session_key
        session_record.is_active = False
        session_record.save()
        
        # Try to view a page
        response = self.client.get(reverse('dashboard'))
        # Should be forced to redirect to login page!
        self.assertRedirects(response, reverse('login'))

    def test_soft_deletes(self):
        """Verify soft deletion behavior on Client, Item, Worker, and JobWorker."""
        from apps.products.models import Client, Item
        from apps.workforce.models import Worker, JobWorker

        # Create test Client and Item
        client = Client.objects.create(name="Soft Client Ltd")
        item = Item.objects.create(
            client=client,
            code="SOFT-001",
            name="Soft Bracket",
            casting_required=True,
            machining_required=False,
            polishing_required=False,
            packing_required=False
        )

        # Create Worker and JobWorker
        worker = Worker.objects.create(name="Soft Worker", salary_model="DAILY", daily_rate=500)
        jw = JobWorker.objects.create(name="Soft JobWorker", process="casting")

        # Verify initial states
        self.assertFalse(client.is_deleted)
        self.assertFalse(item.is_deleted)
        self.assertFalse(worker.is_deleted)
        self.assertFalse(jw.is_deleted)

        # Perform soft delete
        client.delete()
        item.delete()
        worker.delete()
        jw.delete()

        # Refresh
        client.refresh_from_db()
        item.refresh_from_db()
        worker.refresh_from_db()
        jw.refresh_from_db()

        # Assert marked as deleted
        self.assertTrue(client.is_deleted)
        self.assertTrue(item.is_deleted)
        self.assertTrue(worker.is_deleted)
        self.assertTrue(jw.is_deleted)

        # Assert hidden from standard managers
        self.assertFalse(Client.objects.filter(id=client.id).exists())
        self.assertFalse(Item.objects.filter(id=item.id).exists())
        self.assertFalse(Worker.objects.filter(id=worker.id).exists())
        self.assertFalse(JobWorker.objects.filter(id=jw.id).exists())

        # Assert visible in all_objects manager
        self.assertTrue(Client.all_objects.filter(id=client.id).exists())
        self.assertTrue(Item.all_objects.filter(id=item.id).exists())
        self.assertTrue(Worker.all_objects.filter(id=worker.id).exists())
        self.assertTrue(JobWorker.all_objects.filter(id=jw.id).exists())

    def test_database_backup_command(self):
        """Verify the custom backup_db management command produces compressed outputs."""
        import os
        from django.conf import settings
        from django.core.management import call_command
        import gzip
        import json

        # Ensure we have a backup directory
        backups_dir = os.path.join(settings.BASE_DIR, 'backups')
        
        # Run command
        call_command('backup_db')

        # Assert folder exists
        self.assertTrue(os.path.exists(backups_dir))
        
        # Find files in backup folder
        files = [os.path.join(backups_dir, f) for f in os.listdir(backups_dir) if f.endswith('.json.gz')]
        self.assertTrue(len(files) > 0)
        
        latest_file = max(files, key=os.path.getctime)
        self.assertTrue(os.path.exists(latest_file))
        self.assertTrue(os.path.getsize(latest_file) > 0)

        # Verify compression contains valid JSON data
        with gzip.open(latest_file, 'rt', encoding='utf-8') as f:
            data = json.load(f)
            self.assertIsInstance(data, list)

    def test_csv_log_export(self):
        """Verify the CSV Log Export view streams correct formatted outputs and respects RBAC."""
        # Create a mock audit log entry to ensure data exists
        AuditLog.objects.create(
            user=self.admin_user,
            ip_address="127.0.0.1",
            department="security",
            action="CREATE",
            object_repr="Test Security Object",
            details="Verifying CSV Export Capability."
        )

        # 1. Non-admin operator tries to export logs
        self.client.login(username='standard_operator', password=self.password)
        response = self.client.get(reverse('export_audit_logs'))
        # Should deny access and redirect
        self.assertRedirects(response, reverse('dashboard'))

        # 2. Admin operator tries to export logs
        self.client.login(username='admin_operator', password=self.password)
        response = self.client.get(reverse('export_audit_logs'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertTrue(response.streaming)

        # Parse CSV stream content
        content = b"".join(response.streaming_content).decode('utf-8')
        lines = content.splitlines()
        self.assertTrue(len(lines) >= 2) # Header + at least one data row
        
        # Assert header values
        self.assertIn("Timestamp", lines[0])
        self.assertIn("Operator", lines[0])
        self.assertIn("IP Address", lines[0])
        self.assertIn("Department", lines[0])
        self.assertIn("Action", lines[0])
        self.assertIn("Target Object", lines[0])
        self.assertIn("Details", lines[0])
        
        # Assert details value is in the data row
        self.assertIn("Verifying CSV Export Capability.", content)

