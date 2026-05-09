#pyrefly: ignore [missing-import]
import csv
import json
# pyrefly: ignore [missing-import]
from django.shortcuts import render, redirect
# pyrefly: ignore [missing-import]
from django.http import JsonResponse, HttpResponse
# pyrefly: ignore [missing-import]
from django.views.decorators.csrf import csrf_exempt
# pyrefly: ignore [missing-import]
from django.utils import timezone
# pyrefly: ignore [missing-import]
from django.db.models import Q
from django.contrib import messages
import pandas as pd
from .models import PackageScan


def index(request):
    today = timezone.localdate()
    recent = PackageScan.objects.filter(scanned_at__date=today)[:20]
    return render(request, 'scanner/index.html', {'recent': recent})


@csrf_exempt
def scan(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        tracking_id = (data.get('tracking_id') or '').strip()
        if not tracking_id:
            return JsonResponse({'error': 'No tracking ID'}, status=400)

        pkg = PackageScan.objects.create(
            tracking_id=tracking_id,
            order_id=data.get('order_id', ''),
            driver_name=data.get('driver_name', ''),
            courier=data.get('courier', ''),
            condition=data.get('condition', 'Good condition'),
            notes=data.get('notes', ''),
        )
        return JsonResponse({
            'id': pkg.id,
            'tracking_id': pkg.tracking_id,
            'scanned_at': timezone.localtime(pkg.scanned_at).strftime('%Y-%m-%d %H:%M:%S'),
            'courier': pkg.get_courier_display(),
        })
    return JsonResponse({'error': 'POST only'}, status=405)


def records(request):
    q = request.GET.get('q', '')
    today_str = timezone.localdate().strftime('%Y-%m-%d')
    date_from = request.GET.get('from', today_str)
    date_to = request.GET.get('to', today_str)

    qs = PackageScan.objects.all()
    if q:
        qs = qs.filter(Q(tracking_id__icontains=q) | Q(order_id__icontains=q) | Q(driver_name__icontains=q) | Q(condition__icontains=q) | Q(notes__icontains=q))
    if date_from:
        qs = qs.filter(scanned_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(scanned_at__date__lte=date_to)

    return render(request, 'scanner/records.html', {'scans': qs, 'q': q, 'date_from': date_from, 'date_to': date_to})


def export_csv(request):
    q = request.GET.get('q', '')
    today_str = timezone.localdate().strftime('%Y-%m-%d')
    date_from = request.GET.get('from', today_str)
    date_to = request.GET.get('to', today_str)

    qs = PackageScan.objects.all()
    if q:
        qs = qs.filter(Q(tracking_id__icontains=q) | Q(order_id__icontains=q))
    if date_from:
        qs = qs.filter(scanned_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(scanned_at__date__lte=date_to)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="trackguard_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Tracking ID', 'Driver Name', 'Order ID', 'Courier', 'Condition', 'Notes', 'Scanned At'])
    for s in qs:
        local_time = timezone.localtime(s.scanned_at).strftime('%Y-%m-%d %H:%M:%S')

        writer.writerow([s.id, s.tracking_id, s.driver_name, s.order_id, s.get_courier_display(), s.condition, s.notes,
                         local_time])
    return response


def delete_scan(request, pk):
    if request.method == 'POST':
        PackageScan.objects.filter(pk=pk).delete()
    return redirect('records')


def download_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="upload_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tracking ID', 'Order ID', 'Driver Name', 'Courier', 'Condition', 'Notes'])
    return response


def upload_data(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        file_name = uploaded_file.name.lower()
        
        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, "Unsupported file format. Please upload CSV or Excel.")
                return redirect('records')

            # Ensure 'Tracking ID' is in columns
            if 'Tracking ID' not in df.columns:
                messages.error(request, "Missing 'Tracking ID' column in the uploaded file.")
                return redirect('records')

            df = df.fillna('')
            
            created_count = 0
            for _, row in df.iterrows():
                tracking_id = str(row.get('Tracking ID', '')).strip()
                if not tracking_id:
                    continue

                PackageScan.objects.create(
                    tracking_id=tracking_id,
                    order_id=str(row.get('Order ID', '')).strip(),
                    driver_name=str(row.get('Driver Name', '')).strip(),
                    courier=str(row.get('Courier', '')).strip()[:50],
                    condition=str(row.get('Condition', 'Good condition')).strip()[:50] or 'Good condition',
                    notes=str(row.get('Notes', '')).strip()[:500]
                )
                created_count += 1
                
            messages.success(request, f"Successfully imported {created_count} records.")
            
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
            
    return redirect('records')
