"""원가/관리회계 마스터 시드 — 생명보험사 시나리오 (5본부/15부서/50명/20프로젝트)"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.evaluation.models import (
    Department, Division, Employee, Project, ProjectAssignment,
)


# ── 본부 5개 (IT 금융 플랫폼사 자체 조직)
DIVISIONS = [
    {'code': 'D001', 'name': '경영지원본부'},
    {'code': 'D002', 'name': '플랫폼개발본부'},
    {'code': 'D003', 'name': '데이터·AI본부'},
    {'code': 'D004', 'name': '인프라·보안본부'},
    {'code': 'D005', 'name': '사업·서비스본부'},
]

# ── 부서 15개 (본부당 3개)
DEPARTMENTS = [
    # 경영지원 — 전부 공통관리
    ('DPT-D001-01', '경영기획팀',       'D001', 'COMMON'),
    ('DPT-D001-02', '재무회계팀',       'D001', 'COMMON'),
    ('DPT-D001-03', '인사총무팀',       'D001', 'COMMON'),
    # 플랫폼개발 — 핵심 코어 개발
    ('DPT-D002-01', '결제플랫폼팀',     'D002', 'PROJECT'),
    ('DPT-D002-02', '계좌·거래팀',      'D002', 'PROJECT'),
    ('DPT-D002-03', 'API플랫폼팀',      'D002', 'PROJECT'),
    # 데이터·AI
    ('DPT-D003-01', '데이터엔지니어링팀', 'D003', 'PROJECT'),
    ('DPT-D003-02', 'AI/ML팀',          'D003', 'PROJECT'),
    ('DPT-D003-03', '리스크모델팀',     'D003', 'PROJECT'),
    # 인프라·보안
    ('DPT-D004-01', '클라우드인프라팀', 'D004', 'PROJECT'),
    ('DPT-D004-02', 'SRE팀',            'D004', 'PROJECT'),
    ('DPT-D004-03', '정보보안팀',       'D004', 'COMMON'),
    # 사업·서비스
    ('DPT-D005-01', '프로덕트팀',       'D005', 'PROJECT'),
    ('DPT-D005-02', 'B2B영업팀',        'D005', 'PROJECT'),
    ('DPT-D005-03', '고객성공팀',       'D005', 'PROJECT'),
]

# ── 직급별 월 표준인건비 (KRW)
RANK_COST = {
    'EXECUTIVE': Decimal('15_000_000'),
    'DIRECTOR':  Decimal('10_000_000'),
    'DEPUTY':    Decimal('8_500_000'),
    'MANAGER':   Decimal('7_000_000'),
    'SENIOR':    Decimal('5_500_000'),
    'STAFF':     Decimal('4_200_000'),
}
RANK_HOURLY = {k: (v / Decimal('160')).quantize(Decimal('0.01')) for k, v in RANK_COST.items()}

# ── 인력 50명 (본부당 10명: 본부장1 + 부장1 + 차장2 + 과장2 + 대리2 + 사원2)
KOREAN_FAMILY = ['김', '이', '박', '최', '정', '강', '조', '윤', '장', '임', '한', '오', '서', '신', '권']
KOREAN_GIVEN = ['민준', '서연', '도윤', '하은', '시우', '지유', '예준', '수아', '주원', '지호',
                '건우', '서윤', '태민', '소희', '재현', '유진', '동현', '나연', '현우', '예린',
                '성민', '아린', '준서', '하린', '지훈', '시아', '윤호', '채원', '승현', '수빈',
                '우진', '하늘', '태윤', '다은', '재윤', '시은', '민재', '주아', '연우', '예나',
                '서진', '하영', '진우', '소율', '준혁', '예진', '도현', '하윤', '민호', '수현']

# 본부별 부서 코드 모음 (인력 배치용)
DEPT_BY_DIV = {
    'D001': ['DPT-D001-01', 'DPT-D001-02', 'DPT-D001-03'],
    'D002': ['DPT-D002-01', 'DPT-D002-02', 'DPT-D002-03'],
    'D003': ['DPT-D003-01', 'DPT-D003-02', 'DPT-D003-03'],
    'D004': ['DPT-D004-01', 'DPT-D004-02', 'DPT-D004-03'],
    'D005': ['DPT-D005-01', 'DPT-D005-02', 'DPT-D005-03'],
}


def build_employees():
    """50명 — 본부당 10명, 직급/부서 균형 배치"""
    rows = []
    seq = 1
    rank_distribution = [
        ('EXECUTIVE', 1),
        ('DIRECTOR', 1),
        ('DEPUTY', 2),
        ('MANAGER', 2),
        ('SENIOR', 2),
        ('STAFF', 2),
    ]
    for div_idx, div in enumerate(DIVISIONS):
        depts = DEPT_BY_DIV[div['code']]
        sub = 0
        for rank, count in rank_distribution:
            for _ in range(count):
                family = KOREAN_FAMILY[(seq - 1) % len(KOREAN_FAMILY)]
                given = KOREAN_GIVEN[(seq - 1) % len(KOREAN_GIVEN)]
                rows.append({
                    'emp_no': f'E{seq:05d}',
                    'name': f'{family}{given}',
                    'rank': rank,
                    'dept_code': depts[sub % len(depts)],
                    'div_code': div['code'],
                    'monthly_cost': RANK_COST[rank],
                    'hourly_cost': RANK_HOURLY[rank],
                })
                seq += 1
                sub += 1
    return rows


# ── 프로젝트 20개 (본부당 4개) — IT 금융 플랫폼사 사업 시나리오
PROJECTS = [
    # 경영지원본부 — 내부 IT/관리 시스템
    ('PRJ-2026-001', 'ERP 차세대 도입',                'D001', date(2026, 1, 15), date(2026, 12, 31), Decimal('2_500_000_000'), 'ACTIVE'),
    ('PRJ-2026-002', '그룹사 통합 인사 시스템',        'D001', date(2026, 3,  1), date(2026,  9, 30), Decimal('600_000_000'),    'ACTIVE'),
    ('PRJ-2026-003', '결산자동화·재무리포팅',          'D001', date(2026, 2,  1), date(2026,  8, 31), Decimal('800_000_000'),    'ACTIVE'),
    ('PRJ-2026-004', '그룹웨어/협업툴 도입',           'D001', date(2026, 5,  1), date(2026, 11, 30), Decimal('400_000_000'),    'PLANNING'),
    # 플랫폼개발본부 — 코어 금융 플랫폼
    ('PRJ-2026-005', '차세대 결제 게이트웨이',         'D002', date(2026, 1, 10), date(2026, 10, 31), Decimal('3_000_000_000'), 'ACTIVE'),
    ('PRJ-2026-006', '오픈뱅킹 API 허브',              'D002', date(2026, 2, 15), date(2026, 12, 31), Decimal('2_200_000_000'), 'ACTIVE'),
    ('PRJ-2026-007', '가상자산 거래 엔진',             'D002', date(2026, 4,  1), date(2027,  3, 31), Decimal('4_500_000_000'), 'ACTIVE'),
    ('PRJ-2026-008', '마이데이터 통합 플랫폼',         'D002', date(2026, 6,  1), date(2027,  3, 31), Decimal('1_800_000_000'), 'PLANNING'),
    # 데이터·AI본부
    ('PRJ-2026-009', '실시간 사기탐지(FDS) 엔진',      'D003', date(2026, 1, 20), date(2026, 11, 30), Decimal('2_400_000_000'), 'ACTIVE'),
    ('PRJ-2026-010', '신용평가 AI 모델 고도화',        'D003', date(2026, 3,  1), date(2026, 10, 31), Decimal('1_500_000_000'), 'ACTIVE'),
    ('PRJ-2026-011', '데이터 레이크하우스 구축',       'D003', date(2026, 2, 10), date(2026, 12, 31), Decimal('2_800_000_000'), 'ACTIVE'),
    ('PRJ-2026-012', 'LLM 기반 상담 어시스턴트',       'D003', date(2026, 5,  1), date(2026, 12, 31), Decimal('1_200_000_000'), 'PLANNING'),
    # 인프라·보안본부
    ('PRJ-2026-013', '멀티클라우드 마이그레이션',      'D004', date(2026, 1, 15), date(2027,  6, 30), Decimal('5_500_000_000'), 'ACTIVE'),
    ('PRJ-2026-014', '제로트러스트 보안체계 도입',     'D004', date(2026, 2,  1), date(2026, 12, 31), Decimal('1_800_000_000'), 'ACTIVE'),
    ('PRJ-2026-015', 'SRE 옵저버빌리티 고도화',        'D004', date(2026, 4,  1), date(2026, 11, 30), Decimal('900_000_000'),    'ACTIVE'),
    ('PRJ-2026-016', 'ISMS-P 인증 대응',               'D004', date(2026, 6,  1), date(2027,  2, 28), Decimal('500_000_000'),    'PLANNING'),
    # 사업·서비스본부 — 외부 고객/프로덕트
    ('PRJ-2026-017', '모바일 종합금융 앱 리뉴얼',      'D005', date(2026, 1,  5), date(2026, 11, 30), Decimal('3_500_000_000'), 'ACTIVE'),
    ('PRJ-2026-018', 'B2B 결제 SaaS 출시',             'D005', date(2026, 3,  1), date(2026, 12, 31), Decimal('2_000_000_000'), 'ACTIVE'),
    ('PRJ-2026-019', '고객 온보딩(eKYC) 개편',         'D005', date(2026, 2, 15), date(2026,  9, 30), Decimal('1_100_000_000'), 'ACTIVE'),
    ('PRJ-2026-020', '글로벌 송금 서비스 런칭',        'D005', date(2026, 5,  1), date(2027,  4, 30), Decimal('2_800_000_000'), 'PLANNING'),
]


class Command(BaseCommand):
    help = '원가/관리회계 마스터 시드 — 5본부/15부서/50명/20프로젝트 (생명보험사)'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='기존 마스터 전부 삭제 후 재생성')

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts['reset']:
            ProjectAssignment.objects.all().delete()
            Project.objects.all().delete()
            Employee.objects.all().delete()
            Department.objects.all().delete()
            Division.objects.all().delete()
            self.stdout.write(self.style.WARNING('기존 마스터 삭제'))

        # 1) 본부
        div_map = {}
        for d in DIVISIONS:
            div, _ = Division.objects.get_or_create(code=d['code'], defaults={'name': d['name']})
            div_map[d['code']] = div

        # 2) 부서
        dept_map = {}
        for code, name, div_code, kind in DEPARTMENTS:
            dept, _ = Department.objects.get_or_create(
                code=code,
                defaults={'name': name, 'division': div_map[div_code], 'kind': kind},
            )
            dept_map[code] = dept

        # 3) 인력
        emp_map = {}
        for row in build_employees():
            emp, _ = Employee.objects.get_or_create(
                emp_no=row['emp_no'],
                defaults={
                    'name': row['name'],
                    'department': dept_map[row['dept_code']],
                    'rank': row['rank'],
                    'standard_monthly_cost': row['monthly_cost'],
                    'standard_hourly_cost': row['hourly_cost'],
                    'effective_from': date(2026, 1, 1),
                    'is_active': True,
                },
            )
            emp_map[row['emp_no']] = emp

        # 4) 본부장/부서장 — 본부별 EXECUTIVE를 본부장, DIRECTOR를 첫 부서장으로
        for div in div_map.values():
            execs = Employee.objects.filter(department__division=div, rank='EXECUTIVE').first()
            if execs:
                div.head = execs
                div.save(update_fields=['head'])
        for dept in dept_map.values():
            director = Employee.objects.filter(department=dept, rank='DIRECTOR').first()
            if director:
                dept.manager = director
                dept.save(update_fields=['manager'])

        # 5) 프로젝트 — PM은 주관 본부의 부장(DIRECTOR) 한 명을 라운드로빈
        directors_by_div = {
            code: list(Employee.objects.filter(department__division=div, rank='DIRECTOR'))
            for code, div in div_map.items()
        }
        prj_map = {}
        for i, (code, name, div_code, sd, ed, budget, status) in enumerate(PROJECTS):
            div = div_map[div_code]
            pms = directors_by_div[div_code]
            pm = pms[i % len(pms)] if pms else None
            prj, _ = Project.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 'division': div, 'pm': pm,
                    'start_date': sd, 'end_date': ed,
                    'budget': budget, 'status': status,
                },
            )
            prj_map[code] = prj

        # 6) 인력 투입 — 각 프로젝트에 주관 본부 인력 3~5명을 라운드로빈, 투입률 30~80%
        all_emps_by_div = {
            code: list(Employee.objects.filter(department__division=div).exclude(rank='EXECUTIVE'))
            for code, div in div_map.items()
        }
        assign_count = 0
        roles = ['PM', 'PL', 'Dev', 'Dev', 'QA']
        pcts = [Decimal('100'), Decimal('80'), Decimal('60'), Decimal('60'), Decimal('40')]
        for i, prj in enumerate(prj_map.values()):
            pool = all_emps_by_div[prj.division.code]
            for k in range(min(5, len(pool))):
                emp = pool[(i + k) % len(pool)]
                ProjectAssignment.objects.get_or_create(
                    project=prj, employee=emp,
                    defaults={
                        'period_from': prj.start_date,
                        'period_to': None,
                        'allocation_pct': pcts[k],
                        'role': roles[k],
                    },
                )
                assign_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'완료: 본부 {len(div_map)} / 부서 {len(dept_map)} / '
            f'인력 {Employee.objects.count()} / 프로젝트 {len(prj_map)} / '
            f'인력투입 {assign_count}건'
        ))
