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
]
