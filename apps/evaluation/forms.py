import json

from django import forms

from django.forms import inlineformset_factory

from .models import (
    AllocationRule, CostCategory, CostEntry, Department, Division,
    FinancialProduct, InternalTransfer, Portfolio, Project, ProjectBudget,
    RevenueEntry,
)

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


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'code', 'name', 'division', 'department', 'pm',
            'kind', 'cost_center_type', 'priority', 'status',
            'start_date', 'end_date',
            'customer', 'customer_type', 'contract_amount',
            'budget', 'planned_mm', 'is_allocatable', 'allocation_key',
            'approved_by', 'approved_at',
        ]
        labels = {
            'code': '프로젝트 코드',
            'name': '프로젝트명',
            'division': '주관 본부',
            'department': '주관 부서',
            'pm': 'PM (프로젝트 매니저)',
            'kind': '프로젝트 유형',
            'cost_center_type': '원가센터 유형',
            'priority': '우선순위',
            'status': '상태',
            'start_date': '시작일',
            'end_date': '종료일',
            'customer': '고객 / 스폰서',
            'customer_type': '고객 구분',
            'contract_amount': '계약금액',
            'budget': '총 예산',
            'planned_mm': '계획 공수 (M/M)',
            'is_allocatable': '공통비 배분 대상',
            'allocation_key': '배분 기준',
            'approved_by': '승인자',
            'approved_at': '승인일',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'PRJ-2026-021'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 청약 데이터 마이그레이션'}),
            'division': forms.Select(attrs={'class': INPUT_CLS}),
            'department': forms.Select(attrs={'class': INPUT_CLS}),
            'pm': forms.Select(attrs={'class': INPUT_CLS}),
            'kind': forms.Select(attrs={'class': INPUT_CLS}),
            'cost_center_type': forms.Select(attrs={'class': INPUT_CLS}),
            'priority': forms.Select(attrs={'class': INPUT_CLS}),
            'status': forms.Select(attrs={'class': INPUT_CLS}),
            'start_date': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'customer': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 영업본부 (내부) / ABC생명 (외부)'}),
            'customer_type': forms.Select(attrs={'class': INPUT_CLS}),
            'contract_amount': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '0'}),
            'budget': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '1000000000'}),
            'planned_mm': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '예: 24.00'}),
            'allocation_key': forms.Select(attrs={'class': INPUT_CLS}),
            'approved_by': forms.TextInput(attrs={'class': INPUT_CLS}),
            'approved_at': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        sd, ed = cleaned.get('start_date'), cleaned.get('end_date')
        if sd and ed and ed < sd:
            raise forms.ValidationError('종료일이 시작일보다 빠를 수 없습니다.')
        dept, div = cleaned.get('department'), cleaned.get('division')
        if dept and div and dept.division_id != div.id:
            raise forms.ValidationError(f'주관 부서({dept.name})가 선택한 본부({div.name}) 소속이 아닙니다.')
        return cleaned


class ProjectBudgetForm(forms.ModelForm):
    class Meta:
        model = ProjectBudget
        fields = ['category', 'amount', 'memo']
        labels = {'category': '항목', 'amount': '예산', 'memo': '비고'}
        widgets = {
            'category': forms.Select(attrs={'class': INPUT_CLS}),
            'amount': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'placeholder': '0'}),
            'memo': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '비고'}),
        }


ProjectBudgetFormSet = inlineformset_factory(
    Project, ProjectBudget,
    form=ProjectBudgetForm,
    extra=6,  # 신규 등록 시 6개 항목 모두 빈 줄 표시
    can_delete=True,
)


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ['code', 'name', 'head']
        labels = {'code': '본부 코드', 'name': '본부명', 'head': '본부장'}
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'D006'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 글로벌사업본부'}),
            'head': forms.Select(attrs={'class': INPUT_CLS}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['code', 'name', 'division', 'kind', 'manager']
        labels = {
            'code': '부서 코드', 'name': '부서명', 'division': '소속 본부',
            'kind': '부서 유형', 'manager': '부서장',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'DPT-D006-01'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 글로벌결제팀'}),
            'division': forms.Select(attrs={'class': INPUT_CLS}),
            'kind': forms.Select(attrs={'class': INPUT_CLS}),
            'manager': forms.Select(attrs={'class': INPUT_CLS}),
        }

    def __init__(self, *args, **kwargs):
        # division이 URL로부터 고정될 때 미리 셋팅
        initial_division = kwargs.pop('initial_division', None)
        super().__init__(*args, **kwargs)
        if initial_division and not self.is_bound:
            self.fields['division'].initial = initial_division


class CostEntryForm(forms.ModelForm):
    """원가 수동 입력"""
    class Meta:
        model = CostEntry
        fields = ['period', 'entry_date', 'category', 'amount',
                  'division', 'department', 'project', 'employee',
                  'ref', 'memo']
        labels = {
            'period': '회계 기간 (YYYY-MM)',
            'entry_date': '발생일',
            'category': '항목',
            'amount': '금액',
            'division': '본부',
            'department': '부서',
            'project': '프로젝트',
            'employee': '인력',
            'ref': '참조',
            'memo': '메모',
        }
        widgets = {
            'period': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '2026-04'}),
            'entry_date': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'category': forms.Select(attrs={'class': INPUT_CLS}),
            'amount': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'division': forms.Select(attrs={'class': INPUT_CLS}),
            'department': forms.Select(attrs={'class': INPUT_CLS}),
            'project': forms.Select(attrs={'class': INPUT_CLS}),
            'employee': forms.Select(attrs={'class': INPUT_CLS}),
            'ref': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '인보이스 번호 등'}),
            'memo': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def clean_period(self):
        v = self.cleaned_data.get('period', '').strip()
        try:
            y, m = v.split('-')
            int(y); int(m)
            if not (1 <= int(m) <= 12):
                raise ValueError
        except Exception:
            raise forms.ValidationError('YYYY-MM 형식이어야 합니다 (예: 2026-04)')
        return v

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(f) for f in ('division', 'department', 'project', 'employee')):
            raise forms.ValidationError('본부/부서/프로젝트/인력 중 최소 한 곳에 귀속시켜야 합니다.')
        return cleaned


class RevenueEntryForm(forms.ModelForm):
    """수익 원장 수동 입력"""
    class Meta:
        model = RevenueEntry
        fields = ['period', 'entry_date', 'amount',
                  'division', 'department', 'project',
                  'customer', 'ref', 'memo']
        labels = {
            'period': '회계 기간 (YYYY-MM)',
            'entry_date': '발생일',
            'amount': '금액',
            'division': '본부',
            'department': '부서',
            'project': '프로젝트',
            'customer': '고객',
            'ref': '참조',
            'memo': '메모',
        }
        widgets = {
            'period': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '2026-04'}),
            'entry_date': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'division': forms.Select(attrs={'class': INPUT_CLS}),
            'department': forms.Select(attrs={'class': INPUT_CLS}),
            'project': forms.Select(attrs={'class': INPUT_CLS}),
            'customer': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: ABC생명 / 내부'}),
            'ref': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '계약서 번호 등'}),
            'memo': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def clean_period(self):
        v = self.cleaned_data.get('period', '').strip()
        try:
            y, m = v.split('-')
            int(y); int(m)
            if not (1 <= int(m) <= 12):
                raise ValueError
        except Exception:
            raise forms.ValidationError('YYYY-MM 형식이어야 합니다 (예: 2026-04)')
        return v

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(f) for f in ('division', 'department', 'project')):
            raise forms.ValidationError('본부/부서/프로젝트 중 최소 한 곳에 귀속시켜야 합니다.')
        return cleaned


class AllocationRuleForm(forms.ModelForm):
    """배분 규칙 등록/수정"""
    class Meta:
        model = AllocationRule
        fields = [
            'code', 'name',
            'source_category', 'source_department',
            'driver_type', 'target_dimension',
            'priority', 'is_active',
            'effective_from', 'effective_to',
        ]
        labels = {
            'code': '규칙 코드',
            'name': '규칙명',
            'source_category': '배분 대상 항목',
            'source_department': '출발 부서',
            'driver_type': '배분 기준(Driver)',
            'target_dimension': '배분 대상 차원',
            'priority': '실행 순서',
            'is_active': '활성',
            'effective_from': '유효 시작',
            'effective_to': '유효 종료',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'ALLOC-COMMON-01'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '예: 공통관리부서 관리비 → 프로젝트 안분'}),
            'source_category': forms.Select(attrs={'class': INPUT_CLS}),
            'source_department': forms.Select(attrs={'class': INPUT_CLS}),
            'driver_type': forms.Select(attrs={'class': INPUT_CLS}),
            'target_dimension': forms.Select(attrs={'class': INPUT_CLS}),
            'priority': forms.NumberInput(attrs={'class': INPUT_CLS, 'placeholder': '10'}),
            'effective_from': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'class': INPUT_CLS, 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        ef, et = cleaned.get('effective_from'), cleaned.get('effective_to')
        if ef and et and et < ef:
            raise forms.ValidationError('유효 종료일이 시작일보다 빠를 수 없습니다.')
        return cleaned


class AllocationRunForm(forms.Form):
    """배분 시뮬 실행"""
    rule = forms.ModelChoiceField(
        label='배분 규칙',
        queryset=AllocationRule.objects.filter(is_active=True).order_by('priority', 'code'),
        widget=forms.Select(attrs={'class': INPUT_CLS}),
    )
    period = forms.CharField(
        label='회계 기간 (YYYY-MM)',
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '2026-04'}),
    )
    note = forms.CharField(
        label='메모', required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2, 'placeholder': '시뮬 의도/담당자 등'}),
    )

    def clean_period(self):
        v = self.cleaned_data.get('period', '').strip()
        try:
            y, m = v.split('-')
            int(y); int(m)
            if not (1 <= int(m) <= 12):
                raise ValueError
        except Exception:
            raise forms.ValidationError('YYYY-MM 형식이어야 합니다 (예: 2026-04)')
        return v


class AllocateSalaryForm(forms.Form):
    """월 인건비 안분 실행"""
    period = forms.CharField(
        label='회계 기간 (YYYY-MM)',
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '2026-04'}),
    )
    reset = forms.BooleanField(
        label='기존 안분 항목 삭제 후 재생성', required=False,
        help_text='체크하면 해당 기간의 source=SALARY 항목을 모두 삭제 후 새로 생성합니다.',
    )

    def clean_period(self):
        v = self.cleaned_data.get('period', '').strip()
        try:
            y, m = v.split('-')
            int(y); int(m)
            if not (1 <= int(m) <= 12):
                raise ValueError
        except Exception:
            raise forms.ValidationError('YYYY-MM 형식이어야 합니다 (예: 2026-04)')
        return v
