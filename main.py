"""
Gerçek Linux Masaüstü — Render.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mimari:
  Python → Xvfb + Openbox + x11vnc başlatır
  → websockify PORT'ta dinler (hem noVNC statik hem WebSocket)
  → Render.com'un tek portuna doğrudan bağlı

Bu yaklaşım Render.com HTTPS/WSS ile tam uyumludur.
"""

import os
import sys
import subprocess
import time
import shutil

DISPLAY    = os.environ.get("DISPLAY", ":1")
PORT       = os.environ.get("PORT", "5000")
RESOLUTION = os.environ.get("RESOLUTION", "1280x720")
VNC_PORT   = "5900"
NOVNC_DIR  = "/usr/share/novnc"

env = {**os.environ, "DISPLAY": DISPLAY, "HOME": "/root"}

def run(cmd, **kw):
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **kw)

def wait_for_display(timeout=10):
    for _ in range(timeout * 4):
        r = subprocess.run(["xdpyinfo", "-display", DISPLAY],
                           capture_output=True)
        if r.returncode == 0:
            return True
        time.sleep(0.25)
    return False

def wait_for_port(port, timeout=15):
    import socket
    for _ in range(timeout * 4):
        try:
            s = socket.create_connection(("127.0.0.1", int(port)), 0.3)
            s.close()
            return True
        except OSError:
            time.sleep(0.25)
    return False

# ══════════════════════════════════════════════════════════
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🐧  Gerçek Linux Masaüstü — Başlatılıyor")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# ── 1. Xvfb ──────────────────────────────────────────────
w, h = (RESOLUTION + "x24").split("x")[:2]
print(f"[1/5] Xvfb {DISPLAY} ({w}x{h}) başlatılıyor...")
run(["Xvfb", DISPLAY,
     "-screen", "0", f"{w}x{h}x24",
     "-ac", "+render", "+extension", "RANDR", "-noreset"])

if not wait_for_display():
    print("  ❌ Xvfb başlatılamadı!")
    sys.exit(1)
print("  ✅ Xvfb hazır")

# ── 2. Masaüstü arka planı ───────────────────────────────
subprocess.run(["xsetroot", "-solid", "#0e1117"],
               env=env, capture_output=True)

# ── 3. Openbox ───────────────────────────────────────────
print("[2/5] Openbox başlatılıyor...")
run(["openbox", "--display", DISPLAY], env=env)
time.sleep(1.5)
print("  ✅ Openbox hazır")

# ── 4. İlk terminal ──────────────────────────────────────
print("[3/5] xterm açılıyor...")
run(["xterm",
     "-bg", "#0e1117", "-fg", "#e2e8f0",
     "-fa", "Monospace", "-fs", "12",
     "-geometry", "100x30+50+50",
     "-title", "Terminal — Linux Masaüstü"],
    env=env)
time.sleep(0.5)

# ── 5. x11vnc ────────────────────────────────────────────
print(f"[4/5] x11vnc :{VNC_PORT} başlatılıyor...")
run(["x11vnc",
     "-display", DISPLAY,
     "-forever",
     "-nopw",
     "-shared",
     "-rfbport", VNC_PORT,
     "-quiet",
     "-noxrecord",
     "-noxfixes",
     "-noxdamage",
     "-permitfiletransfer",
     "-desktop", "Linux Masaüstü"],
    env=env)

if not wait_for_port(VNC_PORT):
    print("  ⚠️  x11vnc başlatılamadı, devam ediliyor...")
else:
    print("  ✅ x11vnc hazır")

# ── 6. Özel noVNC index sayfası ──────────────────────────
custom_index = """\
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linux Masaüstü</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#06070d;color:#e8eaf0;font-family:'Sora',sans-serif;min-height:100vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px;padding:20px}
.glow{position:fixed;inset:0;z-index:-1;
  background:radial-gradient(ellipse at 30% 50%,#00e5ff08,transparent 55%),
             radial-gradient(ellipse at 75% 25%,#7c6aff08,transparent 55%)}
.logo{font-size:80px;animation:g 3s ease-in-out infinite alternate}
@keyframes g{0%{filter:drop-shadow(0 0 12px #00e5ff50)}100%{filter:drop-shadow(0 0 36px #00e5ffaa)}}
h1{font-size:38px;font-weight:700;
  background:linear-gradient(135deg,#00e5ff,#7c6aff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center}
.sub{color:#8892a4;font-size:14px;text-align:center;line-height:1.8;max-width:440px}
.card{background:#0f1119;border:1px solid #ffffff0e;border-radius:16px;padding:22px 26px;
  width:100%;max-width:480px;display:flex;flex-direction:column;gap:2px}
.row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;
  border-bottom:1px solid #ffffff06;font-size:13px}
.row:last-child{border:none}
.k{color:#8892a4}.v{color:#00e5ff;font-weight:600}
.badge{background:rgba(46,213,115,.12);border:1px solid rgba(46,213,115,.3);
  color:#2ed573;border-radius:20px;padding:3px 12px;font-size:11px;font-weight:700}
.btns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.btn{padding:14px 32px;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;
  border:none;transition:all .2s;text-decoration:none;font-family:'Sora',sans-serif;
  display:inline-flex;align-items:center;gap:8px}
.primary{background:linear-gradient(135deg,#00e5ff,#7c6aff);color:#000}
.primary:hover{transform:translateY(-2px);box-shadow:0 14px 35px #00e5ff40}
.sec{background:rgba(255,255,255,.06);color:#e8eaf0;border:1px solid rgba(255,255,255,.1)}
.sec:hover{background:rgba(255,255,255,.11)}
.apps{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;max-width:480px}
.ab{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#c9d1d9;
  border-radius:10px;padding:8px 14px;font-size:12px;cursor:pointer;transition:all .15s;
  font-family:inherit}
.ab:hover{background:rgba(255,255,255,.1);color:#fff;border-color:rgba(0,229,255,.3)}
</style>
</head>
<body>
<div class="glow"></div>
<div class="logo">🐧</div>
<h1>Linux Masaüstü</h1>
<p class="sub">Ubuntu 22.04 LTS üzerinde gerçek X11 masaüstü.<br>
Openbox · Xvfb · x11vnc · noVNC</p>

<div class="btns">
  <a class="btn primary" href="/vnc.html?autoconnect=true&resize=scale&quality=7&compression=2">
    🖥️ Masaüstüne Bağlan
  </a>
  <a class="btn sec" href="/vnc.html?autoconnect=true&resize=scale&view_only=true">
    👁 Sadece İzle
  </a>
</div>

<div class="card">
  <div class="row"><span class="k">İşletim Sistemi</span><span class="v">Ubuntu 22.04 LTS</span></div>
  <div class="row"><span class="k">Pencere Yöneticisi</span><span class="v">Openbox</span></div>
  <div class="row"><span class="k">Protokol</span><span class="v">VNC → WSS (noVNC)</span></div>
  <div class="row"><span class="k">Çözünürlük</span><span class="v">1280 × 720</span></div>
  <div class="row"><span class="k">Durum</span><span class="badge">● Canlı</span></div>
</div>

<p style="color:#4a5568;font-size:12px;text-align:center">
  Sağ tık → Menü &nbsp;|&nbsp;
  Ctrl+Alt+T → Terminal &nbsp;|&nbsp;
  Ctrl+Alt+F → Dosyalar
</p>
</body>
</html>
"""

try:
    os.makedirs(NOVNC_DIR, exist_ok=True)
    with open(os.path.join(NOVNC_DIR, "index.html"), "w") as f:
        f.write(custom_index)
    print("  ✅ Özel ana sayfa oluşturuldu")
except Exception as e:
    print(f"  ⚠️  Ana sayfa yazılamadı: {e}")

# ── 7. websockify — PORT üzerinde hem statik hem WS ──────
print(f"\n[5/5] websockify :{PORT} başlatılıyor (statik + WebSocket)...")
print(f"  → http://0.0.0.0:{PORT}/")
print(f"  → Masaüstü: http://0.0.0.0:{PORT}/vnc.html?autoconnect=true")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

# os.execv ile mevcut process'i websockify ile değiştir
# Bu sayede Render.com'un port kontrolü doğru çalışır
websockify = shutil.which("websockify") or "/usr/bin/websockify"

os.execv(websockify, [
    "websockify",
    "--web", NOVNC_DIR,
    "--heartbeat", "30",
    "--log-file", "/dev/null",
    PORT,
    f"127.0.0.1:{VNC_PORT}",
])
