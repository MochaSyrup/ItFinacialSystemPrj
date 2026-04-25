"""Celery 태스크 — 인터페이스 스케줄 디스패치 & 개별 실행"""
import logging

from celery import shared_task
from django.utils import timezone

from .models import Interface, InterfaceLog
from .protocols import execute_interface

log = logging.getLogger(__name__)


def _cron_matches(expr: str, dt) -> bool:
    """`expr` (5필드 cron) 이 `dt` (초·마이크로초 버림) 에 걸리는지."""
    if not expr:
        return False
    try:
        from croniter import croniter
    except ImportError:
        return False
    try:
        # croniter.match 가 True → dt 가 expr 의 발사 시점과 일치
        return croniter.match(expr, dt.replace(second=0, microsecond=0))
    except Exception as exc:
        log.warning('cron parse failed: %r — %s', expr, exc)
        return False


@shared_task(name='apps.interfaces.tasks.run_interface')
def run_interface(interface_id: int) -> dict:
    """인터페이스 1건 실행 — 활성 상태 확인 후 어댑터 호출."""
    iface = Interface.objects.filter(pk=interface_id, is_active=True).first()
    if not iface:
        return {'interface_id': interface_id, 'skipped': True, 'reason': 'not found or inactive'}
    log_obj = execute_interface(iface)
    return {
        'interface_id': interface_id,
        'log_id': log_obj.pk,
        'status': log_obj.status,
        'latency_ms': log_obj.latency_ms,
    }


@shared_task(name='apps.interfaces.tasks.dispatch_interfaces')
def dispatch_interfaces() -> dict:
    """매분 실행 — 현재 시각에 cron 이 걸리는 활성 인터페이스를 비동기 trigger."""
    now = timezone.localtime()
    active = Interface.objects.filter(is_active=True).exclude(schedule_cron='')
    dispatched = []
    for iface in active:
        if _cron_matches(iface.schedule_cron, now):
            run_interface.delay(iface.pk)
            dispatched.append(iface.code)
    return {
        'at': now.strftime('%Y-%m-%d %H:%M'),
        'checked': active.count(),
        'dispatched': len(dispatched),
        'codes': dispatched,
    }


@shared_task(name='apps.interfaces.tasks.cleanup_old_logs')
def cleanup_old_logs(keep_days: int = 90) -> dict:
    """보관 기간 초과 로그 삭제 — 운영 시 Beat 에 추가해 일 1회 정도 실행."""
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=keep_days)
    deleted, _ = InterfaceLog.objects.filter(executed_at__lt=cutoff).delete()
    return {'deleted': deleted, 'cutoff': cutoff.isoformat()}
