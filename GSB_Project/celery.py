import os
from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GSB_Project.settings')

app = Celery('GSB_Project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Dedicated queues — each with its own worker pool for independent scaling
app.conf.task_queues = (
    Queue('celery_default', Exchange('celery_default'), routing_key='default'),
    Queue('celery_ocr',     Exchange('celery_ocr'),     routing_key='ocr'),
    Queue('celery_ai',      Exchange('celery_ai'),      routing_key='ai'),
    Queue('celery_math',    Exchange('celery_math'),    routing_key='math'),
)
app.conf.task_default_queue = 'celery_default'
app.conf.task_default_exchange = 'celery_default'
app.conf.task_default_routing_key = 'default'
