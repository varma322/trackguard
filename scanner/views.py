# pyrefly: ignore [missing-import]
import csv
import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
import pandas as pd
from .models import PackageScan, Order, ImportBatch


def is_admin(user):
    return user.is_staff


# ─── SCANNER ────────────────────────────────────────────────────────────────

@login_required
def index(request):
    if not request.user.is_staff:
        return redirect('records')
    today = timezone.localdate()
    recent = PackageScan.objects.filter(scanned_at__date=today).select_related('linked_order')[:20]
    return render(request, 'scanner/index.html', {'recent': recent})


@csrf_exempt
@login_required
@user_passes_test(is_admin)
def scan(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        tracking_id = (data.get('tracking_id') or '').strip()
        if not tracking_id:
            return JsonResponse({'error': 'No tracking ID'}, status=400)

        order_id_input = (data.get('order_id') or '').strip()

        # Auto-detect order_id from tracking_id if not provided
        auto_detected = False
        if not order_id_input:
            # Search comma-separated amazon_tracking_id field
            matched = Order.objects.filter(
                Q(amazon_tracking_id=tracking_id) |
                Q(amazon_tracking_id__startswith=tracking_id + ',') |
                Q(amazon_tracking_id__endswith=',' + tracking_id) |
                Q(amazon_tracking_id__contains=',' + tracking_id + ',')
            ).first()
            if matched:
                order_id_input = matched.order_id
                auto_detected = True

        pkg = PackageScan.objects.create(
            tracking_id=tracking_id,
            order_id=order_id_input,
            driver_name=data.get('driver_name', ''),
            courier=data.get('courier', ''),
            condition=data.get('condition', 'Good condition'),
            notes=data.get('notes', ''),
        )

        # Auto-link to Order by order_id (allow multiple scans per order)
        order_linked = None
        if order_id_input:
            try:
                order = Order.objects.get(order_id=order_id_input)
                pkg.linked_order = order
                pkg.save(update_fields=['linked_order'])
                # Only update status if it hasn't been received yet
                if order.status == 'pending':
                    order.status = 'received'
                    order.save(update_fields=['status'])
                order_linked = order.order_id
            except Order.DoesNotExist:
                pass

        return JsonResponse({
            'id': pkg.id,
            'tracking_id': pkg.tracking_id,
            'order_id': order_id_input,
            'scanned_at': timezone.localtime(pkg.scanned_at).strftime('%Y-%m-%d %H:%M:%S'),
            'courier': pkg.get_courier_display(),
            'order_linked': order_linked,
            'auto_detected': auto_detected,
        })
    return JsonResponse({'error': 'POST only'}, status=405)


# ─── SCAN RECORDS ────────────────────────────────────────────────────────────

@login_required
def records(request):
    q = request.GET.get('q', '')
    today_str = timezone.localdate().strftime('%Y-%m-%d')
    date_from = request.GET.get('from', today_str)
    date_to = request.GET.get('to', today_str)

    qs = PackageScan.objects.all()
    if q:
        qs = qs.filter(
            Q(tracking_id__icontains=q) | Q(order_id__icontains=q) |
            Q(driver_name__icontains=q) | Q(condition__icontains=q) | Q(notes__icontains=q)
        )
    if date_from:
        qs = qs.filter(scanned_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(scanned_at__date__lte=date_to)

    return render(request, 'scanner/records.html', {
        'scans': qs, 'q': q, 'date_from': date_from, 'date_to': date_to
    })


@login_required
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
    response['Content-Disposition'] = 'attachment; filename="trackguard_scans.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Tracking ID', 'Driver Name', 'Order ID', 'Courier', 'Condition', 'Notes', 'Scanned At'])
    for s in qs:
        writer.writerow([
            s.id, s.tracking_id, s.driver_name, s.order_id,
            s.get_courier_display(), s.condition, s.notes,
            timezone.localtime(s.scanned_at).strftime('%Y-%m-%d %H:%M:%S')
        ])
    return response


@login_required
@user_passes_test(is_admin)
def delete_scan(request, pk):
    if request.method == 'POST':
        PackageScan.objects.filter(pk=pk).delete()
    return redirect('records')


@login_required
@user_passes_test(is_admin)
def download_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="upload_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tracking ID', 'Order ID', 'Driver Name', 'Courier', 'Condition', 'Notes'])
    return response


@login_required
@user_passes_test(is_admin)
def upload_data(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        file_name = uploaded_file.name.lower()
        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif file_name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, "Unsupported file format.")
                return redirect('records')

            if 'Tracking ID' not in df.columns:
                messages.error(request, "Missing 'Tracking ID' column.")
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
            messages.success(request, f"Successfully imported {created_count} scan records.")
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
    return redirect('records')


# ─── ORDERS ──────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    total = Order.objects.count()
    by_status = {s: Order.objects.filter(status=s).count() for s, _ in Order.STATUS_CHOICES}
    recent_orders = Order.objects.all()[:10]

    # Product breakdown
    product_stats = (
        Order.objects.values('product')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    # Unmatched scans: have an order_id but are not linked to any Order
    unmatched = PackageScan.objects.filter(order_id__gt='', linked_order__isnull=True).count()

    # Overdue pending: orders placed more than 7 days ago still pending
    overdue_date = timezone.localdate() - timedelta(days=7)
    overdue = Order.objects.filter(status='pending', order_date__lte=overdue_date)
    overdue_count = overdue.count()

    return render(request, 'scanner/dashboard.html', {
        'total': total,
        'by_status': by_status,
        'recent_orders': recent_orders,
        'product_stats': product_stats,
        'unmatched': unmatched,
        'overdue_count': overdue_count,
        'overdue_orders': overdue[:5],
    })


@login_required
def orders_list(request):
    q = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    page_num = request.GET.get('page', 1)

    qs = Order.objects.prefetch_related('scans').all()
    if q:
        qs = qs.filter(
            Q(order_id__icontains=q) | Q(email__icontains=q) |
            Q(product__icontains=q) | Q(notes__icontains=q) |
            Q(amazon_tracking_id__icontains=q)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if date_from:
        qs = qs.filter(order_date__gte=date_from)
    if date_to:
        qs = qs.filter(order_date__lte=date_to)

    total = qs.count()
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(page_num)

    return render(request, 'scanner/orders.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Order.STATUS_CHOICES,
        'total': total,
    })


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('scans'), pk=pk)
    return render(request, 'scanner/order_detail.html', {
        'order': order,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
@user_passes_test(is_admin)
def import_orders(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        file_name = uploaded_file.name.lower()
        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif file_name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, "Unsupported file format. Upload CSV or Excel.")
                return redirect('orders_list')

            df.columns = [c.strip() for c in df.columns]
            required = {'ORDER ID'}
            missing = required - set(df.columns.str.upper())
            if missing:
                messages.error(request, f"Missing columns: {', '.join(missing)}")
                return redirect('orders_list')

            df = df.fillna('')
            col_map = {c.upper(): c for c in df.columns}

            imported = skipped = 0
            batch = ImportBatch.objects.create(filename=uploaded_file.name, total_rows=len(df))

            for _, row in df.iterrows():
                order_id = str(row.get(col_map.get('ORDER ID', ''), '')).strip()
                if not order_id:
                    skipped += 1
                    continue

                raw_date = str(row.get(col_map.get('ORDER DATE', ''), '')).strip()
                order_date = None
                if raw_date:
                    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%b-%Y'):
                        try:
                            order_date = datetime.strptime(raw_date, fmt).date()
                            break
                        except ValueError:
                            continue

                _, created = Order.objects.get_or_create(
                    order_id=order_id,
                    defaults={
                        'email': str(row.get(col_map.get('EMAIL', ''), '')).strip(),
                        'product': str(row.get(col_map.get('PRODUCT', ''), '')).strip(),
                        'order_date': order_date,
                        'status': 'pending',
                    }
                )
                if created:
                    imported += 1
                else:
                    skipped += 1

            batch.imported_count = imported
            batch.skipped_count = skipped
            batch.save()
            messages.success(request, f"Import complete: {imported} new orders added, {skipped} skipped (duplicates).")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return redirect('orders_list')


@login_required
@user_passes_test(is_admin)
def batch_status_import(request):
    """
    Import Amazon order report CSV to:
    1. Update order statuses (Shipped → received, Delivered → delivered, Cancelled → cancelled)
    2. Store tracking IDs against orders for auto-detection on scan
    """
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        file_name = uploaded_file.name.lower()
        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, dtype=str)
            elif file_name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file, dtype=str)
            else:
                messages.error(request, "Unsupported file format.")
                return redirect('orders_list')

            df.columns = [c.strip() for c in df.columns]
            df = df.fillna('')
            col_map = {c.upper(): c for c in df.columns}

            # Detect Order ID column — Amazon uses 'Order ID' or 'order-id'
            order_col = col_map.get('ORDER ID') or col_map.get('ORDER-ID') or col_map.get('ORDERID')
            if not order_col:
                messages.error(request, "Could not find Order ID column. Expected 'Order ID' or 'order-id'.")
                return redirect('orders_list')

            # Detect status column
            status_col = col_map.get('ORDER STATUS') or col_map.get('STATUS') or col_map.get('SHIPMENT STATUS')

            # Detect tracking column
            tracking_col = (col_map.get('TRACKING NUMBER') or col_map.get('TRACKING ID') or
                            col_map.get('CARRIER TRACKING NUMBER') or col_map.get('TRACKING-NUMBER'))

            # Amazon status → TrackGuard status mapping
            AMAZON_STATUS_MAP = {
                'shipped': 'received',
                'out for delivery': 'received',
                'delivered': 'delivered',
                'cancelled': 'cancelled',
                'canceled': 'cancelled',
                'returned': 'returned',
                'return initiated': 'returned',
                'undeliverable': 'issue',
                'pending': 'pending',
            }

            updated = tracking_updated = not_found = 0

            for _, row in df.iterrows():
                order_id = str(row.get(order_col, '')).strip()
                if not order_id:
                    continue

                try:
                    order = Order.objects.get(order_id=order_id)
                except Order.DoesNotExist:
                    not_found += 1
                    continue

                changed = False

                # Update status
                if status_col:
                    raw_status = str(row.get(status_col, '')).strip().lower()
                    new_status = AMAZON_STATUS_MAP.get(raw_status)
                    if new_status and order.status != new_status:
                        order.amazon_status = str(row.get(status_col, '')).strip()
                        order.status = new_status
                        changed = True
                        updated += 1

                # Store / append tracking IDs (comma-separated, avoid duplicates)
                if tracking_col:
                    tracking_id = str(row.get(tracking_col, '')).strip()
                    if tracking_id:
                        existing_ids = [t.strip() for t in order.amazon_tracking_id.split(',') if t.strip()]
                        if tracking_id not in existing_ids:
                            existing_ids.append(tracking_id)
                            order.amazon_tracking_id = ', '.join(existing_ids)
                            changed = True
                            tracking_updated += 1

                if changed:
                    order.save()

            msg_parts = []
            if updated:
                msg_parts.append(f"{updated} order status(es) updated")
            if tracking_updated:
                msg_parts.append(f"{tracking_updated} tracking ID(s) stored")
            if not_found:
                msg_parts.append(f"{not_found} order ID(s) not found in your records")

            if msg_parts:
                messages.success(request, "Amazon report imported: " + ", ".join(msg_parts) + ".")
            else:
                messages.info(request, "No changes made. Statuses may already be up to date.")

            # Auto-reconcile newly linked tracking IDs
            reconciled = _perform_reconciliation()
            if reconciled:
                messages.success(request, f"Auto-reconciled {reconciled} scan(s) using new tracking IDs.")

        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")

    return redirect('orders_list')


@login_required
@user_passes_test(is_admin)
def update_order_status(request, pk):
    if request.method == 'POST':
        order = get_object_or_404(Order, pk=pk)
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '').strip()
        if new_status in dict(Order.STATUS_CHOICES):
            order.status = new_status
            if notes:
                order.notes = notes
            order.save()
    return redirect(request.POST.get('next', 'orders_list'))


@login_required
@user_passes_test(is_admin)
def bulk_update_status(request):
    if request.method == 'POST':
        pks = request.POST.getlist('selected_orders')
        new_status = request.POST.get('bulk_status')
        if pks and new_status in dict(Order.STATUS_CHOICES):
            updated = Order.objects.filter(pk__in=pks).update(status=new_status)
            messages.success(request, f"{updated} orders updated to '{new_status}'.")
        else:
            messages.error(request, "Select orders and a valid status.")
    return redirect('orders_list')


@login_required
def export_orders_csv(request):
    q = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    qs = Order.objects.prefetch_related('scans').all()
    if q:
        qs = qs.filter(Q(order_id__icontains=q) | Q(email__icontains=q) | Q(product__icontains=q))
    if status_filter:
        qs = qs.filter(status=status_filter)
    if date_from:
        qs = qs.filter(order_date__gte=date_from)
    if date_to:
        qs = qs.filter(order_date__lte=date_to)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Email', 'Product', 'Order Date', 'Status', 'Amazon Status',
                     'Amazon Tracking ID(s)', 'Scanned Tracking ID(s)', 'First Scan Time', 'Notes'])
    for o in qs:
        scans = list(o.scans.order_by('scanned_at'))
        first_scan_time = timezone.localtime(scans[0].scanned_at).strftime('%Y-%m-%d %H:%M:%S') if scans else ''
        scanned_ids = ', '.join(s.tracking_id for s in scans)
        writer.writerow([
            o.order_id, o.email, o.product,
            o.order_date.strftime('%d-%m-%Y') if o.order_date else '',
            o.get_status_display(), o.amazon_status, o.amazon_tracking_id,
            scanned_ids, first_scan_time, o.notes
        ])
    return response


@login_required
@user_passes_test(is_admin)
def download_orders_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['EMAIL', 'ORDER ID', 'PRODUCT', 'ORDER DATE'])
    writer.writerow(['example@gmail.com', '403-1234567-8901234', 'Fujifilm Instax Mini 11', '30-11-2025'])
    return response


@login_required
@user_passes_test(is_admin)
def download_amazon_report_template(request):
    """Sample Amazon order report format so user knows what to upload"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="amazon_report_sample.csv"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Order Date', 'Order Status', 'Tracking Number', 'Carrier Name', 'Product Name'])
    writer.writerow(['403-1234567-8901234', '30-11-2025', 'Delivered', 'TBA847392749', 'Amazon', 'Fujifilm Instax Mini 11'])
    writer.writerow(['402-9876543-2109876', '30-11-2025', 'Cancelled', '', '', 'Philips Trimmer'])
    return response


@login_required
def product_summary(request):
    """Per-product breakdown with status counts"""
    products = (
        Order.objects.values('product')
        .annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            received=Count('id', filter=Q(status='received')),
            delivered=Count('id', filter=Q(status='delivered')),
            cancelled=Count('id', filter=Q(status='cancelled')),
            returned=Count('id', filter=Q(status='returned')),
            issue=Count('id', filter=Q(status='issue')),
        )
        .order_by('-total')
    )
    return render(request, 'scanner/product_summary.html', {'products': products})


def _perform_reconciliation():
    """
    Match unlinked PackageScan records to Orders:
    1. By order_id stored on the scan
    2. By tracking_id matching any of the comma-separated amazon_tracking_id values on Order
    Multiple scans can link to the same order (multi-unit deliveries).
    """
    matched_count = 0

    # Pass 1: match by order_id on the scan
    unlinked_by_order = PackageScan.objects.filter(
        linked_order__isnull=True
    ).exclude(order_id='')

    for scan in unlinked_by_order:
        try:
            order = Order.objects.get(order_id=scan.order_id)
            scan.linked_order = order
            scan.save(update_fields=['linked_order'])
            if order.status == 'pending':
                order.status = 'received'
                order.save(update_fields=['status'])
            matched_count += 1
        except (Order.DoesNotExist, Order.MultipleObjectsReturned):
            continue

    # Pass 2: match by tracking_id vs amazon_tracking_id (comma-separated)
    still_unlinked = PackageScan.objects.filter(linked_order__isnull=True)
    # Build a lookup: tracking_id → order for all orders that have amazon_tracking_id set
    orders_with_tracking = Order.objects.exclude(amazon_tracking_id='')
    tracking_to_order = {}
    for order in orders_with_tracking:
        for tid in order.amazon_tracking_id.split(','):
            tid = tid.strip()
            if tid:
                tracking_to_order[tid] = order

    for scan in still_unlinked:
        order = tracking_to_order.get(scan.tracking_id)
        if order:
            scan.linked_order = order
            if not scan.order_id:
                scan.order_id = order.order_id
            scan.save(update_fields=['linked_order', 'order_id'])
            if order.status == 'pending':
                order.status = 'received'
                order.save(update_fields=['status'])
            matched_count += 1

    return matched_count


@login_required
@user_passes_test(is_admin)
def reconcile_orders(request):
    matched_count = _perform_reconciliation()
    if matched_count > 0:
        messages.success(request, f"Successfully reconciled {matched_count} order(s).")
    else:
        messages.info(request, "No unlinked scans matched with pending orders.")
    return redirect('orders_list')


@login_required
@user_passes_test(is_admin)
def bulk_update_order_ids(request):
    if request.method == 'POST':
        data = request.POST.get('data', '').strip()
        if not data:
            messages.error(request, "No data provided.")
            return redirect('records')

        lines = data.split('\n')
        updated_count = 0
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                tracking_id = parts[0].strip()
                order_id = parts[1].strip()
                updated = PackageScan.objects.filter(tracking_id=tracking_id, order_id='').update(order_id=order_id)
                updated_count += updated

        if updated_count > 0:
            reconciled = _perform_reconciliation()
            msg = f"Updated {updated_count} scan(s)."
            if reconciled > 0:
                msg += f" Automatically reconciled {reconciled} order(s)."
            messages.success(request, msg)
        else:
            messages.info(request, "No matching scans found to update.")

    return redirect('records')
