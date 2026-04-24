from django.conf import settings
from django.db import models


# ============================================================
# 원가/관리회계 — 조직 마스터
# ============================================================

class Division(models.Model):
    """본부 (5개 운영)"""
    code = models.CharField(max_length=16, unique=True, help_text='예: D001')
    name = models.CharField(max_length=64)
    head = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='heading_divisions',
        help_text='본부장',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'[{self.code}] {self.name}'


class Department(models.Model):
    """부서 (본부 하위)"""
    class Kind(models.TextChoices):
        COMMON = 'COMMON', '공통관리'
        PROJECT = 'PROJECT', '프로젝트수행'

    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='departments')
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PROJECT)
    manager = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managing_departments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['division__code', 'code']

    def __str__(self):
        return f'{self.name} ({self.division.name})'


class Employee(models.Model):
    """인력 — 표준인건비 시점 관리"""
    class Rank(models.TextChoices):
        STAFF = 'STAFF', '사원'
        SENIOR = 'SENIOR', '대리'
        MANAGER = 'MANAGER', '과장'
        DEPUTY = 'DEPUTY', '차장'
        DIRECTOR = 'DIRECTOR', '부장'
        EXECUTIVE = 'EXECUTIVE', '임원'

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    emp_no = models.CharField(max_length=16, unique=True, help_text='사번')
    name = models.CharField(max_length=64)
    rank = models.CharField(max_length=12, choices=Rank.choices, default=Rank.STAFF)
    standard_monthly_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='월 표준인건비 (KRW)',
    )
    standard_hourly_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='시간당 표준단가 (배분용)',
    )
    effective_from = models.DateField(help_text='표준가 효력 시작')
    effective_to = models.DateField(null=True, blank=True, help_text='효력 종료 (null=현행)')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['emp_no']

    def __str__(self):
        return f'{self.emp_no} {self.name}'


class Project(models.Model):
    """프로젝트 (동시 20여 개 운영) — 원가집계/배분/성과분석 입력 단위"""
    class Status(models.TextChoices):
        PLANNING = 'PLANNING', '기획'
        ACTIVE = 'ACTIVE', '진행중'
        SUSPENDED = 'SUSPENDED', '중단'
        CLOSED = 'CLOSED', '종료'

    class Kind(models.TextChoices):
        DEVELOPMENT = 'DEVELOPMENT', '개발'
        MAINTENANCE = 'MAINTENANCE', '유지보수'
        OPERATION = 'OPERATION', '운영'
        RESEARCH = 'RESEARCH', '연구'

    class CostCenterType(models.TextChoices):
        REVENUE = 'REVENUE', '수익센터'
        COST = 'COST', '비용센터'
        COMMON = 'COMMON', '공통(배분대상)'

    class CustomerType(models.TextChoices):
        EXTERNAL = 'EXTERNAL', '외부 고객'
        INTERNAL = 'INTERNAL', '내부 (내부대체)'

    class AllocationKey(models.TextChoices):
        MANHOUR = 'MANHOUR', '공수(M/M)'
        REVENUE = 'REVENUE', '매출'
        HEADCOUNT = 'HEADCOUNT', '인원수'
        EQUAL = 'EQUAL', '균등'

    class Priority(models.TextChoices):
        HIGH = 'HIGH', '높음'
        MID = 'MID', '보통'
        LOW = 'LOW', '낮음'

    # 식별/소속
    code = models.CharField(max_length=32, unique=True, help_text='예: PRJ-2026-001')
    name = models.CharField(max_length=128)
    division = models.ForeignKey(Division, on_delete=models.PROTECT, related_name='projects', help_text='주관 본부')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='projects',
        help_text='주관 부서 (부서별 P&L 집계 단위)',
    )
    pm = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pm_of_projects',
    )

    # 분류
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.DEVELOPMENT, help_text='원가 행태 구분')
    cost_center_type = models.CharField(
        max_length=12, choices=CostCenterType.choices, default=CostCenterType.COST,
        help_text='배분 룰 적용 대상 결정',
    )

    # 일정/상태
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNING)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MID)

    # 수익
    customer = models.CharField(max_length=128, blank=True, help_text='고객/스폰서')
    customer_type = models.CharField(
        max_length=12, choices=CustomerType.choices, default=CustomerType.INTERNAL,
        help_text='외부=실매출 / 내부=내부대체',
    )
    contract_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='계약금액 / 예상매출 (KRW) — 성과(매출-원가) 계산 근거',
    )

    # 원가/배분
    budget = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='총 예산 (KRW) — ProjectBudget 합계로 계산되지만 별도 관리 가능',
    )
    planned_mm = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text='계획 공수 M/M (인월) — 인건비 예산 검증 키',
    )
    is_allocatable = models.BooleanField(
        default=True, help_text='공통비 배분 대상 포함 여부',
    )
    allocation_key = models.CharField(
        max_length=12, choices=AllocationKey.choices, default=AllocationKey.MANHOUR,
        help_text='표준원가 배분 시 기준',
    )

    # 거버넌스
    approved_by = models.CharField(max_length=64, blank=True, help_text='승인자')
    approved_at = models.DateField(null=True, blank=True, help_text='승인일')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', 'code']

    def __str__(self):
        return f'[{self.code}] {self.name}'


class ProjectBudget(models.Model):
    """프로젝트별 원가 항목 예산 분해 — 집행 추적 및 항목별 변동 분석용"""
    class Category(models.TextChoices):
        LABOR = 'LABOR', '인건비'
        OUTSRC = 'OUTSRC', '외주비'
        LICENSE = 'LICENSE', '라이선스'
        EQUIPMENT = 'EQUIPMENT', '장비/HW'
        TRAINING = 'TRAINING', '교육/출장'
        OTHER = 'OTHER', '기타'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='budgets')
    category = models.CharField(max_length=12, choices=Category.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text='해당 항목 예산 (KRW)')
    memo = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['project', 'category']
        unique_together = [('project', 'category')]

    def __str__(self):
        return f'{self.project.code} / {self.get_category_display()} {self.amount}'


class CostCategory(models.Model):
    """원가 항목 마스터 — CostEntry 의 분류 키"""
    code = models.CharField(max_length=16, unique=True, help_text='예: LABOR, OUTSRC, LICENSE')
    name = models.CharField(max_length=64)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
        help_text='상위 항목 (트리 구조)',
    )
    is_allocatable = models.BooleanField(default=True, help_text='공통비 배분 대상 여부')
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'code']
        verbose_name = '원가 항목'
        verbose_name_plural = '원가 항목'

    def __str__(self):
        return f'[{self.code}] {self.name}'


class CostEntry(models.Model):
    """원가 원장 — 한 줄 = 한 건의 비용 발생. 수정 금지(immutable), 보정은 reverses 로 역분개"""
    class Source(models.TextChoices):
        MANUAL = 'MANUAL', '수동 입력'
        IMPORT = 'IMPORT', 'CSV 업로드'
        SALARY = 'SALARY', '월 인건비 안분'
        ALLOCATION = 'ALLOCATION', '표준원가 배분'
        REVERSAL = 'REVERSAL', '역분개'

    period = models.CharField(max_length=7, help_text='회계 기간 YYYY-MM')
    entry_date = models.DateField(help_text='실제 발생일')
    category = models.ForeignKey(CostCategory, on_delete=models.PROTECT, related_name='entries')
    amount = models.DecimalField(max_digits=18, decimal_places=2, help_text='금액 (KRW)')

    # 귀속 차원 — 4개 중 하나 이상
    division = models.ForeignKey(
        Division, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cost_entries',
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cost_entries',
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cost_entries',
    )
    employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cost_entries',
    )

    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    ref = models.CharField(max_length=64, blank=True, help_text='출처 참조 (배치ID, 인보이스No 등)')
    memo = models.TextField(blank=True)
    reverses = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reversed_by', help_text='역분개 대상',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_cost_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period', '-entry_date', '-id']
        indexes = [
            models.Index(fields=['period', 'division']),
            models.Index(fields=['period', 'department']),
            models.Index(fields=['period', 'project']),
            models.Index(fields=['period', 'category']),
            models.Index(fields=['period', 'source']),
        ]
        verbose_name = '원가 원장'
        verbose_name_plural = '원가 원장'

    def __str__(self):
        return f'{self.period} {self.category.code} {self.amount}'


class RevenueEntry(models.Model):
    """수익 원장 — 실현 매출. CostEntry와 같은 차원으로 P&L 매칭"""
    class Source(models.TextChoices):
        MANUAL = 'MANUAL', '수동 입력'
        IMPORT = 'IMPORT', 'CSV 업로드'

    period = models.CharField(max_length=7, help_text='회계 기간 YYYY-MM')
    entry_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    division = models.ForeignKey(Division, null=True, blank=True, on_delete=models.SET_NULL, related_name='revenue_entries')
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name='revenue_entries')
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name='revenue_entries')
    customer = models.CharField(max_length=128, blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    ref = models.CharField(max_length=64, blank=True)
    memo = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_revenue_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period', '-entry_date', '-id']
        indexes = [
            models.Index(fields=['period', 'division']),
            models.Index(fields=['period', 'department']),
            models.Index(fields=['period', 'project']),
        ]
        verbose_name = '수익 원장'
        verbose_name_plural = '수익 원장'

    def __str__(self):
        return f'{self.period} REV {self.amount}'


class InternalTransfer(models.Model):
    """내부거래 — 부서간 비용 이전. 본부/전사 집계 시 자동 elimination"""
    period = models.CharField(max_length=7, help_text='회계 기간 YYYY-MM')
    entry_date = models.DateField()
    from_department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='transfers_out', help_text='지출 부서')
    to_department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='transfers_in', help_text='수익 부서')
    category = models.ForeignKey(CostCategory, on_delete=models.PROTECT, related_name='internal_transfers')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_eliminated = models.BooleanField(default=True, help_text='본부/전사 집계 시 제거 여부')
    memo = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_internal_transfers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period', '-entry_date', '-id']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(from_department=models.F('to_department')),
                name='internal_transfer_distinct_depts',
            ),
        ]
        verbose_name = '내부거래'
        verbose_name_plural = '내부거래'

    def __str__(self):
        return f'{self.period} {self.from_department.code}→{self.to_department.code} {self.amount}'


class AllocationRule(models.Model):
    """배분 규칙 — 공통비를 어떤 기준으로 어디에 배분할지"""
    class DriverType(models.TextChoices):
        HEADCOUNT = 'HEADCOUNT', '인원수'
        MANHOUR = 'MANHOUR', '공수(M/M)'
        REVENUE = 'REVENUE', '매출'
        EQUAL = 'EQUAL', '균등'
        MANUAL = 'MANUAL', '수동값'

    class TargetDimension(models.TextChoices):
        PROJECT = 'PROJECT', '프로젝트'
        DEPARTMENT = 'DEPARTMENT', '부서'
        EMPLOYEE = 'EMPLOYEE', '인력'

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    source_category = models.ForeignKey(CostCategory, on_delete=models.PROTECT, related_name='alloc_rules', help_text='배분 대상 비용 항목')
    source_department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name='alloc_rules_out', help_text='출발 부서 (null=전사 공통)')
    driver_type = models.CharField(max_length=12, choices=DriverType.choices)
    target_dimension = models.CharField(max_length=12, choices=TargetDimension.choices)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=10, help_text='다단계 배분 시 실행 순서')
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['priority', 'code']
        verbose_name = '배분 규칙'
        verbose_name_plural = '배분 규칙'

    def __str__(self):
        return f'[{self.code}] {self.name}'


class AllocationDriver(models.Model):
    """배분 기준값 — period × target_id 별 driver 수치 (DriverType=MANUAL 일 때 핵심)"""
    rule = models.ForeignKey(AllocationRule, on_delete=models.CASCADE, related_name='drivers')
    period = models.CharField(max_length=7)
    target_id = models.IntegerField(help_text='Department/Project/Employee ID — rule.target_dimension에 따름')
    driver_value = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        unique_together = [('rule', 'period', 'target_id')]
        verbose_name = '배분 기준값'
        verbose_name_plural = '배분 기준값'


class AllocationRun(models.Model):
    """배분 실행 이력 — 시뮬→확정 단계"""
    class Status(models.TextChoices):
        SIMULATED = 'SIMULATED', '시뮬레이션'
        COMMITTED = 'COMMITTED', '확정'
        REVERSED = 'REVERSED', '취소'

    period = models.CharField(max_length=7)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SIMULATED)
    run_at = models.DateTimeField(auto_now_add=True)
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='allocation_runs')
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-run_at']
        verbose_name = '배분 실행'
        verbose_name_plural = '배분 실행'

    def __str__(self):
        return f'Run #{self.pk} {self.period} {self.get_status_display()}'


class AllocationResult(models.Model):
    """배분 결과 — COMMITTED 시 cost_entry 자동 생성"""
    run = models.ForeignKey(AllocationRun, on_delete=models.CASCADE, related_name='results')
    rule = models.ForeignKey(AllocationRule, on_delete=models.CASCADE, related_name='results')
    target_dimension = models.CharField(max_length=12, choices=AllocationRule.TargetDimension.choices)
    target_id = models.IntegerField()
    driver_value = models.DecimalField(max_digits=18, decimal_places=4)
    driver_share = models.DecimalField(max_digits=9, decimal_places=6, help_text='0.0~1.0 비중')
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)
    cost_entry = models.ForeignKey(CostEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='allocation_result')

    class Meta:
        ordering = ['rule', 'target_id']
        verbose_name = '배분 결과'
        verbose_name_plural = '배분 결과'


class ProjectAssignment(models.Model):
    """인력 투입 — 인건비 안분 키"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='assignments')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='assignments')
    period_from = models.DateField(help_text='투입 시작일')
    period_to = models.DateField(null=True, blank=True, help_text='투입 종료일 (null=진행중)')
    allocation_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        help_text='투입률 % (0~100) — 인건비 안분 비율',
    )
    role = models.CharField(max_length=32, blank=True, help_text='PM / PL / Dev / QA 등')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_from']

    def __str__(self):
        return f'{self.project.code} ← {self.employee.name} ({self.allocation_pct}%)'


# ============================================================
# 금융상품 평가 — 기존
# ============================================================

class Portfolio(models.Model):
    name = models.CharField(max_length=128)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portfolios',
    )
    base_currency = models.CharField(max_length=8, default='KRW')
    valuation_date = models.DateField(
        null=True, blank=True,
        help_text='평가 기준일 (비워두면 오늘 기준)'
    )
    weight_limit_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=40,
        help_text='종목당 비중 한도 (% — 초과 시 알람)'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FinancialProduct(models.Model):
    class Kind(models.TextChoices):
        STOCK = 'STOCK', '주식'
        BOND = 'BOND', '채권'
        DERIV = 'DERIV', '파생상품'
        PROJECT = 'PROJECT', '프로젝트'

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='products')
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    notional = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    book_value = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text='장부가/취득원가 — 평가손익 계산에 사용'
    )
    metrics_json = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f'{self.code} {self.name}'


class PriceHistory(models.Model):
    """시세/지표 일별 스냅샷 — 히스토리컬 VaR, 시계열 차트, 스트레스 base"""
    product = models.ForeignKey(
        FinancialProduct, on_delete=models.CASCADE, related_name='prices',
    )
    date = models.DateField()
    price = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        help_text='현재가(주식)/가격(채권 par 기준)/지수가(파생). PROJECT 는 null',
    )
    yield_rate = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        help_text='채권 YTM / 프로젝트 할인율 — kind 별',
    )
    volatility = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        help_text='rolling 20d 연 변동성',
    )

    class Meta:
        unique_together = [('product', 'date')]
        ordering = ['product', 'date']
        indexes = [models.Index(fields=['product', 'date'])]
        verbose_name = '시세 히스토리'
        verbose_name_plural = '시세 히스토리'

    def __str__(self):
        return f'{self.product.code} @ {self.date}'
