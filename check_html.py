import os
import django
from django.test.client import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

c = Client(SERVER_NAME='localhost')
response = c.get('/')
html = response.content.decode('utf-8')
for line in html.splitlines():
    if 'stylesheet' in line or 'tailwind' in line or 'css' in line:
        print(line.strip())
