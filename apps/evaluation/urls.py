from django.urls import path

from . import views

app_name = 'evaluation'

urlpatterns = [
    path('portfolios/', views.portfolio, name='portfolio'),
    path('portfolios/new/', views.portfolio_create, name='portfolio_create'),
    path('portfolios/<int:pk>/', views.portfolio_detail, name='portfolio_detail'),
    path('portfolios/<int:pk>/edit/', views.portfolio_update, name='portfolio_update'),
    path('portfolios/<int:pk>/delete/', views.portfolio_delete, name='portfolio_delete'),

    path('products/', views.product, name='product'),
    path('products/new/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),

    path('risk/', views.risk, name='risk'),

    # 원가/관리회계
    path('costing/', views.costing_dashboard, name='costing_dashboard'),
    path('costing/divisions/', views.costing_division, name='costing_division'),
    path('costing/divisions/new/', views.costing_division_create, name='costing_division_create'),
    path('costing/divisions/<int:pk>/delete/', views.costing_division_delete, name='costing_division_delete'),
    path('costing/departments/new/', views.costing_department_create, name='costing_department_create'),
    path('costing/departments/<int:pk>/delete/', views.costing_department_delete, name='costing_department_delete'),
    path('costing/employees/', views.costing_employee, name='costing_employee'),
    path('costing/projects/', views.costing_project, name='costing_project'),
    path('costing/projects/new/', views.costing_project_create, name='costing_project_create'),
    path('costing/projects/<int:pk>/', views.costing_project_detail, name='costing_project_detail'),
    path('costing/projects/<int:pk>/delete/', views.costing_project_delete, name='costing_project_delete'),

    # 원가 원장
    path('costing/ledger/', views.costing_ledger, name='costing_ledger'),
    path('costing/ledger/new/', views.costing_ledger_create, name='costing_ledger_create'),
    path('costing/ledger/allocate/', views.costing_ledger_allocate, name='costing_ledger_allocate'),

    # 수익 원장
    path('costing/revenue/', views.costing_revenue, name='costing_revenue'),
    path('costing/revenue/new/', views.costing_revenue_create, name='costing_revenue_create'),
    path('costing/revenue/<int:pk>/delete/', views.costing_revenue_delete, name='costing_revenue_delete'),

    # 표준원가 배분
    path('costing/allocation/rules/', views.allocation_rule_list, name='allocation_rules'),
    path('costing/allocation/rules/new/', views.allocation_rule_create, name='allocation_rule_create'),
    path('costing/allocation/rules/<int:pk>/delete/', views.allocation_rule_delete, name='allocation_rule_delete'),
    path('costing/allocation/runs/', views.allocation_run_list, name='allocation_runs'),
    path('costing/allocation/runs/new/', views.allocation_run_simulate, name='allocation_run_simulate'),
    path('costing/allocation/runs/<int:pk>/', views.allocation_run_detail, name='allocation_run_detail'),
    path('costing/allocation/runs/<int:pk>/commit/', views.allocation_run_commit, name='allocation_run_commit'),
    path('costing/allocation/runs/<int:pk>/reverse/', views.allocation_run_reverse, name='allocation_run_reverse'),
    path('costing/allocation/runs/<int:pk>/delete/', views.allocation_run_delete, name='allocation_run_delete'),
]
