"""회계 기간 마감 + CostEntry immutable 테스트"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .costing import close_period, reopen_period
from .models import (
    CostCategory,
    CostEntry,
    Division,
    Department,
    FiscalPeriod,
    ImmutableEntryError,
    PeriodClosedError,
    RevenueEntry,
)


def _master():
    div = Division.objects.create(code='D001', name='본부1')
    dept = Department.objects.create(division=div, code='DPT-01', name='부서1')
    cat = CostCategory.objects.create(code='LABOR', name='인건비')
    return div, dept, cat


class FiscalPeriodCloseReopenTests(TestCase):
    def test_close_then_reopen(self):
        close_period('2026-04', note='Q1 마감')
        self.assertTrue(FiscalPeriod.objects.get(period='2026-04').is_closed)
        reopen_period('2026-04', note='보정 필요')
        self.assertFalse(FiscalPeriod.objects.get(period='2026-04').is_closed)


class CostEntryImmutableTests(TestCase):
    def setUp(self):
        self.div, self.dept, self.cat = _master()

    def _create(self, period='2026-04', amount=100):
        return CostEntry.objects.create(
            period=period, entry_date=date(2026, 4, 15),
            category=self.cat, amount=Decimal(amount),
            division=self.div, department=self.dept,
        )

    def test_create_on_open_period_ok(self):
        ce = self._create()
        self.assertEqual(ce.amount, Decimal('100'))

    def test_update_existing_entry_blocked(self):
        ce = self._create()
        ce.amount = Decimal('999')
        with self.assertRaises(ImmutableEntryError):
            ce.save()

    def test_create_on_closed_period_blocked(self):
        close_period('2026-04')
        with self.assertRaises(PeriodClosedError):
            self._create(period='2026-04')

    def test_delete_on_closed_period_blocked(self):
        ce = self._create(period='2026-03')
        close_period('2026-03')
        with self.assertRaises(PeriodClosedError):
            ce.delete()

    def test_reopen_unblocks_writes(self):
        close_period('2026-03')
        with self.assertRaises(PeriodClosedError):
            self._create(period='2026-03')
        reopen_period('2026-03')
        ce = self._create(period='2026-03', amount=200)
        self.assertIsNotNone(ce.pk)

    def test_seed_skip_period_check_bypass(self):
        """_skip_period_check=True 로 시드/마이그레이션 경로에서 우회 가능"""
        close_period('2026-01')
        ce = CostEntry(
            period='2026-01', entry_date=date(2026, 1, 15),
            category=self.cat, amount=Decimal('50'),
            division=self.div, department=self.dept,
        )
        ce.save(_skip_period_check=True)
        self.assertIsNotNone(ce.pk)


class RevenueEntryPeriodGuardTests(TestCase):
    def setUp(self):
        self.div, self.dept, self.cat = _master()

    def test_revenue_create_blocked_on_closed_period(self):
        close_period('2026-02')
        re = RevenueEntry(
            period='2026-02', entry_date=date(2026, 2, 15),
            amount=Decimal('1000'), division=self.div, department=self.dept,
        )
        with self.assertRaises(PeriodClosedError):
            re.save()


class PeriodMgmtViewsTests(TestCase):
    def setUp(self):
        self.div, self.dept, self.cat = _master()
        CostEntry.objects.create(
            period='2026-03', entry_date=date(2026, 3, 15),
            category=self.cat, amount=Decimal('500'),
            division=self.div, department=self.dept,
        )

    def test_periods_list_includes_ledger_periods(self):
        resp = self.client.get(reverse('evaluation:costing_periods'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '2026-03')
        self.assertContains(resp, 'OPEN')

    def test_close_view_locks_period(self):
        resp = self.client.post(
            reverse('evaluation:costing_period_close', args=['2026-03']),
            data={'note': '분기 마감'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(FiscalPeriod.objects.get(period='2026-03').is_closed)

    def test_reopen_view_unlocks_period(self):
        close_period('2026-03')
        resp = self.client.post(
            reverse('evaluation:costing_period_reopen', args=['2026-03']),
            data={'note': '수정'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(FiscalPeriod.objects.get(period='2026-03').is_closed)


class AllocationPeriodGuardTests(TestCase):
    """commit/reverse 가 마감된 기간에서 차단되는지"""

    def setUp(self):
        from .models import AllocationRule, AllocationRun
        self.div, self.dept, self.cat = _master()
        self.rule = AllocationRule.objects.create(
            code='RULE-X', name='X',
            source_category=self.cat, source_department=self.dept,
            driver_type='EQUAL', target_dimension='DEPARTMENT',
            effective_from=date(2026, 1, 1),
        )
        self.run = AllocationRun.objects.create(
            period='2026-04', status='SIMULATED', total_amount=Decimal('1000'),
        )

    def test_commit_blocked_on_closed_period(self):
        from .costing import commit_allocation
        close_period('2026-04')
        with self.assertRaises(PeriodClosedError):
            commit_allocation(self.run)


class CeleryEvaluationTaskTests(TestCase):
    """allocate_salary_for_period / refresh_market_data 동작 확인"""

    def setUp(self):
        from .models import Portfolio, FinancialProduct, PriceHistory
        self.div, self.dept, self.cat = _master()
        self.pf = Portfolio.objects.create(name='PF1')
        self.product = FinancialProduct.objects.create(
            portfolio=self.pf, code='S001', name='주식1', kind='STOCK',
            notional=Decimal('1000000'), metrics_json={'volatility': 0.3},
        )
        # 어제까지 시세 1건
        from datetime import timedelta
        from django.utils import timezone
        yesterday = timezone.localdate() - timedelta(days=1)
        PriceHistory.objects.create(
            product=self.product, date=yesterday,
            price=Decimal('100.000000'), volatility=Decimal('0.300000'),
        )

    def test_refresh_market_data_adds_one_row_per_product(self):
        from apps.evaluation.tasks import refresh_market_data
        from django.utils import timezone
        result = refresh_market_data.run()
        self.assertEqual(result['added'], 1)
        self.assertEqual(self.product.prices.count(), 2)
        latest = self.product.prices.order_by('-date').first()
        self.assertEqual(latest.date, timezone.localdate())

    def test_refresh_market_data_idempotent_same_day(self):
        from apps.evaluation.tasks import refresh_market_data
        refresh_market_data.run()
        result2 = refresh_market_data.run()
        self.assertEqual(result2['added'], 0)

    def test_allocate_salary_for_period_skipped_on_closed_period(self):
        from apps.evaluation.tasks import allocate_salary_for_period
        close_period('2026-04')
        result = allocate_salary_for_period.run('2026-04')
        self.assertTrue(result.get('skipped'))


# ============================================================
# metrics.py — 평가 지표 정확성
# ============================================================

class MetricsBasicTests(TestCase):
    def test_npv_zero_when_rate_zero_sums(self):
        from .metrics import npv
        # discount=0 이면 단순 합
        self.assertAlmostEqual(npv([-100, 50, 50, 50], 0.0), 50.0)

    def test_npv_decreases_with_higher_rate(self):
        from .metrics import npv
        cfs = [-100, 50, 50, 50]
        self.assertGreater(npv(cfs, 0.05), npv(cfs, 0.20))

    def test_irr_recovers_known_rate(self):
        from .metrics import irr, npv
        # NPV(r) = 0 인 r 을 찾는지 (정확한 값보다 NPV 수렴이 본질)
        cfs = [-1000, 400, 400, 400]
        r = irr(cfs)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(npv(cfs, r), 0.0, places=2)
        # 대략 9~10% 사이
        self.assertGreater(r, 0.09)
        self.assertLess(r, 0.10)

    def test_irr_returns_none_on_all_positive(self):
        from .metrics import irr
        self.assertIsNone(irr([100, 100, 100]))

    def test_bond_price_at_par_when_ytm_equals_coupon(self):
        from .metrics import bond_price
        # YTM = 쿠폰금리 → 가격 = par
        price = bond_price(par=10000, coupon_rate=0.05, ytm=0.05, maturity_years=5)
        self.assertAlmostEqual(price, 10000.0, places=2)

    def test_bond_price_below_par_when_ytm_above_coupon(self):
        from .metrics import bond_price
        # YTM > 쿠폰 → 할인채
        price = bond_price(par=10000, coupon_rate=0.04, ytm=0.06, maturity_years=5)
        self.assertLess(price, 10000)

    def test_duration_less_than_maturity_for_coupon_bond(self):
        from .metrics import macaulay_duration
        # 쿠폰 있는 채권의 듀레이션 < 만기
        d = macaulay_duration(par=10000, coupon_rate=0.05, ytm=0.05, maturity_years=5)
        self.assertLess(d, 5.0)
        self.assertGreater(d, 4.0)

    def test_convexity_positive_for_normal_bond(self):
        from .metrics import convexity
        c = convexity(par=10000, coupon_rate=0.05, ytm=0.05, maturity_years=5)
        self.assertGreater(c, 0)

    def test_parametric_var_scales_with_holding_period(self):
        from .metrics import parametric_var
        v1 = parametric_var(notional=1_000_000, sigma_annual=0.30, holding_days=1)
        v10 = parametric_var(notional=1_000_000, sigma_annual=0.30, holding_days=10)
        # √10 배 증가
        self.assertAlmostEqual(v10 / v1, (10 ** 0.5), places=3)

    def test_historical_var_returns_none_for_short_series(self):
        from .metrics import historical_var_rate
        self.assertIsNone(historical_var_rate([100, 101, 99], confidence=0.95))

    def test_historical_var_handles_simple_series(self):
        from .metrics import historical_var_rate
        # 100일치 — 균등하게 작은 하락이 다수 끼어 있어야 5% 분위수가 음수
        # (단 한 번의 큰 하락은 idx=int(99*0.05)=4 라 5번째 최저가 잡혀야 함)
        prices = [100.0]
        for i in range(99):
            # 5일마다 -2% 드롭, 나머지는 +0.3%
            prices.append(prices[-1] * (0.98 if i % 5 == 0 else 1.003))
        var = historical_var_rate(prices, confidence=0.95)
        self.assertIsNotNone(var)
        self.assertGreater(var, 0)


class ComputeAndAggregateTests(TestCase):
    def setUp(self):
        from .models import FinancialProduct, Portfolio
        self.pf = Portfolio.objects.create(name='PF', weight_limit_pct=Decimal('40'))
        self.stock = FinancialProduct.objects.create(
            portfolio=self.pf, code='S', name='주식', kind='STOCK',
            notional=Decimal('1000000'),
            metrics_json={'volatility': 0.3, 'current_price': 100, 'shares': 10000},
        )
        self.bond = FinancialProduct.objects.create(
            portfolio=self.pf, code='B', name='채권', kind='BOND',
            notional=Decimal('1000000'),
            metrics_json={'par': 10000, 'coupon_rate': 0.05, 'ytm': 0.05, 'maturity_years': 5},
        )
        self.deriv = FinancialProduct.objects.create(
            portfolio=self.pf, code='D', name='파생', kind='DERIV',
            notional=Decimal('500000'),
            metrics_json={'volatility': 0.4, 'leverage': 3},
        )
        self.proj = FinancialProduct.objects.create(
            portfolio=self.pf, code='P', name='프로젝트', kind='PROJECT',
            notional=Decimal('1000000000'),
            metrics_json={'discount_rate': 0.10,
                          'cashflows': [-1000000000, 400000000, 400000000, 400000000]},
        )

    def test_compute_stock_value_uses_price_times_shares(self):
        from .metrics import compute
        c = compute(self.stock)
        self.assertEqual(c['current_value'], 1_000_000.0)  # 100 × 10000
        self.assertGreater(c['metrics']['VaR(95%, 1d)'], 0)

    def test_compute_bond_at_par(self):
        from .metrics import compute
        c = compute(self.bond)
        # par 1만, notional 100만 → scale=100배 → 평가액 ≈ 100만
        self.assertAlmostEqual(c['current_value'], 1_000_000.0, places=0)
        self.assertGreater(c['metrics']['Duration(년)'], 0)

    def test_compute_deriv_var_uses_leveraged_exposure(self):
        from .metrics import compute, parametric_var
        c = compute(self.deriv)
        expected_var = parametric_var(500_000 * 3, 0.4)
        self.assertAlmostEqual(c['metrics']['VaR(95%, 1d)'], expected_var, places=2)

    def test_compute_project_npv_and_irr(self):
        from .metrics import compute
        c = compute(self.proj)
        self.assertIsNotNone(c['metrics']['NPV'])
        self.assertIsNotNone(c['metrics']['IRR'])

    def test_aggregate_totals_match_per_product_sum(self):
        from .metrics import aggregate, compute
        agg = aggregate([self.stock, self.bond, self.deriv, self.proj], weight_limit_pct=40)
        manual = sum(compute(p)['current_value'] for p in [self.stock, self.bond, self.deriv, self.proj])
        self.assertAlmostEqual(agg['total_current_value'], manual, places=0)
        self.assertEqual(agg['count'], 4)

    def test_aggregate_flags_over_limit(self):
        from .metrics import aggregate
        # PROJECT 가 압도적이라 다른 종목들 weight 가 낮음. 한도 1% 로 낮춰서 모두 over
        agg = aggregate([self.stock, self.bond, self.deriv, self.proj], weight_limit_pct=1)
        self.assertGreaterEqual(agg['over_limit_count'], 1)


# ============================================================
# costing.py — 배분 보존 법칙 + 인건비 안분
# ============================================================

def _alloc_master():
    """배분 테스트용 마스터: 1본부 / 3부서 / 직원 + 카테고리"""
    from .models import (
        AllocationRule, CostCategory, CostEntry, Department,
        Division, Employee,
    )
    div = Division.objects.create(code='DV', name='본부')
    src = Department.objects.create(division=div, code='SRC', name='공통')
    t1 = Department.objects.create(division=div, code='T1', name='수행1')
    t2 = Department.objects.create(division=div, code='T2', name='수행2')
    cat = CostCategory.objects.create(code='LIC', name='라이선스')
    Employee.objects.create(department=t1, emp_no='E1', name='A',
                            standard_monthly_cost=Decimal('5000000'),
                            effective_from=date(2026, 1, 1))
    Employee.objects.create(department=t1, emp_no='E2', name='B',
                            standard_monthly_cost=Decimal('5000000'),
                            effective_from=date(2026, 1, 1))
    Employee.objects.create(department=t2, emp_no='E3', name='C',
                            standard_monthly_cost=Decimal('5000000'),
                            effective_from=date(2026, 1, 1))
    return div, src, t1, t2, cat


class SalaryAllocationTests(TestCase):
    """allocate_monthly_salary 의 안분 비율 정확성"""

    def test_split_by_assignment_pct(self):
        from .models import (
            CostEntry, Division, Department, Employee,
            Project, ProjectAssignment,
        )
        div = Division.objects.create(code='DV1', name='본부')
        dept = Department.objects.create(division=div, code='D1', name='부서')
        emp = Employee.objects.create(
            department=dept, emp_no='E', name='홍길동',
            standard_monthly_cost=Decimal('10000000'),
            effective_from=date(2026, 1, 1),
        )
        p1 = Project.objects.create(
            code='P1', name='프1', division=div,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        p2 = Project.objects.create(
            code='P2', name='프2', division=div,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        ProjectAssignment.objects.create(
            project=p1, employee=emp,
            period_from=date(2026, 1, 1), allocation_pct=Decimal('60'),
        )
        ProjectAssignment.objects.create(
            project=p2, employee=emp,
            period_from=date(2026, 1, 1), allocation_pct=Decimal('40'),
        )

        from .costing import allocate_monthly_salary
        result = allocate_monthly_salary('2026-04')
        self.assertEqual(result['created'], 2)

        salary_entries = CostEntry.objects.filter(
            period='2026-04', source=CostEntry.Source.SALARY,
        )
        amounts = {e.project.code: e.amount for e in salary_entries}
        self.assertEqual(amounts['P1'], Decimal('6000000.00'))
        self.assertEqual(amounts['P2'], Decimal('4000000.00'))
        self.assertEqual(sum(amounts.values()), Decimal('10000000.00'))

    def test_idempotent_when_run_twice(self):
        from .models import (
            Division, Department, Employee, Project, ProjectAssignment,
        )
        div = Division.objects.create(code='DV2', name='본부')
        dept = Department.objects.create(division=div, code='D2', name='부서')
        emp = Employee.objects.create(
            department=dept, emp_no='E', name='홍',
            standard_monthly_cost=Decimal('5000000'),
            effective_from=date(2026, 1, 1),
        )
        p = Project.objects.create(
            code='P', name='프', division=div,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        ProjectAssignment.objects.create(
            project=p, employee=emp,
            period_from=date(2026, 1, 1), allocation_pct=Decimal('100'),
        )
        from .costing import allocate_monthly_salary
        r1 = allocate_monthly_salary('2026-04')
        r2 = allocate_monthly_salary('2026-04')
        self.assertEqual(r1['created'], 1)
        self.assertEqual(r2['created'], 0)
        self.assertEqual(r2['skipped'], 1)


class AllocationConservationTests(TestCase):
    """배분 시뮬→확정→취소 의 보존 법칙

    핵심: commit 전후의 전체 CostEntry 합계가 변하지 않아야 한다.
    (배분된 금액 합 + 출발부서 상쇄(-합) = 0)
    """

    def setUp(self):
        from .models import (
            AllocationRule, CostEntry,
        )
        self.div, self.src, self.t1, self.t2, self.cat = _alloc_master()
        # 출발 부서에 라이선스 비용 100만
        CostEntry.objects.create(
            period='2026-04', entry_date=date(2026, 4, 1),
            category=self.cat, amount=Decimal('1000000'),
            division=self.div, department=self.src,
        )
        self.rule = AllocationRule.objects.create(
            code='R-EQ', name='균등', source_category=self.cat,
            source_department=self.src, driver_type='EQUAL',
            target_dimension='DEPARTMENT', effective_from=date(2026, 1, 1),
        )

    def _total(self):
        from .models import CostEntry
        from django.db.models import Sum
        return CostEntry.objects.filter(period='2026-04').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')

    def test_commit_preserves_total(self):
        from .costing import simulate_allocation, commit_allocation
        before = self._total()
        run = simulate_allocation(self.rule, '2026-04')
        commit_allocation(run)
        after = self._total()
        self.assertEqual(before, after, '배분 확정 후 전체 합계가 보존되지 않음 (보존 법칙 위반)')

    def test_reverse_restores_state(self):
        from .costing import simulate_allocation, commit_allocation, reverse_allocation
        before_count = self._total()
        run = simulate_allocation(self.rule, '2026-04')
        commit_allocation(run)
        reverse_allocation(run)
        after = self._total()
        self.assertEqual(before_count, after)

    def test_equal_split_among_targets(self):
        from .costing import simulate_allocation, commit_allocation
        from .models import CostEntry
        run = simulate_allocation(self.rule, '2026-04')
        commit_allocation(run)
        # 출발 부서(SRC) 제외 2개 부서에 균등 분할 → 50만씩
        positives = CostEntry.objects.filter(
            period='2026-04', source='ALLOCATION', amount__gt=0,
        )
        self.assertEqual(positives.count(), 2)
        for e in positives:
            self.assertEqual(e.amount, Decimal('500000.00'))


# ============================================================
# stress.py — 쇼크 방향성 검증
# ============================================================

class StressDirectionTests(TestCase):
    def setUp(self):
        from .models import FinancialProduct, Portfolio
        self.pf = Portfolio.objects.create(name='PF')
        self.stock = FinancialProduct.objects.create(
            portfolio=self.pf, code='S', name='주식', kind='STOCK',
            notional=Decimal('1000000'),
            metrics_json={'volatility': 0.3, 'current_price': 100, 'shares': 10000},
        )
        self.bond = FinancialProduct.objects.create(
            portfolio=self.pf, code='B', name='채권', kind='BOND',
            notional=Decimal('1000000'),
            metrics_json={'par': 10000, 'coupon_rate': 0.05, 'ytm': 0.05, 'maturity_years': 5},
        )

    def test_equity_crash_drops_stock_value(self):
        from .stress import run_scenario
        s = next(s for s in __import__('apps.evaluation.stress', fromlist=['SCENARIOS']).SCENARIOS
                 if s['key'] == 'EQUITY_DOWN_20')
        r = run_scenario([self.stock], s)
        self.assertLess(r['stressed_total'], r['base_total'])
        # -20% 가까이 하락
        self.assertAlmostEqual(r['delta_pct'], -20.0, places=0)

    def test_rate_up_drops_bond_price(self):
        from .stress import run_scenario, SCENARIOS
        s = next(s for s in SCENARIOS if s['key'] == 'IR_UP_100')
        r = run_scenario([self.bond], s)
        self.assertLess(r['stressed_total'], r['base_total'],
                        'YTM 상승 시 채권 가격이 하락해야 함')

    def test_rate_down_raises_bond_price(self):
        from .stress import run_scenario, SCENARIOS
        s = next(s for s in SCENARIOS if s['key'] == 'IR_DOWN_50')
        r = run_scenario([self.bond], s)
        self.assertGreater(r['stressed_total'], r['base_total'])

    def test_volatility_up_increases_var(self):
        from .stress import run_scenario, SCENARIOS
        s = next(s for s in SCENARIOS if s['key'] == 'VOL_UP_100')
        r = run_scenario([self.stock], s)
        # 평가액은 같지만 VaR 는 2배
        self.assertAlmostEqual(r['base_total'], r['stressed_total'])
        self.assertAlmostEqual(r['stressed_var'] / r['base_var'], 2.0, places=2)

    def test_run_all_returns_seven_scenarios(self):
        from .stress import run_all
        results = run_all([self.stock, self.bond])
        self.assertEqual(len(results), 7)
        keys = {r['key'] for r in results}
        self.assertIn('CRISIS', keys)
        self.assertIn('IR_UP_100', keys)
