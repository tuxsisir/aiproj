from django.db.models.signals import post_save
from django.dispatch import receiver
from stratas.models import StrataPlan
from .models import Bylaw

def seed_default_bylaws(strata_plan):
    bylaws_data = [
        {"code": "3(4)", "title": "Quiet Enjoyment & Nuisance", "standard_fine": 200.00},
        {"code": "3(5)", "title": "Pet Control & Leash Requirements", "standard_fine": 150.00},
        {"code": "7(1)", "title": "Parking & Vehicle Restrictions", "standard_fine": 100.00},
        {"code": "14(1)", "title": "Unauthorized Common Property Alterations", "standard_fine": 200.00},
        {"code": "26(1)", "title": "Short-Term Accommodation Restrictions", "standard_fine": 1000.00},
    ]

    for data in bylaws_data:
        Bylaw.objects.get_or_create(
            strata=strata_plan,
            code=data["code"],
            defaults={
                "title": data["title"],
                "standard_fine": data["standard_fine"]
            }
        )

@receiver(post_save, sender=StrataPlan)
def seed_bylaws_on_strata_create(sender, instance, created, **kwargs):
    if created:
        seed_default_bylaws(instance)
