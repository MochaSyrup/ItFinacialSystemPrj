"""Celery 태스크 — 월 인건비 안분 + 시세 스냅샷."""
import random
from datetime import date, timedelta
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from .costing import allocate_monthly_salary
from .models import FinancialProduct, PeriodClosedError, PriceHistory


def _period_str(d: date) -> str:
    return d.strftime('%Y-%m')


def _previous_month(today: date) -> str:
    first = today.replace(day=1)
    return _period_str(first - timedelta(days=1))


@shared_task(name='apps.evaluation.tasks.allocate_salary_for_period')
def allocate_salary_for_period(period: str, reset: bool = False) -> dict:
    """특정 period (YYYY-MM) 의 인건비 안분."""
    try:
        return allocate_monthly_salary(period, reset=reset)
    except PeriodClosedError as exc:
        return {'period': period, 'skipped': True, 'reason': str(exc)}


@shared_task(name='apps.evaluation.tasks.allocate_salary_previous_month')
def allocate_salary_previous_month() -> dict:
    """Beat 용 — 매월 1일 02:00 에 전월 인건비 안분."""
    today = timezone.localdate()
    return allocate_salary_for_period.run(_previous_month(today), reset=False)


@shared_task(name='apps.evaluation.tasks.refresh_market_data')
def refresh_market_data() -> dict:
    """일일 시세 스냅샷 전진 — 각 상품의 최근 가격을 ±1% 랜덤워크로 갱신.

    실제 운영에서는 시장 데이터 피드(KOSCOM/Bloomberg/FRED 등)와 연결해야 하지만
    현재는 데모 목적의 carry-forward. 동일 날짜 중복 생성은 스킵.
    """
    today = timezone.localdate()
    added = 0
    skipped = 0
    for p in FinancialProduct.objects.all():
        latest = p.prices.order_by('-date').first()
        if not latest:
            skipped += 1
            continue
        if latest.date >= today:
            skipped += 1
            continue
        new_price = None
        if latest.price is not None:
            step = Decimal(str(random.uniform(-0.01, 0.01)))
            new_price = (latest.price * (Decimal('1') + step)).quantize(Decimal('0.000001'))
        PriceHistory.objects.create(
            product=p, date=today,
            price=new_price,
            yield_rate=latest.yield_rate,
            volatility=latest.volatility,
        )
        added += 1
    return {'date': today.isoformat(), 'added': added, 'skipped': skipped}
