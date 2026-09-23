import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from core.models import User
from stratas.models import StrataPlan, Membership

user, _ = User.objects.get_or_create(username='managertest999', email='manager999@test.com')
user.set_password('password')
user.save()

strata, _ = StrataPlan.objects.get_or_create(plan_number='EPS 999999', name='Test Strata 999999')
Membership.objects.get_or_create(user=user, strata=strata, role=Membership.Role.STRATA_MANAGER, is_active=True)

client = Client(HTTP_HOST='localhost')
client.login(username='managertest999', password='password')

session = client.session
session['active_strata_id'] = str(strata.id)
session.save()

response = client.get('/dockets/bylaws/new/', HTTP_HOST='localhost')
print(f"GET Status: {response.status_code}")
print(response.content.decode('utf-8')[:1000])

