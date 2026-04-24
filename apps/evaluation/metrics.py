"""금융상품 평가 지표 — 순수 Python 구현."""
from math import sqrt

Z_95 = 1.6449  # 95% one-tail z


# ---------- 기초 함수 ----------

def npv(cashflows, discount_rate):
    return sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, tol=1e-6, max_iter=100):
    if not cashflows or all(cf >= 0 for cf in cashflows) or all(cf <= 0 for cf in cashflows):
        return None
    lo, hi = -0.999, 10.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        v = npv(cashflows, mid)
        if abs(v) < tol:
            return mid
        if npv(cashflows, lo) * v < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def bond_cashflows(par, coupon_rate, maturity_years, freq=1):
    n = int(maturity_years * freq)
    coupon = par * coupon_rate / freq
    return [0.0] + [coupon] * (n - 1) + [coupon + par]


def bond_price(par, coupon_rate, ytm, maturity_years, freq=1):
    n = int(maturity_years * freq)
    y = ytm / freq
    coupon = par * coupon_rate / freq
    pv = sum(coupon / (1 + y) ** t for t in range(1, n + 1))
    pv += par / (1 + y) ** n
    return pv


def macaulay_duration(par, coupon_rate, ytm, maturity_years, freq=1):
    n = int(maturity_years * freq)
    y = ytm / freq
    coupon = par * coupon_rate / freq
    price = bond_price(par, coupon_rate, ytm, maturity_years, freq)
    if price == 0:
        return 0.0
    weighted = sum(t * (coupon / (1 + y) ** t) for t in range(1, n + 1))
    weighted += n * (par / (1 + y) ** n)
    return (weighted / price) / freq


def convexity(par, coupon_rate, ytm, maturity_years, freq=1):
    n = int(maturity_years * freq)
    y = ytm / freq
    coupon = par * coupon_rate / freq
    price = bond_price(par, coupon_rate, ytm, maturity_years, freq)
    if price == 0:
        return 0.0
    s = sum(t * (t + 1) * (coupon / (1 + y) ** t) for t in range(1, n + 1))
    s += n * (n + 1) * (par / (1 + y) ** n)
    return s / (price * (1 + y) ** 2 * freq * freq)


def parametric_var(notional, sigma_annual, holding_days=1, confidence_z=Z_95):
    sigma_holding = sigma_annual * sqrt(holding_days / 252)
    return notional * sigma_holding * confidence_z


def historical_var_rate(prices, confidence=0.95, holding_days=1):
    """가격 시계열 → 과거 수익률 분포의 (1-conf) 분위수 절대값 = 손실률.

    prices: 오래된 → 최근 순서의 float/Decimal 리스트
    반환: 0.0~1.0 (예: 0.025 = 2.5% 손실)
    """
    from math import log
    ps = [float(p) for p in prices if p is not None and float(p) > 0]
    if len(ps) < 30:
        return None
    rets = [log(ps[i] / ps[i - 1]) for i in range(1, len(ps))]
    rets.sort()
    idx = max(0, min(len(rets) - 1, int(len(rets) * (1 - confidence))))
    q = rets[idx]  # 5% 분위수 (가장 음수)
    rate = -q * sqrt(holding_days)
    return max(0.0, rate)


# ---------- per-kind compute ----------

def compute(product):
    """반환 dict 키:
    - 'metrics': 사용자 표시용 {라벨: 값} (VaR, Duration 등)
    - 'current_value': 현재 평가액 (float, 포트폴리오 기준 통화)
    - 'inputs': 계산 입력값 dict (상세 페이지에서 사용)
    - 'trace': 계산 근거 텍스트 리스트 (상세 페이지에서 사용)
    """
    p = product
    notional = float(p.notional or 0)
    m = p.metrics_json or {}

    if p.kind == 'STOCK':
        sigma = float(m.get('volatility', 0.30))
        current_price = m.get('current_price')
        shares = m.get('shares')
        returns = m.get('returns') or []

        if current_price is not None and shares is not None:
            current_value = float(current_price) * float(shares)
        else:
            current_value = notional

        var = parametric_var(current_value, sigma)
        return {
            'metrics': {
                '평가액': current_value,
                'VaR(95%, 1d)': var,
                '연 변동성': sigma,
            },
            'current_value': current_value,
            'inputs': {
                '현재가': current_price,
                '보유수량': shares,
                '연 변동성(σ)': sigma,
                '수익률 시계열 개수': len(returns),
                '신뢰수준 z': Z_95,
                '보유기간(일)': 1,
            },
            'trace': [
                f'평가액 = 현재가 × 수량 = {current_price} × {shares} = {current_value:,.0f}'
                if current_price is not None and shares is not None
                else f'평가액 = notional = {current_value:,.0f}',
                f'σ_1d = σ_연 × √(1/252) = {sigma:.4f} × {sqrt(1/252):.4f} = {sigma * sqrt(1/252):.4f}',
                f'VaR = 평가액 × σ_1d × z = {current_value:,.0f} × {sigma * sqrt(1/252):.4f} × {Z_95:.4f} = {var:,.0f}',
            ],
            'returns': returns,
        }

    if p.kind == 'BOND':
        coupon_rate = float(m.get('coupon_rate', 0.04))
        ytm = float(m.get('ytm', 0.045))
        maturity = float(m.get('maturity_years', 5))
        par = float(m.get('par', 10_000))
        maturity_date = m.get('maturity_date')

        price_per_par = bond_price(par, coupon_rate, ytm, maturity)
        dur = macaulay_duration(par, coupon_rate, ytm, maturity)
        cvx = convexity(par, coupon_rate, ytm, maturity)
        # 포지션 전체 평가액 — notional은 보유 par 기준으로 해석
        scale = (notional / par) if par else 1
        current_value = price_per_par * scale
        book = float(p.book_value or 0) or (par * scale)
        npv_val = current_value - book

        cfs = bond_cashflows(par, coupon_rate, maturity)
        trace = [f't=0 (현재)']
        for t in range(1, int(maturity) + 1):
            cf = cfs[t]
            pv = cf / (1 + ytm) ** t
            trace.append(f't={t}: CF={cf:,.0f}, PV = {cf:,.0f}/(1+{ytm})^{t} = {pv:,.2f}')
        trace.append(f'가격(par={par:,.0f} 기준) = Σ PV = {price_per_par:,.2f}')
        trace.append(f'평가액(포지션) = 가격 × (notional/par) = {price_per_par:,.2f} × {scale:.4f} = {current_value:,.0f}')

        return {
            'metrics': {
                '평가액': current_value,
                '가격(par)': price_per_par,
                'Duration(년)': dur,
                'Convexity': cvx,
            },
            'current_value': current_value,
            'inputs': {
                '액면가(par)': par,
                '쿠폰금리': coupon_rate,
                '만기(년)': maturity,
                '만기일': maturity_date,
                '할인율(YTM)': ytm,
                '보유 par(=notional)': notional,
            },
            'cashflows': cfs,
            'trace': trace,
        }

    if p.kind == 'DERIV':
        sigma = float(m.get('volatility', 0.45))
        leverage = float(m.get('leverage', 3))
        exposure = notional * leverage
        var = parametric_var(exposure, sigma)
        current_value = notional
        return {
            'metrics': {
                '평가액': current_value,
                'VaR(95%, 1d)': var,
                '레버리지': leverage,
                '연 변동성': sigma,
            },
            'current_value': current_value,
            'inputs': {
                '명목금액': notional,
                '레버리지': leverage,
                '실효 노출액': exposure,
                '연 변동성': sigma,
            },
            'trace': [
                f'실효 노출액 = notional × 레버리지 = {notional:,.0f} × {leverage} = {exposure:,.0f}',
                f'VaR = 노출액 × σ × √(1/252) × z = {var:,.0f}',
            ],
        }

    if p.kind == 'PROJECT':
        cfs_raw = m.get('cashflows') or [-notional, notional * 0.3, notional * 0.4, notional * 0.5]
        cfs = [float(x) for x in cfs_raw]
        discount = float(m.get('discount_rate', 0.10))
        npv_val = npv(cfs, discount)
        irr_val = irr(cfs)
        # 현재 평가액 = 남은 현금흐름의 PV (t=1부터)
        remaining_pv = sum(cf / (1 + discount) ** t for t, cf in enumerate(cfs) if t > 0)
        trace = []
        for t, cf in enumerate(cfs):
            pv = cf / (1 + discount) ** t
            trace.append(f't={t}: CF={cf:,.0f}, PV = {cf:,.0f}/(1+{discount})^{t} = {pv:,.2f}')
        trace.append(f'NPV = Σ PV = {npv_val:,.0f}')
        trace.append(f'IRR: NPV=0 인 할인율 = {irr_val:.4%}' if irr_val is not None else 'IRR: 수렴 실패')
        return {
            'metrics': {
                '평가액(남은 PV)': remaining_pv,
                'NPV': npv_val,
                'IRR': irr_val,
                '할인율': discount,
            },
            'current_value': remaining_pv,
            'inputs': {
                '현금흐름': cfs,
                '할인율': discount,
                'N(연차)': len(cfs) - 1,
            },
            'cashflows': cfs,
            'trace': trace,
        }

    return {
        'metrics': {},
        'current_value': notional,
        'inputs': {},
        'trace': [],
    }


# ---------- portfolio aggregate ----------

def aggregate(products, weight_limit_pct=40):
    """per_product: [{'product','metrics','current_value','book_value','pnl','weight_pct','over_limit'}]"""
    computed = []
    total_current_value = 0.0
    total_notional = 0.0
    total_var = 0.0
    bond_durations = []

    for p in products:
        c = compute(p)
        cv = float(c.get('current_value') or 0)
        total_current_value += cv
        total_notional += float(p.notional or 0)

        mvar = c['metrics'].get('VaR(95%, 1d)')
        if mvar is not None:
            total_var += float(mvar)
        mdur = c['metrics'].get('Duration(년)')
        if mdur is not None:
            bond_durations.append(float(mdur))

        computed.append((p, c))

    per_product = []
    total_pnl = 0.0
    over_limit_count = 0
    for p, c in computed:
        cv = float(c.get('current_value') or 0)
        book = float(p.book_value or 0) if p.book_value is not None else 0.0
        pnl = cv - book if p.book_value is not None else None
        weight = (cv / total_current_value * 100) if total_current_value else 0.0
        over = weight > float(weight_limit_pct)
        if pnl is not None:
            total_pnl += pnl
        if over:
            over_limit_count += 1
        per_product.append({
            'product': p,
            'metrics': c['metrics'],
            'current_value': cv,
            'book_value': book if p.book_value is not None else None,
            'pnl': pnl,
            'weight_pct': weight,
            'over_limit': over,
        })

    return {
        'total_notional': total_notional,
        'total_current_value': total_current_value,
        'total_var': total_var,
        'total_pnl': total_pnl,
        'avg_duration': (sum(bond_durations) / len(bond_durations)) if bond_durations else None,
        'count': len(products),
        'per_product': per_product,
        'over_limit_count': over_limit_count,
        'weight_limit_pct': float(weight_limit_pct),
    }
