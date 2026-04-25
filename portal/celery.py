"""Celery 앱 설정.

기동:
    celery -A portal worker -l info
    celery -A portal beat -l info

테스트:
    CELERY_TASK_ALWAYS_EAGER=True 로 동기 실행 (settings 에서 기본 지정)
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal.settings')

app = Celery('portal')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
