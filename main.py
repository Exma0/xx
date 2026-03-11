"""
Tam Yetkili Linux Masaüstü — Render.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Tam root yetkisi — sıfır kısıtlama
• TigerVNC şifresiz (SecurityTypes=None)
• Fluxbox ultra hafif WM
• Tüm CPU/RAM/Disk tam güçte
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
    "LOGNAME":    "root",
    "LANG":       "en_US.UTF-8",
    "LC_ALL":     "en_US.UTF-8",
    "SHELL":      "/bin/bash",
    "PATH":       "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "DBUS_SESSION_BUS_ADDRESS": "disabled:",
}


def sh(*cmd, **kw):
    return subprocess.Popen(
        list(cmd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env, **kw
    )


def sh_out(*cmd):
    try:
        return subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=3
        ).stdout.strip()
    except Exception:
        return ""


def write(path, val):
    try:
        with open(path, "w") as f:
            f.write(str(val))
        return True
    except Exception:
        return False


def wait_port(port, timeout=30):
    for _ in range(timeout * 10):
        try:
            s = socket.create_connection(("127.0.0.1", int(port)), 0.1)
            s.close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


# ══════════════════════════════════════════════════════════
#  SİSTEM OPTİMİZASYONU — Kısıtlama yok, tam güç
# ══════════════════════════════════════════════════════════

def optimize():
    print("⚡ Sistem optimizasyonları...")

    # ulimits — tüm limitleri kaldır
    for res, val in [
        (resource.RLIMIT_NOFILE,  (1048576, 1048576)),
        (resource.RLIMIT_NPROC,   (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
        (resource.RLIMIT_STACK,   (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
        (resource.RLIMIT_CORE,    (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
        (resource.RLIMIT_MEMLOCK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY)),
    ]:
        try:
            resource.setrlimit(res, val)
        except Exception:
            pass
    print("  ✅ ulimits: sınırsız")

    # Kernel VM — RAM'i tam kullan
    vm_params = {
        "/proc/sys/vm/swappiness":               "1",
        "/proc/sys/vm/vfs_cache_pressure":       "50",
        "/proc/sys/vm/dirty_ratio":              "60",
        "/proc/sys/vm/dirty_background_ratio":   "10",
        "/proc/sys/vm/overcommit_memory":        "1",   # bellek aşımına izin ver
        "/proc/sys/vm/overcommit_ratio":         "100",
        "/proc/sys/vm/oom_kill_allocating_task": "0",
        "/proc/sys/vm/panic_on_oom":             "0",
    }
    ok = sum(1 for p, v in vm_params.items() if write(p, v))
    print(f"  ✅ VM params: {ok}/{len(vm_params)}")

    # CPU scheduler — masaüstü için düşük gecikme
    cpu_params = {
        "/proc/sys/kernel/sched_latency_ns":         "4000000",
        "/proc/sys/kernel/sched_min_granularity_ns": "500000",
        "/proc/sys/kernel/sched_wakeup_granularity_ns": "1000000",
        "/proc/sys/kernel/sched_rt_runtime_us":      "-1",  # RT sınırı kaldır
        "/proc/sys/kernel/perf_event_paranoid":      "-1",  # perf tam erişim
        "/proc/sys/kernel/kptr_restrict":            "0",   # kernel pointer tam
        "/proc/sys/fs/file-max":                     "2097152",
        "/proc/sys/fs/nr_open":                      "2097152",
        "/proc/sys/fs/inotify/max_user_watches":     "524288",
        "/proc/sys/fs/inotify/max_user_instances":   "8192",
    }
    ok = sum(1 for p, v in cpu_params.items() if write(p, v))
    print(f"  ✅ CPU/FS params: {ok}/{len(cpu_params)}")

    # CPU governor — performance modu
    import glob
    gov_ok = 0
    for gov in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
        if write(gov, "performance"):
            gov_ok += 1
    if gov_ok:
        print(f"  ✅ {gov_ok} CPU çekirdeği: performance modu")

    # I/O scheduler
    io_ok = 0
    for dev in glob.glob("/sys/block/*/queue/scheduler"):
        for s in ["none", "mq-deadline", "noop"]:
            if write(dev, s):
                io_ok += 1
                break
    if io_ok:
        print(f"  ✅ {io_ok} disk: I/O optimize")

    # Network TCP buffer
    net_params = {
        "/proc/sys/net/core/rmem_max":           "134217728",
        "/proc/sys/net/core/wmem_max":           "134217728",
        "/proc/sys/net/core/netdev_max_backlog": "5000",
        "/proc/sys/net/core/somaxconn":          "65535",
        "/proc/sys/net/ipv4/tcp_fastopen":       "3",
        "/proc/sys/net/ipv4/tcp_tw_reuse":       "1",
        "/proc/sys/net/ipv4/tcp_fin_timeout":    "15",
    }
    ok = sum(1 for p, v in net_params.items() if write(p, v))
    print(f"  ✅ Network params: {ok}/{len(net_params)}")

    # Tmpfs — /tmp'yi RAM'e al
    for tgt, size in [("/tmp", "512m"), ("/var/tmp", "256m")]:
        try:
            os.makedirs(tgt, exist_ok=True)
            r = subprocess.run(
                ["mount", "-t", "tmpfs", "tmpfs", tgt, "-o",
                 f"defaults,noatime,nosuid,size={size}"],
                capture_output=True, timeout=5
            )
            if r.returncode == 0:
                print(f"  ✅ {tgt} → tmpfs ({size} RAM)")
        except Exception:
            pass

    # Cache temizle
    write("/proc/sys/vm/drop_caches", "1")
    print("  ✅ Kernel cache temizlendi")


# ══════════════════════════════════════════════════════════
#  VNC + MASAÜSTÜ BAŞLATMA
# ══════════════════════════════════════════════════════════

def start_vnc():
    w = RESOLUTION.split("x")[0]
    h = RESOLUTION.split("x")[1] if "x" in RESOLUTION else "720"

    # Eski kilitleri temizle
    for f in [
        f"/tmp/.X{DISPLAY[1:]}-lock",
        f"/tmp/.X11-unix/X{DISPLAY[1:]}",
    ]:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    print(f"[1/3] TigerVNC {DISPLAY} ({w}×{h}) başlatılıyor...")

    # ÖNEMLİ: -rfbauth YOK — SecurityTypes=None ile şifresiz
    subprocess.Popen([
        "vncserver",
        DISPLAY,
        "-geometry",      f"{w}x{h}",
        "-depth",         "24",
        "-rfbport",       VNC_PORT,
        "-localhost",     "yes",
        "-SecurityTypes", "None",
        "-fg",
        "-xstartup",      f"{HOME}/.vnc/xstartup",
        "-AlwaysShared",
        "-ZlibLevel",     "1",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if wait_port(VNC_PORT, timeout=25):
        print("  ✅ TigerVNC hazır")
    else:
        print("  ⚠️  TigerVNC başlamayı bekliyor (devam)...")


# ══════════════════════════════════════════════════════════
#  ANA SAYFA
# ══════════════════════════════════════════════════════════

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
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{min-height:100vh;background:var(--bg);color:var(--t1);font-family:var(--font);overflow-x:hidden}}
.aurora{{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}}
.a1{{position:absolute;width:700px;height:600px;top:-150px;left:-100px;border-radius:50%;
  filter:blur(90px);opacity:.1;
  background:radial-gradient(circle,var(--a1),var(--a2),transparent);
  animation:drift 14s ease-in-out infinite alternate}}
.a2{{position:absolute;width:600px;height:500px;bottom:-100px;right:-100px;border-radius:50%;
  filter:blur(90px);opacity:.09;
  background:radial-gradient(circle,var(--a3),var(--a1),transparent);
  animation:drift 11s ease-in-out infinite alternate-reverse}}
@keyframes drift{{0%{{transform:translate(0,0)}}100%{{transform:translate(60px,50px)}}}}
.page{{position:relative;z-index:1;max-width:1060px;margin:0 auto;padding:44px 22px 36px}}
.hdr{{text-align:center;margin-bottom:44px}}
.logo{{font-size:76px;display:block;margin-bottom:16px;
  filter:drop-shadow(0 0 20px var(--a1));
  animation:gp 3s ease-in-out infinite alternate}}
@keyframes gp{{0%{{filter:drop-shadow(0 0 10px #00e5ff30)}}100%{{filter:drop-shadow(0 0 38px #00e5ffaa)}}}}
h1{{font-size:42px;font-weight:700;margin-bottom:10px;
  background:linear-gradient(135deg,var(--a1),var(--a2),var(--a3));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:var(--t2);font-size:14px;line-height:1.8}}
.sub b{{color:var(--a1)}}
.conn{{display:flex;flex-direction:column;align-items:center;gap:14px;margin-bottom:48px}}
.btn-main{{padding:17px 50px;border-radius:15px;font-size:17px;font-weight:700;
  background:linear-gradient(135deg,var(--a1),var(--a2));color:#000;border:none;
  cursor:pointer;font-family:var(--font);transition:all .25s;text-decoration:none;
  display:inline-flex;align-items:center;gap:10px;
  box-shadow:0 8px 32px #00e5ff25}}
.btn-main:hover{{transform:translateY(-3px);box-shadow:0 20px 50px #00e5ff45}}
.btn-row{{display:flex;gap:9px;flex-wrap:wrap;justify-content:center}}
.btn-s{{padding:8px 18px;border-radius:9px;font-size:12px;font-weight:600;
  background:rgba(255,255,255,.05);color:var(--t1);
  border:1px solid rgba(255,255,255,.1);cursor:pointer;font-family:var(--font);
  transition:all .15s;text-decoration:none;display:inline-flex;align-items:center;gap:5px}}
.btn-s:hover{{background:rgba(0,229,255,.08);border-color:rgba(0,229,255,.3);color:var(--a1)}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px}}
@media(max-width:780px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:var(--s1);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:20px}}
.card:hover{{border-color:rgba(0,229,255,.12)}}
.ch{{display:flex;align-items:center;gap:8px;margin-bottom:14px}}
.ci{{font-size:18px}}
.ct{{font-size:11px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.1em}}
.row{{display:flex;justify-content:space-between;align-items:center;
  padding:7px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:12px}}
.row:last-child{{border:none}}
.rk{{color:var(--t2)}}.rv{{color:var(--t1);font-family:var(--mono);font-size:11px}}
.tag{{border-radius:20px;padding:2px 9px;font-size:10px;font-weight:700;font-family:var(--mono)}}
.tg{{background:rgba(46,213,115,.1);border:1px solid rgba(46,213,115,.25);color:var(--green)}}
.tb{{background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);color:var(--a1)}}
.tr{{background:rgba(255,71,87,.1);border:1px solid rgba(255,71,87,.25);color:var(--red)}}
.to{{background:rgba(255,107,53,.1);border:1px solid rgba(255,107,53,.25);color:var(--a4)}}
.rl{{display:flex;justify-content:space-between;font-size:11px;color:var(--t2);margin-bottom:5px}}
.bar{{height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden;margin-bottom:10px}}
.bf{{height:100%;border-radius:3px;transition:width .8s}}
.bc{{background:linear-gradient(90deg,var(--a1),var(--a2))}}
.bm{{background:linear-gradient(90deg,var(--a3),var(--a1))}}
.bd{{background:linear-gradient(90deg,var(--a2),var(--a4))}}
.apps{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}
.app{{display:flex;flex-direction:column;align-items:center;gap:5px;padding:11px 4px;
  border-radius:10px;background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.05);transition:all .15s}}
.app:hover{{background:rgba(0,229,255,.05);border-color:rgba(0,229,255,.15);transform:translateY(-2px)}}
.ai{{font-size:22px;line-height:1}}
.an{{font-size:10px;color:var(--t2);text-align:center;font-weight:500}}
.av{{font-size:9px;color:var(--t3);font-family:var(--mono)}}
.scs{{display:grid;grid-template-columns:1fr 1fr;gap:7px}}
.sc{{display:flex;align-items:center;gap:7px;padding:6px 10px;
  border-radius:7px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04)}}
.sc kbd{{background:rgba(0,229,255,.1);color:var(--a1);border-radius:4px;
  padding:1px 6px;font-size:10px;font-weight:700;font-family:monospace;
  border:1px solid rgba(0,229,255,.2);white-space:nowrap}}
.sd{{font-size:11px;color:var(--t2)}}
.priv{{background:linear-gradient(135deg,rgba(255,71,87,.06),rgba(255,107,53,.06));
  border:1px solid rgba(255,71,87,.2);border-radius:12px;padding:13px 18px;
  display:flex;align-items:center;gap:10px;margin-bottom:14px;font-size:12px;color:var(--t2)}}
.priv b{{color:var(--red)}}
.sp2{{grid-column:span 2}}
.sp3{{grid-column:span 3}}
@media(max-width:780px){{.sp2,.sp3{{grid-column:span 1}}}}
.foot{{text-align:center;color:var(--t3);font-size:11px;padding:20px 0;font-family:var(--mono)}}
</style>
</head>
<body>
<div class="aurora"><div class="a1"></div><div class="a2"></div></div>
<div class="page">

<div class="hdr">
  <span class="logo">🐧</span>
  <h1>Linux Masaüstü</h1>
  <p class="sub">Ubuntu 22.04 LTS &nbsp;·&nbsp; TigerVNC &nbsp;·&nbsp; Fluxbox<br>
  <b>Tam root yetkisi</b> — sıfır kısıtlama — tüm uygulamalar kurulu</p>
</div>

<div class="priv">
  <span style="font-size:20px">🔓</span>
  <div><b>Tam Yetki Modu:</b> root · sudo · NOPASSWD · ulimit sınırsız ·
  perf_event_paranoid=-1 · kptr_restrict=0 · sched_rt_runtime=-1</div>
</div>

<div class="conn">
  <a class="btn-main"
     href="/vnc.html?autoconnect=true&resize=scale&quality=7&compression=3&reconnect=true&reconnect_delay=2000">
    🖥️ &nbsp; Masaüstüne Bağlan
  </a>
  <div class="btn-row">
    <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=9&compression=0">⚡ Max Kalite</a>
    <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=5&compression=5">📶 Orta</a>
    <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&quality=2&compression=9">💾 Düşük Bant</a>
    <a class="btn-s" href="/vnc.html?autoconnect=true&resize=scale&view_only=true">👁 İzle</a>
  </div>
</div>

<div class="grid">

  <div class="card">
    <div class="ch"><span class="ci">🖥️</span><span class="ct">Sistem</span></div>
    <div class="row"><span class="rk">OS</span><span class="rv">Ubuntu 22.04 LTS</span></div>
    <div class="row"><span class="rk">Kernel</span><span class="rv" id="kern">...</span></div>
    <div class="row"><span class="rk">VNC</span><span class="rv">TigerVNC</span></div>
    <div class="row"><span class="rk">WM</span><span class="rv">Fluxbox</span></div>
    <div class="row"><span class="rk">Çözünürlük</span><span class="rv">{w}×{h}</span></div>
    <div class="row"><span class="rk">Yetki</span><span class="tag tr">🔓 root / FULL</span></div>
    <div class="row"><span class="rk">Durum</span><span class="tag tg">● Canlı</span></div>
  </div>

  <div class="card">
    <div class="ch"><span class="ci">📊</span><span class="ct">Kaynaklar (Canlı)</span></div>
    <div class="rl"><span>CPU</span><span id="cv">...</span></div>
    <div class="bar"><div class="bf bc" id="cb" style="width:0%"></div></div>
    <div class="rl"><span>RAM</span><span id="mv">...</span></div>
    <div class="bar"><div class="bf bm" id="mb" style="width:0%"></div></div>
    <div class="rl"><span>Disk</span><span id="dv">...</span></div>
    <div class="bar"><div class="bf bd" id="db" style="width:0%"></div></div>
    <div class="row" style="margin-top:8px">
      <span class="rk">Çalışma Süresi</span><span class="rv" id="up">...</span>
    </div>
    <div class="row"><span class="rk">CPU Çekirdek</span><span class="rv" id="co">...</span></div>
  </div>

  <div class="card">
    <div class="ch"><span class="ci">⚡</span><span class="ct">Optimizasyonlar</span></div>
    <div class="row"><span class="rk">CPU</span><span class="tag to">performance</span></div>
    <div class="row"><span class="rk">Swappiness</span><span class="rv">1</span></div>
    <div class="row"><span class="rk">File Limit</span><span class="rv">1.048.576</span></div>
    <div class="row"><span class="rk">RT Runtime</span><span class="rv">sınırsız</span></div>
    <div class="row"><span class="rk">TCP Buffer</span><span class="rv">128 MB</span></div>
    <div class="row"><span class="rk">Tmpfs</span><span class="tag tb">RAM Disk</span></div>
    <div class="row"><span class="rk">Overcommit</span><span class="rv">Aktif</span></div>
  </div>

  <div class="card sp3">
    <div class="ch"><span class="ci">📦</span><span class="ct">Kurulu Uygulamalar</span></div>
    <div class="apps">
      <div class="app"><div class="ai">🌐</div><div class="an">Chromium</div></div>
      <div class="app"><div class="ai">🐍</div><div class="an">Python 3</div><div class="av" id="pv">...</div></div>
      <div class="app"><div class="ai">🟢</div><div class="an">Node.js</div><div class="av" id="nv">...</div></div>
      <div class="app"><div class="ai">📝</div><div class="an">Geany IDE</div></div>
      <div class="app"><div class="ai">📁</div><div class="an">PCManFM</div></div>
      <div class="app"><div class="ai">🖥️</div><div class="an">xterm/urxvt</div></div>
      <div class="app"><div class="ai">📊</div><div class="an">htop/strace</div></div>
      <div class="app"><div class="ai">🔧</div><div class="an">Git/GCC/cmake</div></div>
      <div class="app"><div class="ai">🔬</div><div class="an">tmux/screen</div></div>
      <div class="app"><div class="ai">🎬</div><div class="an">ffmpeg</div></div>
      <div class="app"><div class="ai">📡</div><div class="an">nmap/netcat</div></div>
      <div class="app"><div class="ai">⚡</div><div class="an">Flask/FastAPI</div></div>
      <div class="app"><div class="ai">🔢</div><div class="an">NumPy/Pandas</div></div>
      <div class="app"><div class="ai">🤖</div><div class="an">scikit-learn</div></div>
      <div class="app"><div class="ai">📦</div><div class="an">pm2/yarn/pnpm</div></div>
    </div>
  </div>

  <div class="card sp3">
    <div class="ch"><span class="ci">⌨️</span><span class="ct">Klavye Kısayolları</span></div>
    <div class="scs">
      <div class="sc"><kbd>Ctrl+Alt+T</kbd><span class="sd">Terminal (xterm)</span></div>
      <div class="sc"><kbd>Ctrl+Alt+U</kbd><span class="sd">Terminal (urxvt)</span></div>
      <div class="sc"><kbd>Ctrl+Alt+B</kbd><span class="sd">Chromium</span></div>
      <div class="sc"><kbd>Ctrl+Alt+F</kbd><span class="sd">Dosya Gezgini</span></div>
      <div class="sc"><kbd>Ctrl+Alt+E</kbd><span class="sd">Geany IDE</span></div>
      <div class="sc"><kbd>Ctrl+Alt+H</kbd><span class="sd">htop</span></div>
      <div class="sc"><kbd>Ctrl+Alt+P</kbd><span class="sd">Python 3 REPL</span></div>
      <div class="sc"><kbd>Ctrl+Alt+N</kbd><span class="sd">Node.js REPL</span></div>
      <div class="sc"><kbd>Alt+F4</kbd><span class="sd">Pencereyi Kapat</span></div>
      <div class="sc"><kbd>Alt+Tab</kbd><span class="sd">Pencere Değiştir</span></div>
      <div class="sc"><kbd>Sağ Tık</kbd><span class="sd">Uygulama Menüsü</span></div>
      <div class="sc"><kbd>Print</kbd><span class="sd">Ekran Görüntüsü</span></div>
    </div>
  </div>

</div>

<div class="foot">Ubuntu 22.04 LTS · TigerVNC · Fluxbox · noVNC · Render.com</div>
</div>

<script>
async function stats() {{
  try {{
    const d = await fetch('/stats').then(r=>r.json());
    if(d.cpu!==undefined){{document.getElementById('cv').textContent=d.cpu+'%';document.getElementById('cb').style.width=d.cpu+'%';}}
    if(d.rp!==undefined){{document.getElementById('mv').textContent=d.rp+'% · '+d.ru+'/'+d.rt;document.getElementById('mb').style.width=d.rp+'%';}}
    if(d.dp!==undefined){{document.getElementById('dv').textContent=d.dp+'% · '+d.du+'/'+d.dt;document.getElementById('db').style.width=d.dp+'%';}}
    if(d.kern) document.getElementById('kern').textContent=d.kern;
    if(d.up)   document.getElementById('up').textContent=d.up;
    if(d.co)   document.getElementById('co').textContent=d.co+' çekirdek';
    if(d.pv)   document.getElementById('pv').textContent=d.pv;
    if(d.nv)   document.getElementById('nv').textContent=d.nv;
  }}catch(e){{}}
}}
stats(); setInterval(stats,4000);
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


# ══════════════════════════════════════════════════════════
#  STATS API + WEBSOCKIFY
# ══════════════════════════════════════════════════════════

def start():
    import threading, json
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.request import urlopen

    def fmt(b):
        if b > 1e9: return f"{b/1e9:.1f}G"
        if b > 1e6: return f"{b/1e6:.0f}M"
        return f"{b/1e3:.0f}K"

    def upstr(s):
        h = int(s // 3600); m = int((s % 3600) // 60)
        return f"{h}s {m}d"

    def get_stats():
        d = {}
        try:
            import psutil
            d["cpu"] = round(psutil.cpu_percent(0.1), 1)
            d["co"]  = psutil.cpu_count()
            vm = psutil.virtual_memory()
            d["rp"] = round(vm.percent, 1)
            d["ru"] = fmt(vm.used)
            d["rt"] = fmt(vm.total)
            dk = psutil.disk_usage("/")
            d["dp"] = round(dk.percent, 1)
            d["du"] = fmt(dk.used)
            d["dt"] = fmt(dk.total)
            d["up"] = upstr(time.time() - psutil.boot_time())
        except ImportError:
            d["cpu"] = 0
        try:
            d["kern"] = sh_out("uname", "-r")
            d["pv"]   = sh_out("python3", "--version").split()[-1]
            d["nv"]   = sh_out("node", "--version")
        except Exception:
            pass
        return json.dumps(d).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path == "/stats":
                body = get_stats()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    # Stats API — PORT+1'de dinle, noVNC index'e /stats olarak gömüldü
    stats_port = int(PORT) + 1
    try:
        srv = HTTPServer(("0.0.0.0", stats_port), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"  ✅ Stats API :{stats_port}")
    except Exception as e:
        print(f"  ⚠️  Stats: {e}")

    # websockify — ana PORT
    ws = shutil.which("websockify") or "/usr/bin/websockify"
    print(f"[3/3] websockify :{PORT} başlatılıyor...")
    print(f"  → http://0.0.0.0:{PORT}/")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    os.execv(ws, [
        "websockify",
        "--web",       NOVNC_DIR,
        "--heartbeat", "30",
        PORT,
        f"127.0.0.1:{VNC_PORT}",
    ])


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🔓  Tam Yetkili Linux Masaüstü — Başlatılıyor")
print(f"      PORT={PORT}  RES={RESOLUTION}")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

print("\n⚡ [A] Sistem optimizasyonları...")
optimize()

print("\n🖥️  [B] Masaüstü...")
start_vnc()

print("\n🌐 [C] Web arayüzü...")
write_index()
start()
