import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from stratas.models import StrataPlan, Membership
from faker import Faker

User = get_user_model()

class Command(BaseCommand):
    help = 'Initialize the database with demo users, stratas, and memberships.'

    def handle(self, *args, **options):
        fake = Faker()

        self.stdout.write(self.style.WARNING("Starting demo data generation..."))

        # 1. Create Superuser
        admin_email = "sisir@sisir.com"
        admin_username = "sisir"
        admin_password = "Hello@World123"

        if not User.objects.filter(username=admin_username).exists():
            User.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password
            )
            self.stdout.write(self.style.SUCCESS(f"Created Superuser: {admin_username}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Superuser {admin_username} already exists."))

        # 2. Create Strata Plans
        strata_1_data = {
            "name": "kings landing 2",
            "plan_number": "eps 8291",
            "street_address": "13623 81A Ave",
            "city": "Surrey",
            "state_province": "BC",
            "postal_code": "v3w 3n7",
            "country": "CA",
            "total_units": 120,
        }
        
        strata_2_data = {
            "name": "kings landing (original)",
            "plan_number": "eps 9112",
            "street_address": "13291 82 Ave",
            "city": "Surrey",
            "state_province": "BC",
            "postal_code": "v3w 3n7",
            "country": "CA",
            "total_units": 80,
        }

        s1, _ = StrataPlan.objects.get_or_create(plan_number=strata_1_data["plan_number"], defaults=strata_1_data)
        s2, _ = StrataPlan.objects.get_or_create(plan_number=strata_2_data["plan_number"], defaults=strata_2_data)
        
        self.stdout.write(self.style.SUCCESS(f"Created/Verified Strata Plans: {s1.name} and {s2.name}"))

        # Helper to generate members
        def create_members(strata, role, count):
            for _ in range(count):
                email = fake.unique.email()
                user = User.objects.create_user(
                    username=email.split('@')[0] + str(random.randint(1000, 9999)),
                    email=email,
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    password="password123"
                )
                
                # Generate a random unit number for owners/council
                unit_num = str(random.randint(100, 999)) if role in [Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT] else ""
                
                Membership.objects.create(
                    user=user,
                    strata=strata,
                    role=role,
                    unit_number=unit_num
                )
            self.stdout.write(f"  -> Generated {count} {role}(s) for {strata.plan_number}")

        # 3. Generate Memberships for Building 1
        self.stdout.write(f"Generating members for {s1.name}...")
        create_members(s1, Membership.Role.COUNCIL_PRESIDENT, 1)
        create_members(s1, Membership.Role.COUNCIL_MEMBER, 5)
        create_members(s1, Membership.Role.STRATA_MANAGER, 2)
        create_members(s1, Membership.Role.CARETAKER, 1)

        # Generate Memberships for Building 2
        self.stdout.write(f"Generating members for {s2.name}...")
        create_members(s2, Membership.Role.COUNCIL_PRESIDENT, 1)
        create_members(s2, Membership.Role.COUNCIL_MEMBER, 5)
        create_members(s2, Membership.Role.STRATA_MANAGER, 2)
        create_members(s2, Membership.Role.CARETAKER, 1)

        # 4. Generate Mock Incidents for Kings Landing 2
        from dockets.models import Incident, IncidentResponse, Bylaw
        from django.utils import timezone
        import datetime
        
        self.stdout.write(f"Generating mock incidents for {s1.name}...")
        admin_user = User.objects.get(username=admin_username)
        bylaws = list(Bylaw.objects.filter(strata=s1))
        
        # Fallback for pre-existing strata plans that missed the post_save signal
        if not bylaws:
            from dockets.signals import seed_default_bylaws
            seed_default_bylaws(s1)
            bylaws = list(Bylaw.objects.filter(strata=s1))
        
        if bylaws:
            # Incident 1: Notice Issued, clock running
            i1 = Incident.objects.create(
                strata=s1,
                created_by=admin_user,
                incident_type=Incident.Type.BYLAW,
                title="Unauthorized Hardwood Flooring Installation",
                unit_number="402",
                bylaw=bylaws[3],  # 14(1)
                description="Contractors observed bringing in hardwood flooring materials without council approval.",
                recipient_email="unit402@example.com",
            )
            i1.calculate_and_set_deadline()
            i1.save()
            
            # Incident 2: Response Received, ready for voting
            i2 = Incident.objects.create(
                strata=s1,
                created_by=admin_user,
                incident_type=Incident.Type.BYLAW,
                title="Excessive Noise - Barking Dog",
                unit_number="115",
                bylaw=bylaws[0],  # 3(4)
                description="Multiple reports of dog barking incessantly during quiet hours on weekend.",
                recipient_email="unit115@example.com",
            )
            i2.calculate_and_set_deadline()
            
            # Wind back the deadline so it looks realistic
            i2.notice_issued_at = timezone.now() - datetime.timedelta(days=10)
            i2.statutory_deadline = i2.notice_issued_at + datetime.timedelta(days=18)
            i2.status = Incident.Status.VOTING_OPEN
            i2.save()
            
            IncidentResponse.objects.create(
                incident=i2,
                response_type=IncidentResponse.ResponseType.WRITTEN,
                statement="I apologize for the noise. My dog was anxious because I was away at the hospital. I have now hired a dog sitter."
            )
            self.stdout.write(self.style.SUCCESS("  -> 2 Mock incidents created (1 Notice Issued, 1 Ready for Vote)."))

        self.stdout.write(self.style.SUCCESS("Demo data generation complete!"))
