"""스트레스 테스트 엔진 — 금리/주가/변동성 쇼크를 재평가.

`compute()` 재사용 방식:
  쇼크 적용된 metrics_json + notional 을 들고 있는 proxy 객체를 만들어
  metrics.compute() 를 다시 호출 → stressed current_value 획득 → 대비 delta 계산.
"""
from dataclasses import dataclass
from typing import Dict, List

from . import metrics


# --- 시나리오 정의 ---------------------------------------------------

SCENARIOS: List[Dict] = [
    {
        'key': 'IR_UP_100',
        'label': '금리 +100bp',
        'desc': '전 구간 채권 수익률 1.0%p 상승',
        'shocks': {'interest_rate': 0.010},
        'tone': 'bad_for_bond',
    },
    {
        'key': 'IR_DOWN_50',
        'label': '금리 -50bp',
        'desc': '전 구간 채권 수익률 0.5%p 하락 (채권 가격 상승)',
        'shocks': {'interest_rate': -0.005},
        'tone': 'good_for_bond',
    },
    {
        'key': 'EQUITY_DOWN_20',
        'label': '주가 -20%',
        'desc': '전 종목 주가 20% 일시 하락',
        'shocks': {'equity': -0.20},
        'tone': 'bad_for_equity',
    },
    {
        'key': 'EQUITY_DOWN_10',
        'label': '주가 -10%',
        'desc': '전 종목 주가 10% 조정',
        'shocks': {'equity': -0.10},
        'tone': 'bad_for_equity',
    },
    {
        'key': 'VOL_UP_50',
        'label': '변동성 ×1.5',
        'desc': '모든 변동성 1.5배 확대 (VaR 증가)',
        'shocks': {'volatility': 1.5},
        'tone': 'bad_for_var',
    },
    {
        'key': 'VOL_UP_100',
        'label': '변동성 ×2.0',
        'desc': '모든 변동성 2배 (위기 수준)',
        'shocks': {'volatility': 2.0},
        'tone': 'bad_for_var',
    },
    {
        'key': 'CRISIS',
        'label': '복합 위기',
        'desc': '금리 +100bp + 주가 -20% + 변동성 ×1.5 동시',
        'shocks': {
            'interest_rate': 0.010,
            'equity': -0.20,
            'volatility': 1.5,
        },
        'tone': 'worst',
    },
]


@dataclass
class _StressedProduct:
    """compute() 가 kind/notional/book_value/metrics_json 만 참조하므로 dict-like proxy"""
    kind: str
    notional: float
    book_value: object
    metrics_json: dict

    def __str__(self):
        return f'Stressed<{self.kind}>'

    # compute() 내부 p.kind == 'STOCK' 등 비교에서 문자열과 동작해야 함
    # TextChoices 가 아닌 순수 str 로 복사했으므로 문제 없음.


def _apply_shocks(product, shocks: dict) -> _StressedProduct:
    """쇼크 dict 를 metrics_json 에 반영한 proxy 반환"""
    m = dict(product.metrics_json or {})

    ir = shocks.get('interest_rate', 0)
    eq = shocks.get('equity', 0)
    vol_mult = shocks.get('volatility')

    if product.kind == 'BOND' and ir != 0:
        m['ytm'] = float(m.get('ytm', 0.045)) + ir

    if product.kind == 'PROJECT' and ir != 0:
        m['discount_rate'] = float(m.get('discount_rate', 0.10)) + ir

    if product.kind == 'STOCK' and eq != 0:
        if m.get('current_price'):
            m['current_price'] = float(m['current_price']) * (1 + eq)

    if vol_mult is not None:
        if 'volatility' in m:
            m['volatility'] = float(m['volatility']) * vol_mult

    return _StressedProduct(
        kind=product.kind,
        notional=float(product.notional or 0),
        book_value=product.book_value,
        metrics_json=m,
    )


def run_scenario(products, scenario: dict) -> dict:
    """시나리오 1개를 전체 상품에 적용. products = iterable of FinancialProduct"""
    base_total = 0.0
    stressed_total = 0.0
    base_var = 0.0
    stressed_var = 0.0
    per_product = []

    for p in products:
        base = metrics.compute(p)
        stressed = metrics.compute(_apply_shocks(p, scenario['shocks']))

        b_val = float(base.get('current_value') or 0)
        s_val = float(stressed.get('current_value') or 0)
        b_var = float(base.get('metrics', {}).get('VaR(95%, 1d)') or 0)
        s_var = float(stressed.get('metrics', {}).get('VaR(95%, 1d)') or 0)

        base_total += b_val
        stressed_total += s_val
        base_var += b_var
        stressed_var += s_var

        per_product.append({
            'product': p,
            'base_value': b_val,
            'stressed_value': s_val,
            'delta': s_val - b_val,
            'delta_pct': ((s_val - b_val) / b_val * 100) if b_val else 0,
        })

    per_product.sort(key=lambda r: r['delta'])

    return {
        'key': scenario['key'],
        'label': scenario['label'],
        'desc': scenario['desc'],
        'tone': scenario['tone'],
        'shocks': scenario['shocks'],
        'base_total': base_total,
        'stressed_total': stressed_total,
        'delta': stressed_total - base_total,
        'delta_pct': ((stressed_total - base_total) / base_total * 100) if base_total else 0,
        'base_var': base_var,
        'stressed_var': stressed_var,
        'var_delta': stressed_var - base_var,
        'per_product': per_product,
    }


def run_all(products, scenarios=None) -> list:
    """전체 시나리오 실행"""
    scenarios = scenarios or SCENARIOS
    products = list(products)
    return [run_scenario(products, s) for s in scenarios]
