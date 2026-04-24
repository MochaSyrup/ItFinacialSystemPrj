"""월 인건비 안분 — 사용: python manage.py allocate_salary 2026-04 [--reset]"""
from django.core.management.base import BaseCommand, CommandError

from apps.evaluation.costing import allocate_monthly_salary


class Command(BaseCommand):
    help = '월 인건비 안분 — ProjectAssignment 기준으로 CostEntry(source=SALARY) 생성'

    def add_arguments(self, parser):
        parser.add_argument('period', help='회계 기간 YYYY-MM (예: 2026-04)')
        parser.add_argument('--reset', action='store_true', help='해당 기간 SALARY 항목 삭제 후 재생성')

    def handle(self, *args, **opts):
        period = opts['period']
        try:
            from apps.evaluation.costing import parse_period
            parse_period(period)
        except Exception:
            raise CommandError(f'잘못된 기간 형식: {period} (YYYY-MM 이어야 함)')

        result = allocate_monthly_salary(period, reset=opts['reset'])
        self.stdout.write(self.style.SUCCESS(
            f"완료 [{result['period']}] 생성 {result['created']}건 / "
            f"스킵 {result['skipped']}건 / 리셋삭제 {result['reset_deleted']}건"
        ))
