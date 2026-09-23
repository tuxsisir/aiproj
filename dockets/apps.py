from django.apps import AppConfig

class DocketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dockets"

    def ready(self):
        import dockets.signals  # noqa
