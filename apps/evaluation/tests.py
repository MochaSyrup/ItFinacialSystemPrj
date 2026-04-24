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
