#!/bin/bash
# TrackGuard - Package Evidence System
# Run this script to start the local server

cd "$(dirname "$0")"

echo ""
echo "  ▣ TRACKGUARD - Package Evidence System"
echo "  ─────────────────────────────────────"
echo ""
echo "  Starting server at: http://localhost:8000"
echo "  Press Ctrl+C to stop"
echo ""

python manage.py runserver 0.0.0.0:8000
