import json
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
from .utils import mask_config


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

    total = qs.count()
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    base_qs = '&'.join(f'{k}={v}' for k, v in [('q', q), ('protocol', protocol)] if v)

    return render(request, 'interfaces/list.html', {
        'page_title': '인터페이스 관리',
        'page_subtitle': '인터페이스 통합관리 / 등록 · 설정',
        'page_obj': page_obj,
        'interfaces': page_obj.object_list,
        'q': q,
        'protocol': protocol,
        'protocol_choices': Interface.Protocol.choices,
        'total': total,
        'base_qs': base_qs,
    })


def interface_detail(request, pk):
    obj = get_object_or_404(Interface, pk=pk)
    logs_qs = obj.logs.order_by('-executed_at')
    recent_logs = list(logs_qs[:20])
    total = logs_qs.count()
    success = logs_qs.filter(status=InterfaceLog.Status.SUCCESS).count()
    success_rate = round(success / total * 100, 1) if total else 0.0
    avg_latency = logs_qs.filter(latency_ms__isnull=False).aggregate(a=Avg('latency_ms'))['a'] or 0
    return render(request, 'interfaces/detail.html', {
        'page_title': f'인터페이스 상세 — {obj.code}',
        'page_subtitle': obj.name,
        'obj': obj,
        'config_masked': mask_config(obj.config_json or {}),
        'recent_logs': recent_logs,
        'kpi': {
            'total': total, 'success': success, 'fail': total - success,
            'success_rate': success_rate, 'avg_latency': round(avg_latency),
        },
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
        'protocol_hints_json': json.dumps(PROTOCOL_CONFIG_HINTS, ensure_ascii=False),
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
        'protocol_hints_json': json.dumps(PROTOCOL_CONFIG_HINTS, ensure_ascii=False),
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


@require_POST
def log_retry_bulk(request):
    """여러 실패 로그 일괄 재처리.

    - log_ids (리스트): 체크박스 선택
    - scope=all: 현재 실패 로그 전부 (최대 100건)
    """
    ids = request.POST.getlist('log_ids')
    scope = request.POST.get('scope', '')
    if scope == 'all':
        originals = InterfaceLog.objects.filter(status=InterfaceLog.Status.FAIL).order_by('-executed_at')[:100]
    else:
        if not ids:
            messages.warning(request, '재처리할 로그를 선택하세요.')
            return redirect('interfaces:execute')
        originals = InterfaceLog.objects.filter(pk__in=ids, status=InterfaceLog.Status.FAIL)

    # 동일 인터페이스 중복 호출 제거 (실패 로그 여러 건이 같은 iface 를 가리킬 수 있음)
    seen = set()
    targets = []
    for log in originals:
        if log.interface_id in seen:
            continue
        seen.add(log.interface_id)
        targets.append(log.interface)

    if not targets:
        messages.warning(request, '재처리 대상이 없습니다.')
        return redirect('interfaces:execute')

    ok, fail = 0, 0
    for iface in targets:
        new_log = execute_interface(iface)
        if new_log.status == InterfaceLog.Status.SUCCESS:
            ok += 1
        else:
            fail += 1
    messages.success(request, f'일괄 재처리 완료 — 성공 {ok}건, 실패 {fail}건 (인터페이스 {len(targets)}개)')
    return redirect('interfaces:execute')


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
