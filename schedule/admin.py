from django.contrib import admin

from .models import KeyDate


@admin.register(KeyDate)
class KeyDateAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "category", "repeats_yearly", "strata")
    list_filter = ("category", "repeats_yearly")
    search_fields = ("title", "strata__name", "strata__plan_number")
