from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Seeds four test users with specific roles/groups for access control verification'

    def handle(self, *args, **options):
        # Define users to create
        users_data = [
            {
                'username': 'admin_user',
                'email': 'admin@foundry.com',
                'password': 'Foundry@2026',
                'group': 'System Admin',
                'is_staff': True,
                'is_superuser': True
            },
            {
                'username': 'operator_user',
                'email': 'operator@foundry.com',
                'password': 'Foundry@2026',
                'group': 'Production Operator',
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'logistics_user',
                'email': 'logistics@foundry.com',
                'password': 'Foundry@2026',
                'group': 'Logistics Supervisor',
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'hr_user',
                'email': 'hr@foundry.com',
                'password': 'Foundry@2026',
                'group': 'HR & Accounts Manager',
                'is_staff': False,
                'is_superuser': False
            }
        ]

        self.stdout.write(self.style.WARNING("Starting test user seeding process..."))

        for user_info in users_data:
            username = user_info['username']
            email = user_info['email']
            password = user_info['password']
            group_name = user_info['group']

            # Ensure the Group exists
            group, created_group = Group.objects.get_or_create(name=group_name)
            if created_group:
                self.stdout.write(self.style.SUCCESS(f"Created missing Group: '{group_name}'"))

            # Create or update User
            user, created_user = User.objects.get_or_create(username=username, defaults={
                'email': email,
                'is_staff': user_info['is_staff'],
                'is_superuser': user_info['is_superuser'],
            })

            # Set password and save
            user.set_password(password)
            user.is_staff = user_info['is_staff']
            user.is_superuser = user_info['is_superuser']
            user.save()

            # Assign to Group
            user.groups.clear()
            user.groups.add(group)

            status_str = "Created new" if created_user else "Updated existing"
            self.stdout.write(
                self.style.SUCCESS(
                    f"✔ {status_str} User: '{username}' | Role: '{group_name}' | Pwd: '{password}'"
                )
            )

        self.stdout.write(self.style.SUCCESS("🎉 Seeding completed successfully!"))
