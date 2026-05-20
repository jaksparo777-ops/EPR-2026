from django.test import TestCase, Client
from django.urls import reverse
from inventory.models import Worker, JobWorker, Item, StockTransaction

class MachiningEntryTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create test items
        self.item1 = Item.objects.create(
            code="ITEM1",
            name="Test Item 1",
            casting_weight=0.150,
            machining_weight=0.120
        )
        self.item2 = Item.objects.create(
            code="ITEM2",
            name="Test Item 2",
            casting_weight=0.300,
            machining_weight=0.250
        )
        
        # Create test workers
        self.worker1 = Worker.objects.create(
            name="John Doe",
            employee_id="EMP-0001",
            active=True
        )
        self.job_worker1 = JobWorker.objects.create(
            name="External Forge Ltd",
            jw_code="JW-0001",
            active=True
        )

    def test_multi_row_creation_success(self):
        """Test creating multiple machining transactions in one form post."""
        url = reverse("machining_entry")
        
        # Post payload with lists for items, quantities, and weights
        payload = {
            "direction": "machining_out",
            "worker": f"w_{self.worker1.id}",
            "date": "2026-05-17",
            "item[]": [str(self.item1.id), str(self.item2.id)],
            "quantity[]": ["10", "20"],
            "rejection_quantity[]": ["0", "0"],
            "weight[]": ["1.5", "6.0"],
        }
        
        response = self.client.post(url, payload)
        
        # Should redirect back to machining_entry after success
        self.assertRedirects(response, url)
        
        # Verify 2 transactions were created in the database
        txs = StockTransaction.objects.filter(transaction_type="machining_out")
        self.assertEqual(txs.count(), 2)
        
        tx1 = txs.get(item=self.item1)
        self.assertEqual(tx1.quantity, 10)
        self.assertEqual(tx1.weight, 1.5)
        self.assertEqual(tx1.worker, self.worker1)
        self.assertEqual(tx1.job_worker, None)
        self.assertEqual(tx1.rejection_quantity, 0)
        self.assertEqual(tx1.created_at.strftime("%Y-%m-%d"), "2026-05-17")
        
        tx2 = txs.get(item=self.item2)
        self.assertEqual(tx2.quantity, 20)
        self.assertEqual(tx2.weight, 6.0)
        self.assertEqual(tx2.worker, self.worker1)
        self.assertEqual(tx2.job_worker, None)
        self.assertEqual(tx2.rejection_quantity, 0)
        self.assertEqual(tx2.created_at.strftime("%Y-%m-%d"), "2026-05-17")

    def test_single_row_edit_success(self):
        """Test editing a single existing machining transaction using edit_id with single parameters."""
        # Pre-create a transaction to edit
        tx = StockTransaction.objects.create(
            transaction_type="machining_out",
            item=self.item1,
            worker=self.worker1,
            quantity=5,
            rejection_quantity=0,
            weight=0.75
        )
        
        url = reverse("machining_entry")
        
        # Payload containing single values + edit_id
        payload = {
            "edit_id": str(tx.id),
            "direction": "machining_in",
            "worker": f"jw_{self.job_worker1.id}",
            "date": "2026-05-18",
            "item": str(self.item2.id),
            "quantity": "12",
            "rejection_quantity": "3",
            "weight": "3.0",
        }
        
        response = self.client.post(url, payload)
        
        self.assertRedirects(response, url)
        
        # Retrieve and verify updated transaction
        tx.refresh_from_db()
        self.assertEqual(tx.transaction_type, "machining_in")
        self.assertEqual(tx.item, self.item2)
        self.assertEqual(tx.worker, None)
        self.assertEqual(tx.job_worker, self.job_worker1)
        self.assertEqual(tx.quantity, 12)
        self.assertEqual(tx.rejection_quantity, 3)
        self.assertEqual(tx.weight, 3.0)
        self.assertEqual(tx.created_at.strftime("%Y-%m-%d"), "2026-05-18")

    def test_array_row_edit_success(self):
        """Test editing a single existing machining transaction using edit_id with array inputs."""
        # Pre-create a transaction to edit
        tx = StockTransaction.objects.create(
            transaction_type="machining_out",
            item=self.item1,
            worker=self.worker1,
            quantity=8,
            rejection_quantity=0,
            weight=1.20
        )
        
        url = reverse("machining_entry")
        
        # Payload containing array lists + edit_id (how the dynamic form posts it)
        payload = {
            "edit_id": str(tx.id),
            "direction": "machining_in",
            "worker": f"jw_{self.job_worker1.id}",
            "date": "2026-05-18",
            "item[]": [str(self.item2.id)],
            "quantity[]": ["15"],
            "rejection_quantity[]": ["2"],
            "weight[]": ["3.75"],
        }
        
        response = self.client.post(url, payload)
        
        self.assertRedirects(response, url)
        
        # Retrieve and verify updated transaction
        tx.refresh_from_db()
        self.assertEqual(tx.transaction_type, "machining_in")
        self.assertEqual(tx.item, self.item2)
        self.assertEqual(tx.worker, None)
        self.assertEqual(tx.job_worker, self.job_worker1)
        self.assertEqual(tx.quantity, 15)
        self.assertEqual(tx.rejection_quantity, 2)
        self.assertEqual(tx.weight, 3.75)
        self.assertEqual(tx.created_at.strftime("%Y-%m-%d"), "2026-05-18")

    def test_job_worker_code_collision_avoidance(self):
        """Test that the JobWorker auto-generated code successfully increments to avoid unique constraint collisions."""
        # Pre-create a job worker with an out-of-order code (JW-1003)
        jw1 = JobWorker.objects.create(
            name="Ramesh Forge",
            jw_code="JW-1003",
            process="machining"
        )
        
        # Creating a second worker without code.
        # Under the old code, this would try to generate 'JW-1003' because last_jw has id=2 (1000 + 2 + 1 = 1003)
        # and would fail unique constraint integrity.
        # Under the new loop code, it will skip 'JW-1003' and successfully generate 'JW-1004'.
        jw2 = JobWorker.objects.create(
            name="Mehul Forge",
            process="machining"
        )
        
        self.assertEqual(jw2.jw_code, "JW-1004")


class BOMCreationTests(TestCase):
    def setUp(self):
        # Create test items (components)
        self.comp1 = Item.objects.create(
            code="COMP1",
            name="Component 1",
            category="KHAL",
            material="BRASS",
            casting_weight=0.5,
            machining_weight=0.4,
            lot_size=10,
            lot_with_box=12,
            casting_required=True,
            machining_required=True
        )
        self.comp2 = Item.objects.create(
            code="COMP2",
            name="Component 2",
            category="DASTA",
            material="COPPER",
            casting_weight=0.3,
            machining_weight=0.2,
            lot_size=20,
            lot_with_box=24,
            polishing_required=True,
            packing_required=True
        )

        # Create workers and allocations for components
        self.worker = Worker.objects.create(name="Internal Worker")
        self.job_worker = JobWorker.objects.create(name="External Worker")

        from inventory.models import ItemWorkerAllocation
        ItemWorkerAllocation.objects.create(
            item=self.comp1,
            worker=self.worker,
            rate_per_piece=5.00
        )
        ItemWorkerAllocation.objects.create(
            item=self.comp2,
            job_worker=self.job_worker,
            rate_per_piece=3.00
        )

        # Create staff user for request authorization
        from django.contrib.auth.models import User
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password"
        )

    def test_bom_creation_maps_and_merges_successfully(self):
        """Test that saving a BOM via Master Data post action maps and merges component details correctly."""
        from django.test import Client
        from django.urls import reverse
        from inventory.models import Item, ItemWorkerAllocation, ItemComposition

        client = Client()
        client.login(username="admin", password="password")
        url = reverse("master_data")

        # Post action to create a BOM/Set
        payload = {
            "form_type": "bom",
            "new_set_name": "Set 1",
            "new_set_code": "SET1",
            "category": "OTHER",
            "variant": "Premium Pack",
            "component_id[]": [str(self.comp1.id), str(self.comp2.id)],
            "component_qty[]": ["2", "3"],
            "casting_required": "on",
            "machining_required": "on",
            "polishing_required": "on",
            "packing_required": "on"
        }

        response = client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        # Retrieve parent Set
        parent_set = Item.objects.get(code="SET1")
        self.assertEqual(parent_set.item_type, "SET")
        self.assertEqual(parent_set.variant, "Premium Pack")

        # 1. Verify detail merging
        # Category: KHAL + DASTA
        self.assertEqual(parent_set.category, "KHAL + DASTA")
        # Material: BRASS + COPPER
        self.assertEqual(parent_set.material, "BRASS + COPPER")
        # Machining Weight: (0.4 * 2) + (0.2 * 3) = 1.4
        self.assertAlmostEqual(parent_set.machining_weight, 1.4)
        # Casting Weight: (0.5 * 2) + (0.3 * 3) = 1.9
        self.assertAlmostEqual(parent_set.casting_weight, 1.9)
        # Process Requirements: Union of all requirements
        self.assertTrue(parent_set.casting_required)
        self.assertTrue(parent_set.machining_required)
        self.assertTrue(parent_set.polishing_required)
        self.assertTrue(parent_set.packing_required)

        # 2. Verify worker allocation auto-mapping
        allocs = ItemWorkerAllocation.objects.filter(item=parent_set)
        self.assertEqual(allocs.count(), 2)

        # Worker rate should be 5.00 * 2 = 10.00
        worker_alloc = allocs.get(worker=self.worker)
        self.assertAlmostEqual(float(worker_alloc.rate_per_piece), 10.00)

        # Job Worker rate should be 3.00 * 3 = 9.00
        jw_alloc = allocs.get(job_worker=self.job_worker)
        self.assertAlmostEqual(float(jw_alloc.rate_per_piece), 9.00)


class ItemCartonCalculationTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(
            code="K6+D6",
            name="K6+D6 Set",
            lot_size=40,
            lot_with_box=39
        )

    def test_smart_carton_calculations(self):
        """Test the calculate_cartons_and_loose method on Item model."""
        # 1. Perfectly divisible by lot_size (40)
        cartons, loose = self.item.calculate_cartons_and_loose(40)
        self.assertEqual(cartons, 1)
        self.assertEqual(loose, 0)

        # 2. Perfectly divisible by lot_with_box (39)
        cartons, loose = self.item.calculate_cartons_and_loose(39)
        self.assertEqual(cartons, 1)
        self.assertEqual(loose, 0)

        # 3. Two lots of lot_size (80)
        cartons, loose = self.item.calculate_cartons_and_loose(80)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 0)

        # 4. Two boxes of lot_with_box (78)
        cartons, loose = self.item.calculate_cartons_and_loose(78)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 0)

        # 5. Imperfect division: 79 pieces (should choose divisor 39 to get 2 cartons + 1 loose)
        cartons, loose = self.item.calculate_cartons_and_loose(79)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 1)

        # 6. Imperfect division: 41 pieces (should choose divisor 40 to get 1 carton + 1 loose)
        cartons, loose = self.item.calculate_cartons_and_loose(41)
        self.assertEqual(cartons, 1)
        self.assertEqual(loose, 1)


class CartonLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create test items
        self.item1 = Item.objects.create(
            code="ITM1",
            name="Item 1",
            lot_size=10,
            lot_with_box=12,
            machining_weight=0.1
        )
        self.item2 = Item.objects.create(
            code="ITM2",
            name="Item 2",
            lot_size=20,
            lot_with_box=24,
            machining_weight=0.2
        )
        
        # Create a worker
        self.worker1 = Worker.objects.create(
            name="John Worker",
            employee_id="EMP-0002",
            active=True
        )
        
        # Create test client
        from inventory.models import Client as ERPClient
        self.erp_client = ERPClient.objects.create(
            name="Big Client Corp"
        )
        
        # Ensure we have active polishing WIP matching to pack items
        # FIFO matching requires polishing_in transactions to pack items
        StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=self.item1,
            worker=self.worker1,
            quantity=100,
            weight=10.0
        )
        StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=self.item2,
            worker=self.worker1,
            quantity=100,
            weight=20.0
        )

    def test_pack_single_item_carton_success(self):
        """Test packing a single item carton and verify database state and dual-writing."""
        url = reverse("packaging")
        payload = {
            "pack_type": "single",
            "item": str(self.item1.id),
            "quantity": "27",
            "weight": "2.7",
            "packaging_type": "regular",
            "cleaning": "YES",
            "labeling": "YES",
            "packing": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # Verify Carton was created
        from inventory.models import Carton, CartonItem
        cartons = Carton.objects.filter(status='READY')
        self.assertEqual(cartons.count(), 1)
        
        carton = cartons.first()
        self.assertEqual(carton.carton_type, "SINGLE")
        self.assertEqual(carton.carton_label, "ITM1-REG")
        self.assertEqual(carton.total_quantity, 27)
        self.assertAlmostEqual(float(carton.total_weight), 2.7)
        self.assertTrue(carton.cleaning)
        self.assertTrue(carton.labeling)
        self.assertTrue(carton.packing)
        
        # Verify CartonItem was created
        self.assertEqual(carton.items.count(), 1)
        ci = carton.items.first()
        self.assertEqual(ci.item, self.item1)
        self.assertEqual(ci.quantity, 27)
        self.assertAlmostEqual(float(ci.weight), 2.7)
        
        # Verify symmetrical StockTransaction was written
        from inventory.models import StockTransaction
        txs = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            notes__contains=f"[Carton #{carton.id}]"
        )
        self.assertEqual(txs.count(), 1)
        tx = txs.first()
        self.assertEqual(tx.quantity, 27)
        self.assertEqual(tx.item, self.item1)

    def test_pack_single_item_box_carton_success(self):
        """Test packing a single item carton with box packaging and verify structured labeling."""
        url = reverse("packaging")
        payload = {
            "pack_type": "single",
            "item": str(self.item1.id),
            "quantity": "36",
            "weight": "3.6",
            "packaging_type": "box",
            "cleaning": "YES",
            "labeling": "YES",
            "packing": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        from inventory.models import Carton
        carton = Carton.objects.get(carton_label="ITM1-BOX")
        self.assertEqual(carton.carton_type, "SINGLE")
        self.assertEqual(carton.total_quantity, 36)
        self.assertAlmostEqual(float(carton.total_weight), 3.6)

    def test_pack_now_autodetects_packaging_type(self):
        """Test GET pack now action auto-detects packaging type based on lot size multiple."""
        # 1. Create a polish entry with 12 pieces (multiple of lot_with_box = 12)
        polishing_tx = StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=self.item1,
            worker=self.worker1,
            quantity=12,
            weight=1.2
        )
        
        url = reverse("packaging") + f"?pack={polishing_tx.id}"
        response = self.client.get(url)
        self.assertRedirects(response, reverse("packaging"))
        
        from inventory.models import Carton
        carton = Carton.objects.get(carton_label="ITM1-BOX")
        self.assertEqual(carton.total_quantity, 12)
        
        # 2. Create another polish entry with 10 pieces (multiple of lot_size = 10)
        polishing_tx2 = StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=self.item1,
            worker=self.worker1,
            quantity=10,
            weight=1.0
        )
        
        url2 = reverse("packaging") + f"?pack={polishing_tx2.id}"
        response2 = self.client.get(url2)
        self.assertRedirects(response2, reverse("packaging"))
        
        carton2 = Carton.objects.get(carton_label="ITM1-REG")
        self.assertEqual(carton2.total_quantity, 10)

    def test_pack_mixed_item_carton_success(self):
        """Test packing a mixed item carton and verify database state."""
        url = reverse("packaging")
        payload = {
            "pack_type": "mixed",
            "carton_label": "Special Mixed Pack",
            "item[]": [str(self.item1.id), str(self.item2.id)],
            "quantity[]": ["5", "8"],
            "weight[]": ["0.5", "1.6"],
            "cleaning": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        from inventory.models import Carton
        carton = Carton.objects.get(carton_label="Special Mixed Pack")
        self.assertEqual(carton.carton_type, "MIXED")
        self.assertEqual(carton.total_quantity, 13)
        self.assertTrue(carton.cleaning)
        self.assertFalse(carton.labeling)
        
        # Verify both items are in the carton
        self.assertEqual(carton.items.count(), 2)
        ci1 = carton.items.get(item=self.item1)
        self.assertEqual(ci1.quantity, 5)
        ci2 = carton.items.get(item=self.item2)
        self.assertEqual(ci2.quantity, 8)

    def test_pack_queue_bucket_success(self):
        """Test packing multiple items directly from the queue bucket into 1 mixed carton."""
        from inventory.models import StockTransaction, Carton
        
        # 1. Fetch the polishing entries created in setUp()
        pol_tx_1 = StockTransaction.objects.filter(item=self.item1, transaction_type="polishing_in").first()
        pol_tx_2 = StockTransaction.objects.filter(item=self.item2, transaction_type="polishing_in").first()
        
        url = reverse("packaging")
        payload = {
            "pack_type": "mixed",
            "carton_label": "Bucket Carton #1",
            "consume_queue_ids": f"{pol_tx_1.id},{pol_tx_2.id}",
            "item[]": [str(self.item1.id), str(self.item2.id)],
            "quantity[]": ["10", "20"], # pack partial/full amounts
            "weight[]": ["1.0", "4.0"],
            "cleaning": "YES",
            "labeling": "YES",
            "packing": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # 2. Verify carton and carton items
        carton = Carton.objects.get(carton_label="Bucket Carton #1")
        self.assertEqual(carton.carton_type, "MIXED")
        self.assertEqual(carton.total_quantity, 30)
        self.assertAlmostEqual(float(carton.total_weight), 5.0)
        
        # 3. Verify exactly selected polishing entries are marked as PACKED
        tx1_done = StockTransaction.objects.filter(
            notes__startswith=f"PACKED #{pol_tx_1.id}",
            transaction_type="packaging_in"
        ).exists()
        tx2_done = StockTransaction.objects.filter(
            notes__startswith=f"PACKED #{pol_tx_2.id}",
            transaction_type="packaging_in"
        ).exists()
        self.assertTrue(tx1_done)
        self.assertTrue(tx2_done)

    def test_dispatch_carton_success(self):
        """Test dispatching a packaged carton and verify status updates and dual-writing."""
        # 1. Create a packed carton first
        from inventory.models import Carton, CartonItem
        carton = Carton.objects.create(
            carton_type="MIXED",
            carton_label="Dispatch Test Mixed",
            cleaning=True
        )
        ci1 = CartonItem.objects.create(
            carton=carton,
            item=self.item1,
            quantity=15,
            weight=1.5
        )
        ci2 = CartonItem.objects.create(
            carton=carton,
            item=self.item2,
            quantity=25,
            weight=5.0
        )
        carton.save() # trigger totals calculation
        
        # 2. Dispatch the carton via dispatch view
        url = reverse("dispatch")
        payload = {
            "client": str(self.erp_client.id),
            "dispatch_type": "cartons",
            "cartons_selected": [str(carton.id)]
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # Verify carton is marked dispatched
        carton.refresh_from_db()
        self.assertEqual(carton.status, "DISPATCHED")
        self.assertEqual(carton.client, self.erp_client)
        self.assertIsNotNone(carton.dispatched_at)
        
        # Verify symmetrical StockTransaction was written
        from inventory.models import StockTransaction
        txs = StockTransaction.objects.filter(
            transaction_type="dispatch_out",
            client=self.erp_client
        )
        self.assertEqual(txs.count(), 2)
        self.assertEqual(txs.filter(item=self.item1).first().quantity, 15)
        self.assertEqual(txs.filter(item=self.item2).first().quantity, 25)

    def test_packaging_rejection_replaced_from_loose_buffer(self):
        """Test inspection rejections replaced from global loose buffer (no worker impact)."""
        from inventory.models import StockTransaction, Carton
        
        # Outstanding polishing entry of 10 pieces
        pol_tx = StockTransaction.objects.filter(item=self.item1, transaction_type="polishing_in").first()
        pol_tx.quantity = 10
        pol_tx.save()
        
        url = reverse("packaging")
        payload = {
            "pack_type": "single",
            "item": str(self.item1.id),
            "quantity": "5",
            "weight": "0.5",
            "rejections": "2",
            "replace_from_buffer": "YES",
            "cleaning": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # Verify job worker accounts are completely unaffected
        pol_tx.refresh_from_db()
        self.assertEqual(pol_tx.rejection_quantity, 0)
        
        # Verify carton has full lot size
        carton = Carton.objects.filter(carton_label__startswith="ITM1").first()
        self.assertEqual(carton.total_quantity, 5)
        
        # Verify packaging_in transaction tracked the rejections
        pkg_tx = StockTransaction.objects.get(transaction_type="packaging_in", notes__contains=f"PACKED #{pol_tx.id}")
        self.assertEqual(pkg_tx.rejection_quantity, 2)
        self.assertEqual(pkg_tx.quantity, 5)

    def test_packaging_rejection_deducted_from_jobworker(self):
        """Test inspection rejections deducted from job worker's outstanding queue entry."""
        from inventory.models import StockTransaction, Carton
        
        # Outstanding polishing entry of 10 pieces
        pol_tx = StockTransaction.objects.filter(item=self.item1, transaction_type="polishing_in").first()
        pol_tx.quantity = 10
        pol_tx.save()
        
        url = reverse("packaging")
        payload = {
            "pack_type": "single",
            "item": str(self.item1.id),
            "quantity": "5",
            "weight": "0.5",
            "rejections": "2",
            "replace_from_buffer": "NO",
            "cleaning": "YES"
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # Verify rejections are deducted from the job worker's queue entry
        pol_tx.refresh_from_db()
        self.assertEqual(pol_tx.rejection_quantity, 2)
        
        # Verify carton is generated with specified quantity
        carton = Carton.objects.filter(carton_label__startswith="ITM1").first()
        self.assertEqual(carton.total_quantity, 5)
        
        # Verify packaging_in transaction does not track buffer replacement
        pkg_tx = StockTransaction.objects.get(transaction_type="packaging_in", notes__contains=f"PACKED #{pol_tx.id}")
        self.assertEqual(pkg_tx.rejection_quantity, 0)
        self.assertEqual(pkg_tx.quantity, 5)

    def test_inline_attendance_editing(self):
        """Test inline marking and clearing (status NONE) of attendance records."""
        from inventory.models import Attendance, Worker
        from django.urls import reverse
        from django.utils import timezone
        from django.contrib.auth.models import User
        
        admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin_test@example.com",
            password="password"
        )
        self.client.force_login(admin_user)
        
        worker = Worker.objects.create(
            name="Test Worker",
            employee_id="EMP-999",
            salary_model="DAILY",
            daily_rate=500.0,
            overtime_rate=100.0
        )
        
        url = reverse("mark_attendance")
        date_str = "2026-05-15"
        
        # 1. Mark Present and 2h OT
        payload = {
            "worker_id": str(worker.id),
            "status": "PRESENT",
            "date": date_str,
            "ot_hours": "2.0"
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        
        attendance = Attendance.objects.get(worker=worker, date=date_str)
        self.assertEqual(attendance.status, "PRESENT")
        self.assertEqual(attendance.overtime_hours, 2.0)
        
        # 2. Reset / Clear attendance (status NONE)
        payload["status"] = "NONE"
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        
        self.assertFalse(Attendance.objects.filter(worker=worker, date=date_str).exists())

    def test_to_buffer_stock_functionality(self):
        """Test moving pending packaging items directly to Dedicated Loose Buffer stock."""
        from inventory.models import StockTransaction
        from inventory.services import get_stock_by_item
        
        # 1. Inspect initial stock
        initial_stock = get_stock_by_item(self.item1)
        # Polishing stock should be 100 since we have polishing_in of 100
        self.assertEqual(initial_stock['polishing'], 100)
        self.assertEqual(initial_stock['ready'], 0)
        
        # Get polishing transaction entry id
        pol_entry = StockTransaction.objects.filter(item=self.item1, transaction_type="polishing_in").first()
        
        # 2. Trigger to_buffer with 15 pcs
        url = reverse("packaging")
        response = self.client.get(f"{url}?to_buffer={pol_entry.id}&qty=15")
        self.assertRedirects(response, url)
        
        # 3. Verify stock calculations:
        # - Polished loose buffer stock MUST remain 100 pcs (since 15 pcs were NOT packed into cartons!)
        # - Ready packed stock MUST remain 0 pcs (since 15 pcs are loose!)
        updated_stock = get_stock_by_item(self.item1)
        self.assertEqual(updated_stock['polishing'], 100)
        self.assertEqual(updated_stock['ready'], 0)
        
        # 4. Verify that the entry remaining quantity has decreased:
        # A new packaging_in transaction of 15 pcs with [DEDICATED BUFFER] must exist
        dedicated_tx = StockTransaction.objects.get(
            transaction_type="packaging_in",
            item=self.item1,
            notes__contains="[DEDICATED BUFFER]"
        )
        self.assertEqual(dedicated_tx.quantity, 15)
        
        # 5. Delete the Spare stock declaration via delete_spare_id GET parameter
        response = self.client.get(f"{url}?delete_spare_id={dedicated_tx.id}")
        self.assertRedirects(response, url)
        
        # Verify the Spare transaction is deleted
        self.assertFalse(StockTransaction.objects.filter(id=dedicated_tx.id).exists())
        
        # Verify that the Loose stock numbers are perfectly correct
        final_stock = get_stock_by_item(self.item1)
        self.assertEqual(final_stock['polishing'], 100)
        self.assertEqual(final_stock['ready'], 0)

    def test_set_component_rejection_buffer_replacement(self):
        """Test component-level rejections replacement from buffer for SET items during packaging."""
        import json
        from django.urls import reverse
        from inventory.models import Item, StockTransaction, ItemComposition
        
        # 1. Create component items and a parent SET item
        comp1 = Item.objects.create(code="C1", name="Comp 1", machining_weight=0.1)
        comp2 = Item.objects.create(code="C2", name="Comp 2", machining_weight=0.15)
        set_item = Item.objects.create(code="SET1", name="Set 1", item_type="SET")
        
        ItemComposition.objects.create(parent_item=set_item, component_item=comp1, quantity=1)
        ItemComposition.objects.create(parent_item=set_item, component_item=comp2, quantity=1)
        
        # 2. Add some loose polished stock for component items (the buffer)
        StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=comp1,
            quantity=10,
            weight=1.0
        )
        StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=comp2,
            quantity=10,
            weight=1.5
        )
        
        # 3. Add outstanding polishing entry for the parent SET
        set_pol_tx = StockTransaction.objects.create(
            transaction_type="polishing_in",
            item=set_item,
            quantity=5,
            weight=1.25
        )
        
        # 4. Pack the SET with 1 rejection of comp1 replaced from buffer
        url = reverse("packaging")
        payload = {
            "pack_type": "set",
            "item": str(set_item.id),
            "quantity": "5",
            "weight": "1.25",
            "replace_from_buffer": "YES",
            "cleaning": "YES",
            "component_rejections": json.dumps({
                str(comp1.id): 1,
                str(comp2.id): 0
            })
        }
        
        response = self.client.post(url, payload)
        self.assertRedirects(response, url)
        
        # 5. Verify dedicated buffer consumption transaction is created for comp1
        comp1_consumption = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            item=comp1,
            notes__contains="[DEDICATED BUFFER CONSUMPTION]"
        )
        self.assertTrue(comp1_consumption.exists())
        self.assertEqual(comp1_consumption.first().quantity, 1)
        
        # 6. Verify NO consumption transaction exists for comp2
        comp2_consumption = StockTransaction.objects.filter(
            transaction_type="packaging_in",
            item=comp2,
            notes__contains="[DEDICATED BUFFER CONSUMPTION]"
        )
        self.assertFalse(comp2_consumption.exists())
