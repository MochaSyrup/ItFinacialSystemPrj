from collections import Counter

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import metrics
from .forms import KIND_HINTS, FinancialProductForm, PortfolioForm
from .models import FinancialProduct, Portfolio


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
