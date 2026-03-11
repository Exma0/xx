"""
Tam Yetkili Linux Masaüstü + Minecraft Panel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VNC Desktop  → PORT (websockify)
  MC Panel     → 8080 (Flask+SocketIO)
  MC Server    → 25565 (auto-start)
  CF Tunnel    → 8080'i internete açar
"""

import os, sys, subprocess, time, shutil, socket, resource, threading, re

PORT       = os.environ.get("PORT", "5000")
DISPLAY    = ":1"
RESOLUTION = os.environ.get("RESOLUTION", "1280x720")
VNC_PORT   = "5901"
NOVNC_DIR  = "/usr/share/novnc"
HOME       = "/root"
PANEL_PORT = 8080

env = {
    **os.environ,
    "DISPLAY": DISPLAY, "HOME": HOME, "USER": "root", "LOGNAME": "root",
    "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "SHELL": "/bin/bash",
    "JAVA_HOME": "/usr/lib/jvm/java-21-openjdk-amd64",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
}

tunnel_url = ""   # Cloudflare tunnel URL (panel için)


def write(path, val):
    try:
        with open(path, "w") as f: f.write(str(val))
        return True
    except Exception:
        return False


def wait_port(port, timeout=30):
    for _ in range(timeout * 10):
        try:
            s = socket.create_connection(("127.0.0.1", int(port)), 0.1)
            s.close(); return True
        except OSError:
            time.sleep(0.1)
    return False


# ══════════════════════════════════════════════════════
def optimize():
    print("⚡ Sistem optimizasyonları...")
    for res, val in [
        (resource.RLIMIT_NOFILE,  (1048576, 1048576)),
        (resource.RLIMIT_NPROC,   (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
        (resource.RLIMIT_STACK,   (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
    ]:
        try: resource.setrlimit(res, val)
        except Exception: pass

    params = {
        "/proc/sys/vm/swappiness": "1",
        "/proc/sys/vm/overcommit_memory": "1",
        "/proc/sys/vm/vfs_cache_pressure": "50",
        "/proc/sys/vm/dirty_ratio": "60",
        "/proc/sys/kernel/sched_rt_runtime_us": "-1",
        "/proc/sys/kernel/perf_event_paranoid": "-1",
        "/proc/sys/fs/file-max": "2097152",
        "/proc/sys/fs/inotify/max_user_watches": "524288",
        "/proc/sys/net/core/rmem_max": "134217728",
        "/proc/sys/net/core/wmem_max": "134217728",
        "/proc/sys/net/core/somaxconn": "65535",
        "/proc/sys/net/ipv4/tcp_fastopen": "3",
    }
    ok = sum(1 for p, v in params.items() if write(p, v))
    print(f"  ✅ {ok} kernel parametresi")

    import glob
    for gov in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
        write(gov, "performance")
    for dev in glob.glob("/sys/block/*/queue/scheduler"):
        for s in ["none", "mq-deadline"]:
            if write(dev, s): break

    for tgt, sz in [("/tmp", "512m"), ("/var/tmp", "256m")]:
        os.makedirs(tgt, exist_ok=True)
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", tgt,
                        "-o", f"defaults,noatime,size={sz}"], capture_output=True)
    write("/proc/sys/vm/drop_caches", "1")
    print("  ✅ Optimizasyon tamam")


# ══════════════════════════════════════════════════════
def start_vnc():
    w = RESOLUTION.split("x")[0]
    h = RESOLUTION.split("x")[1] if "x" in RESOLUTION else "720"
    for f in [f"/tmp/.X{DISPLAY[1:]}-lock", f"/tmp/.X11-unix/X{DISPLAY[1:]}"]:
        try: os.remove(f)
        except FileNotFoundError: pass

    print(f"[1/5] TigerVNC {DISPLAY} ({w}×{h})...")
    subprocess.Popen([
        "vncserver", DISPLAY,
        "-geometry", f"{w}x{h}", "-depth", "24",
        "-rfbport", VNC_PORT, "-localhost", "yes",
        "-SecurityTypes", "None", "-fg",
        "-xstartup", f"{HOME}/.vnc/xstartup",
        "-AlwaysShared", "-ZlibLevel", "1",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if wait_port(VNC_PORT, 25):
        print("  ✅ TigerVNC hazır")
    else:
        print("  ⚠️  TigerVNC başlıyor...")


# ══════════════════════════════════════════════════════
def start_mc_panel():
    """MC panelini arka planda başlat"""
    print(f"[2/5] Minecraft Panel :{PANEL_PORT} başlatılıyor...")
    subprocess.Popen(
        [sys.executable, "/app/mc_panel.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    if wait_port(PANEL_PORT, 20):
        print("  ✅ MC Panel hazır")
    else:
        print("  ⚠️  MC Panel başlıyor...")


# ══════════════════════════════════════════════════════
def start_cloudflare_tunnel():
    """Panel için Cloudflare tunnel başlat ve URL al"""
    global tunnel_url
    print(f"[3/5] Cloudflare Tunnel :{PANEL_PORT} → internet...")
    log_file = "/tmp/cf_panel.log"

    proc = subprocess.Popen([
        "cloudflared", "tunnel",
        "--url", f"http://localhost:{PANEL_PORT}",
        "--no-autoupdate", "--loglevel", "info",
    ], stdout=open(log_file, "w"), stderr=subprocess.STDOUT)

    # URL'i bekle (max 30 sn)
    for _ in range(60):
        try:
            with open(log_file) as f:
                content = f.read()
            urls = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
            if urls:
                tunnel_url = urls[0]
                print(f"  ✅ Panel URL: {tunnel_url}")
                return tunnel_url
        except Exception:
            pass
        time.sleep(0.5)

    print("  ⚠️  Tunnel URL alınamadı")
    return ""


# ══════════════════════════════════════════════════════
def write_index():
    """Ana sayfa — panel URL ile"""
    w = RESOLUTION.split("x")[0]
    h = RESOLUTION.split("x")[1] if "x" in RESOLUTION else "720"
    panel = tunnel_url or f"http://localhost:{PANEL_PORT}"

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linux Masaüstü</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#05060c;--s1:#0b0d16;--a1:#00e5ff;--a2:#7c6aff;--a3:#00ffaa;--a4:#ff6b35;
  --green:#2ed573;--t1:#eef0f8;--t2:#8892a4;--t3:#3d4558;--font:'Sora',sans-serif;--mono:'JetBrains Mono',monospace;}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{min-height:100vh;background:var(--bg);color:var(--t1);font-family:var(--font)}}
.aurora{{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}}
.a1{{position:absolute;width:700px;height:600px;top:-150px;left:-100px;border-radius:50%;
  filter:blur(90px);opacity:.1;background:radial-gradient(circle,var(--a1),var(--a2),transparent);
  animation:drift 14s ease-in-out infinite alternate}}
.a2{{position:absolute;width:600px;height:500px;bottom:-100px;right:-100px;border-radius:50%;
  filter:blur(90px);opacity:.09;background:radial-gradient(circle,var(--a3),var(--a1),transparent);
  animation:drift 11s ease-in-out infinite alternate-reverse}}
@keyframes drift{{0%{{transform:translate(0,0)}}100%{{transform:translate(60px,50px)}}}}
.page{{position:relative;z-index:1;max-width:980px;margin:0 auto;padding:48px 22px 40px}}
.hdr{{text-align:center;margin-bottom:44px}}
.logo{{font-size:72px;display:block;margin-bottom:14px;filter:drop-shadow(0 0 18px var(--a1));
  animation:gp 3s ease-in-out infinite alternate}}
@keyframes gp{{0%{{filter:drop-shadow(0 0 10px #00e5ff30)}}100%{{filter:drop-shadow(0 0 38px #00e5ffaa)}}}}
h1{{font-size:40px;font-weight:700;margin-bottom:8px;
  background:linear-gradient(135deg,var(--a1),var(--a2),var(--a3));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:var(--t2);font-size:14px;line-height:1.8}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.card{{background:var(--s1);border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:24px;
  display:flex;flex-direction:column;gap:14px}}
.card-icon{{font-size:40px;text-align:center}}
.card-title{{font-size:18px;font-weight:700;text-align:center}}
.card-desc{{font-size:13px;color:var(--t2);text-align:center;line-height:1.7}}
.btn-big{{padding:14px 28px;border-radius:12px;font-size:15px;font-weight:700;border:none;
  cursor:pointer;font-family:var(--font);transition:all .2s;text-decoration:none;
  display:block;text-align:center}}
.btn-vnc{{background:linear-gradient(135deg,var(--a1),var(--a2));color:#000}}
.btn-vnc:hover{{transform:translateY(-2px);box-shadow:0 14px 40px #00e5ff40}}
.btn-mc{{background:linear-gradient(135deg,var(--a3),#00a550);color:#000}}
.btn-mc:hover{{transform:translateY(-2px);box-shadow:0 14px 40px #00ffaa40}}
.btn-row{{display:flex;gap:8px;flex-wrap:wrap}}
.btn-sm{{padding:7px 14px;border-radius:8px;font-size:12px;font-weight:600;
  background:rgba(255,255,255,.06);color:var(--t1);border:1px solid rgba(255,255,255,.1);
  cursor:pointer;text-decoration:none;transition:all .15s}}
.btn-sm:hover{{background:rgba(255,255,255,.1)}}
.mc-url{{background:rgba(0,255,170,.06);border:1px solid rgba(0,255,170,.2);
  border-radius:10px;padding:12px 16px;font-family:var(--mono);font-size:13px;
  color:var(--a3);word-break:break-all;margin-top:4px}}
.foot{{text-align:center;color:var(--t3);font-size:11px;padding:20px 0;font-family:var(--mono)}}
</style>
</head>
<body>
<div class="aurora"><div class="a1"></div><div class="a2"></div></div>
<div class="page">
  <div class="hdr">
    <span class="logo">🐧</span>
    <h1>Linux Masaüstü</h1>
    <p class="sub">Ubuntu 22.04 · TigerVNC · Fluxbox · Java 21 · Minecraft Panel</p>
  </div>

  <div class="cards">
    <div class="card">
      <div class="card-icon">🖥️</div>
      <div class="card-title">Grafik Masaüstü</div>
      <div class="card-desc">Gerçek Linux masaüstü.<br>Terminal, Chromium, Geany IDE, Dosya gezgini ve daha fazlası.</div>
      <a class="btn-big btn-vnc" href="/vnc.html?autoconnect=true&resize=scale&quality=7&compression=3&reconnect=true">
        🖥️ Masaüstüne Bağlan
      </a>
      <div class="btn-row">
        <a class="btn-sm" href="/vnc.html?autoconnect=true&resize=scale&quality=9&compression=0">⚡ Max Kalite</a>
        <a class="btn-sm" href="/vnc.html?autoconnect=true&resize=scale&quality=3&compression=9">💾 Düşük Bant</a>
        <a class="btn-sm" href="/vnc.html?autoconnect=true&resize=scale&view_only=true">👁 İzle</a>
      </div>
    </div>

    <div class="card">
      <div class="card-icon">⛏️</div>
      <div class="card-title">Minecraft Yönetim Paneli</div>
      <div class="card-desc">Paper MC otomatik kurulu ve çalışıyor.<br>Konsol · Oyuncular · Pluginler · Dosyalar · Ayarlar</div>
      <a class="btn-big btn-mc" href="{panel}" target="_blank">
        ⛏️ MC Panelini Aç
      </a>
      <div style="font-size:12px;color:var(--t2)">Panel URL:</div>
      <div class="mc-url">{panel}</div>
    </div>
  </div>

  <div class="foot">Ubuntu 22.04 · TigerVNC · Fluxbox · Paper MC · Cloudflare Tunnel · Render.com</div>
</div>
</body>
</html>
"""
    try:
        os.makedirs(NOVNC_DIR, exist_ok=True)
        with open(os.path.join(NOVNC_DIR, "index.html"), "w") as f:
            f.write(html)
        print("  ✅ Ana sayfa yazıldı")
    except Exception as e:
        print(f"  ⚠️  {e}")


# ══════════════════════════════════════════════════════
def start_websockify():
    ws = shutil.which("websockify") or "/usr/bin/websockify"
    print(f"[5/5] websockify :{PORT} başlatılıyor...")
    print(f"  → VNC Desktop: http://0.0.0.0:{PORT}/")
    print(f"  → MC Panel:    {tunnel_url or f'http://localhost:{PANEL_PORT}'}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    os.execv(ws, ["websockify", "--web", NOVNC_DIR,
                  "--heartbeat", "30", PORT, f"127.0.0.1:{VNC_PORT}"])


# ══════════════════════════════════════════════════════
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🚀  Linux Masaüstü + Minecraft Panel")
print(f"      PORT={PORT} | {RESOLUTION}")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

print("\n⚡ [A] Optimizasyon...")
optimize()

print("\n🖥️  [B] VNC...")
start_vnc()

print("\n⛏️  [C] Minecraft Panel...")
start_mc_panel()

print("\n🌐 [D] Cloudflare Tunnel...")
start_cloudflare_tunnel()

print("\n📄 [E] Ana sayfa...")
write_index()

start_websockify()
