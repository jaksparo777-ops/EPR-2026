from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from apps.products.models import Item
from apps.workforce.models import Worker, JobWorker
from apps.ledger_pay.models import ItemWorkerAllocation
from apps.products.bulk_import import (
    validate_items_data,
    validate_workers_data,
    validate_job_workers_data,
    commit_items_import,
    commit_workers_import,
    commit_job_workers_import,
)

class SecurityRBACAndAccessTestCase(TestCase):
    """
    Automated verification of role-based access control (RBAC).
    Verifies that unauthenticated, unauthorized, and authorized users
    are handled correctly by core decorators and middleware.
    """

    def setUp(self):
        self.client = Client()

        # Retrieve or create Groups
        self.admin_group, _ = Group.objects.get_or_create(name='System Admin')
        self.operator_group, _ = Group.objects.get_or_create(name='Production Operator')
        self.logistics_group, _ = Group.objects.get_or_create(name='Logistics Supervisor')
        self.hr_group, _ = Group.objects.get_or_create(name='HR & Accounts Manager')

        # Create test users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            email='admin@test.com',
            password='testpassword'
        )
        self.admin_user.groups.add(self.admin_group)

        self.operator_user = User.objects.create_user(
            username='operator_test',
            email='operator@test.com',
            password='testpassword'
        )
        self.operator_user.groups.add(self.operator_group)

        self.logistics_user = User.objects.create_user(
            username='logistics_test',
            email='logistics@test.com',
            password='testpassword'
        )
        self.logistics_user.groups.add(self.logistics_group)

        self.hr_user = User.objects.create_user(
            username='hr_test',
            email='hr@test.com',
            password='testpassword'
        )
        self.hr_user.groups.add(self.hr_group)

        self.regular_user = User.objects.create_user(
            username='regular_test',
            email='regular@test.com',
            password='testpassword'
        )

        # Standard secure URLs for verification
        self.dashboard_url = reverse('dashboard')
        self.casting_url = reverse('casting_entry')
        self.packaging_url = reverse('packaging')
        self.labor_ledger_url = reverse('labor_ledger')

    def test_unauthenticated_user_redirects_to_login(self):
        """
        Unauthenticated requests to restricted pages must redirect to the login screen.
        """
        urls = [self.dashboard_url, self.casting_url, self.packaging_url, self.labor_ledger_url]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)

    def test_production_operator_access(self):
        """
        Production operators must have access to furnace casting, machining, etc.,
        but be strictly blocked from packaging and payroll.
        """
        self.client.login(username='operator_test', password='testpassword')

        # 1. Allowed sections
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(self.casting_url)
        self.assertEqual(response.status_code, 200)

        # 2. Blocked sections (redirect to dashboard with error)
        response = self.client.get(self.packaging_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

        response = self.client.get(self.labor_ledger_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

    def test_logistics_supervisor_access(self):
        """
        Logistics supervisors must have access to dispatch and packaging dashboards,
        but be strictly blocked from casting logs and payroll ledger.
        """
        self.client.login(username='logistics_test', password='testpassword')

        # 1. Allowed sections
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(self.packaging_url)
        self.assertEqual(response.status_code, 200)

        # 2. Blocked sections
        response = self.client.get(self.casting_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

        response = self.client.get(self.labor_ledger_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

    def test_hr_accounts_manager_access(self):
        """
        HR/Accounts managers must have access to worker records and salary ledgers,
        but be blocked from casting logs and packaging queues.
        """
        self.client.login(username='hr_test', password='testpassword')

        # 1. Allowed sections
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(self.labor_ledger_url)
        self.assertEqual(response.status_code, 200)

        # 2. Blocked sections
        response = self.client.get(self.casting_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

        response = self.client.get(self.packaging_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

    def test_system_admin_bypass_and_global_access(self):
        """
        System admin user (or superuser/staff) must have unrestricted global access.
        """
        self.client.login(username='admin_test', password='testpassword')

        urls = [self.dashboard_url, self.casting_url, self.packaging_url, self.labor_ledger_url]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_unauthorized_regular_user_blocked_from_all(self):
        """
        A standard authenticated user with no specific role/groups must be blocked
        from all operational screens except the dashboard.
        """
        self.client.login(username='regular_test', password='testpassword')

        # 1. Allowed sections
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

        # 2. Blocked sections
        restricted_urls = [self.casting_url, self.packaging_url, self.labor_ledger_url]
        for url in restricted_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, self.dashboard_url)


class BulkImportTestCase(TestCase):
    """
    Automated verification of bulk importing engine (items and workers).
    Validates formatting checks, Excel/CSV parsed converters, and transactional rollback.
    """

    def setUp(self):
        self.client = Client()
        self.admin_group, _ = Group.objects.get_or_create(name='System Admin')
        self.admin_user = User.objects.create_user(
            username='import_admin',
            email='import_admin@test.com',
            password='testpassword'
        )
        self.admin_user.groups.add(self.admin_group)

    def test_validate_items_correct_data(self):
        """
        Tests that validate_items_data correctly parses valid item spreadsheet rows.
        """
        rows = [
            ["ITM001", "Cast Bolt", "Bolt", "Hex", "Steel", "10mm", "0.25", "0.20", "15.5", "100", "110", "Y", "Y", "N", "N", "Test note"]
        ]
        validated = validate_items_data(rows)
        self.assertEqual(len(validated), 1)
        row = validated[0]
        self.assertEqual(row["action"], "INSERT")
        self.assertEqual(len(row["errors"]), 0)
        self.assertEqual(row["data"]["code"], "ITM001")
        self.assertEqual(row["data"]["name"], "Cast Bolt")
        self.assertEqual(row["data"]["casting_weight"], 0.25)
        self.assertEqual(row["data"]["machining_weight"], 0.2)
        self.assertEqual(row["data"]["rate_per_piece"], 15.5)
        self.assertEqual(row["data"]["lot_size"], 100)
        self.assertEqual(row["data"]["lot_with_box"], 110)
        self.assertTrue(row["data"]["casting_required"])
        self.assertTrue(row["data"]["machining_required"])
        self.assertFalse(row["data"]["polishing_required"])
        self.assertFalse(row["data"]["packing_required"])

    def test_validate_items_missing_required_fields(self):
        """
        Tests that validate_items_data correctly identifies missing code or name.
        """
        rows = [
            ["", "Item Without Code", "Bolt"],
            ["ITM002", "", "Bolt"]
        ]
        validated = validate_items_data(rows)
        self.assertEqual(len(validated), 2)
        self.assertEqual(validated[0]["action"], "ERROR")
        self.assertIn("Item Code is required.", validated[0]["errors"])
        self.assertEqual(validated[1]["action"], "ERROR")
        self.assertIn("Item Name is required.", validated[1]["errors"])

    def test_validate_items_negative_numbers_and_invalid_booleans(self):
        """
        Tests that validate_items_data identifies numeric and boolean errors.
        """
        rows = [
            ["ITM003", "Test Item", "Bolt", "", "", "", "-0.5", "abc", "-10", "abc", "0", "INVALID_BOOL", "Y"]
        ]
        validated = validate_items_data(rows)
        self.assertEqual(validated[0]["action"], "ERROR")
        errors = validated[0]["errors"]
        self.assertTrue(any("Casting weight cannot be negative" in e for e in errors))
        self.assertTrue(any("'abc' is not a valid decimal number" in e for e in errors))
        self.assertTrue(any("Rate per piece cannot be negative" in e for e in errors))
        self.assertTrue(any("'abc' is not a valid whole number" in e for e in errors))
        self.assertTrue(any("'INVALID_BOOL' must be Y or N" in e for e in errors))

    def test_validate_workers_correct_data(self):
        """
        Tests that validate_workers_data correctly parses valid worker rows.
        """
        rows = [
            ["Vijay Patel", "EMP001", "9876543210", "Caster", "casting", "500", "8", "DAILY", "", "", "50", "12345", "Emergency", "99999", "A+"]
        ]
        validated = validate_workers_data(rows)
        self.assertEqual(len(validated), 1)
        row = validated[0]
        self.assertEqual(row["action"], "INSERT")
        self.assertEqual(len(row["errors"]), 0)
        self.assertEqual(row["data"]["name"], "Vijay Patel")
        self.assertEqual(row["data"]["employee_id"], "EMP001")
        self.assertEqual(row["data"]["process"], "casting")
        self.assertEqual(row["data"]["daily_rate"], 500.0)
        self.assertEqual(row["data"]["salary_model"], "DAILY")
        self.assertEqual(row["data"]["overtime_rate"], 50.0)

    def test_validate_workers_missing_or_invalid_fields(self):
        """
        Tests that validate_workers_data detects missing fields or invalid process.
        """
        rows = [
            ["", "EMP002", "", "Operator", "casting", "400", "8", "DAILY"],
            ["Ramesh Kumar", "EMP003", "", "Operator", "invalid_proc", "400", "8", "DAILY"],
            ["Suresh Kumar", "EMP004", "", "Operator", "casting", "400", "8", "MONTHLY"]
        ]
        validated = validate_workers_data(rows)
        self.assertEqual(validated[0]["action"], "ERROR")
        self.assertIn("Worker Name is required.", validated[0]["errors"])
        self.assertEqual(validated[1]["action"], "ERROR")
        self.assertIn("Process must be one of: casting, machining, polishing, packaging.", validated[1]["errors"])
        self.assertEqual(validated[2]["action"], "ERROR")
        self.assertIn("Salary Model must be DAILY or FIXED.", validated[2]["errors"])

    def test_commit_items_atomic_rollback(self):
        """
        Tests that commit_items_import is atomic: if one row has an error, nothing is saved.
        """
        rows = [
            {
                "row_idx": 1,
                "action": "INSERT",
                "errors": [],
                "data": {
                    "code": "TX001", "name": "Item A", "category": "Bolt", "sub_category": "", "material": "Steel", "variant": "",
                    "casting_weight": 0.1, "machining_weight": 0.1, "rate_per_piece": 10.0, "lot_size": 100, "lot_with_box": 100,
                    "casting_required": True, "machining_required": True, "polishing_required": False, "packing_required": False, "notes": ""
                }
            },
            {
                "row_idx": 2,
                "action": "ERROR",
                "errors": ["Some error occurred"],
                "data": {"code": "TX002", "name": "Item B"}
            }
        ]
        
        initial_count = Item.objects.filter(code="TX001").count()
        self.assertEqual(initial_count, 0)
        
        with self.assertRaises(ValueError):
            commit_items_import(rows)
            
        # Verify row 1 was NOT saved (rolled back successfully)
        self.assertEqual(Item.objects.filter(code="TX001").count(), 0)

    def test_commit_items_success_and_updates(self):
        """
        Tests that commit_items_import saves new records and updates existing ones.
        """
        # Create an existing item
        Item.objects.create(
            code="ITM-EXIST",
            name="Old Name",
            category="Old Cat",
            rate_per_piece=5.0
        )
        
        rows = [
            {
                "row_idx": 1,
                "action": "INSERT",
                "errors": [],
                "data": {
                    "code": "ITM-NEW", "name": "New Item", "category": "Cat", "sub_category": "", "material": "Iron", "variant": "",
                    "casting_weight": 1.0, "machining_weight": 1.0, "rate_per_piece": 12.0, "lot_size": 50, "lot_with_box": 50,
                    "casting_required": True, "machining_required": True, "polishing_required": True, "packing_required": True, "notes": ""
                }
            },
            {
                "row_idx": 2,
                "action": "UPDATE",
                "errors": [],
                "data": {
                    "code": "ITM-EXIST", "name": "Updated Name", "category": "New Cat", "sub_category": "", "material": "Steel", "variant": "",
                    "casting_weight": 1.5, "machining_weight": 1.2, "rate_per_piece": 7.5, "lot_size": 200, "lot_with_box": 210,
                    "casting_required": True, "machining_required": True, "polishing_required": False, "packing_required": False, "notes": "Updated"
                }
            }
        ]
        
        created, updated = commit_items_import(rows)
        self.assertEqual(created, 1)
        self.assertEqual(updated, 1)
        
        # Verify new item
        new_item = Item.objects.get(code="ITM-NEW")
        self.assertEqual(new_item.name, "New Item")
        self.assertEqual(new_item.rate_per_piece, 12.0)
        
        # Verify updated item
        updated_item = Item.objects.get(code="ITM-EXIST")
        self.assertEqual(updated_item.name, "Updated Name")
        self.assertEqual(updated_item.rate_per_piece, 7.5)
        self.assertFalse(updated_item.polishing_required)

    def test_template_download_endpoints(self):
        """
        Tests template download endpoints return appropriate content-types.
        """
        self.client.login(username='import_admin', password='testpassword')
        
        # Items Template xlsx
        res1 = self.client.get(reverse('download_item_template') + '?format=xlsx')
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        # Workers Template csv
        res2 = self.client.get(reverse('download_worker_template') + '?format=csv')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2['Content-Type'], 'text/csv')

        # Job Workers Template xlsx
        res3 = self.client.get(reverse('download_job_worker_template') + '?format=xlsx')
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        # Job Workers Template csv
        res4 = self.client.get(reverse('download_job_worker_template') + '?format=csv')
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4['Content-Type'], 'text/csv')

    def test_validate_job_workers_correct_data(self):
        """
        Tests that validate_job_workers_data correctly parses valid job worker rows.
        """
        # Create an item first to validate rate mapping
        Item.objects.create(code="ITM-A", name="Item A", rate_per_piece=10.0)
        Item.objects.create(code="ITM-B", name="Item B", rate_per_piece=12.0)

        rows = [
            ["JW-100", "Star Casting", "9876543210", "star@cast.com", "Industrial Area", "27AAAAA1111A1Z1", "casting", "ITM-A:15.5, ITM-B:18.0"],
            ["JW-101", "Group Casting", "9876543210", "", "", "", "casting", "ITM-A:15.0.ITM-B:18.0"]  # tests dot separator replacement!
        ]
        validated = validate_job_workers_data(rows)
        self.assertEqual(len(validated), 2)
        
        # Row 1
        row = validated[0]
        self.assertEqual(row["action"], "INSERT")
        self.assertEqual(len(row["errors"]), 0)
        self.assertEqual(row["data"]["jw_code"], "JW-100")
        self.assertEqual(row["data"]["name"], "Star Casting")
        self.assertEqual(row["data"]["process"], "casting")
        self.assertEqual(row["data"]["rates"]["ITM-A"], 15.5)
        self.assertEqual(row["data"]["rates"]["ITM-B"], 18.0)

        # Row 2
        row2 = validated[1]
        self.assertEqual(row2["action"], "INSERT")
        self.assertEqual(len(row2["errors"]), 0)
        self.assertEqual(row2["data"]["jw_code"], "JW-101")
        self.assertEqual(row2["data"]["name"], "Group Casting")
        self.assertEqual(row2["data"]["rates"]["ITM-A"], 15.0)
        self.assertEqual(row2["data"]["rates"]["ITM-B"], 18.0)

    def test_validate_job_workers_missing_or_invalid_fields(self):
        """
        Tests that validate_job_workers_data detects missing fields, invalid process, or invalid rate formats.
        """
        # Create an item first to validate rate mapping
        Item.objects.create(code="ITM-A", name="Item A", rate_per_piece=10.0)

        rows = [
            ["", "Star Casting", "", "", "", "", "casting", ""],  # missing code (now allowed and auto-generated)
            ["JW-200", "", "", "", "", "", "casting", ""],  # missing name
            ["JW-300", "Star Casting", "", "", "", "", "invalid_proc", ""],  # invalid process
            ["JW-400", "Star Casting", "", "", "", "", "casting", "NONEXIST:10.0"],  # non-existent item
            ["JW-500", "Star Casting", "", "", "", "", "casting", "ITM-A:invalid_rate"]  # invalid rate format
        ]
        validated = validate_job_workers_data(rows)
        
        # Row 0: Valid insertion with auto-generated code
        self.assertEqual(validated[0]["action"], "INSERT")
        self.assertEqual(len(validated[0]["errors"]), 0)
        
        # Rows 1-4: Contain validation errors
        self.assertEqual(validated[1]["action"], "ERROR")
        self.assertIn("Name is required.", validated[1]["errors"])
        self.assertEqual(validated[2]["action"], "ERROR")
        self.assertIn("Process must be one of: casting, machining, polishing, packaging.", validated[2]["errors"])
        self.assertEqual(validated[3]["action"], "ERROR")
        self.assertIn("Item Code 'NONEXIST' not found in Item Master.", validated[3]["errors"])
        self.assertEqual(validated[4]["action"], "ERROR")
        self.assertTrue(any("Invalid rate value" in e for e in validated[4]["errors"]))

    def test_commit_job_workers_success_and_updates(self):
        """
        Tests that commit_job_workers_import correctly saves/updates job workers and their rate allocations.
        """
        item_a = Item.objects.create(code="ITM-A", name="Item A", rate_per_piece=10.0)
        item_b = Item.objects.create(code="ITM-B", name="Item B", rate_per_piece=12.0)

        # Create existing JobWorker
        jw_exist = JobWorker.objects.create(
            jw_code="JW-EXIST",
            name="Old Jobber",
            process="machining"
        )
        # Allocate one rate to existing jobber
        ItemWorkerAllocation.objects.create(item=item_a, job_worker=jw_exist, rate_per_piece=8.0)

        # Create existing JobWorker by Name
        jw_by_name = JobWorker.objects.create(
            jw_code="JW-NAME-MATCH",
            name="Name Matcher",
            process="machining"
        )

        rows = [
            {
                "row_idx": 1,
                "action": "INSERT",
                "errors": [],
                "data": {
                    "jw_code": "JW-NEW",
                    "name": "New Jobber",
                    "phone": "9999999999",
                    "email": "new@jobber.com",
                    "address": "Street 1",
                    "gst_number": "GST1",
                    "process": "casting",
                    "rates": {"ITM-A": 15.0, "ITM-B": 20.0}
                }
            },
            {
                "row_idx": 2,
                "action": "UPDATE",
                "errors": [],
                "data": {
                    "jw_code": "JW-EXIST",
                    "name": "Updated Jobber",
                    "phone": "8888888888",
                    "email": "exist@jobber.com",
                    "address": "Street 2",
                    "gst_number": "GST2",
                    "process": "machining",
                    "rates": {"ITM-B": 25.0}  # item_a rate should be deleted, item_b rate should be set
                }
            },
            {
                "row_idx": 3,
                "action": "INSERT",
                "errors": [],
                "data": {
                    "jw_code": "",  # empty code to test auto-generation!
                    "name": "Auto Jobber",
                    "phone": "7777777777",
                    "email": "auto@jobber.com",
                    "address": "Street 3",
                    "gst_number": "GST3",
                    "process": "machining",
                    "rates": {"ITM-A": 10.0}
                }
            },
            {
                "row_idx": 4,
                "action": "UPDATE",
                "errors": [],
                "data": {
                    "jw_code": "",  # blank code!
                    "name": "Name Matcher",  # matches by name!
                    "phone": "6666666666",
                    "email": "matcher@jobber.com",
                    "address": "Street 4",
                    "gst_number": "GST4",
                    "process": "polishing",
                    "rates": {"ITM-B": 18.0}
                }
            }
        ]

        created, updated = commit_job_workers_import(rows)
        self.assertEqual(created, 2)
        self.assertEqual(updated, 2)

        # Verify new JobWorker and its allocations
        jw_new = JobWorker.objects.get(jw_code="JW-NEW")
        self.assertEqual(jw_new.name, "New Jobber")
        self.assertEqual(jw_new.process, "casting")
        self.assertEqual(jw_new.phone, "9999999999")
        
        allocs_new = ItemWorkerAllocation.objects.filter(job_worker=jw_new)
        self.assertEqual(allocs_new.count(), 2)
        self.assertEqual(allocs_new.get(item=item_a).rate_per_piece, 15.0)
        self.assertEqual(allocs_new.get(item=item_b).rate_per_piece, 20.0)

        # Verify updated JobWorker and its allocations
        jw_upd = JobWorker.objects.get(jw_code="JW-EXIST")
        self.assertEqual(jw_upd.name, "Updated Jobber")
        self.assertEqual(jw_upd.phone, "8888888888")
        
        allocs_upd = ItemWorkerAllocation.objects.filter(job_worker=jw_upd)
        self.assertEqual(allocs_upd.count(), 1)
        self.assertEqual(allocs_upd.get(item=item_b).rate_per_piece, 25.0)
        self.assertFalse(allocs_upd.filter(item=item_a).exists())

        # Verify auto-generated JobWorker and its allocations
        jw_auto = JobWorker.objects.get(name="Auto Jobber")
        self.assertTrue(jw_auto.jw_code.startswith("JW-"))
        self.assertEqual(jw_auto.phone, "7777777777")
        
        allocs_auto = ItemWorkerAllocation.objects.filter(job_worker=jw_auto)
        self.assertEqual(allocs_auto.count(), 1)
        self.assertEqual(allocs_auto.get(item=item_a).rate_per_piece, 10.0)

        # Verify name-matched updated JobWorker and its allocations
        jw_matcher = JobWorker.objects.get(name="Name Matcher")
        self.assertEqual(jw_matcher.jw_code, "JW-NAME-MATCH")  # retains original code!
        self.assertEqual(jw_matcher.phone, "6666666666")
        self.assertEqual(jw_matcher.process, "polishing")
        
        allocs_matcher = ItemWorkerAllocation.objects.filter(job_worker=jw_matcher)
        self.assertEqual(allocs_matcher.count(), 1)
        self.assertEqual(allocs_matcher.get(item=item_b).rate_per_piece, 18.0)

    def test_validate_workers_with_piece_rates(self):
        """
        Tests that validate_workers_data parses piece rate allocation correctly for internal workers.
        """
        item_a = Item.objects.create(code="ITM-A", name="Item A", rate_per_piece=10.0)
        rows = [
            ["Vijay Patel", "EMP001", "9876543210", "Caster", "casting", "500", "8", "DAILY", "", "", "50", "12345", "Emergency", "99999", "A+", "ITM-A:12.50"]
        ]
        validated = validate_workers_data(rows)
        self.assertEqual(len(validated), 1)
        row = validated[0]
        self.assertEqual(row["action"], "INSERT")
        self.assertEqual(len(row["errors"]), 0)
        self.assertEqual(row["data"]["rates"]["ITM-A"], 12.50)

    def test_commit_workers_with_piece_rates(self):
        """
        Tests that commit_workers_import correctly saves worker piece rate allocations.
        """
        item_a = Item.objects.create(code="ITM-A", name="Item A", rate_per_piece=10.0)
        rows = [
            {
                "row_idx": 1,
                "action": "INSERT",
                "errors": [],
                "data": {
                    "name": "Vijay Patel",
                    "employee_id": "EMP-NEW",
                    "phone": "9876543210",
                    "designation": "Caster",
                    "process": "casting",
                    "daily_rate": 500.0,
                    "standard_shift_hours": 8,
                    "salary_model": "DAILY",
                    "monthly_fixed_salary": 0.0,
                    "monthly_allowance": 0.0,
                    "overtime_rate": 50.0,
                    "identity_number": "12345",
                    "emergency_contact_name": "Emergency",
                    "emergency_contact_phone": "99999",
                    "blood_group": "A+",
                    "rates": {"ITM-A": 14.50}
                }
            }
        ]

        created, updated = commit_workers_import(rows)
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)

        worker = Worker.objects.get(employee_id="EMP-NEW")
        allocs = ItemWorkerAllocation.objects.filter(worker=worker)
        self.assertEqual(allocs.count(), 1)
        self.assertEqual(allocs.get(item=item_a).rate_per_piece, 14.50)


class SoftDeleteAndTrashBinTestCase(TestCase):
    """
    Automated verification of soft-deletion filtering and Trash Bin management.
    """

    def setUp(self):
        # Create standard test client
        from django.test import Client as TestClient
        self.client = TestClient()
        
        # User & RBAC Setup
        self.admin_group, _ = Group.objects.get_or_create(name='System Admin')
        self.admin_user = User.objects.create_user(
            username='trash_admin',
            email='trash_admin@test.com',
            password='testpassword'
        )
        self.admin_user.groups.add(self.admin_group)

        # Create Items & Workers
        self.item = Item.objects.create(code="ITM-TEST", name="Test Item", rate_per_piece=10.0)
        self.worker_active = Worker.objects.create(name="Active Worker", process="casting")
        self.worker_deleted = Worker.objects.create(name="Deleted Worker", process="casting")
        
        # Allocate Rates
        self.alloc_active = ItemWorkerAllocation.objects.create(
            item=self.item, worker=self.worker_active, rate_per_piece=5.0
        )
        self.alloc_deleted = ItemWorkerAllocation.objects.create(
            item=self.item, worker=self.worker_deleted, rate_per_piece=8.0
        )

        # Soft Delete one worker
        self.worker_deleted.delete()

    def test_soft_deleted_worker_and_allocations_hidden(self):
        """
        Soft-deleted workers and their piece rate allocations must be hidden from normal UI listings.
        """
        # Active workers should show up in normal manager
        active_workers = list(Worker.objects.all())
        self.assertIn(self.worker_active, active_workers)
        self.assertNotIn(self.worker_deleted, active_workers)

        # Item's active allocations should exclude the soft-deleted worker
        active_allocations = self.item.active_allocations
        self.assertEqual(len(active_allocations), 1)
        self.assertEqual(active_allocations[0], self.alloc_active)

    def test_trash_bin_view_context(self):
        """
        The master_data view context must contain all soft-deleted records for rendering.
        """
        self.client.login(username='trash_admin', password='testpassword')
        response = self.client.get(reverse('master_data') + '?tab=trash')
        self.assertEqual(response.status_code, 200)
        
        deleted_workers = list(response.context['deleted_workers'])
        self.assertIn(self.worker_deleted, deleted_workers)
        self.assertNotIn(self.worker_active, deleted_workers)

    def test_recover_deleted_record(self):
        """
        Restoring a soft-deleted worker must successfully reactivate them and restore allocations.
        """
        self.client.login(username='trash_admin', password='testpassword')
        
        # Verify initial soft-deleted state
        self.assertTrue(self.worker_deleted.is_deleted)
        
        # Trigger recovery endpoint
        url = reverse('recover_deleted_record', kwargs={'model_type': 'worker', 'record_id': self.worker_deleted.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect back to trash
        
        # Refresh from database
        self.worker_deleted.refresh_from_db()
        self.assertFalse(self.worker_deleted.is_deleted)
        self.assertTrue(self.worker_deleted.active)

        # Allocation should now be active again
        active_allocations = self.item.active_allocations
        self.assertEqual(len(active_allocations), 2)
        self.assertIn(self.alloc_deleted, active_allocations)

    def test_permanent_delete_record(self):
        """
        Physically purges the record from the database.
        """
        self.client.login(username='trash_admin', password='testpassword')
        
        # Enable DEBUG to expose 400 Bad Request underlying exceptions
        from django.conf import settings
        original_debug = settings.DEBUG
        settings.DEBUG = True
        
        try:
            # Trigger permanent delete
            url = reverse('permanent_delete_record', kwargs={'model_type': 'worker', 'record_id': self.worker_deleted.id})
            response = self.client.get(url)
        finally:
            settings.DEBUG = original_debug
            
        if response.status_code != 302:
            print("\n--- DEBUG INFO ---")
            print("STATUS CODE:", response.status_code)
            print("CONTENT:", response.content.decode('utf-8'))
            print("------------------\n")
        self.assertEqual(response.status_code, 302)

        # Worker should be physically purged
        with self.assertRaises(Worker.DoesNotExist):
            Worker.all_objects.get(id=self.worker_deleted.id)




