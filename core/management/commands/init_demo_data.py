import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from stratas.models import StrataPlan, Membership
from dockets.models import Incident, IncidentEvent, Bylaw
from faker import Faker

User = get_user_model()

class Command(BaseCommand):
    help = 'Initialize the database with demo users, stratas, and memberships.'

    def handle(self, *args, **options):
        fake = Faker()
        self.stdout.write(self.style.WARNING("Starting demo data generation..."))

        # 1. Create a Single Demo Strata Plan
        strata_data = {
            "name": "DEMO STRATA",
            "plan_number": "EPS 123",
            "street_address": "123 Demo Street",
            "city": "Vancouver",
            "state_province": "BC",
            "postal_code": "V6B 1A1",
            "country": "CA",
            "total_units": 100,
        }
        
        s1, _ = StrataPlan.objects.get_or_create(plan_number=strata_data["plan_number"], defaults=strata_data)
        self.stdout.write(self.style.SUCCESS(f"Created/Verified Strata Plan: {s1.name}"))

        # Helper to generate random members
        def create_random_members(strata, role, count):
            for _ in range(count):
                email = fake.unique.email()
                user = User.objects.create_user(
                    username=email.split('@')[0] + str(random.randint(1000, 9999)),
                    email=email,
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    password="helloworld"
                )
                unit_num = str(random.randint(100, 999))
                Membership.objects.create(
                    user=user,
                    strata=strata,
                    role=role,
                    unit_number=unit_num
                )
            self.stdout.write(f"  -> Generated {count} random {role}(s)")

        # 2. Create Specific Manager
        manager_user, created = User.objects.get_or_create(
            email="manager@manager.com",
            defaults={
                "username": "manager",
                "first_name": "Mike",
                "last_name": "M",
            }
        )
        if created:
            manager_user.set_password("helloworld")
            manager_user.save()
        else:
            manager_user.set_password("helloworld")
            manager_user.save()

        Membership.objects.get_or_create(
            user=manager_user,
            strata=s1,
            defaults={"role": Membership.Role.STRATA_MANAGER}
        )
        self.stdout.write(self.style.SUCCESS("  -> Created specific Manager: Mike M"))

        # 3. Create Specific Council Member
        council_user, created = User.objects.get_or_create(
            email="council@council.com",
            defaults={
                "username": "council",
                "first_name": "Sara",
                "last_name": "G",
            }
        )
        if created:
            council_user.set_password("helloworld")
            council_user.save()
        else:
            council_user.set_password("helloworld")
            council_user.save()

        Membership.objects.get_or_create(
            user=council_user,
            strata=s1,
            defaults={
                "role": Membership.Role.COUNCIL_PRESIDENT,
                "unit_number": "PH1"
            }
        )
        self.stdout.write(self.style.SUCCESS("  -> Created specific Council Member: Sara G"))

        # 4. Create 7 random council members
        create_random_members(s1, Membership.Role.COUNCIL_MEMBER, 7)

        # 5. Generate 15 Mock Incidents
        self.stdout.write(f"Generating 15 mock incidents for {s1.name}...")
        
        bylaws = list(Bylaw.objects.filter(strata=s1))
        if not bylaws:
            from dockets.signals import seed_default_bylaws
            seed_default_bylaws(s1)
            bylaws = list(Bylaw.objects.filter(strata=s1))
            
        incident_titles = [
            "Noise complaint - Loud music at night",
            "Improper parking in visitor stall",
            "Garbage left in hallway",
            "Pet waste not picked up",
            "Smoking on balcony",
            "Unauthorized alterations to unit",
            "Damage to common property",
            "Short-term rental suspected",
            "Water leak originating from unit",
            "Items stored on patio",
            "Moving without booking elevator",
            "Harassment of strata staff",
            "Propped open security door",
            "Unregistered pet",
            "Bicycles brought through lobby"
        ]

        if bylaws:
            for i in range(15):
                title = incident_titles[i % len(incident_titles)]
                bylaw = random.choice(bylaws)
                unit = str(random.randint(100, 999))
                
                incident = Incident.objects.create(
                    strata=s1,
                    created_by=manager_user,
                    incident_type=Incident.Type.BYLAW,
                    title=f"{title} (Unit {unit})",
                    unit_number=unit,
                    bylaw=bylaw,
                    description=fake.paragraph(nb_sentences=3),
                    recipient_email=f"unit{unit}@example.com",
                    status=Incident.Status.IN_REVIEW
                )
                
            self.stdout.write(self.style.SUCCESS("  -> 15 Mock incidents created (IN_REVIEW status)."))

        self.stdout.write(self.style.SUCCESS("Demo data generation complete!"))
