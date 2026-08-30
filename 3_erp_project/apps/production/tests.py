from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from datetime import date
from apps.master_data.models import LegalEntity
from apps.authentication.models import Worker, SalaryModel
from apps.production.models import Holiday, Attendance, AttendanceStatus

class HolidayPayrollTests(TestCase):
    def setUp(self):
        # Create user and log in
        User = get_user_model()
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='password')
        self.client.login(username='admin', password='password')
        
        # Create Company (LegalEntity)
        self.company = LegalEntity.objects.create(
            name="Test Casting Unit",
            address="123 Industrial Area"
        )
        
        # Associate user with company to bypass CompanyScopeMiddleware redirect
        self.user.company = self.company
        self.user.save()
        
        # Create Worker with DAILY salary model
        self.worker = Worker.objects.create(
            name="Ramesh Kumar",
            company=self.company,
            salary_model=SalaryModel.DAILY,
            daily_rate=600.0,
            overtime_rate=100.0
        )

    def test_paid_holiday_no_work(self):
        """
        If a daily-wage worker does NOT work on a paid holiday (unmarked or status HOLIDAY),
        they receive 1.0x daily_rate pay for the day off.
        """
        # Create a paid holiday in 2026-07 (e.g., 2026-07-15)
        holiday = Holiday.objects.create(
            date=date(2026, 7, 15),
            name="National Holiday",
            company=self.company,
            is_paid=True
        )
        
        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # Get labor ledger for July 2026
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # The worker should be paid for 2 present days + 1 paid holiday = 3 days total
        # Expected wages = 3 * 600.0 = 1800.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1800.0)

    def test_paid_holiday_worked_present(self):
        """
        If they DO work on a paid holiday (marked as PRESENT), they receive standard worked rate
        (1.0x daily_rate) and no additional holiday bonus (Option B).
        """
        # Create a paid holiday
        holiday = Holiday.objects.create(
            date=date(2026, 7, 15),
            name="National Holiday",
            company=self.company,
            is_paid=True
        )
        
        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # Worker works on the holiday day
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 15), status='PRESENT')
        
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Total days present = 3. Holiday pay days = 0 (since they worked).
        # Expected wages = 3 * 600.0 = 1800.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1800.0)

    def test_paid_holiday_worked_half_day(self):
        """
        If they work a HALF_DAY on a paid holiday, they receive standard pay (Option B) which is
        0.5x worked rate. However, the system ensures they do not earn less than they would have by
        staying home (minimum guarantee of 1.0x daily_rate on a paid holiday).
        Therefore, they should get 0.5x worked + 0.5x holiday pay = 1.0x daily_rate.
        """
        # Create a paid holiday
        holiday = Holiday.objects.create(
            date=date(2026, 7, 15),
            name="National Holiday",
            company=self.company,
            is_paid=True
        )
        
        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # Worker works HALF_DAY on the holiday day
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 15), status='HALF_DAY')
        
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Total days present = 2. Total half days = 1. Holiday pay days = 0.5.
        # Expected wages = (2 * 600) + (1 * 0.5 * 600) + (0.5 * 600) = 1200 + 300 + 300 = 1800.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1800.0)

    def test_unpaid_holiday(self):
        """
        Unpaid holidays do not yield any pay if the worker stays home.
        """
        # Create an unpaid holiday
        holiday = Holiday.objects.create(
            date=date(2026, 7, 15),
            name="Unpaid Holiday",
            company=self.company,
            is_paid=False
        )
        
        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Expected wages = 2 * 600.0 = 1200.0 (Unpaid holiday yields 0)
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1200.0)

    def test_paid_holiday_marked_absent(self):
        """
        If marked ABSENT on a paid holiday, they receive ₹0.
        """
        # Create a paid holiday
        holiday = Holiday.objects.create(
            date=date(2026, 7, 15),
            name="National Holiday",
            company=self.company,
            is_paid=True
        )
        
        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # Worker is marked ABSENT on the holiday day
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 15), status='ABSENT')
        
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Expected wages = 2 * 600.0 = 1200.0 (Absent on holiday yields 0)
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1200.0)

    def test_unpaid_weekly_off(self):
        """
        By default, weekly off is Sunday (6) and unpaid.
        Worker stays home on Sunday (2026-07-12). They should get ₹0 for Sunday.
        """
        self.company.weekly_off = 6 # Sunday
        self.company.is_weekly_off_paid = False
        self.company.save()

        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # 2026-07-12 is Sunday. No attendance record.
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Expected wages = 2 * 600.0 = 1200.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 1200.0)

    def test_paid_weekly_off(self):
        """
        Weekly off is Sunday (6) and paid.
        Worker stays home on Sunday (2026-07-12). They should get 1.0x daily rate.
        """
        self.company.weekly_off = 6 # Sunday
        self.company.is_weekly_off_paid = True
        self.company.save()

        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # 2026-07-12 is Sunday. No attendance record.
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Expected wages = 2 present + 4 paid Sundays = 6 * 600.0 = 3600.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 3600.0)

    def test_weekly_off_override_working_day(self):
        """
        Weekly off is Sunday (6) and paid, but Sunday (2026-07-12) is overridden as a regular working day.
        Worker stays home on Sunday. They should get ₹0 for Sunday (since it's now a working day).
        """
        self.company.weekly_off = 6 # Sunday
        self.company.is_weekly_off_paid = True
        self.company.save()

        # Create working day override holiday record on Sunday
        Holiday.objects.create(
            date=date(2026, 7, 12),
            name="Working Sunday Shift",
            company=self.company,
            is_paid=False,
            is_working_day_override=True
        )

        # Worker has 2 ordinary PRESENT days
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 10), status='PRESENT')
        Attendance.objects.create(worker=self.worker, date=date(2026, 7, 11), status='PRESENT')
        
        # Sunday (2026-07-12) has no attendance record (stayed home on a working day)
        response = self.client.get(reverse('labor_ledger') + '?month=2026-07')
        self.assertEqual(response.status_code, 200)
        
        # Expected wages = 2 present + 3 paid Sundays = 5 * 600.0 = 3000.0
        earnings = response.context['staff_ledger'][0]['earnings']
        self.assertEqual(earnings, 3000.0)


class BulkImportExportScopingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='password')
        self.client.login(username='admin', password='password')
        
        self.company1 = LegalEntity.objects.create(name="Company A", address="123 Road")
        self.company2 = LegalEntity.objects.create(name="Company B", address="456 Lane")
        
        self.user.company = self.company1
        self.user.save()

        # Import Item model dynamically to avoid circular import issues
        from apps.master_data.models import Item
        self.item1 = Item.objects.create(code="ITEM-A", name="Item of A", company=self.company1)
        self.item2 = Item.objects.create(code="ITEM-B", name="Item of B", company=self.company2)

    def test_export_filters_by_active_company(self):
        """
        When switched to Company A, exporting items must only return items belonging to Company A.
        """
        response = self.client.get(reverse('export_current_data', args=['items']))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("ITEM-A", content)
        self.assertNotIn("ITEM-B", content)

    def test_import_validates_company_scope(self):
        """
        When switched to Company A, importing items belonging to Company B should trigger a validation error.
        """
        csv_content = (
            "Item Code*,Item Name*,Category (BRASS/MORTAR/PESTLE/CHOPPING_BOARD/OTHER)*,Company Scope (NC/OM/GLOBAL)*\n"
            "ITEM-B,Item of B,PESTLE,Company B\n"
        )
        response = self.client.post(
            reverse('master_bulk_import') + '?tab=items',
            {'preview': '1', 'csv_data_cache': csv_content}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cannot import record for company &#x27;Company B&#x27; while active company is &#x27;Company A&#x27;")


class SQLExplorerSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = LegalEntity.objects.create(name="Security Test Company", address="100 Factory Way")
        self.superuser = User.objects.create_superuser(username='admin_sec', email='admin_sec@test.com', password='password')
        self.superuser.company = self.company
        self.superuser.save()

        self.regular_user = User.objects.create_user(username='staff_sec', email='staff_sec@test.com', password='password', is_staff=True, role='CASTING_MGR')
        self.regular_user.company = self.company
        self.regular_user.save()
        
        from apps.authentication.models import AuthorizedDevice
        AuthorizedDevice.objects.create(
            device_id='DEV-TESTING',
            name='Test Device',
            is_approved=True,
            status='APPROVED'
        )

    def test_non_admin_write_blocked(self):
        """
        Regular staff user attempting to execute a DML write query in SQL Explorer must be blocked with 403.
        """
        self.client.login(username='staff_sec', password='password')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()
        self.client.cookies['device_token'] = 'DEV-TESTING'

        response = self.client.post(
            reverse('sql_explorer_run_api'),
            data={'query': 'UPDATE master_data_item SET name="Test" WHERE id=999999;', 'allow_write': True},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("strictly restricted to System Administrators", response.json()['error'])

    def test_admin_write_allowed(self):
        """
        Superuser / System Admin attempting to execute a DML write query in SQL Explorer is permitted.
        """
        self.client.login(username='admin_sec', password='password')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()
        self.client.cookies['device_token'] = 'DEV-TESTING'

        response = self.client.post(
            reverse('sql_explorer_run_api'),
            data={'query': "UPDATE master_data_item SET name='Test' WHERE id=999999;", 'allow_write': True},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_mutation'])


class DeviceSecuritySystemTests(TestCase):
    def setUp(self):
        from apps.authentication.models import CustomUser, AuthorizedDevice
        from apps.master_data.models import LegalEntity

        self.company = LegalEntity.objects.create(name="Test Security Unit")
        self.admin_user = CustomUser.objects.create_superuser(username='sec_admin', email='sec_admin@test.com', password='password', role='ADMIN')
        self.admin_user.company = self.company
        self.admin_user.save()

        self.staff_user = CustomUser.objects.create_user(username='sec_staff', email='sec_staff@test.com', password='password', is_staff=True, role='CASTING_MGR')
        self.staff_user.company = self.company
        self.staff_user.save()

        self.device = AuthorizedDevice.objects.create(
            device_id='DEV-UNITTEST-001',
            name='Test iPhone',
            status='PENDING',
            is_approved=False
        )

    def test_user_agent_parsing(self):
        from apps.authentication.utils import parse_user_agent_details
        ua_iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        meta = parse_user_agent_details(ua_iphone)
        self.assertEqual(meta['device_type'], 'MOBILE')
        self.assertEqual(meta['brand_model'], 'Apple iPhone')
        self.assertEqual(meta['os_info'], 'iOS 17.5')
        self.assertEqual(meta['browser_info'], 'Safari')

        ua_samsung = "Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        meta_s = parse_user_agent_details(ua_samsung)
        self.assertEqual(meta_s['device_type'], 'TABLET')
        self.assertEqual(meta_s['brand_model'], 'Samsung Galaxy')
        self.assertEqual(meta_s['os_info'], 'Android 14')

    def test_device_approve_and_reject_flow(self):
        self.client.login(username='sec_admin', password='password')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

        # Approve API test
        resp = self.client.post(reverse('device_approve_api', kwargs={'device_pk': self.device.id}))
        self.assertEqual(resp.status_code, 200)
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_approved)
        self.assertEqual(self.device.status, 'APPROVED')

        # Reject API test
        resp_rej = self.client.post(
            reverse('device_reject_api', kwargs={'device_pk': self.device.id}),
            data={'reason': 'Unauthorized Device'},
            content_type='application/json'
        )
        self.assertEqual(resp_rej.status_code, 200)
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_approved)
        self.assertEqual(self.device.status, 'REJECTED')
        self.assertEqual(self.device.rejection_reason, 'Unauthorized Device')


class AuditSystemTests(TestCase):
    def setUp(self):
        from apps.authentication.models import CustomUser, AuthorizedDevice, SystemAuditLog
        from apps.master_data.models import LegalEntity

        self.company = LegalEntity.objects.create(name="Audit Test Unit")
        self.admin_user = CustomUser.objects.create_superuser(username='audit_admin', email='audit_admin@test.com', password='password', role='ADMIN')
        self.admin_user.company = self.company
        self.admin_user.save()

        self.device = AuthorizedDevice.objects.create(
            device_id='DEV-AUDIT-001',
            name='Audit Test Laptop',
            status='APPROVED',
            is_approved=True
        )

    def test_log_system_audit_event(self):
        from apps.authentication.utils import log_system_audit_event, classify_network_scope
        
        self.assertEqual(classify_network_scope('192.168.1.50'), 'FACTORY_LOCAL')
        self.assertEqual(classify_network_scope('203.0.113.195'), 'EXTERNAL_REMOTE')

        log = log_system_audit_event(
            user=self.admin_user,
            device=self.device,
            ip_address='192.168.1.50',
            event_type='CREATE',
            module_name='Test Department',
            object_repr='Test Item #1',
            changes_json={'qty': 100}
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, 'CREATE')
        self.assertEqual(log.network_scope, 'FACTORY_LOCAL')

    def test_audit_logs_api(self):
        from apps.authentication.models import SystemAuditLog
        SystemAuditLog.objects.create(
            user=self.admin_user,
            event_type='UPDATE',
            module_name='Sales Orders',
            object_repr='Order #99'
        )
        self.client.login(username='audit_admin', password='password')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

        resp = self.client.get(reverse('audit_logs_api'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertGreaterEqual(len(data['logs']), 1)


class MultiCompanyAccessTests(TestCase):
    def setUp(self):
        from apps.authentication.models import CustomUser, AuthorizedDevice
        from apps.master_data.models import LegalEntity

        self.nc = LegalEntity.objects.create(name="NC Casting Unit")
        self.om = LegalEntity.objects.create(name="Om Industries Unit")

        self.multi_user = CustomUser.objects.create_user(
            username='multi_mgr',
            password='password',
            role='CUSTOM',
            is_global_access=False
        )
        self.multi_user.allowed_companies.set([self.nc, self.om])

        self.device = AuthorizedDevice.objects.create(
            device_id='DEV-MULTI-001',
            name='Multi Device',
            status='APPROVED',
            is_approved=True
        )

    def test_multi_company_allowed_views(self):
        """
        User assigned to NC and OM can access NC and OM, but gets blocked from global access.
        """
        self.assertTrue(self.multi_user.can_access_company(self.nc.id))
        self.assertTrue(self.multi_user.can_access_company(self.om.id))
        self.assertFalse(self.multi_user.can_access_company('global'))

    def test_select_company_redirection_for_non_global_user(self):
        self.client.login(username='multi_mgr', password='password')
        self.client.cookies['device_token'] = 'DEV-MULTI-001'

        resp = self.client.post(reverse('select_company'), {'company_id': 'global'})
        session_company = self.client.session.get('active_company_id')
        self.assertNotEqual(session_company, 'global')



