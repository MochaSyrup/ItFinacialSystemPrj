from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncHour
from django.shortcuts import render
from django.utils import timezone

from apps.interfaces.models import Interface, InterfaceLog


PROTOCOL_TONE = {
    'REST': 'blue', 'SOAP': 'purple', 'MQ': 'amber',
    'SFTP': 'emerald', 'BATCH': 'slate',
}


def dashboard(request):
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    iface_qs = Interface.objects.all()
    iface_total = iface_qs.count()
    iface_active = iface_qs.filter(is_active=True).count()
    iface_inactive = iface_total - iface_active

    today_logs = InterfaceLog.objects.filter(executed_at__gte=today_start)
    today_count = today_logs.count()
    today_fail = today_logs.filter(status='FAIL').count()
    yesterday_count = InterfaceLog.objects.filter(
        executed_at__gte=yesterday_start, executed_at__lt=today_start
    ).count()

    if yesterday_count:
        delta_pct = (today_count - yesterday_count) / yesterday_count * 100
        delta_sub = f'전일 대비 {delta_pct:+.1f}%'
    else:
        delta_sub = '전일 데이터 없음'

    fail_rate = (today_fail / today_count * 100) if today_count else 0.0
    avg_latency = today_logs.filter(latency_ms__isnull=False).aggregate(v=Avg('latency_ms'))['v'] or 0

    kpis = [
        {'label': '등록 인터페이스', 'value': f'{iface_total:,}',
         'sub': f'활성 {iface_active} / 비활성 {iface_inactive}',
         'icon': 'bi-diagram-3', 'tone': 'blue', 'sub_tone': 'ok'},
        {'label': '오늘 호출', 'value': f'{today_count:,}',
         'sub': delta_sub,
         'icon': 'bi-activity', 'tone': 'indigo', 'sub_tone': 'muted'},
        {'label': '실패율', 'value': f'{fail_rate:.2f}%',
         'sub': '임계치 1.00% 이내' if fail_rate < 1.0 else '임계치 초과',
         'icon': 'bi-exclamation-triangle', 'tone': 'amber',
         'sub_tone': 'ok' if fail_rate < 1.0 else 'warn'},
        {'label': '평균 응답시간', 'value': f'{int(avg_latency):,}', 'unit': 'ms',
         'sub': 'SLA 500ms',
         'icon': 'bi-stopwatch', 'tone': 'emerald',
         'sub_tone': 'ok' if avg_latency < 500 else 'warn'},
    ]

    # 시간대별 호출 추이 (오늘 00시부터 현재까지, 시간 단위)
    hourly = (
        today_logs
        .annotate(h=TruncHour('executed_at'))
        .values('h')
        .annotate(
            success=Count('id', filter=Q(status='SUCCESS')),
            fail=Count('id', filter=Q(status='FAIL')),
        )
        .order_by('h')
    )
    buckets = {row['h'].hour: row for row in hourly}
    hours = list(range(now.hour + 1))
    call_chart = {
        'labels': [f'{h:02d}' for h in hours],
        'success': [buckets.get(h, {}).get('success', 0) for h in hours],
        'fail':    [buckets.get(h, {}).get('fail', 0)    for h in hours],
    }

    # 프로토콜 분포 (활성 인터페이스 기준 등록 건수)
    proto_rows = (
        iface_qs.values('protocol')
        .annotate(c=Count('id'))
        .order_by('-c')
    )
    proto_map = dict(Interface.Protocol.choices)
    protocol_chart = {
        'labels': [proto_map.get(r['protocol'], r['protocol']) for r in proto_rows],
        'data':   [r['c'] for r in proto_rows],
    }

    # 최근 실행 로그 Top 10
    recent_logs = []
    for log in InterfaceLog.objects.select_related('interface').order_by('-executed_at')[:10]:
        recent_logs.append({
            'id': log.pk,
            'time': timezone.localtime(log.executed_at).strftime('%H:%M:%S'),
            'name': log.interface.code,
            'protocol': log.interface.get_protocol_display(),
            'protocol_tone': PROTOCOL_TONE.get(log.interface.protocol, 'slate'),
            'target': log.interface.target_system or '-',
            'latency': f'{log.latency_ms:,}ms' if log.latency_ms is not None else '-',
            'status': 'ok' if log.status == 'SUCCESS' else 'fail',
        })

    # 빠른 실행 패널용 활성 인터페이스 + 최근 실행 요약
    quick_interfaces = []
    active_list = list(iface_qs.filter(is_active=True).order_by('code'))
    last_by_id = {}
    for log in (InterfaceLog.objects
                .filter(interface__in=active_list)
                .order_by('interface_id', '-executed_at')):
        last_by_id.setdefault(log.interface_id, log)
    for iface in active_list:
        last = last_by_id.get(iface.id)
        quick_interfaces.append({
            'obj': iface,
            'tone': PROTOCOL_TONE.get(iface.protocol, 'slate'),
            'last_status': last.status if last else None,
            'last_at': timezone.localtime(last.executed_at).strftime('%H:%M:%S') if last else None,
            'last_latency': last.latency_ms if last else None,
        })

    # 실패 알람: 최근 15분 실패 로그
    alert_cutoff = timezone.now() - timedelta(minutes=15)
    recent_fail_qs = (InterfaceLog.objects
                     .select_related('interface')
                     .filter(status='FAIL', executed_at__gte=alert_cutoff)
                     .order_by('-executed_at'))
    recent_fail_count = recent_fail_qs.count()
    recent_fail_samples = list(recent_fail_qs[:5])

    return render(request, 'monitoring/dashboard.html', {
        'page_title': '모니터링',
        'page_subtitle': '인터페이스 통합관리 / 실시간 현황',
        'kpis': kpis,
        'call_chart': call_chart,
        'protocol_chart': protocol_chart,
        'recent_logs': recent_logs,
        'quick_interfaces': quick_interfaces,
        'recent_fail_count': recent_fail_count,
        'recent_fail_samples': recent_fail_samples,
    })
