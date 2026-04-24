"""금융상품 평가 시드 — 포트폴리오 3개 × 상품 8~12개 + 365일 시세 히스토리

주식: Geometric Brownian Motion
채권: YTM Ornstein-Uhlenbeck (mean-reverting) + bond_price 재계산
파생: 명목가 GBM + 변동성 워크
프로젝트: 시세 없음 (할인율만 기록)
"""
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.evaluation.metrics import bond_price
from apps.evaluation.models import FinancialProduct, PriceHistory, Portfolio


PORTFOLIOS = [
    {
        'name': '보장성 운용 포트폴리오',
        'base_currency': 'KRW',
        'weight_limit_pct': 30,
        'products': [
            ('BOND_KTB_2028', '국고채 2028년물', 'BOND',  1_500_000_000, {
                'coupon_rate': 0.0325, 'ytm_base': 0.035, 'maturity_years': 4,
                'par': 10_000, 'ytm_vol': 0.012,
            }),
            ('BOND_KTB_2030', '국고채 2030년물', 'BOND',  1_000_000_000, {
                'coupon_rate': 0.045, 'ytm_base': 0.041, 'maturity_years': 6,
                'par': 10_000, 'ytm_vol': 0.015,
            }),
            ('BOND_KTB_2035', '국고채 2035년물', 'BOND',  800_000_000, {
                'coupon_rate': 0.048, 'ytm_base': 0.044, 'maturity_years': 11,
                'par': 10_000, 'ytm_vol': 0.018,
            }),
            ('BOND_SK_030', 'SK 회사채 3년', 'BOND',  500_000_000, {
                'coupon_rate': 0.058, 'ytm_base': 0.055, 'maturity_years': 3,
                'par': 10_000, 'ytm_vol': 0.020,
            }),
            ('BOND_KT_050', 'KT 회사채 5년', 'BOND',  400_000_000, {
                'coupon_rate': 0.052, 'ytm_base': 0.050, 'maturity_years': 5,
                'par': 10_000, 'ytm_vol': 0.018,
            }),
            ('BOND_LOCAL', '지방채(서울) 5년', 'BOND',  300_000_000, {
                'coupon_rate': 0.044, 'ytm_base': 0.043, 'maturity_years': 5,
                'par': 10_000, 'ytm_vol': 0.012,
            }),
            ('STK_005930', '삼성전자', 'STOCK',  600_000_000, {
                'base_price': 72000, 'shares': 8000, 'mu': 0.08, 'sigma': 0.27,
            }),
            ('STK_000660', 'SK하이닉스', 'STOCK',  300_000_000, {
                'base_price': 185000, 'shares': 1600, 'mu': 0.12, 'sigma': 0.38,
            }),
            ('STK_105560', 'KB금융', 'STOCK',  200_000_000, {
                'base_price': 82000, 'shares': 2400, 'mu': 0.06, 'sigma': 0.24,
            }),
            ('STK_005380', '현대차', 'STOCK',  250_000_000, {
                'base_price': 245000, 'shares': 1000, 'mu': 0.07, 'sigma': 0.26,
            }),
            ('PRJ_SOLAR_A', '태양광 발전 A단지', 'PROJECT', 1_500_000_000, {
                'discount_rate': 0.08,
                'cashflows': [-1_500_000_000, 400_000_000, 500_000_000, 500_000_000, 500_000_000],
            }),
        ],
    },
    {
        'name': '성장주 포트폴리오',
        'base_currency': 'KRW',
        'weight_limit_pct': 25,
        'products': [
            ('STK_035420', 'NAVER', 'STOCK',  300_000_000, {
                'base_price': 198000, 'shares': 1500, 'mu': 0.10, 'sigma': 0.34,
            }),
            ('STK_035720', '카카오', 'STOCK',  200_000_000, {
                'base_price': 54000, 'shares': 3700, 'mu': 0.08, 'sigma': 0.42,
            }),
            ('STK_006400', '삼성SDI', 'STOCK',  250_000_000, {
                'base_price': 410000, 'shares': 600, 'mu': 0.11, 'sigma': 0.36,
            }),
            ('STK_051910', 'LG화학', 'STOCK',  200_000_000, {
                'base_price': 380000, 'shares': 530, 'mu': 0.09, 'sigma': 0.32,
            }),
            ('STK_US_TSLA', 'Tesla', 'STOCK',  150_000_000, {
                'base_price': 240, 'shares': 480, 'mu': 0.15, 'sigma': 0.55,
            }),
            ('STK_US_NVDA', 'NVIDIA', 'STOCK',  300_000_000, {
                'base_price': 680, 'shares': 330, 'mu': 0.25, 'sigma': 0.48,
            }),
            ('STK_US_AAPL', 'Apple Inc.', 'STOCK',  400_000_000, {
                'base_price': 195, 'shares': 1500, 'mu': 0.12, 'sigma': 0.25,
            }),
            ('DRV_KOSPI200', 'KOSPI200 선물', 'DERIV',  200_000_000, {
                'base_price': 100, 'vol_base': 0.22, 'leverage': 5,
            }),
            ('DRV_NQ_LEV', '나스닥 레버리지 ETN', 'DERIV',  150_000_000, {
                'base_price': 100, 'vol_base': 0.45, 'leverage': 2,
            }),
            ('DRV_SPY_INV', 'S&P500 인버스 ETF', 'DERIV',  100_000_000, {
                'base_price': 100, 'vol_base': 0.20, 'leverage': 1,
            }),
        ],
    },
    {
        'name': '대체투자 포트폴리오',
        'base_currency': 'KRW',
        'weight_limit_pct': 35,
        'products': [
            ('PRJ_SOLAR_B', '태양광 발전 B단지', 'PROJECT',  2_000_000_000, {
                'discount_rate': 0.09,
                'cashflows': [-2_000_000_000, 450_000_000, 550_000_000, 650_000_000, 700_000_000, 700_000_000],
            }),
            ('PRJ_WIND_OFF', '해상풍력 1단계', 'PROJECT',  3_500_000_000, {
                'discount_rate': 0.10,
                'cashflows': [-3_500_000_000, 600_000_000, 800_000_000, 1_000_000_000, 1_200_000_000, 1_200_000_000],
            }),
            ('PRJ_DC_ANSAN', '안산 데이터센터', 'PROJECT',  2_500_000_000, {
                'discount_rate': 0.085,
                'cashflows': [-2_500_000_000, 500_000_000, 600_000_000, 700_000_000, 800_000_000, 800_000_000],
            }),
            ('PRJ_LOGISTICS', '이천 물류센터', 'PROJECT',  1_200_000_000, {
                'discount_rate': 0.075,
                'cashflows': [-1_200_000_000, 280_000_000, 300_000_000, 320_000_000, 340_000_000, 360_000_000],
            }),
            ('BOND_HY_1', '하이일드 회사채', 'BOND',  400_000_000, {
                'coupon_rate': 0.085, 'ytm_base': 0.082, 'maturity_years': 4,
                'par': 10_000, 'ytm_vol': 0.030,
            }),
            ('BOND_US_TR', '미국채 10Y', 'BOND',  800_000_000, {
                'coupon_rate': 0.042, 'ytm_base': 0.040, 'maturity_years': 10,
                'par': 10_000, 'ytm_vol': 0.020,
            }),
            ('DRV_FX_HEDGE', 'USD/KRW FX 헤지', 'DERIV',  500_000_000, {
                'base_price': 1350, 'vol_base': 0.10, 'leverage': 1,
            }),
            ('DRV_GOLD_FUT', '금 선물', 'DERIV',  300_000_000, {
                'base_price': 2400, 'vol_base': 0.18, 'leverage': 2,
            }),
        ],
    },
]


class Command(BaseCommand):
    help = '금융상품 평가 시드 — 3 포트폴리오 × ~30상품 + 시세 히스토리'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=365, help='히스토리 일수 (기본 365)')
        parser.add_argument('--reset', action='store_true', help='기존 포트폴리오 전부 삭제 후 재생성')

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        days = opts['days']

        if opts['reset']:
            PriceHistory.objects.all().delete()
            FinancialProduct.objects.all().delete()
            Portfolio.objects.all().delete()
            self.stdout.write(self.style.WARNING('기존 포트폴리오/상품/시세 전부 삭제'))

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        pf_count = 0
        p_count = 0
        for pf_data in PORTFOLIOS:
            pf, pf_new = Portfolio.objects.get_or_create(
                name=pf_data['name'],
                defaults={
                    'base_currency': pf_data['base_currency'],
                    'weight_limit_pct': pf_data['weight_limit_pct'],
                },
            )
            if pf_new:
                pf_count += 1
            for (code, name, kind, notional, params) in pf_data['products']:
                initial_metrics = self._initial_metrics(kind, params)
                p, p_new = FinancialProduct.objects.get_or_create(
                    portfolio=pf, code=code,
                    defaults={
                        'name': name, 'kind': kind,
                        'notional': Decimal(notional),
                        'metrics_json': initial_metrics,
                    },
                )
                if p_new:
                    p_count += 1
                # 기존 시세 삭제 후 재생성 (재실행 가능)
                PriceHistory.objects.filter(product=p).delete()
                self._generate_history(p, params, start_date, days)

        total = PriceHistory.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'완료: 포트폴리오 {Portfolio.objects.count()}개 '
            f'(신규 {pf_count}), 상품 {FinancialProduct.objects.count()}개 '
            f'(신규 {p_count}), 시세 {total:,}건'
        ))

    def _initial_metrics(self, kind, params):
        """최초 metrics_json — 시세 생성 후 current 값으로 덮어씌워짐"""
        if kind == 'STOCK':
            return {
                'current_price': params['base_price'],
                'shares': params['shares'],
                'volatility': params['sigma'],
            }
        if kind == 'BOND':
            return {
                'coupon_rate': params['coupon_rate'],
                'ytm': params['ytm_base'],
                'maturity_years': params['maturity_years'],
                'par': params['par'],
            }
        if kind == 'DERIV':
            return {
                'volatility': params['vol_base'],
                'leverage': params['leverage'],
            }
        if kind == 'PROJECT':
            return {
                'discount_rate': params['discount_rate'],
                'cashflows': params['cashflows'],
            }
        return {}

    def _generate_history(self, product, params, start_date, days):
        kind = product.kind
        bulk = []

        if kind == 'STOCK':
            mu = params['mu']
            sigma = params['sigma']
            price = params['base_price']
            returns = []
            dt = 1 / 252

            for i in range(days + 1):
                d = start_date + timedelta(days=i)
                if i > 0:
                    z = random.gauss(0, 1)
                    ret = (mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z
                    price = price * math.exp(ret)
                    returns.append(ret)
                window = returns[-20:]
                if len(window) >= 5:
                    mean = sum(window) / len(window)
                    var = sum((r - mean) ** 2 for r in window) / max(1, len(window) - 1)
                    vol = math.sqrt(var) * math.sqrt(252)
                else:
                    vol = sigma
                bulk.append(PriceHistory(
                    product=product, date=d,
                    price=Decimal(str(round(price, 4))),
                    volatility=Decimal(str(round(vol, 6))),
                ))
            # 현재값 반영
            product.metrics_json['current_price'] = round(price, 2)
            product.metrics_json['volatility'] = round(float(bulk[-1].volatility), 4)
            product.save(update_fields=['metrics_json'])

        elif kind == 'BOND':
            par = params['par']
            coupon = params['coupon_rate']
            maturity = params['maturity_years']
            ytm_base = params['ytm_base']
            ytm_vol = params['ytm_vol']
            ytm = ytm_base
            theta = 0.5  # OU mean-reversion speed
            dt = 1 / 252

            for i in range(days + 1):
                d = start_date + timedelta(days=i)
                if i > 0:
                    z = random.gauss(0, 1)
                    ytm = max(0.001, ytm + theta * (ytm_base - ytm) * dt + ytm_vol * math.sqrt(dt) * z)
                remaining = max(0.1, maturity - i / 365.0)
                try:
                    price = bond_price(par, coupon, ytm, remaining)
                except Exception:
                    price = par
                bulk.append(PriceHistory(
                    product=product, date=d,
                    price=Decimal(str(round(price, 4))),
                    yield_rate=Decimal(str(round(ytm, 6))),
                ))
            product.metrics_json['ytm'] = round(ytm, 6)
            product.save(update_fields=['metrics_json'])

        elif kind == 'DERIV':
            vol_base = params['vol_base']
            vol_vol = 0.50
            cur_vol = vol_base
            price = params['base_price']
            price_mu = 0.05
            theta_v = 2.0
            dt = 1 / 252

            for i in range(days + 1):
                d = start_date + timedelta(days=i)
                if i > 0:
                    z1 = random.gauss(0, 1)
                    z2 = random.gauss(0, 1)
                    cur_vol = max(0.03, cur_vol + theta_v * (vol_base - cur_vol) * dt + vol_vol * math.sqrt(dt) * z1)
                    price = price * math.exp((price_mu - 0.5 * cur_vol**2) * dt + cur_vol * math.sqrt(dt) * z2)
                bulk.append(PriceHistory(
                    product=product, date=d,
                    price=Decimal(str(round(price, 4))),
                    volatility=Decimal(str(round(cur_vol, 6))),
                ))
            product.metrics_json['volatility'] = round(cur_vol, 4)
            product.save(update_fields=['metrics_json'])

        elif kind == 'PROJECT':
            # 프로젝트 — 시세 없음, 할인율만 천천히 움직임
            disc_base = params['discount_rate']
            disc = disc_base
            for i in range(days + 1):
                d = start_date + timedelta(days=i)
                if i > 0:
                    z = random.gauss(0, 1) * 0.002
                    disc = max(0.01, disc + 0.5 * (disc_base - disc) * (1/252) + z * math.sqrt(1/252))
                bulk.append(PriceHistory(
                    product=product, date=d,
                    price=None,
                    yield_rate=Decimal(str(round(disc, 6))),
                ))
            product.metrics_json['discount_rate'] = round(disc, 6)
            product.save(update_fields=['metrics_json'])

        PriceHistory.objects.bulk_create(bulk, batch_size=500)
