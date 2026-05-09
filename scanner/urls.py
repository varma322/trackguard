from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('scan/', views.scan, name='scan'),
    path('records/', views.records, name='records'),
    path('export/', views.export_csv, name='export_csv'),
    path('upload/', views.upload_data, name='upload_data'),
    path('template/', views.download_template, name='download_template'),
    path('delete/<int:pk>/', views.delete_scan, name='delete_scan'),
]
