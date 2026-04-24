INTERFACE_MANAGE_VIEWS = {'list', 'create', 'update', 'delete', 'toggle'}
INTERFACE_LOGS_VIEWS = {'logs', 'log_detail'}
INTERFACE_EXECUTE_VIEWS = {'execute', 'run', 'log_retry'}

EVAL_PORTFOLIO_VIEWS = {
    'portfolio', 'portfolio_create', 'portfolio_update',
    'portfolio_delete', 'portfolio_detail',
}
EVAL_PRODUCT_VIEWS = {'product', 'product_create', 'product_update', 'product_delete', 'product_detail'}

COSTING_DASHBOARD_VIEWS = {'costing_dashboard'}
COSTING_DIVISION_VIEWS = {
    'costing_division', 'costing_division_create', 'costing_division_delete',
    'costing_department_create', 'costing_department_delete',
}
COSTING_EMPLOYEE_VIEWS = {'costing_employee'}
COSTING_PROJECT_VIEWS = {
    'costing_project', 'costing_project_create', 'costing_project_delete',
    'costing_project_detail',
}
COSTING_LEDGER_VIEWS = {'costing_ledger', 'costing_ledger_create', 'costing_ledger_allocate'}
COSTING_REVENUE_VIEWS = {'costing_revenue', 'costing_revenue_create', 'costing_revenue_delete'}
COSTING_ALLOCATION_VIEWS = {
    'allocation_rules', 'allocation_rule_create', 'allocation_rule_delete',
    'allocation_runs', 'allocation_run_simulate', 'allocation_run_detail',
    'allocation_run_commit', 'allocation_run_reverse', 'allocation_run_delete',
}


def nav(request):
    match = getattr(request, 'resolver_match', None)
    current = match.url_name if match else ''
    namespace = match.namespace if match else ''

    group = current
    if namespace == 'interfaces':
        if current in INTERFACE_MANAGE_VIEWS:
            group = 'interface_manage'
        elif current in INTERFACE_EXECUTE_VIEWS:
            group = 'execute'
        elif current in INTERFACE_LOGS_VIEWS:
            group = 'logs'
    elif namespace == 'evaluation':
        if current in EVAL_PORTFOLIO_VIEWS:
            group = 'portfolio'
        elif current in EVAL_PRODUCT_VIEWS:
            group = 'product'
        elif current == 'risk':
            group = 'risk'
        elif current in COSTING_DASHBOARD_VIEWS:
            group = 'costing_dashboard'
        elif current in COSTING_DIVISION_VIEWS:
            group = 'costing_division'
        elif current in COSTING_EMPLOYEE_VIEWS:
            group = 'costing_employee'
        elif current in COSTING_PROJECT_VIEWS:
            group = 'costing_project'
        elif current in COSTING_LEDGER_VIEWS:
            group = 'costing_ledger'
        elif current in COSTING_REVENUE_VIEWS:
            group = 'costing_revenue'
        elif current in COSTING_ALLOCATION_VIEWS:
            group = 'costing_allocation'

    # 헤더 실패 뱃지 — 최근 15분 실패 카운트
    fail_count = 0
    status_label = '시스템 정상'
    status_tone = 'ok'
    try:
        from datetime import timedelta
        from django.utils import timezone as tz
        from apps.interfaces.models import InterfaceLog
        cutoff = tz.now() - timedelta(minutes=15)
        fail_count = InterfaceLog.objects.filter(
            status='FAIL', executed_at__gte=cutoff,
        ).count()
        if fail_count:
            status_label = f'최근 15분 실패 {fail_count}건'
            status_tone = 'warn'
    except Exception:
        pass

    return {
        'current_nav': current,
        'current_group': group,
        'system_status': {'label': status_label, 'tone': status_tone},
        'recent_fail_count': fail_count,
    }
