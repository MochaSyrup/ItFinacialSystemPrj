from django.urls import path

from . import views

app_name = 'interfaces'

urlpatterns = [
    path('', views.interface_list, name='list'),
    path('new/', views.interface_create, name='create'),
    path('<int:pk>/', views.interface_detail, name='detail'),
    path('<int:pk>/edit/', views.interface_update, name='update'),
    path('<int:pk>/delete/', views.interface_delete, name='delete'),
    path('<int:pk>/toggle/', views.interface_toggle, name='toggle'),
    path('execute/', views.execute, name='execute'),
    path('<int:pk>/run/', views.interface_run, name='run'),
    path('logs/', views.logs, name='logs'),
    path('logs/<int:pk>/', views.log_detail, name='log_detail'),
    path('logs/<int:pk>/retry/', views.log_retry, name='log_retry'),
    path('logs/retry_bulk/', views.log_retry_bulk, name='log_retry_bulk'),
]
