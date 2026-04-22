from django.conf import settings
from django.db import models


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
