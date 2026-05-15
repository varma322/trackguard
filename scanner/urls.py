from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='scanner/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Scanner
    path('', views.index, name='index'),
    path('scan/', views.scan, name='scan'),
    path('records/', views.records, name='records'),
    path('export/', views.export_csv, name='export_csv'),
    path('upload/', views.upload_data, name='upload_data'),
    path('template/', views.download_template, name='download_template'),
    path('delete/<int:pk>/', views.delete_scan, name='delete_scan'),
    path('bulk-update-order-ids/', views.bulk_update_order_ids, name='bulk_update_order_ids'),

    # Orders & Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('orders/', views.orders_list, name='orders_list'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/import/', views.import_orders, name='import_orders'),
    path('orders/amazon-import/', views.batch_status_import, name='batch_status_import'),
    path('orders/update-status/<int:pk>/', views.update_order_status, name='update_order_status'),
    path('orders/bulk-update/', views.bulk_update_status, name='bulk_update_status'),
    path('orders/export/', views.export_orders_csv, name='export_orders_csv'),
    path('orders/template/', views.download_orders_template, name='download_orders_template'),
    path('orders/amazon-template/', views.download_amazon_report_template, name='download_amazon_report_template'),
    path('orders/reconcile/', views.reconcile_orders, name='reconcile_orders'),
    
    # Products
    path('products/', views.product_summary, name='product_summary'),
]
