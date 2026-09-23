import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import models
from dockets.models import Bylaw

print("Fields in Bylaw:")
for f in Bylaw._meta.fields:
    print(f.name, type(f))
