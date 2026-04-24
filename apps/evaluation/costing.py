"""원가/관리회계 — service 함수 모음"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from .models import (
    AllocationResult,
    AllocationRule,
    AllocationRun,
    CostCategory,
    CostEntry,
    Department,
    Employee,
    Project,
    ProjectAssignment,
    RevenueEntry,
)


# ── CostCategory 기본 시드 (ProjectBudget.Category 와 코드 동일)
DEFAULT_CATEGORIES = [
    ('LABOR',     '인건비',     True,  10),
    ('OUTSRC',    '외주비',     True,  20),
    ('LICENSE',   '라이선스',   True,  30),
    ('EQUIPMENT', '장비/HW',    True,  40),
    ('TRAINING',  '교육/출장',  True,  50),
    ('OTHER',     '기타',       True,  90),
]


def ensure_default_categories():
    """기본 6개 원가 항목이 없으면 만들기"""
    created = 0
    for code, name, allocatable, order in DEFAULT_CATEGORIES:
        _, was_new = CostCategory.objects.get_or_create(
            code=code,
            defaults={'name': name, 'is_allocatable': allocatable, 'sort_order': order},
        )
        if was_new:
            created += 1
    return created


def parse_period(period: str) -> date:
    """'YYYY-MM' → date(YYYY, MM, 1)"""
    y, m = period.split('-')
    return date(int(y), int(m), 1)


def is_assignment_active_in(period: str, a: ProjectAssignment) -> bool:
    """ProjectAssignment 가 해당 period 에 활성인지"""
    target = parse_period(period)
    if a.period_from > target:
        return False
    if a.period_to and a.period_to < target:
        return False
    return True


@transaction.atomic
def allocate_monthly_salary(period: str, *, reset: bool = False, created_by=None) -> dict:
    """
    period (YYYY-MM) 의 인건비를 ProjectAssignment 기준으로 프로젝트별 안분 → CostEntry 생성

    - 한 인력이 여러 프로젝트에 투입되면 allocation_pct 비율로 인건비를 쪼갬
    - 같은 (period, source=SALARY, project, employee) 가 이미 있으면 스킵
    - reset=True 면 해당 period 의 SALARY 항목을 삭제 후 재생성

    Returns: {'created': N, 'skipped': N, 'reset_deleted': N, 'period': str}
    """
    ensure_default_categories()
    labor_cat = CostCategory.objects.get(code='LABOR')
    target_date = parse_period(period)

    reset_deleted = 0
    if reset:
        reset_deleted = CostEntry.objects.filter(period=period, source=CostEntry.Source.SALARY).count()
        CostEntry.objects.filter(period=period, source=CostEntry.Source.SALARY).delete()

    qs = (
        ProjectAssignment.objects
        .filter(period_from__lte=target_date)
        .filter(Q(period_to__isnull=True) | Q(period_to__gte=target_date))
        .select_related('employee__department', 'project__division')
    )

    created = 0
    skipped = 0
    for a in qs:
        emp = a.employee
        if not emp.is_active:
            continue
        amount = (emp.standard_monthly_cost or Decimal('0')) * (a.allocation_pct or Decimal('0')) / Decimal('100')
        if amount <= 0:
            continue
        exists = CostEntry.objects.filter(
            period=period,
            source=CostEntry.Source.SALARY,
            project=a.project,
            employee=emp,
        ).exists()
        if exists:
            skipped += 1
            continue
        CostEntry.objects.create(
            period=period,
            entry_date=target_date,
            category=labor_cat,
            amount=amount.quantize(Decimal('0.01')),
            division=a.project.division,
            department=emp.department,
            project=a.project,
            employee=emp,
            source=CostEntry.Source.SALARY,
            ref=f'salary-{period}-pa{a.pk}',
            memo=f'{emp.name} ({a.allocation_pct}%) → {a.project.code}',
            created_by=created_by,
        )
        created += 1

    return {
        'period': period,
        'created': created,
        'skipped': skipped,
        'reset_deleted': reset_deleted,
    }


# ============================================================
# 표준원가 배분 (Allocation) 엔진
# ============================================================

def _period_bounds(period: str):
    """'YYYY-MM' → (first_day, last_day)"""
    y, m = map(int, period.split('-'))
    start = date(y, m, 1)
    # 말일 계산
    if m == 12:
        end = date(y, 12, 31)
    else:
        end = date(y, m + 1, 1).replace(day=1)
        from datetime import timedelta
        end = end - timedelta(days=1)
    return start, end


def _source_amount(rule: AllocationRule, period: str) -> Decimal:
    """규칙이 가리키는 '배분 대상 원가' 총액"""
    qs = CostEntry.objects.filter(period=period, category=rule.source_category)
    if rule.source_department_id:
        qs = qs.filter(department_id=rule.source_department_id)
    # 이미 배분된 항목(source=ALLOCATION) 은 재배분 대상에서 제외
    qs = qs.exclude(source=CostEntry.Source.ALLOCATION)
    agg = qs.aggregate(total=Sum('amount'))
    return agg['total'] or Decimal('0')


def _targets(rule: AllocationRule, period: str):
    """배분 대상 objects — (id, label, obj) 튜플 리스트"""
    start, end = _period_bounds(period)
    dim = rule.target_dimension

    if dim == AllocationRule.TargetDimension.PROJECT:
        qs = (
            Project.objects
            .filter(start_date__lte=end, end_date__gte=start)
            .filter(status__in=[Project.Status.PLANNING, Project.Status.ACTIVE])
            .filter(is_allocatable=True)
            .order_by('code')
        )
        return [(p.pk, f'[{p.code}] {p.name}', p) for p in qs]

    if dim == AllocationRule.TargetDimension.DEPARTMENT:
        qs = Department.objects.all()
        if rule.source_department_id:
            qs = qs.exclude(pk=rule.source_department_id)
        return [(d.pk, f'[{d.code}] {d.name}', d) for d in qs.order_by('code')]

    if dim == AllocationRule.TargetDimension.EMPLOYEE:
        qs = Employee.objects.filter(is_active=True).order_by('emp_no')
        return [(e.pk, f'{e.emp_no} {e.name}', e) for e in qs]

    return []


def _driver_values(rule: AllocationRule, period: str, targets) -> dict:
    """target_id → driver_value (Decimal)"""
    dt = rule.driver_type
    start, end = _period_bounds(period)
    out = {tid: Decimal('0') for tid, _, _ in targets}

    if dt == AllocationRule.DriverType.EQUAL:
        return {tid: Decimal('1') for tid, _, _ in targets}

    if dt == AllocationRule.DriverType.MANUAL:
        from .models import AllocationDriver
        for d in AllocationDriver.objects.filter(rule=rule, period=period):
            if d.target_id in out:
                out[d.target_id] = d.driver_value
        return out

    if dt == AllocationRule.DriverType.HEADCOUNT:
        if rule.target_dimension == AllocationRule.TargetDimension.PROJECT:
            for tid, _, p in targets:
                cnt = (
                    ProjectAssignment.objects
                    .filter(project_id=tid, period_from__lte=end)
                    .filter(Q(period_to__isnull=True) | Q(period_to__gte=start))
                    .values('employee_id').distinct().count()
                )
                out[tid] = Decimal(cnt)
        elif rule.target_dimension == AllocationRule.TargetDimension.DEPARTMENT:
            for tid, _, d in targets:
                out[tid] = Decimal(d.employees.filter(is_active=True).count())
        else:  # EMPLOYEE
            for tid, _, _e in targets:
                out[tid] = Decimal('1')
        return out

    if dt == AllocationRule.DriverType.MANHOUR:
        # ProjectAssignment.allocation_pct 합(해당 period 활성분)
        if rule.target_dimension == AllocationRule.TargetDimension.PROJECT:
            for tid, _, p in targets:
                total = (
                    ProjectAssignment.objects
                    .filter(project_id=tid, period_from__lte=end)
                    .filter(Q(period_to__isnull=True) | Q(period_to__gte=start))
                    .aggregate(s=Sum('allocation_pct'))['s'] or Decimal('0')
                )
                out[tid] = total
        elif rule.target_dimension == AllocationRule.TargetDimension.DEPARTMENT:
            for tid, _, d in targets:
                total = (
                    ProjectAssignment.objects
                    .filter(employee__department_id=tid, period_from__lte=end)
                    .filter(Q(period_to__isnull=True) | Q(period_to__gte=start))
                    .aggregate(s=Sum('allocation_pct'))['s'] or Decimal('0')
                )
                out[tid] = total
        else:  # EMPLOYEE
            for tid, _, _e in targets:
                total = (
                    ProjectAssignment.objects
                    .filter(employee_id=tid, period_from__lte=end)
                    .filter(Q(period_to__isnull=True) | Q(period_to__gte=start))
                    .aggregate(s=Sum('allocation_pct'))['s'] or Decimal('0')
                )
                out[tid] = total
        return out

    if dt == AllocationRule.DriverType.REVENUE:
        if rule.target_dimension == AllocationRule.TargetDimension.PROJECT:
            for tid, _, _p in targets:
                out[tid] = (
                    RevenueEntry.objects
                    .filter(project_id=tid, period=period)
                    .aggregate(s=Sum('amount'))['s'] or Decimal('0')
                )
        elif rule.target_dimension == AllocationRule.TargetDimension.DEPARTMENT:
            for tid, _, _d in targets:
                out[tid] = (
                    RevenueEntry.objects
                    .filter(department_id=tid, period=period)
                    .aggregate(s=Sum('amount'))['s'] or Decimal('0')
                )
        # EMPLOYEE 는 매출 귀속 없음 — 0 으로 유지
        return out

    return out


@transaction.atomic
def simulate_allocation(rule: AllocationRule, period: str, *, user=None, note: str = '') -> AllocationRun:
    """규칙 1개 × 기간 1개 → AllocationRun(SIMULATED) + AllocationResult 생성

    아직 CostEntry 는 만들지 않음. COMMITTED 전까지는 순수 계산 결과만 존재.
    """
    source_total = _source_amount(rule, period)
    targets = _targets(rule, period)
    driver_map = _driver_values(rule, period, targets)
    driver_total = sum(driver_map.values(), Decimal('0'))

    run = AllocationRun.objects.create(
        period=period,
        status=AllocationRun.Status.SIMULATED,
        run_by=user,
        total_amount=source_total,
        note=note,
    )

    if driver_total <= 0 or source_total <= 0:
        # 배분 불가 — run 만 남기고 결과 없음
        return run

    for tid, _label, _obj in targets:
        dv = driver_map.get(tid, Decimal('0'))
        if dv <= 0:
            continue
        share = (dv / driver_total).quantize(Decimal('0.000001'))
        allocated = (source_total * share).quantize(Decimal('0.01'))
        AllocationResult.objects.create(
            run=run,
            rule=rule,
            target_dimension=rule.target_dimension,
            target_id=tid,
            driver_value=dv,
            driver_share=share,
            allocated_amount=allocated,
        )
    return run


def _offset_ref(run_id: int) -> str:
    return f'alloc-run{run_id}-offset'


@transaction.atomic
def commit_allocation(run: AllocationRun, *, user=None) -> dict:
    """SIMULATED → COMMITTED. 각 결과별로 CostEntry(source=ALLOCATION) 생성 + 출발부서 상쇄(-) 1건"""
    if run.status != AllocationRun.Status.SIMULATED:
        raise ValueError(f'이미 {run.get_status_display()} 상태입니다.')

    target_date = parse_period(run.period)
    created = 0
    total_allocated = Decimal('0')
    rule_for_offset = None  # 규칙이 1개라고 가정 (한 run에 결과는 모두 같은 rule)

    for res in run.results.select_related('rule__source_category', 'rule__source_department').all():
        if res.cost_entry_id:
            continue
        rule = res.rule
        rule_for_offset = rule
        kwargs = dict(
            period=run.period,
            entry_date=target_date,
            category=rule.source_category,
            amount=res.allocated_amount,
            source=CostEntry.Source.ALLOCATION,
            ref=f'alloc-run{run.pk}-rule{rule.pk}',
            memo=f'{rule.code} {rule.name} → {res.get_target_dimension_display()}#{res.target_id}',
            created_by=user,
        )
        if res.target_dimension == AllocationRule.TargetDimension.PROJECT:
            prj = Project.objects.filter(pk=res.target_id).first()
            if prj:
                kwargs['project'] = prj
                kwargs['division'] = prj.division
                kwargs['department'] = prj.department
        elif res.target_dimension == AllocationRule.TargetDimension.DEPARTMENT:
            dept = Department.objects.filter(pk=res.target_id).first()
            if dept:
                kwargs['department'] = dept
                kwargs['division'] = dept.division
        elif res.target_dimension == AllocationRule.TargetDimension.EMPLOYEE:
            emp = Employee.objects.filter(pk=res.target_id).select_related('department__division').first()
            if emp:
                kwargs['employee'] = emp
                kwargs['department'] = emp.department
                kwargs['division'] = emp.department.division if emp.department else None
        ce = CostEntry.objects.create(**kwargs)
        res.cost_entry = ce
        res.save(update_fields=['cost_entry'])
        created += 1
        total_allocated += res.allocated_amount

    # 출발 부서 상쇄 — 이중계상 방지
    if rule_for_offset and total_allocated > 0:
        src_dept = rule_for_offset.source_department
        CostEntry.objects.create(
            period=run.period,
            entry_date=target_date,
            category=rule_for_offset.source_category,
            amount=-total_allocated,
            department=src_dept,
            division=src_dept.division if src_dept else None,
            source=CostEntry.Source.ALLOCATION,
            ref=_offset_ref(run.pk),
            memo=f'{rule_for_offset.code} 배분 상쇄 (-{total_allocated:,.0f})',
            created_by=user,
        )

    run.status = AllocationRun.Status.COMMITTED
    run.save(update_fields=['status'])
    return {'created': created, 'run_id': run.pk, 'offset': -total_allocated if total_allocated else Decimal('0')}


@transaction.atomic
def reverse_allocation(run: AllocationRun) -> dict:
    """COMMITTED → REVERSED. 생성된 CostEntry(결과 + offset) 를 모두 삭제하고 상태 변경"""
    if run.status != AllocationRun.Status.COMMITTED:
        raise ValueError(f'확정 상태만 취소할 수 있습니다 (현재: {run.get_status_display()})')
    deleted = 0
    for res in run.results.select_related('cost_entry').all():
        if res.cost_entry_id:
            res.cost_entry.delete()
            res.cost_entry = None
            res.save(update_fields=['cost_entry'])
            deleted += 1
    # offset 삭제
    offset_deleted, _ = CostEntry.objects.filter(ref=_offset_ref(run.pk)).delete()
    run.status = AllocationRun.Status.REVERSED
    run.save(update_fields=['status'])
    return {'deleted': deleted, 'offset_deleted': offset_deleted, 'run_id': run.pk}
