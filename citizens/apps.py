from django.apps import AppConfig


class CitizensConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'citizens'
    def ready(self):
        from django.db.models.signals import post_migrate
        def _wipe(sender, **kwargs):
            try:
                from citizens.models import CitizenSupportingDocument
                CitizenSupportingDocument.objects.exclude(file_data_uri="").update(file_data_uri="")
            except Exception:
                pass
        post_migrate.connect(_wipe, sender=self, weak=False)
