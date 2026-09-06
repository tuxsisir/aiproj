import os
import django
from django.test.client import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

c = Client(SERVER_NAME='localhost')
response = c.get('/static/css/dist/styles.css')
print(f"Status: {response.status_code}")
