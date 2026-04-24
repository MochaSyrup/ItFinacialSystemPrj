from django.contrib import admin

from .models import (
    AllocationDriver,
    AllocationResult,
    AllocationRule,
    AllocationRun,
    CostCategory,
    CostEntry,
    Department,
    Division,
    Employee,
    FinancialProduct,
    InternalTransfer,
    Portfolio,
    Project,
    ProjectAssignment,
    ProjectBudget,
    RevenueEntry,
)


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'base_currency', 'created_at')
    search_fields = ('name',)


@admin.register(FinancialProduct)
class FinancialProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'portfolio', 'kind', 'notional')
    list_filter = ('kind', 'portfolio')
    search_fields = ('code', 'name')


# ============================================================
# 원가/관리회계 — 마스터
# ============================================================

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'head', 'created_at')
    search_fields = ('code', 'name')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'division', 'kind', 'manager')
    list_filter = ('division', 'kind')
    search_fields = ('code', 'name')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('emp_no', 'name', 'department', 'rank', 'standard_monthly_cost', 'is_active')
    list_filter = ('department__division', 'department', 'rank', 'is_active')
    search_fields = ('emp_no', 'name')


class ProjectBudgetInline(admin.TabularInline):
    model = ProjectBudget
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'division', 'department', 'kind', 'status', 'customer_type',
                    'start_date', 'end_date', 'contract_amount', 'budget')
    list_filter = ('division', 'department', 'kind', 'cost_center_type', 'customer_type', 'status', 'priority')
    search_fields = ('code', 'name', 'customer')
    inlines = [ProjectBudgetInline]


@admin.register(ProjectBudget)
class ProjectBudgetAdmin(admin.ModelAdmin):
    list_display = ('project', 'category', 'amount')
    list_filter = ('category',)
    search_fields = ('project__code', 'project__name')


@admin.register(ProjectAssignment)
class ProjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ('project', 'employee', 'role', 'allocation_pct', 'period_from', 'period_to')
    list_filter = ('project', 'role')
    search_fields = ('project__code', 'employee__name', 'employee__emp_no')


@admin.register(CostCategory)
class CostCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent', 'is_allocatable', 'sort_order')
    list_filter = ('is_allocatable',)
    search_fields = ('code', 'name')


@admin.register(CostEntry)
class CostEntryAdmin(admin.ModelAdmin):
    list_display = ('period', 'entry_date', 'category', 'amount', 'division', 'department', 'project', 'employee', 'source')
    list_filter = ('period', 'source', 'category', 'division', 'department')
    search_fields = ('ref', 'memo', 'project__code', 'employee__name', 'employee__emp_no')
    raw_id_fields = ('reverses',)
    readonly_fields = ('created_at',)


@admin.register(RevenueEntry)
class RevenueEntryAdmin(admin.ModelAdmin):
    list_display = ('period', 'entry_date', 'amount', 'division', 'department', 'project', 'customer', 'source')
    list_filter = ('period', 'source', 'division')
    search_fields = ('customer', 'ref', 'memo', 'project__code')


@admin.register(InternalTransfer)
class InternalTransferAdmin(admin.ModelAdmin):
    list_display = ('period', 'entry_date', 'from_department', 'to_department', 'category', 'amount', 'is_eliminated')
    list_filter = ('period', 'is_eliminated', 'category')
    search_fields = ('memo',)


class AllocationDriverInline(admin.TabularInline):
    model = AllocationDriver
    extra = 0


@admin.register(AllocationRule)
class AllocationRuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'source_category', 'source_department', 'driver_type', 'target_dimension', 'is_active', 'priority')
    list_filter = ('is_active', 'driver_type', 'target_dimension')
    search_fields = ('code', 'name')
    inlines = [AllocationDriverInline]


@admin.register(AllocationRun)
class AllocationRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'period', 'status', 'run_at', 'run_by', 'total_amount')
    list_filter = ('status', 'period')


@admin.register(AllocationResult)
class AllocationResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'rule', 'target_dimension', 'target_id', 'driver_value', 'driver_share', 'allocated_amount', 'cost_entry')
    list_filter = ('run', 'rule', 'target_dimension')
