import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from core.models import User
from stratas.models import StrataPlan, Membership
from dockets.models import Bylaw, Incident

user, _ = User.objects.get_or_create(username='managertest99', email='manager99@test.com')
user.set_password('password')
user.save()

client = Client(HTTP_HOST='localhost')
client.login(username='managertest99', password='password')

response = client.post('/stratas/onboarding/', {
    'persona': 'MANAGER',
    'plan_number': 'EPS 9999',
    'name': 'Test Strata 9999',
    'brokerage_name': 'Test Brokerage',
    'phone_number': '123-456-7890'
}, HTTP_HOST='localhost')

print(f"Response status: {response.status_code}")
if response.status_code == 302:
    print(f"Redirected to: {response.url}")
    strata = StrataPlan.objects.get(plan_number='EPS9999')
    bylaws = Bylaw.objects.filter(strata=strata)
    incidents = Incident.objects.filter(strata=strata)
    print("Bylaws:", [b.code for b in bylaws])
    print("Incidents:", [i.title for i in incidents])
else:
    print("Form failed or not redirected.")
    print(response.content.decode('utf-8')[:500])

