from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncHour
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PROTOCOL_CONFIG_HINTS, InterfaceForm
from .models import Interface, InterfaceLog
from .protocols import execute_interface


def _stub(request, template, title, subtitle):
    return render(request, template, {'page_title': title, 'page_subtitle': subtitle})


def interface_list(request):
    qs = Interface.objects.all().order_by('-created_at')
    q = request.GET.get('q', '').strip()
    protocol = request.GET.get('protocol', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(target_system__icontains=q))
    if protocol:
        qs = qs.filter(protocol=protocol)

    return render(request, 'interfaces/list.html', {
        'page_title': '인터페이스 관리',
        'page_subtitle': '인터페이스 통합관리 / 등록 · 설정',
        'interfaces': qs,
        'q': q,
        'protocol': protocol,
        'protocol_choices': Interface.Protocol.choices,
        'total': qs.count(),
    })


def interface_create(request):
    if request.method == 'POST':
        form = InterfaceForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'인터페이스 "{obj.code}" 등록 완료')
            return redirect('interfaces:list')
    else:
        form = InterfaceForm()
    return render(request, 'interfaces/form.html', {
        'page_title': '인터페이스 등록',
        'page_subtitle': '인터페이스 통합관리 / 신규 등록',
        'form': form,
        'mode': 'create',
        'protocol_config_hints': PROTOCOL_CONFIG_HINTS,
        'protocol_operations': Interface.PROTOCOL_OPERATIONS,
    })


def interface_update(request, pk):
    obj = get_object_or_404(Interface, pk=pk)
    if request.method == 'POST':
        form = InterfaceForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{obj.code}" 수정 완료')
            return redirect('interfaces:list')
    else:
        form = InterfaceForm(instance=obj)
    return render(request, 'interfaces/form.html', {
        'page_title': f'인터페이스 수정 — {obj.code}',
        'page_subtitle': '인터페이스 통합관리 / 수정',
        'form': form,
        'mode': 'update',
        'obj': obj,
        'protocol_config_hints': PROTOCOL_CONFIG_HINTS,
        'protocol_operations': Interface.PROTOCOL_OPERATIONS,
    })


@require_POST
def interface_delete(request, pk):
    obj = get_object_or_404(Interface, pk=pk)
    code = obj.code
    obj.delete()
    messages.success(request, f'"{code}" 삭제 완료')
    return redirect('interfaces:list')


@require_POST
def interface_toggle(request, pk):
    obj = get_object_or_404(Interface, pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active'])
    return render(request, 'interfaces/_active_badge.html', {'obj': obj})


def execute(request):
    tab = request.GET.get('tab', 'manual')
    if tab not in ('manual', 'retry'):
        tab = 'manual'

    interfaces = list(Interface.objects.filter(is_active=True).order_by('code'))
    last_by_iface = {}
    for log in InterfaceLog.objects.filter(interface__in=interfaces).order_by('interface_id', '-executed_at'):
        last_by_iface.setdefault(log.interface_id, log)
    interface_rows = [(iface, last_by_iface.get(iface.id)) for iface in interfaces]

    failed_qs = (InterfaceLog.objects
                 .select_related('interface')
                 .filter(status=InterfaceLog.Status.FAIL)
                 .order_by('-executed_at'))
    failed_count = failed_qs.count()
    failed_logs = list(failed_qs[:50])

    return render(request, 'interfaces/execute.html', {
        'page_title': '실행 / 재처리',
        'page_subtitle': '인터페이스 통합관리 / 수동 실행 및 실패 건 재처리',
        'tab': tab,
        'interface_rows': interface_rows,
        'failed_logs': failed_logs,
        'failed_count': failed_count,
    })


@require_POST
def interface_run(request, pk):
    iface = get_object_or_404(Interface, pk=pk)
    log = execute_interface(iface)
    if log.status == InterfaceLog.Status.SUCCESS:
        messages.success(request, f'"{iface.code}" 실행 성공 ({log.latency_ms}ms)')
    else:
        messages.error(request, f'"{iface.code}" 실행 실패: {log.error}')
    return redirect(request.META.get('HTTP_REFERER') or 'interfaces:execute')


@require_POST
def log_retry(request, pk):
    original = get_object_or_404(InterfaceLog, pk=pk)
    log = execute_interface(original.interface)
    if log.status == InterfaceLog.Status.SUCCESS:
        messages.success(request, f'"{original.interface.code}" 재처리 성공 ({log.latency_ms}ms)')
    else:
        messages.error(request, f'"{original.interface.code}" 재처리 실패: {log.error}')
    return redirect(request.META.get('HTTP_REFERER') or 'interfaces:execute')


PERIODS = {
    '1h': ('최근 1시간', timedelta(hours=1)),
    '24h': ('최근 24시간', timedelta(hours=24)),
    '7d': ('최근 7일', timedelta(days=7)),
    'all': ('전체', None),
}


def logs(request):
    qs = InterfaceLog.objects.select_related('interface').order_by('-executed_at')

    interface_id = request.GET.get('interface', '').strip()
    status = request.GET.get('status', '').strip()
    period = request.GET.get('period', '24h')
    if period not in PERIODS:
        period = '24h'

    delta = PERIODS[period][1]
    if delta is not None:
        qs = qs.filter(executed_at__gte=timezone.now() - delta)
    if interface_id:
        qs = qs.filter(interface_id=interface_id)
    if status:
        qs = qs.filter(status=status)

    total = qs.count()
    success = qs.filter(status=InterfaceLog.Status.SUCCESS).count()
    fail = total - success
    fail_rate = round((fail / total * 100), 2) if total else 0.0
    avg_latency = qs.filter(latency_ms__isnull=False).aggregate(a=Avg('latency_ms'))['a'] or 0

    hourly = (qs.annotate(hour=TruncHour('executed_at'))
                .values('hour')
                .annotate(
                    success=Count('id', filter=Q(status=InterfaceLog.Status.SUCCESS)),
                    fail=Count('id', filter=Q(status=InterfaceLog.Status.FAIL)),
                )
                .order_by('hour'))

    chart = {
        'labels': [h['hour'].strftime('%m-%d %H:%M') for h in hourly],
        'success': [h['success'] for h in hourly],
        'fail': [h['fail'] for h in hourly],
    }

    top_latency = list(
        qs.filter(latency_ms__isnull=False)
          .values('interface__code', 'interface__name')
          .annotate(avg=Avg('latency_ms'), n=Count('id'))
          .order_by('-avg')[:5]
    )
    for row in top_latency:
        row['avg'] = round(row['avg'])

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    qs_params = []
    for k, v in [('interface', interface_id), ('status', status), ('period', period)]:
        if v:
            qs_params.append(f'{k}={v}')
    base_qs = '&'.join(qs_params)

    return render(request, 'interfaces/logs.html', {
        'page_title': '로그 & 성능',
        'page_subtitle': '인터페이스 통합관리 / 호출 로그 및 성능 지표',
        'page_obj': page_obj,
        'kpi': {
            'total': total, 'success': success, 'fail': fail,
            'fail_rate': fail_rate, 'avg_latency': round(avg_latency),
        },
        'chart': chart,
        'top_latency': top_latency,
        'interfaces_all': Interface.objects.all().order_by('code'),
        'filters': {
            'interface': interface_id, 'status': status, 'period': period,
        },
        'periods': [(k, v[0]) for k, v in PERIODS.items()],
        'base_qs': base_qs,
    })


def log_detail(request, pk):
    log = get_object_or_404(InterfaceLog.objects.select_related('interface'), pk=pk)
    return render(request, 'interfaces/log_detail.html', {
        'page_title': f'로그 상세 #{log.pk}',
        'page_subtitle': f'{log.interface.code} @ {log.executed_at:%Y-%m-%d %H:%M:%S}',
        'log': log,
    })
