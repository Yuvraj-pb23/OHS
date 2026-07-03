"""
Celery application configuration for OHS project.

This module initializes the Celery application, binds it to Django settings,
and enables autodiscovery of tasks from all installed Django apps.
"""

import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "OHS.settings")

app = Celery("OHS")

# Load Celery config from Django settings, namespace='CELERY'
# All celery-related settings must be prefixed with CELERY_ in settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all registered Django app configs
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")
