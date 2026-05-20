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
