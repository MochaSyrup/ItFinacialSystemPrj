from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.db.models import Count, Sum

from . import metrics
from django.db.models import ProtectedError

from .forms import (
    KIND_HINTS,
    AllocateSalaryForm,
    AllocationRuleForm,
    AllocationRunForm,
    CostEntryForm,
    RevenueEntryForm,
    DepartmentForm,
    DivisionForm,
    FinancialProductForm,
    PortfolioForm,
    ProjectBudgetFormSet,
    ProjectForm,
)
from .costing import (
    allocate_monthly_salary,
    commit_allocation,
    reverse_allocation,
    simulate_allocation,
)
from .models import (
    AllocationResult,
    AllocationRule,
    AllocationRun,
    CostCategory,
    CostEntry,
    Department,
    Division,
    Employee,
    FinancialProduct,
    Portfolio,
    Project,
    ProjectAssignment,
    ProjectBudget,
    RevenueEntry,
)


# ---------- 포트폴리오 ----------

def portfolio(request):
    rows = []
    for pf in Portfolio.objects.all().order_by('-created_at').prefetch_related('products'):
        prods = list(pf.products.all())
        rows.append({
            'pf': pf,
            'count': len(prods),
            'notional': sum(float(p.notional or 0) for p in prods),
        })
    return render(request, 'evaluation/portfolio.html', {
        'page_title': '포트폴리오',
        'page_subtitle': '금융상품 평가 / 포트폴리오 관리',
        'rows': rows,
    })


def portfolio_create(request):
    if request.method == 'POST':
        form = PortfolioForm(request.POST)
        if form.is_valid():
            pf = form.save()
            messages.success(request, f'포트폴리오 "{pf.name}" 등록 완료')
            return redirect('evaluation:portfolio')
    else:
        form = PortfolioForm()
    return render(request, 'evaluation/portfolio_form.html', {
        'page_title': '포트폴리오 등록',
        'page_subtitle': '금융상품 평가 / 신규 포트폴리오',
        'form': form, 'mode': 'create',
    })


def portfolio_update(request, pk):
    pf = get_object_or_404(Portfolio, pk=pk)
    if request.method == 'POST':
        form = PortfolioForm(request.POST, instance=pf)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{pf.name}" 수정 완료')
            return redirect('evaluation:portfolio')
    else:
        form = PortfolioForm(instance=pf)
    return render(request, 'evaluation/portfolio_form.html', {
        'page_title': f'포트폴리오 수정 — {pf.name}',
        'page_subtitle': '금융상품 평가 / 수정',
        'form': form, 'mode': 'update', 'obj': pf,
    })


@require_POST
def portfolio_delete(request, pk):
    pf = get_object_or_404(Portfolio, pk=pk)
    name = pf.name
    pf.delete()
    messages.success(request, f'"{name}" 삭제 완료')
    return redirect('evaluation:portfolio')


def portfolio_detail(request, pk):
    pf = get_object_or_404(Portfolio, pk=pk)
    products = list(pf.products.all().order_by('kind', 'code'))
    agg = metrics.aggregate(products, weight_limit_pct=pf.weight_limit_pct)
    return render(request, 'evaluation/portfolio_detail.html', {
        'page_title': f'포트폴리오 — {pf.name}',
        'page_subtitle': f'{pf.base_currency} · {len(products)}개 상품',
        'pf': pf,
        'agg': agg,
    })


def product_detail(request, pk):
    obj = get_object_or_404(FinancialProduct.objects.select_related('portfolio'), pk=pk)
    c = metrics.compute(obj)
    pf = obj.portfolio
    # 포트폴리오 전체에서의 비중/한도초과 계산
    siblings = list(pf.products.all())
    agg = metrics.aggregate(siblings, weight_limit_pct=pf.weight_limit_pct)
    my_row = next((r for r in agg['per_product'] if r['product'].pk == obj.pk), None)
    return render(request, 'evaluation/product_detail.html', {
        'page_title': f'{obj.code} — {obj.name}',
        'page_subtitle': f'{obj.get_kind_display()} · {pf.name}',
        'obj': obj,
        'pf': pf,
        'c': c,
        'row': my_row,
    })


# ---------- 금융상품 ----------

def product(request):
    qs = FinancialProduct.objects.select_related('portfolio').order_by('-id')
    kind = request.GET.get('kind', '').strip()
    pf_id = request.GET.get('portfolio', '').strip()
    if kind:
        qs = qs.filter(kind=kind)
    if pf_id:
        qs = qs.filter(portfolio_id=pf_id)
    return render(request, 'evaluation/product.html', {
        'page_title': '금융상품',
        'page_subtitle': '금융상품 평가 / 주식 · 채권 · 파생 · 프로젝트',
        'products': qs,
        'kind_choices': FinancialProduct.Kind.choices,
        'kind': kind,
        'pf_id': pf_id,
        'portfolios': Portfolio.objects.all(),
        'total': qs.count(),
    })


def product_create(request):
    if request.method == 'POST':
        form = FinancialProductForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'상품 "{obj.code}" 등록 완료')
            return redirect('evaluation:product')
    else:
        form = FinancialProductForm()
    return render(request, 'evaluation/product_form.html', {
        'page_title': '금융상품 등록',
        'page_subtitle': '금융상품 평가 / 신규 등록',
        'form': form, 'mode': 'create',
        'kind_hints': KIND_HINTS,
    })


def product_update(request, pk):
    obj = get_object_or_404(FinancialProduct, pk=pk)
    if request.method == 'POST':
        form = FinancialProductForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{obj.code}" 수정 완료')
            return redirect('evaluation:product')
    else:
        form = FinancialProductForm(instance=obj)
    return render(request, 'evaluation/product_form.html', {
        'page_title': f'상품 수정 — {obj.code}',
        'page_subtitle': '금융상품 평가 / 수정',
        'form': form, 'mode': 'update', 'obj': obj,
        'kind_hints': KIND_HINTS,
    })


@require_POST
def product_delete(request, pk):
    obj = get_object_or_404(FinancialProduct, pk=pk)
    code = obj.code
    obj.delete()
    messages.success(request, f'"{code}" 삭제 완료')
    return redirect('evaluation:product')


# ---------- 리스크 분석 ----------

def risk(request):
    portfolios = Portfolio.objects.all().order_by('name')
    pf_id = request.GET.get('portfolio', '').strip()
    selected = None
    agg = None
    kind_distribution = []

    if pf_id:
        selected = portfolios.filter(pk=pf_id).first()
    if not selected and portfolios.exists():
        selected = portfolios.first()

    if selected:
        products = list(selected.products.all().order_by('kind', 'code'))
        agg = metrics.aggregate(products, weight_limit_pct=selected.weight_limit_pct)
        counter = Counter(p.kind for p in products)
        labels_map = dict(FinancialProduct.Kind.choices)
        kind_distribution = [
            {'label': labels_map.get(k, k), 'count': v}
            for k, v in counter.most_common()
        ]

    return render(request, 'evaluation/risk.html', {
        'page_title': '리스크 분석',
        'page_subtitle': '금융상품 평가 / VaR · Duration · NPV · IRR',
        'portfolios': portfolios,
        'selected': selected,
        'agg': agg,
        'kind_distribution': kind_distribution,
        'kind_chart': {
            'labels': [k['label'] for k in kind_distribution],
            'data': [k['count'] for k in kind_distribution],
        },
    })


# ============================================================
# 원가/관리회계
# ============================================================

def _project_progress_pct(project, today):
    """프로젝트 총 기간 중 경과 비율 (0~100, int)"""
    total = (project.end_date - project.start_date).days
    if total <= 0:
        return 100
    elapsed = (today - project.start_date).days
    return max(0, min(100, round(elapsed / total * 100)))


def _default_period_range():
    """기본 기간 — 올해 1월부터 당월까지"""
    from datetime import date
    today = date.today()
    return f'{today.year}-01', f'{today.year:04d}-{today.month:02d}'


def costing_dashboard(request):
    """손익 대시보드 — 기간 필터 / 전사 KPI / 본부·프로젝트 P&L"""
    import json

    default_from, default_to = _default_period_range()
    period_from = request.GET.get('period_from', '').strip() or default_from
    period_to = request.GET.get('period_to', '').strip() or default_to

    # 원가/수익 기초 필터
    ce = CostEntry.objects.filter(period__gte=period_from, period__lte=period_to)
    re = RevenueEntry.objects.filter(period__gte=period_from, period__lte=period_to)

    # 전사 KPI
    total_revenue = re.aggregate(s=Sum('amount'))['s'] or 0
    total_cost = ce.aggregate(s=Sum('amount'))['s'] or 0
    total_profit = total_revenue - total_cost
    margin_pct = (float(total_profit) / float(total_revenue) * 100) if total_revenue else 0

    # 본부별 P&L
    rev_by_div = dict(
        (r['division_id'], r['amount']) for r in
        re.values('division_id').annotate(amount=Sum('amount'))
    )
    cost_by_div = dict(
        (r['division_id'], r['amount']) for r in
        ce.values('division_id').annotate(amount=Sum('amount'))
    )
    div_rows = []
    for d in Division.objects.all().order_by('code'):
        rev = rev_by_div.get(d.pk, 0) or 0
        cost = cost_by_div.get(d.pk, 0) or 0
        profit = rev - cost
        margin = (float(profit) / float(rev) * 100) if rev else 0
        div_rows.append({
            'div': d, 'revenue': rev, 'cost': cost,
            'profit': profit, 'margin': margin,
        })

    # 프로젝트별 P&L (매출 또는 원가가 있는 프로젝트만)
    rev_by_prj = dict(
        (r['project_id'], r['amount']) for r in
        re.exclude(project_id__isnull=True).values('project_id').annotate(amount=Sum('amount'))
    )
    cost_by_prj = dict(
        (r['project_id'], r['amount']) for r in
        ce.exclude(project_id__isnull=True).values('project_id').annotate(amount=Sum('amount'))
    )
    prj_ids = set(rev_by_prj) | set(cost_by_prj)
    prj_map = {
        p.pk: p for p in
        Project.objects.filter(pk__in=prj_ids).select_related('division')
    }
    prj_rows = []
    for pid in prj_ids:
        p = prj_map.get(pid)
        if not p:
            continue
        rev = rev_by_prj.get(pid, 0) or 0
        cost = cost_by_prj.get(pid, 0) or 0
        profit = rev - cost
        margin = (float(profit) / float(rev) * 100) if rev else 0
        prj_rows.append({
            'p': p, 'revenue': rev, 'cost': cost,
            'profit': profit, 'margin': margin,
        })
    prj_rows.sort(key=lambda r: r['profit'])  # 손실 큰 순
    prj_bottom = prj_rows[:10]
    prj_top = sorted(prj_rows, key=lambda r: -r['profit'])[:10]

    # 원가 구성 (source별)
    source_labels = dict(CostEntry.Source.choices)
    src_rows = list(
        ce.values('source').annotate(amount=Sum('amount')).order_by('-amount')
    )
    source_chart = {
        'labels': [source_labels.get(r['source'], r['source']) for r in src_rows],
        'data': [float(r['amount'] or 0) for r in src_rows],
    }

    # 항목(category)별 원가
    cat_rows = list(
        ce.values('category__code', 'category__name')
        .annotate(amount=Sum('amount'))
        .order_by('-amount')
    )

    return render(request, 'evaluation/costing_dashboard.html', {
        'page_title': '손익 대시보드',
        'page_subtitle': f'{period_from} ~ {period_to} · 실적 기준 P&L',
        'period_from': period_from,
        'period_to': period_to,
        'kpi': {
            'revenue': total_revenue,
            'cost': total_cost,
            'profit': total_profit,
            'margin': margin_pct,
        },
        'div_rows': div_rows,
        'prj_top': prj_top,
        'prj_bottom': prj_bottom,
        'cat_rows': cat_rows,
        'source_chart_json': json.dumps(source_chart),
        'totals': {
            'divisions': Division.objects.count(),
            'departments': Department.objects.count(),
            'employees': Employee.objects.filter(is_active=True).count(),
            'projects_active': Project.objects.filter(status__in=['PLANNING', 'ACTIVE']).count(),
        },
    })


def costing_project_detail(request, pk):
    p = get_object_or_404(
        Project.objects.select_related('division', 'department', 'pm'),
        pk=pk,
    )
    from datetime import date
    today = date.today()
    progress = _project_progress_pct(p, today)
    profit = (p.contract_amount or 0) - (p.budget or 0)
    assignments = p.assignments.select_related('employee__department').all()
    budgets = p.budgets.all()
    return render(request, 'evaluation/costing_project_detail.html', {
        'page_title': f'[{p.code}] {p.name}',
        'page_subtitle': '원가/관리회계 / 프로젝트 상세',
        'p': p,
        'progress': progress,
        'profit': profit,
        'assignments': assignments,
        'budgets': budgets,
    })


def costing_division(request):
    """본부/부서 트리 조회"""
    divisions = Division.objects.all().prefetch_related('departments__employees')
    return render(request, 'evaluation/costing_division.html', {
        'page_title': '본부 · 부서',
        'page_subtitle': '원가/관리회계 / 조직 마스터',
        'divisions': divisions,
    })


def costing_employee(request):
    """인력 목록 — 본부 > 부서 그룹화"""
    divisions = (
        Division.objects.all()
        .prefetch_related('departments__employees')
        .order_by('code')
    )
    groups = []
    total = 0
    for div in divisions:
        dept_groups = []
        div_total = 0
        for dept in div.departments.all().order_by('code'):
            emps = list(dept.employees.filter(is_active=True).order_by('emp_no'))
            dept_groups.append({'dept': dept, 'employees': emps})
            div_total += len(emps)
        groups.append({'div': div, 'depts': dept_groups, 'total': div_total})
        total += div_total
    return render(request, 'evaluation/costing_employee.html', {
        'page_title': '인력',
        'page_subtitle': '원가/관리회계 / 인력 마스터',
        'groups': groups,
        'total': total,
    })


def costing_project(request):
    """프로젝트 목록 + 인력 투입 요약"""
    projects = (
        Project.objects.all()
        .select_related('division', 'pm')
        .annotate(assignment_count=Count('assignments'))
    )
    return render(request, 'evaluation/costing_project.html', {
        'page_title': '프로젝트',
        'page_subtitle': '원가/관리회계 / 프로젝트 마스터',
        'projects': projects,
    })


def _build_division_payload():
    """본부 → 부서/인력 페이로드 + 부서별 월급합 (JS 동적 필터링용)"""
    from django.db.models import Sum
    payload = {}
    for div in Division.objects.all().prefetch_related('departments', 'departments__employees'):
        depts = []
        emps = []
        for dept in div.departments.all().order_by('code'):
            dept_emps = list(dept.employees.filter(is_active=True))
            depts.append({
                'id': dept.pk,
                'code': dept.code,
                'name': dept.name,
                'monthly_cost_sum': float(
                    sum((e.standard_monthly_cost or 0) for e in dept_emps)
                ),
                'employee_count': len(dept_emps),
            })
            for e in dept_emps:
                emps.append({
                    'id': e.pk,
                    'emp_no': e.emp_no,
                    'name': e.name,
                    'rank': e.get_rank_display(),
                    'department_id': dept.pk,
                    'monthly_cost': float(e.standard_monthly_cost or 0),
                })
        payload[div.pk] = {'departments': depts, 'employees': emps}
    return payload


def costing_project_create(request):
    import json
    division_payload = _build_division_payload()

    # 단계: form → preview → 확정
    stage = request.POST.get('stage') if request.method == 'POST' else 'edit'

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        budget_formset = ProjectBudgetFormSet(request.POST, prefix='budget')

        if stage == 'back':
            # 미리보기에서 수정으로 돌아가기 — 입력값 유지한 채 form 화면 렌더
            return render(request, 'evaluation/costing_project_form.html', {
                'page_title': '프로젝트 등록',
                'page_subtitle': '원가/관리회계 / 프로젝트 신규',
                'form': form,
                'budget_formset': budget_formset,
                'division_payload_json': json.dumps(division_payload),
                'category_labor_value': ProjectBudget.Category.LABOR.value,
            })

        if form.is_valid() and budget_formset.is_valid():
            if stage == 'confirm':
                # 실제 저장
                p = form.save()
                budget_formset.instance = p
                budget_formset.save()
                messages.success(request, f'프로젝트 "{p.code} {p.name}" 등록 완료')
                return redirect('evaluation:costing_project')

            # 미리보기 단계
            project_preview = form.save(commit=False)
            budget_rows = []
            budget_total = 0
            for bf in budget_formset:
                if bf.cleaned_data and not bf.cleaned_data.get('DELETE'):
                    amt = bf.cleaned_data.get('amount') or 0
                    cat = bf.cleaned_data.get('category')
                    if cat and amt:
                        budget_rows.append({
                            'category_label': dict(ProjectBudget.Category.choices).get(cat, cat),
                            'amount': amt,
                            'memo': bf.cleaned_data.get('memo', ''),
                        })
                        budget_total += float(amt)
            return render(request, 'evaluation/costing_project_preview.html', {
                'page_title': '프로젝트 등록 — 확인',
                'page_subtitle': '아래 내용으로 등록할까요?',
                'form': form,
                'budget_formset': budget_formset,
                'p': project_preview,
                'budget_rows': budget_rows,
                'budget_total': budget_total,
                'profit': float(project_preview.contract_amount or 0) - float(project_preview.budget or 0),
            })
    else:
        form = ProjectForm()
        budget_formset = ProjectBudgetFormSet(prefix='budget')

    return render(request, 'evaluation/costing_project_form.html', {
        'page_title': '프로젝트 등록',
        'page_subtitle': '원가/관리회계 / 프로젝트 신규',
        'form': form,
        'budget_formset': budget_formset,
        'division_payload_json': json.dumps(division_payload),
        'category_labor_value': ProjectBudget.Category.LABOR.value,
    })


@require_POST
def costing_project_delete(request, pk):
    p = get_object_or_404(Project, pk=pk)
    label = f'{p.code} {p.name}'
    p.delete()
    messages.success(request, f'프로젝트 "{label}" 삭제 완료')
    return redirect('evaluation:costing_project')


# ── 본부 CRUD ──

def costing_division_create(request):
    if request.method == 'POST':
        form = DivisionForm(request.POST)
        if form.is_valid():
            d = form.save()
            messages.success(request, f'본부 "[{d.code}] {d.name}" 등록 완료')
            return redirect('evaluation:costing_division')
    else:
        form = DivisionForm()
    return render(request, 'evaluation/costing_division_form.html', {
        'page_title': '본부 등록',
        'page_subtitle': '원가/관리회계 / 본부 신규',
        'form': form,
    })


@require_POST
def costing_division_delete(request, pk):
    d = get_object_or_404(Division, pk=pk)
    label = f'[{d.code}] {d.name}'
    try:
        d.delete()
        messages.success(request, f'본부 "{label}" 삭제 완료')
    except ProtectedError:
        dept_count = d.departments.count()
        prj_count = d.projects.count()
        messages.error(
            request,
            f'본부 "{label}" 삭제 불가 — 소속 부서 {dept_count}개 / 프로젝트 {prj_count}개가 남아 있습니다. 먼저 정리하세요.',
        )
    return redirect('evaluation:costing_division')


# ── 부서 CRUD ──

def costing_department_create(request):
    initial_div_id = request.GET.get('division') or None
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            d = form.save()
            messages.success(request, f'부서 "[{d.code}] {d.name}" 등록 완료')
            return redirect('evaluation:costing_division')
    else:
        form = DepartmentForm(initial_division=initial_div_id)
    return render(request, 'evaluation/costing_department_form.html', {
        'page_title': '부서 등록',
        'page_subtitle': '원가/관리회계 / 부서 신규',
        'form': form,
    })


@require_POST
def costing_department_delete(request, pk):
    d = get_object_or_404(Department, pk=pk)
    label = f'[{d.code}] {d.name}'
    try:
        d.delete()
        messages.success(request, f'부서 "{label}" 삭제 완료')
    except ProtectedError:
        emp_count = d.employees.count()
        messages.error(
            request,
            f'부서 "{label}" 삭제 불가 — 소속 인력 {emp_count}명이 남아 있습니다. 인력을 다른 부서로 옮기거나 삭제하세요.',
        )
    return redirect('evaluation:costing_division')


# ── 원가 원장 ──

def costing_ledger(request):
    """원가 원장 조회 — 필터 + 합계 + 페이지네이션"""
    from django.core.paginator import Paginator
    from django.db.models import Count

    qs = CostEntry.objects.select_related(
        'category', 'division', 'department', 'project', 'employee',
    )

    # 필터
    f = {
        'period_from': request.GET.get('period_from', '').strip(),
        'period_to':   request.GET.get('period_to',   '').strip(),
        'division':    request.GET.get('division',    '').strip(),
        'department':  request.GET.get('department',  '').strip(),
        'project':     request.GET.get('project',     '').strip(),
        'category':    request.GET.get('category',    '').strip(),
        'source':      request.GET.get('source',      '').strip(),
    }
    if f['period_from']:
        qs = qs.filter(period__gte=f['period_from'])
    if f['period_to']:
        qs = qs.filter(period__lte=f['period_to'])
    if f['division']:
        qs = qs.filter(division_id=f['division'])
    if f['department']:
        qs = qs.filter(department_id=f['department'])
    if f['project']:
        qs = qs.filter(project_id=f['project'])
    if f['category']:
        qs = qs.filter(category_id=f['category'])
    if f['source']:
        qs = qs.filter(source=f['source'])

    # 합계 (필터 적용된 결과)
    agg = qs.aggregate(total=Sum('amount'), cnt=Count('id'))
    total_amount = agg['total'] or 0
    total_count = agg['cnt'] or 0

    # 항목별 / 본부별 합 (필터 결과 기준)
    by_category = list(
        qs.values('category__code', 'category__name')
        .annotate(amount=Sum('amount'), cnt=Count('id'))
        .order_by('-amount')
    )
    by_division = list(
        qs.values('division__code', 'division__name')
        .annotate(amount=Sum('amount'), cnt=Count('id'))
        .order_by('-amount')
    )

    page = Paginator(qs, 50).get_page(request.GET.get('page'))

    return render(request, 'evaluation/costing_ledger.html', {
        'page_title': '원가 원장',
        'page_subtitle': '원가/관리회계 / 실집행 원가 조회',
        'page_obj': page,
        'f': f,
        'total_amount': total_amount,
        'total_count': total_count,
        'by_category': by_category,
        'by_division': by_division,
        'divisions': Division.objects.all().order_by('code'),
        'departments': Department.objects.all().order_by('code'),
        'projects': Project.objects.all().order_by('code'),
        'categories': CostCategory.objects.all().order_by('sort_order', 'code'),
        'source_choices': CostEntry.Source.choices,
    })


def costing_ledger_create(request):
    """원가 수동 입력"""
    if request.method == 'POST':
        form = CostEntryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.source = CostEntry.Source.MANUAL
            if request.user.is_authenticated:
                obj.created_by = request.user
            obj.save()
            messages.success(request, f'원가 1건 등록 완료 ({obj.period} {obj.category.code} {obj.amount:,})')
            return redirect('evaluation:costing_ledger')
    else:
        form = CostEntryForm()
    return render(request, 'evaluation/costing_ledger_form.html', {
        'page_title': '원가 수동 입력',
        'page_subtitle': '원가/관리회계 / 원가 원장 / 단건 입력',
        'form': form,
    })


# ── 수익 원장 ──

def costing_revenue(request):
    """수익 원장 조회"""
    from django.core.paginator import Paginator

    qs = RevenueEntry.objects.select_related('division', 'department', 'project')

    f = {
        'period_from': request.GET.get('period_from', '').strip(),
        'period_to':   request.GET.get('period_to', '').strip(),
        'division':    request.GET.get('division', '').strip(),
        'department':  request.GET.get('department', '').strip(),
        'project':     request.GET.get('project', '').strip(),
    }
    if f['period_from']:
        qs = qs.filter(period__gte=f['period_from'])
    if f['period_to']:
        qs = qs.filter(period__lte=f['period_to'])
    if f['division']:
        qs = qs.filter(division_id=f['division'])
    if f['department']:
        qs = qs.filter(department_id=f['department'])
    if f['project']:
        qs = qs.filter(project_id=f['project'])

    agg = qs.aggregate(total=Sum('amount'), cnt=Count('id'))
    total_amount = agg['total'] or 0
    total_count = agg['cnt'] or 0

    by_division = list(
        qs.values('division__code', 'division__name')
        .annotate(amount=Sum('amount'), cnt=Count('id'))
        .order_by('-amount')
    )
    by_project = list(
        qs.values('project__code', 'project__name')
        .annotate(amount=Sum('amount'), cnt=Count('id'))
        .order_by('-amount')[:10]
    )

    page = Paginator(qs, 50).get_page(request.GET.get('page'))

    return render(request, 'evaluation/costing_revenue.html', {
        'page_title': '수익 원장',
        'page_subtitle': '원가/관리회계 / 실현 매출 조회',
        'page_obj': page,
        'f': f,
        'total_amount': total_amount,
        'total_count': total_count,
        'by_division': by_division,
        'by_project': by_project,
        'divisions': Division.objects.all().order_by('code'),
        'departments': Department.objects.all().order_by('code'),
        'projects': Project.objects.all().order_by('code'),
    })


def costing_revenue_create(request):
    if request.method == 'POST':
        form = RevenueEntryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if request.user.is_authenticated:
                obj.created_by = request.user
            obj.save()
            messages.success(request, f'수익 1건 등록 완료 ({obj.period} {obj.amount:,})')
            return redirect('evaluation:costing_revenue')
    else:
        form = RevenueEntryForm()
    return render(request, 'evaluation/costing_revenue_form.html', {
        'page_title': '수익 입력',
        'page_subtitle': '원가/관리회계 / 수익 원장 / 단건 입력',
        'form': form,
    })


@require_POST
def costing_revenue_delete(request, pk):
    r = get_object_or_404(RevenueEntry, pk=pk)
    r.delete()
    messages.success(request, f'수익 #{pk} 삭제 완료')
    return redirect('evaluation:costing_revenue')


# ── 표준원가 배분 (Allocation) ──

def _resolve_targets(results):
    """AllocationResult 리스트에 target_obj 라벨 붙여서 반환"""
    # 차원별로 id 모아서 한 번에 조회
    by_dim = {}
    for r in results:
        by_dim.setdefault(r.target_dimension, set()).add(r.target_id)

    obj_map = {'PROJECT': {}, 'DEPARTMENT': {}, 'EMPLOYEE': {}}
    if 'PROJECT' in by_dim:
        for p in Project.objects.filter(pk__in=by_dim['PROJECT']).select_related('division'):
            obj_map['PROJECT'][p.pk] = p
    if 'DEPARTMENT' in by_dim:
        for d in Department.objects.filter(pk__in=by_dim['DEPARTMENT']).select_related('division'):
            obj_map['DEPARTMENT'][d.pk] = d
    if 'EMPLOYEE' in by_dim:
        for e in Employee.objects.filter(pk__in=by_dim['EMPLOYEE']).select_related('department'):
            obj_map['EMPLOYEE'][e.pk] = e

    rows = []
    for r in results:
        obj = obj_map.get(r.target_dimension, {}).get(r.target_id)
        if obj:
            if r.target_dimension == 'PROJECT':
                label = f'[{obj.code}] {obj.name}'
                sub = obj.division.name if obj.division else ''
            elif r.target_dimension == 'DEPARTMENT':
                label = f'[{obj.code}] {obj.name}'
                sub = obj.division.name if obj.division else ''
            else:
                label = f'{obj.emp_no} {obj.name}'
                sub = obj.department.name if obj.department else ''
        else:
            label = f'{r.get_target_dimension_display()}#{r.target_id} (삭제됨)'
            sub = ''
        rows.append({'r': r, 'label': label, 'sub': sub})
    return rows


def allocation_rule_list(request):
    rules = (
        AllocationRule.objects
        .select_related('source_category', 'source_department')
        .order_by('priority', 'code')
    )
    return render(request, 'evaluation/allocation_rules.html', {
        'page_title': '배분 규칙',
        'page_subtitle': '원가/관리회계 / 표준원가 배분 / 규칙 마스터',
        'rules': rules,
    })


def allocation_rule_create(request):
    if request.method == 'POST':
        form = AllocationRuleForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'배분 규칙 "[{obj.code}] {obj.name}" 등록 완료')
            return redirect('evaluation:allocation_rules')
    else:
        form = AllocationRuleForm()
    return render(request, 'evaluation/allocation_rule_form.html', {
        'page_title': '배분 규칙 등록',
        'page_subtitle': '원가/관리회계 / 표준원가 배분 / 신규 규칙',
        'form': form,
    })


@require_POST
def allocation_rule_delete(request, pk):
    rule = get_object_or_404(AllocationRule, pk=pk)
    label = f'[{rule.code}] {rule.name}'
    try:
        rule.delete()
        messages.success(request, f'규칙 "{label}" 삭제 완료')
    except ProtectedError:
        messages.error(request, f'규칙 "{label}" 삭제 불가 — 연결된 실행 이력이 있습니다.')
    return redirect('evaluation:allocation_rules')


def allocation_run_list(request):
    runs = (
        AllocationRun.objects
        .prefetch_related('results')
        .order_by('-run_at')[:100]
    )
    return render(request, 'evaluation/allocation_runs.html', {
        'page_title': '배분 실행 이력',
        'page_subtitle': '원가/관리회계 / 표준원가 배분 / 시뮬 & 확정',
        'runs': runs,
    })


def allocation_run_simulate(request):
    """신규 시뮬 실행 — 성공 시 detail 로 이동"""
    if request.method == 'POST':
        form = AllocationRunForm(request.POST)
        if form.is_valid():
            user = request.user if request.user.is_authenticated else None
            run = simulate_allocation(
                form.cleaned_data['rule'],
                form.cleaned_data['period'],
                user=user,
                note=form.cleaned_data.get('note', ''),
            )
            messages.success(
                request,
                f'시뮬레이션 완료 — Run #{run.pk} / 대상금액 {run.total_amount:,.0f} / 결과 {run.results.count()}건'
            )
            return redirect('evaluation:allocation_run_detail', pk=run.pk)
    else:
        form = AllocationRunForm()
    return render(request, 'evaluation/allocation_run_form.html', {
        'page_title': '배분 시뮬 실행',
        'page_subtitle': '원가/관리회계 / 표준원가 배분 / 새 시뮬',
        'form': form,
    })


def allocation_run_detail(request, pk):
    run = get_object_or_404(
        AllocationRun.objects.select_related('run_by'),
        pk=pk,
    )
    results = list(
        run.results.select_related('rule__source_category', 'rule__source_department')
        .order_by('-allocated_amount')
    )
    rows = _resolve_targets(results)
    # 집계
    total_allocated = sum((r.allocated_amount for r in results), Decimal('0'))
    rule = results[0].rule if results else None
    return render(request, 'evaluation/allocation_run_detail.html', {
        'page_title': f'Run #{run.pk} — {run.period}',
        'page_subtitle': f'상태: {run.get_status_display()} · 결과 {len(results)}건',
        'run': run,
        'rule': rule,
        'rows': rows,
        'total_allocated': total_allocated,
    })


@require_POST
def allocation_run_commit(request, pk):
    run = get_object_or_404(AllocationRun, pk=pk)
    user = request.user if request.user.is_authenticated else None
    try:
        result = commit_allocation(run, user=user)
        messages.success(request, f'Run #{run.pk} 확정 완료 — CostEntry {result["created"]}건 생성')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('evaluation:allocation_run_detail', pk=run.pk)


@require_POST
def allocation_run_reverse(request, pk):
    run = get_object_or_404(AllocationRun, pk=pk)
    try:
        result = reverse_allocation(run)
        messages.success(request, f'Run #{run.pk} 취소 완료 — CostEntry {result["deleted"]}건 삭제')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('evaluation:allocation_run_detail', pk=run.pk)


@require_POST
def allocation_run_delete(request, pk):
    run = get_object_or_404(AllocationRun, pk=pk)
    if run.status == AllocationRun.Status.COMMITTED:
        messages.error(request, f'Run #{run.pk} 은 확정 상태라 삭제 불가 — 먼저 취소하세요.')
        return redirect('evaluation:allocation_run_detail', pk=run.pk)
    run.delete()
    messages.success(request, f'Run #{pk} 삭제 완료')
    return redirect('evaluation:allocation_runs')


def costing_ledger_allocate(request):
    """월 인건비 안분 실행"""
    result = None
    if request.method == 'POST':
        form = AllocateSalaryForm(request.POST)
        if form.is_valid():
            user = request.user if request.user.is_authenticated else None
            result = allocate_monthly_salary(
                form.cleaned_data['period'],
                reset=form.cleaned_data.get('reset', False),
                created_by=user,
            )
            messages.success(
                request,
                f"[{result['period']}] 안분 완료 — 생성 {result['created']}건 / "
                f"스킵 {result['skipped']}건 / 리셋삭제 {result['reset_deleted']}건"
            )
            from django.urls import reverse
            base = reverse('evaluation:costing_ledger')
            return HttpResponseRedirect(
                f"{base}?period_from={result['period']}&period_to={result['period']}&source=SALARY"
            )
    else:
        form = AllocateSalaryForm()
    return render(request, 'evaluation/costing_ledger_allocate.html', {
        'page_title': '월 인건비 안분',
        'page_subtitle': '원가/관리회계 / 원가 원장 / 인건비 자동 안분',
        'form': form,
        'result': result,
    })
