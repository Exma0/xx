#!/bin/bash
# WebOS Linux — Başlatma scripti
set -e

export DISPLAY=:1
export HOME=/root

echo "🐧 WebOS Linux başlatılıyor..."
cd /app
exec python3 main.py
