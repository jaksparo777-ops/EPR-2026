from django.test import TestCase, Client as HttpClient
from django.contrib.auth.models import User, Group
from apps.products.models import Client, Item, TransactionType
from apps.production.models import StockTransaction
from apps.logistics.models import Carton, CartonItem

class LogisticsTestCase(TestCase):
    def setUp(self):
        # Setup Groups
        self.logistics_group, _ = Group.objects.get_or_create(name='Logistics Supervisor')
        
        # Setup Test User
        self.user = User.objects.create_user(username='logistics_user', password='password123')
        self.user.groups.add(self.logistics_group)
        
        # Setup Client
        self.client_obj = Client.objects.create(
            name="Alpha Client",
            phone="1234567890",
            email="alpha@test.com",
            city="Metropolis"
        )
        
        # Setup Item
        self.item = Item.objects.create(
            client=self.client_obj,
            code="ITM-001",
            name="Base Brackets",
            category="BRACKET",
            casting_weight=1.5,
            machining_weight=1.2,
            lot_size=20,
            lot_with_box=25
        )

    def test_calculate_cartons_and_loose(self):
        # 1. Test standard lot division (lot_size=20, lot_with_box=25)
        # Quantity divisible by lot_size
        cartons, loose = self.item.calculate_cartons_and_loose(40)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 0)
        
        # Quantity divisible by lot_with_box
        cartons, loose = self.item.calculate_cartons_and_loose(50)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 0)
        
        # Non-divisible quantity: remainder closer to lot_size
        # 42 % 20 = 2, 42 % 25 = 17. 2 < 17, so divisor should be 20.
        cartons, loose = self.item.calculate_cartons_and_loose(42)
        self.assertEqual(cartons, 2)
        self.assertEqual(loose, 2)

    def test_carton_creation_and_number_generation(self):
        # Ensure Carton automatic number generation works correctly
        carton = Carton.objects.create(
            carton_type=Carton.CartonType.SINGLE,
            carton_label="Test Batch",
            cleaning=True,
            labeling=True,
            packing=True,
            total_quantity=20,
            total_weight=24.0,
            status=Carton.CartonStatus.READY,
            client=self.client_obj
        )
        self.assertTrue(carton.carton_number.startswith("CTN-"))
        
        # Ensure relation works
        carton_item = CartonItem.objects.create(
            carton=carton,
            item=self.item,
            quantity=20,
            weight=24.0
        )
        self.assertEqual(carton.items.count(), 1)
        self.assertEqual(carton.items.first().quantity, 20)
