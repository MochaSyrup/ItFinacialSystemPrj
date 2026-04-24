"""원가/관리회계 트랜잭션 시드 — 2026-01~04 (인건비/공통비/외주/매출/배분 확정 데이터)

경고: 이 명령은 기존 seed 관련 트랜잭션(ref='seed-*' 또는 'alloc-run*') 을
매 실행마다 삭제한 뒤 재생성합니다. 수동 배분 실행 결과가 같이 지워질 수 있음.
"""
import random
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.evaluation.costing import (
    allocate_monthly_salary, commit_allocation, ensure_default_categories,
    simulate_allocation,
)
from apps.evaluation.models import (
    AllocationRule, AllocationRun, CostCategory, CostEntry,
    Department, Project, RevenueEntry,
)


ALL_MONTHS = ['2026-01', '2026-02', '2026-03', '2026-04']


class Command(BaseCommand):
    help = '원가/관리회계 트랜잭션 시드 — 4개월치 인건비/공통비/외주/매출/배분 확정 생성'

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=4,
                            help='시드 개월 수 (2026-01부터, 기본 4)')

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        months = ALL_MONTHS[:opts['months']]
        if not months:
            raise CommandError('--months 는 1 이상이어야 합니다.')

        ensure_default_categories()

        # 기존 seed 트랜잭션 정리
        AllocationRun.objects.filter(note__startswith='seed').delete()
        AllocationRule.objects.filter(code__startswith='SEED-').delete()
        CostEntry.objects.filter(ref__startswith='seed-').delete()
        CostEntry.objects.filter(ref__startswith='alloc-run').delete()
        RevenueEntry.objects.filter(ref__startswith='seed-').delete()
        self.stdout.write(self.style.WARNING('기존 seed 트랜잭션 정리'))

        cats = {c.code: c for c in CostCategory.objects.all()}
        try:
            admin_dept = Department.objects.get(code='DPT-D001-01')
            finance_dept = Department.objects.get(code='DPT-D001-02')
            security_dept = Department.objects.get(code='DPT-D004-03')
        except Department.DoesNotExist:
            raise CommandError(
                '마스터 시드 먼저 실행: python manage.py seed_costing_master'
            )

        # 프로젝트 contract_amount / customer_type 보정
        # — budget 대비 15~30% 마진으로 계약금액 설정
        external_patterns = ['ABC생명', 'DEF증권', '신한금융', 'KB금융', '우리은행', '하나은행', '삼성화재']
        self.stdout.write('프로젝트 계약금액 보정...')
        for i, prj in enumerate(Project.objects.all().order_by('code')):
            if prj.contract_amount <= 0:
                factor = Decimal(str(round(1.15 + random.random() * 0.15, 3)))
                prj.contract_amount = (prj.budget * factor).quantize(Decimal('0.01'))
                # 절반은 외부 고객
                if i % 2 == 0:
                    prj.customer_type = Project.CustomerType.EXTERNAL
                    prj.customer = external_patterns[i % len(external_patterns)]
                else:
                    prj.customer_type = Project.CustomerType.INTERNAL
                    prj.customer = prj.division.name
                prj.save(update_fields=['contract_amount', 'customer_type', 'customer'])

        # 매출 인식 대상: ACTIVE 전부 + PLANNING 중 시작일이 해당 월 이전인 것
        income_projects = list(
            Project.objects.filter(status__in=['ACTIVE', 'PLANNING'])
            .select_related('division', 'department')
            .order_by('code')
        )

        ce_count = 0
        re_count = 0

        for period in months:
            y, m = map(int, period.split('-'))
            last_day = monthrange(y, m)[1]
            target_date = date(y, m, last_day)
            month_start = date(y, m, 1)
            month_end = target_date

            # 1) 월 인건비 안분
            r = allocate_monthly_salary(period, reset=True)
            ce_count += r['created']
            self.stdout.write(f'[{period}] 인건비 안분 {r["created"]}건')

            # 2) 공통비 정기분 4종
            CostEntry.objects.create(
                period=period, entry_date=target_date,
                category=cats['OTHER'], amount=Decimal('50000000'),
                department=admin_dept, division=admin_dept.division,
                source=CostEntry.Source.MANUAL,
                ref=f'seed-admin-ot-{period}',
                memo='경영기획팀 사무실·운영비 (공통비)',
            )
            CostEntry.objects.create(
                period=period, entry_date=target_date,
                category=cats['LICENSE'], amount=Decimal('20000000'),
                department=finance_dept, division=finance_dept.division,
                source=CostEntry.Source.MANUAL,
                ref=f'seed-erp-{period}',
                memo='재무회계 ERP 월 라이선스',
            )
            CostEntry.objects.create(
                period=period, entry_date=target_date,
                category=cats['LICENSE'], amount=Decimal('15000000'),
                department=security_dept, division=security_dept.division,
                source=CostEntry.Source.MANUAL,
                ref=f'seed-sec-{period}',
                memo='정보보안 보안툴 월 라이선스',
            )
            CostEntry.objects.create(
                period=period, entry_date=target_date,
                category=cats['TRAINING'], amount=Decimal('10000000'),
                department=admin_dept, division=admin_dept.division,
                source=CostEntry.Source.MANUAL,
                ref=f'seed-train-admin-{period}',
                memo='경영기획 교육·출장',
            )
            ce_count += 4

            # 3) 프로젝트별 외주비 — 예산 10억 이상 ACTIVE 프로젝트
            large_active = [p for p in income_projects
                           if p.status == 'ACTIVE' and p.budget >= Decimal('1000000000')]
            for prj in large_active:
                amt = Decimal(random.randint(30, 150)) * Decimal('1000000')
                CostEntry.objects.create(
                    period=period, entry_date=target_date,
                    category=cats['OUTSRC'], amount=amt,
                    project=prj, division=prj.division, department=prj.department,
                    source=CostEntry.Source.MANUAL,
                    ref=f'seed-outsrc-{prj.code}-{period}',
                    memo=f'{prj.code} 외주 개발 용역',
                )
                ce_count += 1

            # 4) 장비/HW — 무작위 4개 ACTIVE 프로젝트
            active_only = [p for p in income_projects if p.status == 'ACTIVE']
            for prj in random.sample(active_only, min(4, len(active_only))):
                amt = Decimal(random.randint(10, 50)) * Decimal('1000000')
                CostEntry.objects.create(
                    period=period, entry_date=date(y, m, random.randint(1, last_day)),
                    category=cats['EQUIPMENT'], amount=amt,
                    project=prj, division=prj.division, department=prj.department,
                    source=CostEntry.Source.MANUAL,
                    ref=f'seed-eq-{prj.code}-{period}',
                    memo=f'{prj.code} 장비·HW 구매',
                )
                ce_count += 1

            # 5) 교육/출장 — 무작위 3개
            for prj in random.sample(active_only, min(3, len(active_only))):
                amt = Decimal(random.randint(2, 5)) * Decimal('1000000')
                CostEntry.objects.create(
                    period=period, entry_date=target_date,
                    category=cats['TRAINING'], amount=amt,
                    project=prj, division=prj.division, department=prj.department,
                    source=CostEntry.Source.MANUAL,
                    ref=f'seed-train-{prj.code}-{period}',
                    memo=f'{prj.code} 교육·출장',
                )
                ce_count += 1

            # 6) 매출 — 프로젝트 기간에 포함되는 모든 ACTIVE/PLANNING
            for prj in income_projects:
                # 프로젝트 기간 체크
                if prj.start_date > month_end or prj.end_date < month_start:
                    continue
                total_months = max(1, (prj.end_date - prj.start_date).days // 30)
                base = prj.contract_amount / Decimal(total_months)
                factor = Decimal(str(round(0.8 + random.random() * 0.4, 3)))  # 0.8~1.2
                rev = (base * factor).quantize(Decimal('0.01'))
                if prj.status == 'PLANNING':
                    rev = (rev * Decimal('0.3')).quantize(Decimal('0.01'))  # 선수금 30%
                if rev <= 0:
                    continue
                RevenueEntry.objects.create(
                    period=period, entry_date=target_date, amount=rev,
                    project=prj, division=prj.division, department=prj.department,
                    customer=prj.customer or '내부',
                    source=RevenueEntry.Source.MANUAL,
                    ref=f'seed-rev-{prj.code}-{period}',
                    memo=f'{prj.code} {period} 매출 인식',
                )
                re_count += 1

        self.stdout.write(f'원가 {ce_count}건 / 매출 {re_count}건')

        # 7) 배분 규칙 3개
        rules = self._seed_rules(cats, admin_dept, finance_dept, security_dept)
        self.stdout.write(f'배분 규칙 {len(rules)}개')

        # 8) 각 월별 배분 시뮬 + 확정
        committed = 0
        for period in months:
            for rule in rules:
                run = simulate_allocation(rule, period, note=f'seed {period}')
                if run.results.exists():
                    commit_allocation(run)
                    committed += 1
        self.stdout.write(f'배분 확정 {committed}건')

        self.stdout.write(self.style.SUCCESS(
            f'완료: {months[0]} ~ {months[-1]} ({len(months)}개월) 트랜잭션 시드'
        ))

    def _seed_rules(self, cats, admin_dept, finance_dept, security_dept):
        r1 = AllocationRule.objects.create(
            code='SEED-ADMIN-01', name='경영기획 공통비 → 프로젝트 (MANHOUR)',
            source_category=cats['OTHER'], source_department=admin_dept,
            driver_type='MANHOUR', target_dimension='PROJECT',
            priority=10, effective_from=date(2026, 1, 1),
        )
        r2 = AllocationRule.objects.create(
            code='SEED-ERP-02', name='재무 ERP 라이선스 → 부서 (HEADCOUNT)',
            source_category=cats['LICENSE'], source_department=finance_dept,
            driver_type='HEADCOUNT', target_dimension='DEPARTMENT',
            priority=20, effective_from=date(2026, 1, 1),
        )
        r3 = AllocationRule.objects.create(
            code='SEED-SEC-03', name='보안툴 라이선스 → 부서 (EQUAL)',
            source_category=cats['LICENSE'], source_department=security_dept,
            driver_type='EQUAL', target_dimension='DEPARTMENT',
            priority=30, effective_from=date(2026, 1, 1),
        )
        return [r1, r2, r3]
