import json

from django import forms

from .models import FinancialProduct, Portfolio

INPUT_CLS = (
    'w-full border border-slate-300 rounded px-3 py-2 text-sm '
    'focus:outline-none focus:ring-2 focus:ring-blue-500'
)


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['name', 'base_currency', 'valuation_date', 'weight_limit_pct']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 보장성 운용 포트폴리오'}),
            'base_currency': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'KRW'}),
            'valuation_date': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'weight_limit_pct': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '40.00'}),
        }


# kind 별 권장 metrics_json 입력
KIND_HINTS = {
    'STOCK':   '예: {"volatility": 0.30}',
    'BOND':    '예: {"coupon_rate": 0.05, "ytm": 0.045, "maturity_years": 5, "par": 1000000}',
    'DERIV':   '예: {"volatility": 0.45, "leverage": 3}',
    'PROJECT': '예: {"discount_rate": 0.10, "cashflows": [-1000000000, 300000000, 400000000, 500000000]}',
}


class FinancialProductForm(forms.ModelForm):
    metrics_json_text = forms.CharField(
        label='지표 입력 (JSON)',
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLS + ' font-mono text-xs',
            'rows': 4,
            'placeholder': '{}',
        }),
        help_text='kind 에 맞는 입력값을 JSON 으로 작성합니다. (비우면 기본값 사용)',
    )

    class Meta:
        model = FinancialProduct
        fields = ['portfolio', 'code', 'name', 'kind', 'notional', 'book_value']
        widgets = {
            'portfolio': forms.Select(attrs={'class': INPUT_CLS}),
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'BOND_KTB_2030'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '국고채 2030년물'}),
            'kind': forms.Select(attrs={'class': INPUT_CLS}),
            'notional': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'book_value': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '취득원가'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.metrics_json:
            self.fields['metrics_json_text'].initial = json.dumps(
                self.instance.metrics_json, ensure_ascii=False, indent=2
            )

    def clean_metrics_json_text(self):
        raw = self.cleaned_data.get('metrics_json_text', '').strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f'JSON 파싱 실패: {e}')

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.metrics_json = self.cleaned_data.get('metrics_json_text') or {}
        if commit:
            obj.save()
        return obj
