# ▣ TrackGuard — Package Evidence System

A lightweight local web app to scan and log delivery package tracking IDs with timestamps.
Built for matching scans against CCTV footage in dispute cases.

---

## Setup (One Time)

**Requirements:** Python 3.10+

```bash
# 1. Install Django
pip install django

# 2. Run database migrations
python manage.py migrate

# 3. (Optional) Create admin user
python manage.py createsuperuser
```

---

## Start the App

```bash
# Option A — use the startup script
bash start.sh

# Option B — manually
python manage.py runserver
```

Then open: **http://localhost:8000**

---

## How to Use

### Scanning Packages
1. Open `http://localhost:8000` in your browser
2. The tracking ID input is always auto-focused
3. Point your USB barcode scanner at the package barcode
4. Scanner types the ID and presses Enter — auto-saved instantly
5. Optionally fill: Order ID, Courier, Notes before scanning

### Viewing Records
- Go to `/records/` — shows all scans with search + date filter
- Each record shows: ID, Tracking ID, Order ID, Courier, **Timestamp (IST)**, Notes

### Matching with CCTV
- Every scan records exact IST timestamp (date + HH:MM:SS)
- Use that timestamp to jump to the exact CCTV footage moment
- Export to CSV to build your evidence file

### Exporting
- Click **⬇ Export CSV** from any page
- CSV columns: ID, Tracking ID, Order ID, Courier, Notes, Scanned At
- Filters (search/date) apply to exports too

---

## Project Structure

```
trackguard/
├── scanner/
│   ├── models.py       # PackageScan model
│   ├── views.py        # Scan, Records, Export, Delete
│   ├── urls.py
│   └── templates/scanner/
│       ├── base.html
│       ├── index.html  # Scanner UI
│       └── records.html
├── trackguard/
│   ├── settings.py     # SQLite, Asia/Kolkata timezone
│   └── urls.py
├── db.sqlite3          # Auto-created database
└── start.sh            # Quick start script
```

---

## Tips

- **Courier auto-detect**: Amazon tracking IDs start with `TBA`, Delhivery with `B2B`/`D`
- **Multiple deliveries same day**: All are timestamped separately — no conflicts
- **Backup your DB**: Just copy `db.sqlite3` to a safe location

---

## Dispute Evidence Workflow

1. Package arrives → scan barcode immediately
2. Note any damage in the Notes field
3. If package goes missing later → search by tracking ID
4. Get exact timestamp from record
5. Pull CCTV footage at that timestamp
6. Export CSV as documentary evidence
