#!/bin/bash
# WebOS Linux — Başlatma scripti
set -e

export DISPLAY=:1
export HOME=/root

echo "🐧 WebOS Linux başlatılıyor..."

# Masaüstü ortamını (XFCE) arka planda başlat
startxfce4 &

cd /app
exec python3 main.py
