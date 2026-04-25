# Celery 앱 로드 — manage.py / gunicorn 기동 시 @shared_task 가 자동 등록되도록 early import
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery 미설치 환경(테스트·로컬)에서 Django 자체는 계속 구동되도록 허용
    pass
