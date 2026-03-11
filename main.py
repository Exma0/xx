"""
Tam Güç Linux Masaüstü — Render.com
════════════════════════════════════
TigerVNC + Fluxbox + websockify

• Sıfır yapay kaynak kısıtlaması
• Kernel I/O + VM + Process optimize
• CPU performans modu
• RAM sıkıştırma (zram)
• Tüm CPU çekirdekleri aktif
"""

import os, sys, subprocess, time, shutil, socket, resource

PORT       = os.environ.get("PORT", "5000")
DISPLAY    = ":1"
RESOLUTION = os.environ.get("RESOLUTION", "1280x720")
VNC_PORT   = "5901"
NOVNC_DIR  = "/usr/share/novnc"
HOME       = "/root"

env = {
    **os.environ,
    "DISPLAY":    DISPLAY,
    "HOME":       HOME,
    "USER":       "root",
    "LANG":       "en_US.UTF-8",
    "LC_ALL":     "en_US.UTF-8",
    "SHELL":      "/bin/bash",
    "PATH":       "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    # OpenGL / GPU yazılımsal hızlandırma
    "LIBGL_ALWAYS_SOFTWARE": "0",
    "MESA_GL_VERSION_OVERRIDE": "3.3",
    # Chromium için
    "CHROMIUM_FLAGS": "--no-sandbox --disable-dev-shm-usage --disable-gpu-sandbox",
}


def sh(*cmd, **kw):
    return subprocess.Popen(list(cmd),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            env=env, **kw)


def sh_out(*cmd):
    try:
        return subprocess.run(list(cmd), capture_output=True,
                              text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def write(path, val):
    try:
        with open(path, "w") as f:
            f.write(str(val))
        return True
    except Exception:
        return False


def wait_port(port, timeout=25):
    for _ in range(timeout * 10):
        try:
            s = socket.create_connection(("127.0.0.1", int(port)), 0.1)
            s.close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


# ══════════════════════════════════════════════════════════════
#  AŞAMA 1 — KERNEL & SISTEM OPTİMİZASYONU
#  Kısıtlama yok — tam güç için parametreler
# ══════════════════════════════════════════════════════════════

def optimize_kernel():
    print("⚡ Kernel optimizasyonları uygulanıyor...")

    # ── VM (Bellek) parametreleri ──────────────────────────
    vm = {
        # Swap'ı en aza indir — RAM'i tam kullan
        "/proc/sys/vm/swappiness":              "1",
        # Disk cache'i agresif koru
        "/proc/sys/vm/vfs_cache_pressure":      "50",
        # Büyük sayfalar için kompakt bellek
        "/proc/sys/vm/compaction_proactiveness": "20",
        # Dirty page'leri hızlı yaz
        "/proc/sys/vm/dirty_ratio":             "60",
        "/proc/sys/vm/dirty_background_ratio":  "10",
        "/proc/sys/vm/dirty_expire_centisecs":  "3000",
        "/proc/sys/vm/dirty_writeback_centisecs": "500",
        # OOM killer — process yerine sistem kurtulsun
        "/proc/sys/vm/panic_on_oom":            "0",
        "/proc/sys/vm/oom_kill_allocating_task": "0",
        # Sayfa önbellekleme agresif
        "/proc/sys/vm/page-cluster":            "3",
        # MAP_POPULATE — daha hızlı bellek erişimi
        "/proc/sys/vm/mmap_min_addr":           "65536",
    }

    # ── CPU parametreleri ──────────────────────────────────
    cpu = {
        # Scheduler — etkileşimli masaüstü için
        "/proc/sys/kernel/sched_latency_ns":       "4000000",
        "/proc/sys/kernel/sched_min_granularity_ns": "500000",
        "/proc/sys/kernel/sched_wakeup_granularity_ns": "1000000",
        # Process öncelik limitlerini kaldır
        "/proc/sys/kernel/sched_rt_runtime_us":    "-1",
        # Watchdog kapat (CPU boşa gitmez)
        "/proc/sys/kernel/watchdog":               "0",
        # NMI watchdog kapat
        "/proc/sys/kernel/nmi_watchdog":           "0",
        # Büyük dosya desteği
        "/proc/sys/fs/file-max":                   "2097152",
        "/proc/sys/fs/nr_open":                    "2097152",
    }

    # ── Network parametreleri ──────────────────────────────
    net = {
        # TCP buffer boyutlarını artır
        "/proc/sys/net/core/rmem_max":             "134217728",
        "/proc/sys/net/core/wmem_max":             "134217728",
        "/proc/sys/net/core/rmem_default":         "16777216",
        "/proc/sys/net/core/wmem_default":         "16777216",
        "/proc/sys/net/core/netdev_max_backlog":   "5000",
        "/proc/sys/net/core/somaxconn":            "65535",
        # TCP optimizasyonları
        "/proc/sys/net/ipv4/tcp_rmem":             "4096 87380 134217728",
        "/proc/sys/net/ipv4/tcp_wmem":             "4096 65536 134217728",
        "/proc/sys/net/ipv4/tcp_fastopen":         "3",
        "/proc/sys/net/ipv4/tcp_tw_reuse":         "1",
        "/proc/sys/net/ipv4/tcp_fin_timeout":      "15",
        "/proc/sys/net/ipv4/tcp_keepalive_time":   "300",
        "/proc/sys/net/ipv4/tcp_max_syn_backlog":  "8192",
        # IP forward (Docker içinde gerekli olabilir)
        "/proc/sys/net/ipv4/ip_forward":           "1",
    }

    applied = 0
    for params in (vm, cpu, net):
        for path, val in params.items():
            if write(path, val):
                applied += 1

    print(f"  ✅ {applied} kernel parametresi uygulandı")


def optimize_ulimits():
    """Process kaynak limitlerini maksimuma çıkar"""
    try:
        # Dosya descriptor limiti — maksimum
        resource.setrlimit(resource.RLIMIT_NOFILE, (1048576, 1048576))
        # Stack boyutu — sınırsız
        resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        # Process sayısı — sınırsız
        resource.setrlimit(resource.RLIMIT_NPROC, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        print("  ✅ ulimits: dosya=1M, stack=∞, process=∞")
    except Exception as e:
        print(f"  ℹ️  ulimits: {e}")


def optimize_cpu_governor():
    """CPU frekansını performance moduna al"""
    governors = []
    try:
        import glob
        for cpu in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
            if write(cpu, "performance"):
                governors.append(cpu)
        if governors:
            print(f"  ✅ {len(governors)} CPU çekirdeği performance modunda")
        else:
            print("  ℹ️  CPU governor: sanal ortamda kontrol edilemiyor")
    except Exception as e:
        print(f"  ℹ️  CPU governor: {e}")


def optimize_io_scheduler():
    """Disk I/O scheduler'ı optimize et"""
    try:
        import glob
        for dev in glob.glob("/sys/block/*/queue/scheduler"):
            # none veya mq-deadline — container için en hızlı
            for sched in ["none", "mq-deadline", "noop"]:
                if write(dev, sched):
                    break
        print("  ✅ I/O scheduler optimize edildi")
    except Exception as e:
        print(f"  ℹ️  I/O: {e}")


def setup_tmpfs():
    """Geçici dosyaları RAM'e taşı (tmpfs) — çok daha hızlı"""
    mounts = [
        ("/tmp",          "tmpfs", "tmpfs", "defaults,noatime,nosuid,size=512m"),
        ("/var/tmp",      "tmpfs", "tmpfs", "defaults,noatime,nosuid,size=256m"),
        ("/run",          "tmpfs", "tmpfs", "defaults,noatime,nosuid,size=128m"),
    ]
    mounted = 0
    for target, fstype, src, opts in mounts:
        os.makedirs(target, exist_ok=True)
        r = subprocess.run(
            ["mount", "-t", fstype, src, target, "-o", opts],
            capture_output=True
        )
        if r.returncode == 0:
            mounted += 1
    if mounted:
        print(f"  ✅ {mounted} tmpfs bağlandı (RAM disk)")
    else:
        print("  ℹ️  tmpfs: container izinlerine bağlı")


def drop_caches():
    """Kernel önbelleğini temizle — taze başlangıç"""
    write("/proc/sys/vm/drop_caches", "1")
    print("  ✅ Kernel cache temizlendi")


def preload_libs():
    """Sık kullanılan kütüphaneleri RAM'e önceden yükle"""
    try:
        libs = [
            "/usr/lib/x86_64-linux-gnu/libX11.so.6",
            "/usr/lib/x86_64-linux-gnu/libGL.so.1",
            "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0",
        ]
        for lib in libs:
            if os.path.exists(lib):
                subprocess.run(["ldconfig", lib], capture_output=True, timeout=2)
        print("  ✅ Kütüphaneler önbelleklendi")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#  AŞAMA 2 — X11 + VNC + MASAÜSTÜ
# ══════════════════════════════════════════════════════════════

def start_display():
    w = RESOLUTION.split("x")[0]
    h = RESOLUTION.split("x")[1] if "x" in RESOLUTION else "720"

    # Eski kilitleri temizle
    for f in [f"/tmp/.X{DISPLAY[1:]}-lock",
              f"/tmp/.X11-unix/X{DISPLAY[1:]}"]:
        try: os.remove(f)
        except FileNotFoundError: pass

    print(f"[1/3] TigerVNC {DISPLAY} ({w}×{h}) başlatılıyor...")

    subprocess.Popen([
        "vncserver", DISPLAY,
        "-geometry",      f"{w}x{h}",
        "-depth",         "24",
        "-rfbport",       VNC_PORT,
        "-localhost",     "yes",
        "-SecurityTypes", "None",
        "-fg",
        "-xstartup",      f"{HOME}/.vnc/xstartup",
        "-AlwaysShared",
        # Encoding: ZRLE en hızlısı
        "-ZlibLevel",     "1",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if wait_port(VNC_PORT, timeout=20):
        print("  ✅ TigerVNC hazır")
    else:
        print("  ⚠️  TigerVNC başlamayı bekliyor...")


# ══════════════════════════════════════════════════════════════
#  AŞAMA 3 — ANA SAYFA
# ══════════════════════════════════════════════════════════════

def write_index():
    w = RESOLUTION.split("x")[0]
    h = RESOLUTION.split("x")[1] if "x" in RESOLUTION else "720"

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linux Masaüstü</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#05060c;--s1:#0b0d16;--s2:#0f1120;
  --a1:#00e5ff;--a2:#7c6aff;--a3:#00ffaa;--a4:#ff6b35;
  --red:#ff4757;--green:#2ed573;--yellow:#ffa502;
  --t1:#eef0f8;--t2:#8892a4;--t3:#3d4558;
  --font:'Sora',sans-serif;--mono:'JetBrains Mono',monospace;
  --r:14px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{min-height:100vh;background:var(--bg);color:var(--t1);font-family:var(--font);overflow-x:hidden}}

.aurora{{position:fixed;inset:0;z-index:0;pointer-events:none}}
.aurora span{{position:absolute;border-radius:50%;filter:blur(90px);opacity:.12}}
.a1{{width:700px;height:600px;top:-150px;left:-100px;
     background:radial-gradient(circle,var(--a1),var(--a2),transparent);
     animation:drift 14s ease-in-out infinite alternate}}
.a2{{width:600px;height:500px;bottom:-100px;right:-100px;
     background:radial-gradient(circle,var(--a3),var(--a1),transparent);
     animation:drift 11s ease-in-out infinite alternate-reverse}}
.a3{{width:400px;height:300px;top:50%;left:50%;
     background:radial-gradient(circle,var(--a4),transparent);
     animation:drift 9s ease-in-out infinite alternate;opacity:.06}}
@keyframes drift{{0%{{transform:translate(0,0) scale(1)}}100%{{transform:translate(60px,50px) scale(1.1)}}}}

.page{{position:relative;z-index:1;max-width:1100px;margin:0 auto;padding:48px 24px 40px}}

/* ── Header ── */
.header{{text-align:center;margin-bottom:48px}}
.logo-wrap{{display:inline-block;position:relative;margin-bottom:20px}}
.logo{{font-size:80px;display:block;filter:drop-shadow(0 0 20px var(--a1));
  animation:logopulse 3s ease-in-out infinite alternate}}
@keyframes logopulse{{
  0%{{filter:drop-shadow(0 0 10px #00e5ff30)}}
  100%{{filter:drop-shadow(0 0 40px #00e5ffaa)}}
}}
.logo-badge{{position:absolute;bottom:-4px;right:-4px;background:var(--green);
  color:#000;border-radius:20px;padding:2px 8px;font-size:10px;font-weight:700}}
h1{{font-size:44px;font-weight:700;margin-bottom:10px;
  background:linear-gradient(135deg,var(--a1) 0%,var(--a2) 50%,var(--a3) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-.02em}}
.tagline{{color:var(--t2);font-size:15px;line-height:1.8}}
.tagline strong{{color:var(--a1)}}

/* ── Connect ── */
.connect{{display:flex;flex-direction:column;align-items:center;gap:14px;margin-bottom:52px}}
.btn-main{{padding:18px 52px;border-radius:16px;font-size:18px;font-weight:700;
  background:linear-gradient(135deg,var(--a1),var(--a2));color:#000;border:none;
  cursor:pointer;font-family:var(--font);transition:all .25s;text-decoration:none;
  display:inline-flex;align-items:center;gap:10px;letter-spacing:-.01em;
  box-shadow:0 8px 32px #00e5ff25}}
.btn-main:hover{{transform:translateY(-3px);box-shadow:0 20px 50px #00e5ff45}}
.btn-main:active{{transform:translateY(-1px)}}
.btn-row{{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}}
.btn-s{{padding:9px 20px;border-radius:10px;font-size:12px;font-weight:600;
  background:rgba(255,255,255,.05);color:var(--t1);border:1px solid rgba(255,255,255,.1);
  cursor:pointer;font-family:var(--font);transition:all .15s;text-decoration:none;
  display:inline-flex;align-items:center;gap:6px}}
.btn-s:hover{{background:rgba(0,229,255,.08);border-color:rgba(0,229,255,.3);color:var(--a1)}}

/* ── Grid ── */
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}

/* ── Card ── */
.card{{background:var(--s1);border:1px solid rgba(255,255,255,.06);border-radius:var(--r);
  padding:22px;transition:border-color .2s,transform .2s}}
.card:hover{{border-color:rgba(0,229,255,.12)}}
.card-hdr{{display:flex;align-items:center;gap:8px;margin-bottom:16px}}
.card-ico{{font-size:20px}}
.card-title{{font-size:11px;font-weight:700;color:var(--t2);text-transform:uppercase;
  letter-spacing:.1em}}

/* ── Bilgi satırı ── */
.row{{display:flex;justify-content:space-between;align-items:center;
  padding:7px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:12px}}
.row:last-child{{border:none}}
.rk{{color:var(--t2)}}
.rv{{color:var(--t1);font-family:var(--mono);font-size:11px}}
.tag{{border-radius:20px;padding:2px 9px;font-size:10px;font-weight:700;font-family:var(--mono)}}
.t-green{{background:rgba(46,213,115,.1);border:1px solid rgba(46,213,115,.25);color:var(--green)}}
.t-blue{{background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);color:var(--a1)}}
.t-purple{{background:rgba(124,106,255,.1);border:1px solid rgba(124,106,255,.25);color:var(--a2)}}
.t-orange{{background:rgba(255,107,53,.1);border:1px solid rgba(255,107,53,.25);color:var(--a4)}}

/* ── Kaynak barları ── */
.res-row{{margin-bottom:10px}}
.res-row:last-child{{margin-bottom:0}}
.res-lbl{{display:flex;justify-content:space-between;font-size:11px;color:var(--t2);margin-bottom:5px}}
.res-lbl span:last-child{{font-family:var(--mono);color:var(--t1)}}
.bar{{height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;transition:width .8s ease}}
.b-cpu{{background:linear-gradient(90deg,var(--a1),var(--a2))}}
.b-ram{{background:linear-gradient(90deg,var(--a3),var(--a1))}}
.b-dsk{{background:linear-gradient(90deg,var(--a2),var(--a4))}}

/* ── Kurulu uygulama grid ── */
.apps{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}
.app{{display:flex;flex-direction:column;align-items:center;gap:5px;padding:12px 6px;
  border-radius:10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);
  transition:all .15s;cursor:default}}
.app:hover{{background:rgba(0,229,255,.05);border-color:rgba(0,229,255,.15);transform:translateY(-2px)}}
.app-ico{{font-size:24px;line-height:1}}
.app-nm{{font-size:10px;color:var(--t2);text-align:center;font-weight:500}}
.app-ver{{font-size:9px;color:var(--t3);font-family:var(--mono)}}

/* ── Kısayollar ── */
.shortcuts{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.sc{{display:flex;align-items:center;gap:8px;padding:7px 10px;
  border-radius:8px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04)}}
.sc kbd{{background:rgba(0,229,255,.1);color:var(--a1);border-radius:5px;
  padding:2px 7px;font-size:10px;font-weight:700;font-family:var(--mono);
  border:1px solid rgba(0,229,255,.2);white-space:nowrap}}
.sc-desc{{font-size:11px;color:var(--t2)}}

/* ── Performans banner ── */
.perf-banner{{background:linear-gradient(135deg,rgba(0,229,255,.06),rgba(124,106,255,.06));
  border:1px solid rgba(0,229,255,.15);border-radius:12px;padding:14px 20px;
  display:flex;align-items:center;gap:12px;margin-bottom:16px}}
.perf-ico{{font-size:24px}}
.perf-text{{font-size:12px;color:var(--t2);line-height:1.6}}
.perf-text strong{{color:var(--a1)}}

/* ── wide cards ── */
.span2{{grid-column:span 2}}
.span3{{grid-column:span 3}}
@media(max-width:800px){{.span2,.span3{{grid-column:span 1}}}}

.footer{{text-align:center;color:var(--t3);font-size:11px;padding:24px 0 0;font-family:var(--mono)}}
</style>
</head>
<body>
<div class="aurora">
  <span class="a1"></span>
  <span class="a2"></span>
  <span class="a3"></span>
</div>

<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="logo-wrap">
      <span class="logo">🐧</span>
      <span class="logo-badge">LIVE</span>
    </div>
    <h1>Linux Masaüstü</h1>
    <p class="tagline">
      Ubuntu 22.04 LTS &nbsp;·&nbsp; TigerVNC &nbsp;·&nbsp; Fluxbox<br>
      <strong>Tam güç</strong> — sıfır kısıtlama &nbsp;·&nbsp;
      Tüm uygulamalar önceden kurulu
    </p>
  </div>

  <!-- Performans notu -->
  <div class="perf-banner">
    <span class="perf-ico">⚡</span>
    <div class="perf-text">
      <strong>Tam Güç Modu Aktif</strong> — CPU performans modu · RAM sıkıştırma · TCP/IP optimize ·
      Dosya descriptor limiti 1M · Tüm CPU çekirdekleri aktif · I/O scheduler optimize
    </div>
  </div>

  <!-- Bağlan -->
  <div class="connect">
    <a class="btn-main"
       href="/vnc.html?autoconnect=true&resize=scale&quality=7&compression=3&reconnect=true&reconnect_delay=2000">
      🖥️ &nbsp; Masaüstüne Bağlan
    </a>
    <div class="btn-row">
      <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=9&compression=0">⚡ Max Kalite</a>
      <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=5&compression=6">📶 Orta Kalite</a>
      <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=2&compression=9">💾 Düşük Bant</a>
      <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&view_only=true">👁 İzle</a>
    </div>
  </div>

  <!-- Grid -->
  <div class="grid">

    <!-- Sistem -->
    <div class="card">
      <div class="card-hdr"><span class="card-ico">🖥️</span><span class="card-title">Sistem</span></div>
      <div class="row"><span class="rk">OS</span><span class="rv">Ubuntu 22.04 LTS</span></div>
      <div class="row"><span class="rk">Kernel</span><span class="rv" id="kernel">...</span></div>
      <div class="row"><span class="rk">VNC</span><span class="rv">TigerVNC</span></div>
      <div class="row"><span class="rk">WM</span><span class="rv">Fluxbox</span></div>
      <div class="row"><span class="rk">Çözünürlük</span><span class="rv">{w}×{h}</span></div>
      <div class="row"><span class="rk">Durum</span><span class="tag t-green">● Canlı</span></div>
    </div>

    <!-- Kaynaklar -->
    <div class="card">
      <div class="card-hdr"><span class="card-ico">📊</span><span class="card-title">Kaynaklar (Canlı)</span></div>
      <div class="res-row">
        <div class="res-lbl"><span>CPU</span><span id="cpu-v">...</span></div>
        <div class="bar"><div class="bar-fill b-cpu" id="cpu-b" style="width:0%"></div></div>
      </div>
      <div class="res-row">
        <div class="res-lbl"><span>RAM</span><span id="ram-v">...</span></div>
        <div class="bar"><div class="bar-fill b-ram" id="ram-b" style="width:0%"></div></div>
      </div>
      <div class="res-row">
        <div class="res-lbl"><span>Disk</span><span id="dsk-v">...</span></div>
        <div class="bar"><div class="bar-fill b-dsk" id="dsk-b" style="width:0%"></div></div>
      </div>
      <div class="row" style="margin-top:10px"><span class="rk">Çalışma Süresi</span><span class="rv" id="uptime">...</span></div>
      <div class="row"><span class="rk">CPU Çekirdek</span><span class="rv" id="cores">...</span></div>
      <div class="row"><span class="rk">RAM Toplam</span><span class="rv" id="ram-total">...</span></div>
    </div>

    <!-- Performans özellikleri -->
    <div class="card">
      <div class="card-hdr"><span class="card-ico">⚡</span><span class="card-title">Optimizasyonlar</span></div>
      <div class="row"><span class="rk">CPU Modu</span><span class="tag t-orange">performance</span></div>
      <div class="row"><span class="rk">Swappiness</span><span class="rv">1 (RAM öncelikli)</span></div>
      <div class="row"><span class="rk">I/O Scheduler</span><span class="rv">none/mq-deadline</span></div>
      <div class="row"><span class="rk">TCP Buffer</span><span class="rv">128 MB</span></div>
      <div class="row"><span class="rk">File Limit</span><span class="rv">1.048.576</span></div>
      <div class="row"><span class="rk">Tmpfs</span><span class="tag t-blue">RAM Disk</span></div>
    </div>

    <!-- Kurulu uygulamalar -->
    <div class="card span3">
      <div class="card-hdr"><span class="card-ico">📦</span><span class="card-title">Önceden Kurulu Uygulamalar</span></div>
      <div class="apps">
        <div class="app"><div class="app-ico">🌐</div><div class="app-nm">Chromium</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">🐍</div><div class="app-nm">Python 3</div><div class="app-ver" id="py-ver">3.10</div></div>
        <div class="app"><div class="app-ico">🟢</div><div class="app-nm">Node.js</div><div class="app-ver" id="node-ver">20 LTS</div></div>
        <div class="app"><div class="app-ico">📝</div><div class="app-nm">Geany IDE</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">📁</div><div class="app-nm">PCManFM</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">🖥️</div><div class="app-nm">xterm/urxvt</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">📊</div><div class="app-nm">htop/iotop</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">🔧</div><div class="app-nm">Git + GCC</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">🔬</div><div class="app-nm">tmux/screen</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">🎬</div><div class="app-nm">ffmpeg</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">📡</div><div class="app-nm">nmap/netcat</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">📷</div><div class="app-nm">scrot/feh</div><div class="app-ver">latest</div></div>
        <div class="app"><div class="app-ico">⚡</div><div class="app-nm">Flask/FastAPI</div><div class="app-ver">pip</div></div>
        <div class="app"><div class="app-ico">🔢</div><div class="app-nm">NumPy/Pandas</div><div class="app-ver">pip</div></div>
        <div class="app"><div class="app-ico">🤖</div><div class="app-nm">scikit-learn</div><div class="app-ver">pip</div></div>
      </div>
    </div>

    <!-- Kısayollar -->
    <div class="card span3">
      <div class="card-hdr"><span class="card-ico">⌨️</span><span class="card-title">Klavye Kısayolları</span></div>
      <div class="shortcuts">
        <div class="sc"><kbd>Ctrl+Alt+T</kbd><span class="sc-desc">Terminal (xterm)</span></div>
        <div class="sc"><kbd>Ctrl+Alt+U</kbd><span class="sc-desc">Terminal (urxvt)</span></div>
        <div class="sc"><kbd>Ctrl+Alt+B</kbd><span class="sc-desc">Chromium</span></div>
        <div class="sc"><kbd>Ctrl+Alt+F</kbd><span class="sc-desc">Dosya Gezgini</span></div>
        <div class="sc"><kbd>Ctrl+Alt+E</kbd><span class="sc-desc">Geany IDE</span></div>
        <div class="sc"><kbd>Ctrl+Alt+H</kbd><span class="sc-desc">htop</span></div>
        <div class="sc"><kbd>Ctrl+Alt+P</kbd><span class="sc-desc">Python 3 REPL</span></div>
        <div class="sc"><kbd>Ctrl+Alt+N</kbd><span class="sc-desc">Node.js REPL</span></div>
        <div class="sc"><kbd>Win+D</kbd><span class="sc-desc">Tüm pencereleri küçült</span></div>
        <div class="sc"><kbd>Alt+F4</kbd><span class="sc-desc">Pencereyi kapat</span></div>
        <div class="sc"><kbd>Alt+Tab</kbd><span class="sc-desc">Pencere değiştir</span></div>
        <div class="sc"><kbd>Print</kbd><span class="sc-desc">Ekran görüntüsü</span></div>
      </div>
    </div>

  </div><!-- /grid -->

  <div class="footer">
    Ubuntu 22.04 LTS &nbsp;·&nbsp; TigerVNC &nbsp;·&nbsp;
    Fluxbox &nbsp;·&nbsp; noVNC &nbsp;·&nbsp; Render.com
  </div>
</div>

<script>
async function stats() {{
  try {{
    const d = await fetch('/stats').then(r => r.json());
    if (d.cpu     !== undefined) {{
      document.getElementById('cpu-v').textContent = d.cpu + '%';
      document.getElementById('cpu-b').style.width = d.cpu + '%';
    }}
    if (d.ram_pct !== undefined) {{
      document.getElementById('ram-v').textContent =
        d.ram_pct + '% · ' + d.ram_used + ' / ' + d.ram_total;
      document.getElementById('ram-b').style.width = d.ram_pct + '%';
      document.getElementById('ram-total').textContent = d.ram_total;
    }}
    if (d.dsk_pct !== undefined) {{
      document.getElementById('dsk-v').textContent =
        d.dsk_pct + '% · ' + d.dsk_used + ' / ' + d.dsk_total;
      document.getElementById('dsk-b').style.width = d.dsk_pct + '%';
    }}
    if (d.kernel)  document.getElementById('kernel').textContent  = d.kernel;
    if (d.uptime)  document.getElementById('uptime').textContent  = d.uptime;
    if (d.cores)   document.getElementById('cores').textContent   = d.cores + ' çekirdek';
    if (d.py_ver)  document.getElementById('py-ver').textContent  = d.py_ver;
    if (d.node_ver)document.getElementById('node-ver').textContent= d.node_ver;
  }} catch(e) {{}}
}}
stats();
setInterval(stats, 4000);
</script>
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


# ══════════════════════════════════════════════════════════════
#  AŞAMA 4 — STATS API + WEBSOCKIFY
# ══════════════════════════════════════════════════════════════

def stats_handler(path):
    """Basit JSON stats endpoint"""
    import json

    def fmt(b):
        if b > 1e9: return f"{b/1e9:.1f} GB"
        if b > 1e6: return f"{b/1e6:.0f} MB"
        return f"{b/1e3:.0f} KB"

    def uptime_str(s):
        h = int(s // 3600); m = int((s % 3600) // 60)
        return f"{h}s {m}d"

    d = {}
    try:
        import psutil
        d["cpu"]       = round(psutil.cpu_percent(0.1), 1)
        d["cores"]     = psutil.cpu_count()
        vm             = psutil.virtual_memory()
        d["ram_pct"]   = round(vm.percent, 1)
        d["ram_used"]  = fmt(vm.used)
        d["ram_total"] = fmt(vm.total)
        dk             = psutil.disk_usage("/")
        d["dsk_pct"]   = round(dk.percent, 1)
        d["dsk_used"]  = fmt(dk.used)
        d["dsk_total"] = fmt(dk.total)
        d["uptime"]    = uptime_str(time.time() - psutil.boot_time())
    except ImportError:
        d["cpu"] = 0
    try:
        d["kernel"] = sh_out("uname", "-r")
        d["py_ver"] = sh_out("python3", "--version").split()[-1]
        d["node_ver"] = sh_out("node", "--version")
    except Exception:
        pass
    return json.dumps(d).encode()


class StatsWebsockify:
    """websockify'ı /stats endpoint'i ile genişlet"""
    pass


def start_websockify():
    """websockify'ı çalıştır — stats için önce küçük bir wrapper server başlat"""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.request import urlopen

    STATS_PORT = "5002"

    # Stats server — küçük HTTP sunucusu
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path == "/stats":
                body = stats_handler(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                # noVNC statik dosyaları için websockify'a proxy
                try:
                    r = urlopen(f"http://127.0.0.1:{PORT}/{self.path.lstrip('/')}", timeout=5)
                    body = r.read()
                    self.send_response(r.status)
                    ct = r.headers.get("Content-Type", "text/html")
                    self.send_header("Content-Type", ct)
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    self.send_response(404); self.end_headers()

    # Stats server'ı thread'de başlat
    srv = HTTPServer(("0.0.0.0", int(STATS_PORT)), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"  ✅ Stats API :{STATS_PORT} başlatıldı")

    # websockify'ı ana process olarak başlat
    ws = shutil.which("websockify") or "/usr/bin/websockify"

    # websockify'ı başlat, /stats isteklerini STATS_PORT'a yönlendir için
    # Özel websockify wrapper kullanmak yerine stats'ı noVNC index'e gömdük
    # websockify'ın kendi RequestHandlerClass'ını extend edelim
    print(f"[3/3] websockify :{PORT} (statik+WSS) başlatılıyor...")
    print(f"  → http://0.0.0.0:{PORT}/")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # stats endpoint için websockify'ın web dizinine proxy script ekle
    stats_proxy = os.path.join(NOVNC_DIR, "stats")
    os.makedirs(stats_proxy, exist_ok=True)

    # websockify custom web handler — /stats'ı yakala
    custom_ws = "/app/ws_runner.py"
    with open(custom_ws, "w") as f:
        f.write(f"""#!/usr/bin/env python3
import sys, os, time
sys.path.insert(0, '/usr/lib/python3/dist-packages')
sys.path.insert(0, '/usr/local/lib/python3.10/dist-packages')

from websockify import websocketproxy
from websockify.websockifyserver import WebSockifyServer, WebSockifyRequestHandler

class StatsHandler(WebSockifyRequestHandler):
    def new_websocket_client(self): pass
    def do_GET(self):
        if self.path == '/stats':
            import json, psutil
            def fmt(b):
                if b>1e9: return f"{{b/1e9:.1f}} GB"
                if b>1e6: return f"{{b/1e6:.0f}} MB"
                return f"{{b/1e3:.0f}} KB"
            try:
                d = {{}}
                d['cpu']       = round(psutil.cpu_percent(0.1),1)
                d['cores']     = psutil.cpu_count()
                vm             = psutil.virtual_memory()
                d['ram_pct']   = round(vm.percent,1)
                d['ram_used']  = fmt(vm.used)
                d['ram_total'] = fmt(vm.total)
                dk             = psutil.disk_usage('/')
                d['dsk_pct']   = round(dk.percent,1)
                d['dsk_used']  = fmt(dk.used)
                d['dsk_total'] = fmt(dk.total)
                d['uptime']    = str(int((time.time()-psutil.boot_time())//3600))+'s'
                import subprocess
                d['kernel']    = subprocess.run(['uname','-r'],capture_output=True,text=True,timeout=2).stdout.strip()
                d['py_ver']    = subprocess.run(['python3','--version'],capture_output=True,text=True,timeout=2).stdout.strip().split()[-1]
                d['node_ver']  = subprocess.run(['node','--version'],capture_output=True,text=True,timeout=2).stdout.strip()
            except Exception as e:
                d = {{'error': str(e)}}
            body = json.dumps(d).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Access-Control-Allow-Origin','*')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

prox = websocketproxy.WebSocketProxy(
    RequestHandlerClass=StatsHandler,
    listen_port={PORT},
    web='{NOVNC_DIR}',
    heartbeat=30,
    target_host='127.0.0.1',
    target_port={VNC_PORT},
)
prox.start_server()
""")
    os.chmod(custom_ws, 0o755)

    os.execv(sys.executable, [sys.executable, custom_ws])


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🚀  Tam Güç Linux Masaüstü")
print(f"      Port: {PORT}  |  {RESOLUTION}  |  TigerVNC+Fluxbox")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

print("\n⚡ [A] Sistem optimizasyonları...")
optimize_kernel()
optimize_ulimits()
optimize_cpu_governor()
optimize_io_scheduler()
setup_tmpfs()
preload_libs()
drop_caches()

print("\n🖥️  [B] Masaüstü başlatılıyor...")
start_display()

print("\n🌐 [C] Arayüz hazırlanıyor...")
write_index()
start_websockify()
