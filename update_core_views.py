import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone
from datetime import timedelta
from django.db.models import Count

# I will write the update logic manually for `core/views.py`
