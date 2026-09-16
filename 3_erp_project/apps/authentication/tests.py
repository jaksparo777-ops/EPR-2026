from django.test import TestCase
from django.urls import reverse
from apps.master_data.models import LegalEntity
from apps.authentication.models import CustomUser, AuthorizedDevice

class AdminCompanySelectionLoginTests(TestCase):
    def setUp(self):
        # Create companies
        self.nc = LegalEntity.objects.create(name="NC Casting", address="Foundry Area 1")
        self.om = LegalEntity.objects.create(name="OM Finishing", address="Finishing Area 2")

        # Create approved device to bypass device security middleware
        self.device = AuthorizedDevice.objects.create(
            device_id="DEV-ADMIN-TEST",
            name="Admin Browser",
            status="APPROVED",
            is_approved=True
        )

        # Create superuser admin (company is None by default)
        self.admin = CustomUser.objects.create_superuser(
            username="admin_user",
            email="admin_user@example.com",
            password="password123",
            role="ADMIN"
        )

        # Create single-company employee
        self.single_user = CustomUser.objects.create_user(
            username="nc_worker",
            email="nc_worker@example.com",
            password="password123",
            role="CUSTOM",
            company=self.nc
        )
        self.single_user.allowed_companies.add(self.nc)

    def test_admin_login_redirects_to_select_company(self):
        """
        When an admin logs in via the login form without a custom 'next' parameter,
        the login form redirects to /select-company/ (Photo 2).
        """
        self.client.cookies['device_token'] = 'DEV-ADMIN-TEST'
        response = self.client.post(reverse('login'), {
            'username': 'admin_user',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('select_company'))

    def test_admin_accessing_dashboard_without_selection_redirects_to_select_company(self):
        """
        If an admin hits the root dashboard URL without having selected an active company,
        the middleware redirects them to /select-company/ rather than defaulting to NC.
        """
        self.client.cookies['device_token'] = 'DEV-ADMIN-TEST'
        self.client.login(username='admin_user', password='password123')
        
        # Access root dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('select_company'))

    def test_admin_can_select_workspace_and_access_dashboard(self):
        """
        Once the admin selects a company workspace (e.g. OM), they can access the dashboard.
        """
        self.client.cookies['device_token'] = 'DEV-ADMIN-TEST'
        self.client.login(username='admin_user', password='password123')

        # Select OM (company 2)
        response = self.client.post(reverse('select_company'), {'company_id': str(self.om.id)})
        self.assertRedirects(response, reverse('dashboard'))

        # Dashboard now loads with active company set to OM
        dash_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_response.status_code, 200)

    def test_single_company_user_auto_scoped(self):
        """
        A single-company worker who logs in is automatically scoped to their company.
        """
        self.client.cookies['device_token'] = 'DEV-ADMIN-TEST'
        self.client.login(username='nc_worker', password='password123')

        dash_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_response.status_code, 200)


class UserInactivityTimeoutTests(TestCase):
    def setUp(self):
        self.company = LegalEntity.objects.create(name="Test Foundry", address="Industrial Area")
        self.device = AuthorizedDevice.objects.create(
            device_id="DEV-TIMEOUT-TEST",
            name="Test Browser",
            status="APPROVED",
            is_approved=True
        )
        self.client.cookies['device_token'] = 'DEV-TIMEOUT-TEST'

        self.admin = CustomUser.objects.create_superuser(
            username="admin_timeout",
            email="admin_timeout@example.com",
            password="password123",
            role="ADMIN"
        )
        self.client.login(username='admin_timeout', password='password123')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

    def test_default_timeout_values_on_model(self):
        """Newly created users should default to 60 minutes and POPUP_WARNING mode."""
        user = CustomUser.objects.create_user(
            username="default_user",
            email="default@example.com",
            password="password123"
        )
        self.assertEqual(user.session_timeout_minutes, 60)
        self.assertEqual(user.timeout_logout_mode, 'POPUP_WARNING')

    def test_user_create_api_with_custom_timeout_and_mode(self):
        """Creating a user via user_create_api should store custom timeout and logout mode."""
        import json
        payload = {
            'username': 'operator_45',
            'email': 'operator45@example.com',
            'password': 'password123',
            'role': 'CUSTOM',
            'session_timeout_minutes': 45,
            'timeout_logout_mode': 'INSTANT_LOGOUT',
            'allowed_company_ids': [self.company.id]
        }
        response = self.client.post(
            reverse('user_create_api'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        created_user = CustomUser.objects.get(username='operator_45')
        self.assertEqual(created_user.session_timeout_minutes, 45)
        self.assertEqual(created_user.timeout_logout_mode, 'INSTANT_LOGOUT')

    def test_user_create_api_timeout_clamping(self):
        """Timeouts below 5 minutes or above 480 minutes should be clamped."""
        import json
        # Below minimum -> clamped to 5
        payload_min = {
            'username': 'operator_low',
            'email': 'low@example.com',
            'password': 'password123',
            'role': 'CUSTOM',
            'session_timeout_minutes': 2,
            'timeout_logout_mode': 'POPUP_WARNING',
            'allowed_company_ids': [self.company.id]
        }
        res_min = self.client.post(
            reverse('user_create_api'),
            data=json.dumps(payload_min),
            content_type='application/json'
        )
        self.assertEqual(res_min.status_code, 200)
        user_low = CustomUser.objects.get(username='operator_low')
        self.assertEqual(user_low.session_timeout_minutes, 5)

        # Above maximum -> clamped to 480
        payload_max = {
            'username': 'operator_high',
            'email': 'high@example.com',
            'password': 'password123',
            'role': 'CUSTOM',
            'session_timeout_minutes': 999,
            'timeout_logout_mode': 'POPUP_WARNING',
            'allowed_company_ids': [self.company.id]
        }
        res_max = self.client.post(
            reverse('user_create_api'),
            data=json.dumps(payload_max),
            content_type='application/json'
        )
        self.assertEqual(res_max.status_code, 200)
        user_high = CustomUser.objects.get(username='operator_high')
        self.assertEqual(user_high.session_timeout_minutes, 480)

    def test_user_edit_api_updates_timeout_and_mode(self):
        """Updating a user via user_edit_api updates session_timeout_minutes and timeout_logout_mode."""
        import json
        user = CustomUser.objects.create_user(
            username="edit_user",
            email="edit@example.com",
            password="password123",
            session_timeout_minutes=60,
            timeout_logout_mode='POPUP_WARNING'
        )
        update_payload = {
            'session_timeout_minutes': 120,
            'timeout_logout_mode': 'INSTANT_LOGOUT'
        }
        response = self.client.post(
            reverse('user_edit_api', args=[user.id]),
            data=json.dumps(update_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.session_timeout_minutes, 120)
        self.assertEqual(user.timeout_logout_mode, 'INSTANT_LOGOUT')


class SessionKeepAliveAndMiddlewareTests(TestCase):
    def setUp(self):
        import time
        self.company = LegalEntity.objects.create(name="Foundry Unit", address="Plot 99")
        self.device = AuthorizedDevice.objects.create(
            device_id="DEV-KEEP-ALIVE-TEST",
            name="Keep Alive Browser",
            status="APPROVED",
            is_approved=True
        )
        self.client.cookies['device_token'] = 'DEV-KEEP-ALIVE-TEST'

        self.user = CustomUser.objects.create_user(
            username="worker_active",
            email="worker@example.com",
            password="password123",
            role="CUSTOM",
            company=self.company,
            session_timeout_minutes=10,  # 10 minutes timeout
            timeout_logout_mode='POPUP_WARNING'
        )
        self.user.allowed_companies.add(self.company)

    def test_keep_alive_api_refreshes_session_timestamp(self):
        """Authenticated call to session_keep_alive_api updates last_user_activity."""
        import json
        import time
        self.client.login(username='worker_active', password='password123')
        
        session = self.client.session
        old_time = time.time() - 300
        session['last_user_activity'] = old_time
        session.save()

        response = self.client.post(reverse('session_keep_alive_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertGreater(data.get('last_user_activity'), old_time)

    def test_inactivity_middleware_allows_active_user(self):
        """A user within their timeout window continues browsing normally."""
        import time
        self.client.login(username='worker_active', password='password123')
        
        # Set last activity to 1 minute ago (timeout is 10 mins)
        session = self.client.session
        session['last_user_activity'] = time.time() - 60
        session.save()

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_inactivity_middleware_logs_out_idle_user(self):
        """When user inactivity exceeds session_timeout_minutes, session is terminated."""
        import time
        self.client.login(username='worker_active', password='password123')

        # Set last activity to 11 minutes ago (exceeds 10-minute timeout)
        session = self.client.session
        session['last_user_activity'] = time.time() - 660
        session.save()

        response = self.client.get(reverse('dashboard'))
        # Should redirect to login with reason=timeout
        self.assertRedirects(response, '/login/?reason=timeout', fetch_redirect_response=False)

        # Confirm session is flushed / user logged out
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_page_renders_timeout_alert_when_reason_is_timeout(self):
        """The login page should display a clear timeout alert banner when reason=timeout."""
        response = self.client.get(reverse('login') + '?reason=timeout')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your session expired due to inactivity')


class AdminMasterRecoveryKeyTests(TestCase):
    def setUp(self):
        self.company = LegalEntity.objects.create(name="Foundry Unit", address="Plot 99")
        self.device = AuthorizedDevice.objects.create(
            device_id="DEV-RECOVERY-TEST",
            name="Recovery Test Device",
            status="APPROVED",
            is_approved=True
        )
        self.client.cookies['device_token'] = 'DEV-RECOVERY-TEST'

        self.superadmin = CustomUser.objects.create_superuser(
            username="super_root",
            email="root@foundry.com",
            password="InitialRootPassword123!",
            role="ADMIN"
        )

        self.worker = CustomUser.objects.create_user(
            username="regular_worker",
            email="worker@foundry.com",
            password="WorkerPassword123!",
            role="CUSTOM",
            company=self.company
        )

        from apps.authentication.models import AdminRecoveryConfig
        self.config = AdminRecoveryConfig.get_config()
        self.config.set_key("SECURE-TEST-KEY-2026", hint="Test Safe")

    def test_admin_recovery_key_verification(self):
        """Model check_key correctly validates matching and non-matching keys."""
        self.assertTrue(self.config.check_key("SECURE-TEST-KEY-2026"))
        self.assertFalse(self.config.check_key("WRONG-KEY"))

    def test_emergency_reset_success_for_admin(self):
        """Admin can reset password using valid Master Recovery Key."""
        import json
        payload = {
            'username': 'super_root',
            'recovery_key': 'SECURE-TEST-KEY-2026',
            'new_password': 'BrandNewPassword2026!'
        }
        response = self.client.post(
            reverse('admin_emergency_reset_api'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')

        # Verify password changed
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.check_password('BrandNewPassword2026!'))

    def test_emergency_reset_rejected_for_non_admin(self):
        """Non-admin worker cannot be reset via emergency admin recovery."""
        import json
        payload = {
            'username': 'regular_worker',
            'recovery_key': 'SECURE-TEST-KEY-2026',
            'new_password': 'NewPassword123!'
        }
        response = self.client.post(
            reverse('admin_emergency_reset_api'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('Super Admins', data.get('error'))

    def test_emergency_reset_rate_limiting(self):
        """3 failed attempts lock emergency recovery for 30 minutes."""
        import json
        payload = {
            'username': 'super_root',
            'recovery_key': 'WRONG-KEY-ATTEMPT',
            'new_password': 'NewPassword123!'
        }
        for i in range(3):
            res = self.client.post(
                reverse('admin_emergency_reset_api'),
                data=json.dumps(payload),
                content_type='application/json'
            )
            self.assertEqual(res.status_code, 400)

        # 4th attempt should be rate limited with 429
        res4 = self.client.post(
            reverse('admin_emergency_reset_api'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res4.status_code, 429)
        self.assertIn('Rate limit exceeded', res4.json().get('error'))

    def test_update_recovery_key_api(self):
        """Authenticated super admin can update the master recovery key."""
        import json
        self.client.login(username='super_root', password='InitialRootPassword123!')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

        payload = {
            'current_password': 'InitialRootPassword123!',
            'new_master_key': 'ROTATED-KEY-XYZ-999',
            'key_hint': 'Vault safe 2'
        }
        response = self.client.post(
            reverse('admin_update_recovery_key_api'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')

        self.config.refresh_from_db()
        self.assertTrue(self.config.check_key('ROTATED-KEY-XYZ-999'))
        self.assertEqual(self.config.key_hint, 'Vault safe 2')


