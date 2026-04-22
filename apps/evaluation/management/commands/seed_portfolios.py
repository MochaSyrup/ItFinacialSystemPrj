from django.core.management.base import BaseCommand

from apps.evaluation.models import FinancialProduct, Portfolio


SEED = [
    {
        'name': '보장성 운용 포트폴리오',
        'base_currency': 'KRW',
        'products': [
            {'code': 'STK_SEC_005930', 'name': '삼성전자 보통주', 'kind': 'STOCK',
             'notional': 500_000_000, 'metrics_json': {'volatility': 0.28}},
            {'code': 'BOND_KTB_2030',  'name': '국고채 2030년물',  'kind': 'BOND',
             'notional': 1_000_000_000, 'metrics_json': {
                 'coupon_rate': 0.045, 'ytm': 0.041, 'maturity_years': 6, 'par': 10_000
             }},
            {'code': 'DRV_KOSPI200',   'name': '코스피200 선물',    'kind': 'DERIV',
             'notional': 200_000_000, 'metrics_json': {'volatility': 0.42, 'leverage': 3}},
        ],
    },
    {
        'name': '장기 프로젝트 포트폴리오',
        'base_currency': 'KRW',
        'products': [
            {'code': 'PRJ_SOLAR_A',    'name': '태양광 발전 A단지', 'kind': 'PROJECT',
             'notional': 1_500_000_000, 'metrics_json': {
                 'discount_rate': 0.08,
                 'cashflows': [-1_500_000_000, 400_000_000, 500_000_000, 500_000_000, 500_000_000],
             }},
            {'code': 'BOND_CORP_SK',   'name': 'SK 회사채 3년',     'kind': 'BOND',
             'notional': 300_000_000, 'metrics_json': {
                 'coupon_rate': 0.058, 'ytm': 0.055, 'maturity_years': 3, 'par': 10_000
             }},
            {'code': 'STK_USD_AAPL',   'name': 'Apple Inc. 보통주', 'kind': 'STOCK',
             'notional': 400_000_000, 'metrics_json': {'volatility': 0.25}},
        ],
    },
]


class Command(BaseCommand):
    help = '금융상품 평가 시드 데이터 (포트폴리오 2개 + 혼합 상품)'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='기존 포트폴리오/상품 전부 삭제 후 재생성')

    def handle(self, *args, **opts):
        if opts['reset']:
            FinancialProduct.objects.all().delete()
            Portfolio.objects.all().delete()
            self.stdout.write(self.style.WARNING('기존 데이터 삭제 완료'))

        created_pf = 0
        created_p = 0
        for pf_data in SEED:
            pf, was_new = Portfolio.objects.get_or_create(
                name=pf_data['name'],
                defaults={'base_currency': pf_data['base_currency']},
            )
            if was_new:
                created_pf += 1
            for p in pf_data['products']:
                _, p_new = FinancialProduct.objects.get_or_create(
                    portfolio=pf, code=p['code'],
                    defaults={
                        'name': p['name'], 'kind': p['kind'],
                        'notional': p['notional'], 'metrics_json': p['metrics_json'],
                    },
                )
                if p_new:
                    created_p += 1

        self.stdout.write(self.style.SUCCESS(
            f'완료: 포트폴리오 {created_pf}개, 상품 {created_p}개 신규 생성'
        ))
