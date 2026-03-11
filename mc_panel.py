"""
⛏️  Minecraft Yönetim Paneli
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flask + SocketIO — Port 8080
Özellikler:
  • Gerçek zamanlı konsol
  • Oyuncu yönetimi
  • Dosya yönetimi
  • Plugin yönetimi
  • Sunucu ayarları
  • Dünya yönetimi
  • Yedekleme
  • Otomatik başlatma
"""

import os, sys, json, time, threading, subprocess, shutil, zipfile
import re, glob, requests
from collections import deque
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file, abort
from flask_socketio import SocketIO, emit

# ── Ayarlar ───────────────────────────────────────────────────
MC_DIR      = Path("/minecraft")
MC_JAR      = MC_DIR / "server.jar"
MC_PORT     = 25565
PANEL_PORT  = 8080
MC_VERSION  = "1.21.1"
MC_RAM      = os.environ.get("MC_RAM", "1G")
EULA_FILE   = MC_DIR / "eula.txt"

# ── Durum ─────────────────────────────────────────────────────
mc_process  = None
console_buf = deque(maxlen=2000)
players     = {}          # name -> {uuid, op, joined}
server_stats = {
    "status":   "stopped",   # stopped / starting / running / stopping
    "tps":      20.0,
    "ram_mb":   0,
    "uptime":   0,
    "started":  None,
    "version":  "—",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "mc-secret-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


# ══════════════════════════════════════════════════════════════
#  MINECRAFT SERVER YÖNETİMİ
# ══════════════════════════════════════════════════════════════

def download_server():
    """Paper MC indir"""
    console_log("[Panel] Paper MC indiriliyor...")
    try:
        r = requests.get(
            f"https://api.papermc.io/v2/projects/paper/versions/{MC_VERSION}/builds",
            timeout=15
        )
        builds = r.json().get("builds", [])
        if not builds:
            raise Exception("Build listesi boş")
        build = builds[-1]["build"]
        jar_name = f"paper-{MC_VERSION}-{build}.jar"
        dl_url = (f"https://api.papermc.io/v2/projects/paper/versions/"
                  f"{MC_VERSION}/builds/{build}/downloads/{jar_name}")
        console_log(f"[Panel] İndiriliyor: {dl_url}")
        r2 = requests.get(dl_url, stream=True, timeout=120)
        with open(MC_JAR, "wb") as f:
            for chunk in r2.iter_content(65536):
                f.write(chunk)
        console_log(f"[Panel] ✅ Paper MC {MC_VERSION} build {build} indirildi")
        return True
    except Exception as e:
        console_log(f"[Panel] ❌ İndirme hatası: {e}")
        return False


def write_configs():
    """server.properties ve eula yaz"""
    (MC_DIR / "eula.txt").write_text("eula=true\n")

    props = MC_DIR / "server.properties"
    if not props.exists():
        props.write_text(f"""
server-port={MC_PORT}
max-players=20
online-mode=false
gamemode=survival
difficulty=normal
level-name=world
motd=\\u00A7a\\u00A7lLinux Masaüstü \\u00A7r\\u00A7fMC Server
view-distance=8
simulation-distance=6
spawn-protection=0
allow-flight=true
enable-rcon=false
max-tick-time=60000
white-list=false
enable-command-block=true
""".strip())

    # Paper optimize config
    paper_cfg = MC_DIR / "config"
    paper_cfg.mkdir(exist_ok=True)


def console_log(line):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"ts": ts, "line": line.rstrip()}
    console_buf.append(entry)
    socketio.emit("console_line", entry)
    # Oyuncu parse
    _parse_line(line)


def _parse_line(line):
    global players, server_stats
    # Oyuncu bağlandı
    m = re.search(r"(\w+)\[.+\] logged in", line)
    if m:
        players[m.group(1)] = {"op": False, "joined": time.time()}
        socketio.emit("players_update", list(players.keys()))
    # Oyuncu çıktı
    m = re.search(r"(\w+) lost connection|(\w+) left the game", line)
    if m:
        p = m.group(1) or m.group(2)
        players.pop(p, None)
        socketio.emit("players_update", list(players.keys()))
    # TPS
    m = re.search(r"TPS from last.*?(\d+\.?\d*),", line)
    if m:
        server_stats["tps"] = float(m.group(1))
    # Version
    m = re.search(r"Starting minecraft server version (.+)", line)
    if m:
        server_stats["version"] = m.group(1).strip()
    # Server hazır
    if "Done" in line and "For help" in line:
        server_stats["status"] = "running"
        server_stats["started"] = time.time()
        socketio.emit("server_status", server_stats)
        console_log("[Panel] ✅ Server hazır!")
    # Kapandı
    if "Stopping server" in line or "Saving worlds" in line:
        server_stats["status"] = "stopping"
        socketio.emit("server_status", server_stats)


def _read_stdout():
    global mc_process
    while mc_process and mc_process.poll() is None:
        try:
            line = mc_process.stdout.readline()
            if line:
                console_log(line.decode("utf-8", errors="replace"))
        except Exception:
            break
    server_stats["status"] = "stopped"
    players.clear()
    socketio.emit("server_status", server_stats)
    socketio.emit("players_update", [])
    console_log("[Panel] 🔴 Server durduruldu")


def _monitor_ram():
    """RAM kullanımını izle"""
    import psutil
    while True:
        time.sleep(5)
        if mc_process and mc_process.poll() is None:
            try:
                proc = psutil.Process(mc_process.pid)
                server_stats["ram_mb"] = int(proc.memory_info().rss / 1024 / 1024)
                if server_stats["started"]:
                    server_stats["uptime"] = int(time.time() - server_stats["started"])
                socketio.emit("stats_update", server_stats)
            except Exception:
                pass


def start_server():
    global mc_process
    if mc_process and mc_process.poll() is None:
        return False, "Server zaten çalışıyor"

    MC_DIR.mkdir(parents=True, exist_ok=True)

    if not MC_JAR.exists():
        server_stats["status"] = "starting"
        socketio.emit("server_status", server_stats)
        if not download_server():
            server_stats["status"] = "stopped"
            socketio.emit("server_status", server_stats)
            return False, "Jar indirilemedi"

    write_configs()
    server_stats["status"] = "starting"
    players.clear()
    socketio.emit("server_status", server_stats)
    socketio.emit("players_update", [])

    jvm = [
        "java",
        f"-Xms512M", f"-Xmx{MC_RAM}",
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=40",
        "-XX:G1HeapRegionSize=8M",
        "-XX:G1ReservePercent=20",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-Dfile.encoding=UTF-8",
        "-jar", str(MC_JAR),
        "--nogui",
    ]

    console_log(f"[Panel] 🚀 Server başlatılıyor... (RAM: {MC_RAM})")
    mc_process = subprocess.Popen(
        jvm, cwd=str(MC_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    threading.Thread(target=_read_stdout, daemon=True).start()
    return True, "Server başlatılıyor"


def stop_server(force=False):
    global mc_process
    if not mc_process or mc_process.poll() is not None:
        return False, "Server çalışmıyor"
    server_stats["status"] = "stopping"
    socketio.emit("server_status", server_stats)
    if force:
        mc_process.kill()
    else:
        send_command("stop")
    return True, "Durduruluyor"


def send_command(cmd):
    global mc_process
    if mc_process and mc_process.poll() is None:
        try:
            mc_process.stdin.write(f"{cmd}\n".encode())
            mc_process.stdin.flush()
            console_log(f"[Konsol] > {cmd}")
            return True
        except Exception as e:
            console_log(f"[Hata] Komut gönderilemedi: {e}")
    return False


# ══════════════════════════════════════════════════════════════
#  HTTP API
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return PANEL_HTML


@app.route("/api/status")
def api_status():
    return jsonify({**server_stats, "players": list(players.keys()),
                    "player_count": len(players)})


@app.route("/api/start", methods=["POST"])
def api_start():
    ok, msg = start_server()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    force = request.json.get("force", False) if request.json else False
    ok, msg = stop_server(force)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/restart", methods=["POST"])
def api_restart():
    stop_server()
    time.sleep(3)
    ok, msg = start_server()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/command", methods=["POST"])
def api_command():
    cmd = request.json.get("cmd", "").strip()
    if not cmd:
        return jsonify({"ok": False})
    ok = send_command(cmd)
    return jsonify({"ok": ok})


@app.route("/api/console/history")
def api_console_history():
    return jsonify(list(console_buf))


# ── Oyuncu yönetimi ──────────────────────────────────────────

@app.route("/api/players")
def api_players():
    send_command("list")
    return jsonify({"players": list(players.keys()), "count": len(players)})


@app.route("/api/players/kick", methods=["POST"])
def api_kick():
    d = request.json
    send_command(f"kick {d['player']} {d.get('reason','')}")
    return jsonify({"ok": True})


@app.route("/api/players/ban", methods=["POST"])
def api_ban():
    d = request.json
    send_command(f"ban {d['player']} {d.get('reason','Banned by admin')}")
    return jsonify({"ok": True})


@app.route("/api/players/pardon", methods=["POST"])
def api_pardon():
    send_command(f"pardon {request.json['player']}")
    return jsonify({"ok": True})


@app.route("/api/players/op", methods=["POST"])
def api_op():
    send_command(f"op {request.json['player']}")
    return jsonify({"ok": True})


@app.route("/api/players/deop", methods=["POST"])
def api_deop():
    send_command(f"deop {request.json['player']}")
    return jsonify({"ok": True})


@app.route("/api/players/gamemode", methods=["POST"])
def api_gamemode():
    d = request.json
    send_command(f"gamemode {d['mode']} {d['player']}")
    return jsonify({"ok": True})


@app.route("/api/players/tp", methods=["POST"])
def api_tp():
    d = request.json
    send_command(f"tp {d['player']} {d.get('to', d['player'])}")
    return jsonify({"ok": True})


@app.route("/api/players/give", methods=["POST"])
def api_give():
    d = request.json
    send_command(f"give {d['player']} {d['item']} {d.get('count',1)}")
    return jsonify({"ok": True})


@app.route("/api/players/msg", methods=["POST"])
def api_msg():
    d = request.json
    send_command(f"tell {d['player']} {d['message']}")
    return jsonify({"ok": True})


# Banlist
@app.route("/api/banlist")
def api_banlist():
    f = MC_DIR / "banned-players.json"
    if f.exists():
        return jsonify(json.loads(f.read_text()))
    return jsonify([])


@app.route("/api/whitelist")
def api_whitelist():
    f = MC_DIR / "whitelist.json"
    if f.exists():
        return jsonify(json.loads(f.read_text()))
    return jsonify([])


@app.route("/api/whitelist/add", methods=["POST"])
def api_whitelist_add():
    send_command(f"whitelist add {request.json['player']}")
    return jsonify({"ok": True})


@app.route("/api/whitelist/remove", methods=["POST"])
def api_whitelist_remove():
    send_command(f"whitelist remove {request.json['player']}")
    return jsonify({"ok": True})


# ── Dosya yönetimi ───────────────────────────────────────────

def safe_path(rel):
    """MC_DIR altında güvenli path"""
    p = (MC_DIR / rel).resolve()
    if not str(p).startswith(str(MC_DIR)):
        abort(403)
    return p


@app.route("/api/files")
def api_files():
    rel = request.args.get("path", "")
    p = safe_path(rel)
    if not p.exists():
        return jsonify([])
    items = []
    for item in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name)):
        stat = item.stat()
        items.append({
            "name": item.name,
            "path": str(item.relative_to(MC_DIR)),
            "type": "dir" if item.is_dir() else "file",
            "size": stat.st_size,
            "modified": int(stat.st_mtime),
            "ext": item.suffix.lower() if item.is_file() else "",
        })
    return jsonify(items)


@app.route("/api/files/read")
def api_file_read():
    p = safe_path(request.args.get("path", ""))
    if not p.is_file():
        abort(404)
    try:
        return jsonify({"content": p.read_text(errors="replace"), "path": str(p.relative_to(MC_DIR))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/write", methods=["POST"])
def api_file_write():
    d = request.json
    p = safe_path(d["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(d["content"])
    return jsonify({"ok": True})


@app.route("/api/files/delete", methods=["POST"])
def api_file_delete():
    p = safe_path(request.json["path"])
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return jsonify({"ok": True})


@app.route("/api/files/mkdir", methods=["POST"])
def api_mkdir():
    safe_path(request.json["path"]).mkdir(parents=True, exist_ok=True)
    return jsonify({"ok": True})


@app.route("/api/files/rename", methods=["POST"])
def api_rename():
    d = request.json
    safe_path(d["from"]).rename(safe_path(d["to"]))
    return jsonify({"ok": True})


@app.route("/api/files/upload", methods=["POST"])
def api_upload():
    rel = request.form.get("path", "")
    for f in request.files.values():
        p = safe_path(rel + "/" + f.filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        f.save(str(p))
    return jsonify({"ok": True})


@app.route("/api/files/download")
def api_download():
    p = safe_path(request.args.get("path", ""))
    if not p.exists():
        abort(404)
    if p.is_dir():
        zip_path = f"/tmp/{p.name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for fp in p.rglob("*"):
                if fp.is_file():
                    z.write(fp, fp.relative_to(p))
        return send_file(zip_path, as_attachment=True, download_name=f"{p.name}.zip")
    return send_file(str(p), as_attachment=True)


# ── Plugin yönetimi ──────────────────────────────────────────

@app.route("/api/plugins")
def api_plugins():
    plugin_dir = MC_DIR / "plugins"
    plugins = []
    for jar in sorted(plugin_dir.glob("*.jar")):
        plugins.append({
            "name": jar.stem,
            "file": jar.name,
            "size": jar.stat().st_size,
            "enabled": not jar.name.endswith(".disabled"),
        })
    return jsonify(plugins)


@app.route("/api/plugins/upload", methods=["POST"])
def api_plugin_upload():
    plugin_dir = MC_DIR / "plugins"
    plugin_dir.mkdir(exist_ok=True)
    for f in request.files.values():
        if f.filename.endswith(".jar"):
            f.save(str(plugin_dir / f.filename))
    return jsonify({"ok": True, "msg": "Plugin yüklendi. Yeniden başlatın."})


@app.route("/api/plugins/delete", methods=["POST"])
def api_plugin_delete():
    p = MC_DIR / "plugins" / request.json["file"]
    if p.exists():
        p.unlink()
    return jsonify({"ok": True})


@app.route("/api/plugins/toggle", methods=["POST"])
def api_plugin_toggle():
    name = request.json["file"]
    p = MC_DIR / "plugins" / name
    if name.endswith(".disabled"):
        new = p.with_suffix("").with_suffix(".jar")
    else:
        new = p.with_suffix(".jar.disabled")
    p.rename(new)
    return jsonify({"ok": True})


@app.route("/api/plugins/search")
def api_plugin_search():
    """Hangar (PaperMC) plugin arama"""
    q = request.args.get("q", "")
    try:
        r = requests.get(
            f"https://hangar.papermc.io/api/v1/projects?q={q}&limit=10",
            timeout=8
        )
        data = r.json()
        results = []
        for p in data.get("result", []):
            results.append({
                "name": p.get("name",""),
                "description": p.get("description",""),
                "downloads": p.get("stats",{}).get("downloads",0),
                "url": f"https://hangar.papermc.io/{p.get('namespace',{}).get('owner','')}/{p.get('name','')}",
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Sunucu ayarları ──────────────────────────────────────────

@app.route("/api/settings")
def api_settings():
    props_file = MC_DIR / "server.properties"
    if not props_file.exists():
        return jsonify({})
    props = {}
    for line in props_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    return jsonify(props)


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    props = request.json
    props_file = MC_DIR / "server.properties"
    lines = ["# Minecraft Server Properties", f"# Güncellendi: {datetime.now()}"]
    for k, v in props.items():
        lines.append(f"{k}={v}")
    props_file.write_text("\n".join(lines) + "\n")
    return jsonify({"ok": True, "msg": "Kaydedildi. Yeniden başlatın."})


# ── Dünya yönetimi ────────────────────────────────────────────

@app.route("/api/worlds")
def api_worlds():
    worlds = []
    for d in MC_DIR.iterdir():
        if d.is_dir() and (d / "level.dat").exists():
            stat = d.stat()
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            worlds.append({"name": d.name, "size": size, "modified": int(stat.st_mtime)})
    return jsonify(worlds)


@app.route("/api/worlds/backup", methods=["POST"])
def api_world_backup():
    world = request.json.get("world", "world")
    src = MC_DIR / world
    if not src.exists():
        return jsonify({"ok": False, "error": "Dünya bulunamadı"})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = MC_DIR / "backups" / f"{world}_{ts}.zip"
    backup_path.parent.mkdir(exist_ok=True)
    send_command("save-off")
    send_command("save-all")
    time.sleep(2)
    with zipfile.ZipFile(str(backup_path), "w", zipfile.ZIP_DEFLATED) as z:
        for fp in src.rglob("*"):
            if fp.is_file():
                z.write(fp, fp.relative_to(MC_DIR))
    send_command("save-on")
    return jsonify({"ok": True, "file": str(backup_path.relative_to(MC_DIR))})


@app.route("/api/worlds/delete", methods=["POST"])
def api_world_delete():
    world = request.json.get("world")
    p = MC_DIR / world
    if p.exists() and (p / "level.dat").exists():
        shutil.rmtree(p)
        return jsonify({"ok": True})
    return jsonify({"ok": False})


# ── Performans ────────────────────────────────────────────────

@app.route("/api/performance")
def api_performance():
    try:
        import psutil
        cpu = psutil.cpu_percent(0.1)
        vm  = psutil.virtual_memory()
        dk  = psutil.disk_usage("/")
        return jsonify({
            "cpu": cpu,
            "ram_pct": vm.percent, "ram_used_mb": int(vm.used/1024/1024),
            "ram_total_mb": int(vm.total/1024/1024),
            "disk_pct": dk.percent,
            "mc_ram_mb": server_stats.get("ram_mb", 0),
            "tps": server_stats.get("tps", 20),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── SocketIO ──────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("console_history", list(console_buf))
    emit("server_status", server_stats)
    emit("players_update", list(players.keys()))


@socketio.on("send_command")
def on_command(data):
    cmd = data.get("cmd", "").strip()
    if cmd:
        send_command(cmd)


# ══════════════════════════════════════════════════════════════
#  PANEL HTML
# ══════════════════════════════════════════════════════════════

PANEL_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⛏️ Minecraft Yönetim Paneli</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#05060c;--s1:#0b0d16;--s2:#0f1120;--s3:#131525;
  --a1:#00e5ff;--a2:#7c6aff;--a3:#00ffaa;
  --red:#ff4757;--green:#2ed573;--yellow:#ffa502;--orange:#ff6b35;
  --t1:#eef0f8;--t2:#8892a4;--t3:#3d4558;
  --font:'Sora',sans-serif;--mono:'JetBrains Mono',monospace;
  --r:12px;--sidebar:220px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--t1);font-family:var(--font);overflow:hidden}

/* Layout */
.layout{display:flex;height:100vh}

/* Sidebar */
.sidebar{width:var(--sidebar);background:var(--s1);border-right:1px solid rgba(255,255,255,.06);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto}
.sb-logo{padding:20px 16px 16px;border-bottom:1px solid rgba(255,255,255,.06)}
.sb-logo h2{font-size:15px;font-weight:700;color:var(--t1);display:flex;align-items:center;gap:8px}
.sb-logo .ver{font-size:10px;color:var(--t2);font-family:var(--mono);margin-top:3px}
.sb-status{display:flex;align-items:center;gap:6px;padding:8px 16px;margin:8px 0 0;
  background:rgba(255,255,255,.03);border-radius:8px;margin:8px 10px 0;font-size:12px}
.status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot-green{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot-red{background:var(--red);box-shadow:0 0 6px var(--red)}
.dot-yellow{background:var(--yellow);box-shadow:0 0 6px var(--yellow);animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.nav{padding:12px 10px;flex:1}
.nav-section{font-size:9px;font-weight:700;color:var(--t3);text-transform:uppercase;
  letter-spacing:.12em;padding:12px 6px 6px;margin-bottom:2px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:9px;
  cursor:pointer;transition:all .15s;font-size:13px;color:var(--t2);margin-bottom:2px}
.nav-item:hover{background:rgba(255,255,255,.06);color:var(--t1)}
.nav-item.active{background:rgba(0,229,255,.1);color:var(--a1);font-weight:600}
.nav-item .ico{font-size:16px;width:20px;text-align:center}
.sb-controls{padding:12px 10px;border-top:1px solid rgba(255,255,255,.06)}
.ctrl-btn{width:100%;padding:8px;border-radius:9px;font-size:12px;font-weight:600;
  border:none;cursor:pointer;font-family:var(--font);transition:all .15s;margin-bottom:6px;
  display:flex;align-items:center;justify-content:center;gap:6px}
.btn-start{background:linear-gradient(135deg,var(--green),#00a550);color:#000}
.btn-start:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(46,213,115,.3)}
.btn-stop{background:rgba(255,71,87,.15);color:var(--red);border:1px solid rgba(255,71,87,.3)}
.btn-stop:hover{background:rgba(255,71,87,.25)}
.btn-restart{background:rgba(255,165,2,.1);color:var(--yellow);border:1px solid rgba(255,165,2,.25)}
.btn-restart:hover{background:rgba(255,165,2,.2)}

/* Main */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{height:52px;background:var(--s1);border-bottom:1px solid rgba(255,255,255,.06);
  display:flex;align-items:center;padding:0 20px;gap:12px;flex-shrink:0}
.page-title{font-size:15px;font-weight:700;flex:1}
.topbar-stats{display:flex;gap:16px;font-size:11px;color:var(--t2);font-family:var(--mono)}
.ts{display:flex;align-items:center;gap:4px}
.ts-val{color:var(--t1);font-weight:500}

/* Pages */
.pages{flex:1;overflow:hidden;position:relative}
.page{display:none;height:100%;overflow-y:auto;padding:20px}
.page.active{display:block}

/* Cards */
.card{background:var(--s1);border:1px solid rgba(255,255,255,.06);border-radius:var(--r);padding:18px}
.card-title{font-size:11px;font-weight:700;color:var(--t2);text-transform:uppercase;
  letter-spacing:.1em;margin-bottom:14px;display:flex;align-items:center;gap:6px}
.card-title::before{content:'';width:3px;height:11px;border-radius:2px;background:var(--a1)}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:14px}

/* Stat cards */
.stat-card{background:var(--s2);border:1px solid rgba(255,255,255,.05);border-radius:10px;
  padding:16px;text-align:center}
.stat-val{font-size:28px;font-weight:700;font-family:var(--mono);
  background:linear-gradient(135deg,var(--a1),var(--a2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-lbl{font-size:11px;color:var(--t2);margin-top:4px}

/* Console */
.console-wrap{height:calc(100vh - 160px);display:flex;flex-direction:column}
.console-out{flex:1;background:#000;border-radius:10px;padding:12px;overflow-y:auto;
  font-family:var(--mono);font-size:12px;line-height:1.6;border:1px solid rgba(255,255,255,.06)}
.console-out::-webkit-scrollbar{width:5px}
.console-out::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}
.log-info{color:#9cdcfe}
.log-warn{color:#dcdcaa}
.log-error{color:#f44747}
.log-panel{color:#00e5ff}
.log-default{color:#d4d4d4}
.console-in{display:flex;gap:8px;margin-top:10px}
.cmd-input{flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);
  color:var(--t1);border-radius:8px;padding:10px 14px;font-family:var(--mono);font-size:13px;outline:none}
.cmd-input:focus{border-color:rgba(0,229,255,.4)}
.cmd-send{padding:10px 20px;background:linear-gradient(135deg,var(--a1),var(--a2));color:#000;
  border:none;border-radius:8px;font-weight:700;cursor:pointer;font-family:var(--font);transition:all .15s}
.cmd-send:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(0,229,255,.3)}

/* Tables */
.table{width:100%;border-collapse:collapse;font-size:13px}
.table th{padding:10px 12px;text-align:left;font-size:10px;font-weight:700;
  color:var(--t2);text-transform:uppercase;letter-spacing:.08em;
  border-bottom:1px solid rgba(255,255,255,.06)}
.table td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.04)}
.table tr:hover td{background:rgba(255,255,255,.02)}
.table tr:last-child td{border:none}

/* Badges */
.badge{border-radius:20px;padding:2px 9px;font-size:10px;font-weight:700;font-family:var(--mono)}
.b-green{background:rgba(46,213,115,.1);border:1px solid rgba(46,213,115,.25);color:var(--green)}
.b-red{background:rgba(255,71,87,.1);border:1px solid rgba(255,71,87,.25);color:var(--red)}
.b-blue{background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);color:var(--a1)}
.b-yellow{background:rgba(255,165,2,.1);border:1px solid rgba(255,165,2,.25);color:var(--yellow)}

/* Buttons */
.btn{padding:6px 14px;border-radius:7px;font-size:12px;font-weight:600;border:none;
  cursor:pointer;font-family:var(--font);transition:all .15s;display:inline-flex;
  align-items:center;gap:5px}
.btn-sm{padding:4px 10px;font-size:11px}
.btn-primary{background:linear-gradient(135deg,var(--a1),var(--a2));color:#000}
.btn-danger{background:rgba(255,71,87,.15);color:var(--red);border:1px solid rgba(255,71,87,.3)}
.btn-danger:hover{background:rgba(255,71,87,.3)}
.btn-warn{background:rgba(255,165,2,.1);color:var(--yellow);border:1px solid rgba(255,165,2,.25)}
.btn-success{background:rgba(46,213,115,.1);color:var(--green);border:1px solid rgba(46,213,115,.3)}
.btn-ghost{background:rgba(255,255,255,.05);color:var(--t2);border:1px solid rgba(255,255,255,.1)}
.btn:hover{transform:translateY(-1px)}

/* File manager */
.file-tree{display:flex;gap:14px;height:calc(100vh - 180px)}
.file-list-pane{width:300px;background:var(--s1);border:1px solid rgba(255,255,255,.06);
  border-radius:var(--r);overflow-y:auto;flex-shrink:0}
.file-editor-pane{flex:1;background:var(--s1);border:1px solid rgba(255,255,255,.06);
  border-radius:var(--r);display:flex;flex-direction:column}
.file-toolbar{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.06);
  display:flex;gap:8px;align-items:center}
.file-breadcrumb{font-size:12px;color:var(--t2);font-family:var(--mono);flex:1}
.file-item{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;
  border-bottom:1px solid rgba(255,255,255,.03);transition:background .1s;font-size:13px}
.file-item:hover{background:rgba(255,255,255,.04)}
.file-item.selected{background:rgba(0,229,255,.07);border-left:2px solid var(--a1)}
.file-ico{font-size:15px;width:20px;text-align:center}
.file-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-size{font-size:10px;color:var(--t3);font-family:var(--mono)}
.editor-area{flex:1;background:#1e1e1e;color:#d4d4d4;font-family:var(--mono);font-size:12px;
  border:none;outline:none;padding:14px;resize:none;line-height:1.6;border-radius:0 0 var(--r) var(--r)}

/* Settings */
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.setting-item{background:var(--s2);border:1px solid rgba(255,255,255,.05);border-radius:9px;padding:12px}
.setting-label{font-size:11px;color:var(--t2);margin-bottom:6px}
.setting-input{width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  color:var(--t1);border-radius:7px;padding:7px 10px;font-family:var(--mono);font-size:12px;outline:none}
.setting-input:focus{border-color:rgba(0,229,255,.4)}
select.setting-input option{background:#1e1e1e}

/* Progress bars */
.prog-bar{height:6px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden;margin-top:6px}
.prog-fill{height:100%;border-radius:3px;transition:width .6s}
.pf-cpu{background:linear-gradient(90deg,var(--a1),var(--a2))}
.pf-ram{background:linear-gradient(90deg,var(--a3),var(--a1))}
.pf-disk{background:linear-gradient(90deg,var(--a2),var(--orange))}

/* Plugin */
.plugin-search{display:flex;gap:8px;margin-bottom:14px}
.search-input{flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);
  color:var(--t1);border-radius:9px;padding:9px 14px;font-family:var(--font);font-size:13px;outline:none}
.search-input:focus{border-color:rgba(0,229,255,.4)}
.search-results{max-height:250px;overflow-y:auto;margin-top:10px}
.search-item{padding:10px 12px;border:1px solid rgba(255,255,255,.06);border-radius:8px;
  margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.si-info .si-name{font-size:13px;font-weight:600}
.si-info .si-desc{font-size:11px;color:var(--t2);margin-top:2px}

/* Modal */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;
  align-items:center;justify-content:center}
.modal-bg.show{display:flex}
.modal{background:var(--s1);border:1px solid rgba(255,255,255,.1);border-radius:16px;
  padding:24px;min-width:380px;max-width:520px;width:90%}
.modal h3{font-size:16px;font-weight:700;margin-bottom:16px}
.modal-input{width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
  color:var(--t1);border-radius:8px;padding:9px 12px;font-family:var(--mono);font-size:13px;
  outline:none;margin-bottom:10px}
.modal-input:focus{border-color:rgba(0,229,255,.4)}
.modal-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}

/* Upload zone */
.upload-zone{border:2px dashed rgba(255,255,255,.15);border-radius:10px;padding:24px;
  text-align:center;cursor:pointer;transition:all .2s;color:var(--t2);font-size:13px}
.upload-zone:hover{border-color:rgba(0,229,255,.4);background:rgba(0,229,255,.04)}
.upload-zone.drag{border-color:var(--a1);background:rgba(0,229,255,.08)}

input[type=file]{display:none}

/* Scrollbar */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.2)}

/* Notification */
.notif{position:fixed;top:16px;right:16px;z-index:200;display:flex;flex-direction:column;gap:8px}
.notif-item{padding:10px 16px;border-radius:10px;font-size:13px;font-weight:600;
  animation:slidein .3s ease;max-width:320px}
.notif-ok{background:rgba(46,213,115,.15);border:1px solid rgba(46,213,115,.3);color:var(--green)}
.notif-err{background:rgba(255,71,87,.15);border:1px solid rgba(255,71,87,.3);color:var(--red)}
.notif-info{background:rgba(0,229,255,.1);border:1px solid rgba(0,229,255,.25);color:var(--a1)}
@keyframes slidein{from{transform:translateX(120px);opacity:0}to{transform:none;opacity:1}}
</style>
</head>
<body>
<div class="layout">

<!-- Sidebar -->
<div class="sidebar">
  <div class="sb-logo">
    <h2>⛏️ MC Panel</h2>
    <div class="ver" id="mc-ver">Paper MC • —</div>
  </div>
  <div class="sb-status">
    <div class="status-dot dot-red" id="status-dot"></div>
    <span id="status-text">Durduruldu</span>
  </div>
  <nav class="nav">
    <div class="nav-section">Genel</div>
    <div class="nav-item active" onclick="goto('dashboard')"><span class="ico">📊</span>Dashboard</div>
    <div class="nav-item" onclick="goto('console')"><span class="ico">💻</span>Konsol</div>
    <div class="nav-section">Yönetim</div>
    <div class="nav-item" onclick="goto('players')"><span class="ico">👥</span>Oyuncular</div>
    <div class="nav-item" onclick="goto('whitelist')"><span class="ico">📋</span>Beyaz Liste</div>
    <div class="nav-item" onclick="goto('banlist')"><span class="ico">🔨</span>Ban Listesi</div>
    <div class="nav-section">Sunucu</div>
    <div class="nav-item" onclick="goto('plugins')"><span class="ico">🔌</span>Pluginler</div>
    <div class="nav-item" onclick="goto('files')"><span class="ico">📁</span>Dosyalar</div>
    <div class="nav-item" onclick="goto('worlds')"><span class="ico">🌍</span>Dünyalar</div>
    <div class="nav-item" onclick="goto('settings')"><span class="ico">⚙️</span>Ayarlar</div>
    <div class="nav-section">Sistem</div>
    <div class="nav-item" onclick="goto('performance')"><span class="ico">📈</span>Performans</div>
  </nav>
  <div class="sb-controls">
    <button class="ctrl-btn btn-start" onclick="serverAction('start')">▶ Başlat</button>
    <button class="ctrl-btn btn-restart" onclick="serverAction('restart')">↺ Yeniden Başlat</button>
    <button class="ctrl-btn btn-stop" onclick="serverAction('stop')">■ Durdur</button>
  </div>
</div>

<!-- Main -->
<div class="main">
  <div class="topbar">
    <div class="page-title" id="page-title">📊 Dashboard</div>
    <div class="topbar-stats">
      <div class="ts">👥 <span class="ts-val" id="tb-players">0</span></div>
      <div class="ts">⚡ <span class="ts-val" id="tb-tps">20</span> TPS</div>
      <div class="ts">🧠 <span class="ts-val" id="tb-ram">—</span></div>
      <div class="ts">⏱ <span class="ts-val" id="tb-uptime">—</span></div>
    </div>
  </div>

  <div class="pages">

  <!-- Dashboard -->
  <div class="page active" id="page-dashboard">
    <div class="grid-3">
      <div class="stat-card"><div class="stat-val" id="d-players">0</div><div class="stat-lbl">👥 Online Oyuncu</div></div>
      <div class="stat-card"><div class="stat-val" id="d-tps">20.0</div><div class="stat-lbl">⚡ TPS</div></div>
      <div class="stat-card"><div class="stat-val" id="d-ram">—</div><div class="stat-lbl">🧠 MC RAM (MB)</div></div>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Sunucu Bilgisi</div>
        <table class="table">
          <tr><td style="color:var(--t2)">Durum</td><td><span class="badge b-red" id="d-status">Durduruldu</span></td></tr>
          <tr><td style="color:var(--t2)">Versiyon</td><td id="d-version">—</td></tr>
          <tr><td style="color:var(--t2)">RAM Limiti</td><td id="d-maxram">—</td></tr>
          <tr><td style="color:var(--t2)">Çalışma Süresi</td><td id="d-uptime">—</td></tr>
          <tr><td style="color:var(--t2)">Port</td><td>25565 (Cloudflare Tunnel)</td></tr>
        </table>
      </div>
      <div class="card">
        <div class="card-title">Online Oyuncular</div>
        <div id="d-playerlist" style="color:var(--t2);font-size:13px">Sunucu çalışmıyor</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Son Konsol</div>
      <div id="d-lastlog" style="font-family:var(--mono);font-size:11px;max-height:180px;overflow-y:auto;line-height:1.7;color:#9cdcfe"></div>
    </div>
  </div>

  <!-- Konsol -->
  <div class="page" id="page-console">
    <div class="console-wrap">
      <div class="card-title" style="margin-bottom:10px">
        💻 Gerçek Zamanlı Konsol
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="clearConsole()">Temizle</button>
        <button class="btn btn-ghost btn-sm" onclick="scrollConsoleBottom()">↓ En Alta</button>
      </div>
      <div class="console-out" id="console-out"></div>
      <div class="console-in">
        <input class="cmd-input" id="cmd-input" placeholder="Komut gir... (örn: list, time set day, tp oyuncu1 oyuncu2)"
          onkeydown="if(event.key==='Enter')sendCmd()">
        <button class="cmd-send" onclick="sendCmd()">▶ Gönder</button>
      </div>
    </div>
  </div>

  <!-- Oyuncular -->
  <div class="page" id="page-players">
    <div class="card" style="margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <div class="card-title" style="margin:0">👥 Online Oyuncular</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost btn-sm" onclick="sendCmd2('say Merhaba!')">📢 Duyuru</button>
          <button class="btn btn-ghost btn-sm" onclick="refreshPlayers()">↺ Yenile</button>
        </div>
      </div>
      <table class="table" id="players-table">
        <thead><tr><th>Oyuncu</th><th>Durum</th><th>İşlemler</th></tr></thead>
        <tbody id="players-body"><tr><td colspan="3" style="color:var(--t2);text-align:center">Yükleniyor...</td></tr></tbody>
      </table>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Toplu İşlemler</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <input class="cmd-input" id="bulk-player" placeholder="Oyuncu adı" style="font-size:12px;padding:8px 12px">
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-danger btn-sm" onclick="playerAction('kick')">👢 Kick</button>
            <button class="btn btn-danger btn-sm" onclick="playerAction('ban')">🔨 Ban</button>
            <button class="btn btn-success btn-sm" onclick="playerAction('op')">⭐ OP</button>
            <button class="btn btn-warn btn-sm" onclick="playerAction('deop')">✕ DeOP</button>
            <button class="btn btn-ghost btn-sm" onclick="playerAction('tp')">🚀 TP</button>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-ghost btn-sm" onclick="setGamemode('survival')">⚔ Survival</button>
            <button class="btn btn-ghost btn-sm" onclick="setGamemode('creative')">🎨 Creative</button>
            <button class="btn btn-ghost btn-sm" onclick="setGamemode('adventure')">🗺 Adventure</button>
            <button class="btn btn-ghost btn-sm" onclick="setGamemode('spectator')">👁 Spectator</button>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Mesaj / Give</div>
        <input class="cmd-input" id="msg-player" placeholder="Oyuncu" style="font-size:12px;padding:8px 12px;margin-bottom:8px">
        <input class="cmd-input" id="msg-text" placeholder="Mesaj" style="font-size:12px;padding:8px 12px;margin-bottom:8px">
        <button class="btn btn-primary btn-sm" style="width:100%" onclick="sendMsg()">📩 Gönder</button>
        <div style="margin-top:10px">
          <input class="cmd-input" id="give-item" placeholder="Item (örn: diamond_sword)" style="font-size:12px;padding:8px 12px;margin-bottom:8px">
          <input class="cmd-input" id="give-count" placeholder="Miktar" type="number" value="1" style="font-size:12px;padding:8px 12px;margin-bottom:8px;width:80px">
          <button class="btn btn-primary btn-sm" onclick="giveItem()">🎁 Give</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Whitelist -->
  <div class="page" id="page-whitelist">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <div class="card-title" style="margin:0">📋 Beyaz Liste</div>
        <div style="display:flex;gap:8px;align-items:center">
          <input class="cmd-input" id="wl-player" placeholder="Oyuncu adı" style="font-size:12px;padding:7px 12px;width:180px">
          <button class="btn btn-success btn-sm" onclick="wlAdd()">+ Ekle</button>
          <button class="btn btn-ghost btn-sm" onclick="sendCmd2('whitelist on')">Aç</button>
          <button class="btn btn-ghost btn-sm" onclick="sendCmd2('whitelist off')">Kapat</button>
        </div>
      </div>
      <table class="table">
        <thead><tr><th>Oyuncu</th><th>UUID</th><th>İşlem</th></tr></thead>
        <tbody id="wl-body"></tbody>
      </table>
    </div>
  </div>

  <!-- Ban -->
  <div class="page" id="page-banlist">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <div class="card-title" style="margin:0">🔨 Ban Listesi</div>
        <div style="display:flex;gap:8px;align-items:center">
          <input class="cmd-input" id="ban-player" placeholder="Oyuncu adı" style="font-size:12px;padding:7px 12px;width:180px">
          <button class="btn btn-danger btn-sm" onclick="banPlayer()">🔨 Ban Et</button>
        </div>
      </div>
      <table class="table">
        <thead><tr><th>Oyuncu</th><th>Sebep</th><th>Tarih</th><th>İşlem</th></tr></thead>
        <tbody id="ban-body"></tbody>
      </table>
    </div>
  </div>

  <!-- Plugins -->
  <div class="page" id="page-plugins">
    <div class="grid-2" style="margin-bottom:0">
      <div class="card" style="height:calc(100vh - 160px);display:flex;flex-direction:column">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <div class="card-title" style="margin:0">🔌 Kurulu Pluginler</div>
          <label for="plugin-upload" class="btn btn-primary btn-sm" style="cursor:pointer">⬆ Yükle</label>
          <input type="file" id="plugin-upload" accept=".jar" onchange="uploadPlugin(this)">
        </div>
        <div style="flex:1;overflow-y:auto">
          <table class="table" id="plugins-table">
            <thead><tr><th>Plugin</th><th>Boyut</th><th>İşlem</th></tr></thead>
            <tbody id="plugins-body"></tbody>
          </table>
        </div>
      </div>
      <div class="card" style="height:calc(100vh - 160px);display:flex;flex-direction:column">
        <div class="card-title">🔍 Plugin Market (Hangar)</div>
        <div class="plugin-search">
          <input class="search-input" id="plugin-search-q" placeholder="Plugin ara... (örn: EssentialsX, WorldEdit)">
          <button class="btn btn-primary" onclick="searchPlugins()">Ara</button>
        </div>
        <div class="search-results" id="search-results" style="flex:1;overflow-y:auto"></div>
      </div>
    </div>
  </div>

  <!-- Dosyalar -->
  <div class="page" id="page-files">
    <div class="file-tree">
      <div class="file-list-pane">
        <div class="file-toolbar">
          <span class="file-breadcrumb" id="file-path">/</span>
          <button class="btn btn-ghost btn-sm" onclick="fileGoUp()">↑</button>
          <button class="btn btn-ghost btn-sm" onclick="fileRefresh()">↺</button>
          <button class="btn btn-primary btn-sm" onclick="showNewFileModal()">+</button>
        </div>
        <div id="file-list"></div>
      </div>
      <div class="file-editor-pane">
        <div class="file-toolbar">
          <span id="editor-filename" style="font-family:var(--mono);font-size:12px;color:var(--t2)">Dosya seçin</span>
          <div style="margin-left:auto;display:flex;gap:6px">
            <button class="btn btn-primary btn-sm" onclick="saveFile()" id="save-btn" disabled>💾 Kaydet</button>
            <button class="btn btn-ghost btn-sm" onclick="downloadFile()">⬇ İndir</button>
            <label class="btn btn-ghost btn-sm" style="cursor:pointer">⬆ Yükle<input type="file" style="display:none" onchange="uploadFile(this)" multiple></label>
            <button class="btn btn-danger btn-sm" onclick="deleteFile()">🗑 Sil</button>
          </div>
        </div>
        <textarea class="editor-area" id="editor-area" placeholder="Düzenlemek için sol panelden dosya seçin..." onchange="document.getElementById('save-btn').disabled=false"></textarea>
      </div>
    </div>
  </div>

  <!-- Dünyalar -->
  <div class="page" id="page-worlds">
    <div class="card">
      <div class="card-title">🌍 Dünya Yönetimi</div>
      <div id="worlds-list"></div>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="card-title">💡 Hızlı Komutlar</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-ghost" onclick="sendCmd2('time set day')">☀ Gündüz</button>
        <button class="btn btn-ghost" onclick="sendCmd2('time set night')">🌙 Gece</button>
        <button class="btn btn-ghost" onclick="sendCmd2('weather clear')">⛅ Açık Hava</button>
        <button class="btn btn-ghost" onclick="sendCmd2('weather rain')">🌧 Yağmur</button>
        <button class="btn btn-ghost" onclick="sendCmd2('weather thunder')">⛈ Fırtına</button>
        <button class="btn btn-ghost" onclick="sendCmd2('difficulty peaceful')">😊 Peaceful</button>
        <button class="btn btn-ghost" onclick="sendCmd2('difficulty easy')">🟢 Easy</button>
        <button class="btn btn-ghost" onclick="sendCmd2('difficulty normal')">🟡 Normal</button>
        <button class="btn btn-ghost" onclick="sendCmd2('difficulty hard')">🔴 Hard</button>
        <button class="btn btn-ghost" onclick="sendCmd2('save-all')">💾 Save All</button>
        <button class="btn btn-ghost" onclick="sendCmd2('kill @e[type=!player]')">⚡ Mob Temizle</button>
      </div>
    </div>
  </div>

  <!-- Ayarlar -->
  <div class="page" id="page-settings">
    <div class="card">
      <div style="display:flex;justify-content:space-between;margin-bottom:14px">
        <div class="card-title" style="margin:0">⚙️ Sunucu Ayarları (server.properties)</div>
        <button class="btn btn-primary" onclick="saveSettings()">💾 Kaydet & Yeniden Başlat</button>
      </div>
      <div class="settings-grid" id="settings-grid"></div>
    </div>
  </div>

  <!-- Performans -->
  <div class="page" id="page-performance">
    <div class="grid-2">
      <div class="card">
        <div class="card-title">💻 Sistem Kaynakları</div>
        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--t2);margin-bottom:4px">
            <span>CPU</span><span id="p-cpu">—</span>
          </div>
          <div class="prog-bar"><div class="prog-fill pf-cpu" id="pb-cpu" style="width:0%"></div></div>
        </div>
        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--t2);margin-bottom:4px">
            <span>RAM</span><span id="p-ram">—</span>
          </div>
          <div class="prog-bar"><div class="prog-fill pf-ram" id="pb-ram" style="width:0%"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--t2);margin-bottom:4px">
            <span>Disk</span><span id="p-disk">—</span>
          </div>
          <div class="prog-bar"><div class="prog-fill pf-disk" id="pb-disk" style="width:0%"></div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">⛏️ Minecraft Kaynakları</div>
        <table class="table">
          <tr><td style="color:var(--t2)">MC RAM</td><td id="p-mc-ram">—</td></tr>
          <tr><td style="color:var(--t2)">TPS</td><td id="p-tps">—</td></tr>
          <tr><td style="color:var(--t2)">Oyuncu</td><td id="p-players">—</td></tr>
        </table>
        <button class="btn btn-ghost" style="margin-top:10px;width:100%" onclick="sendCmd2('tps')">📊 TPS Kontrol</button>
      </div>
    </div>
  </div>

  </div><!-- /pages -->
</div><!-- /main -->
</div><!-- /layout -->

<!-- Modal -->
<div class="modal-bg" id="modal">
  <div class="modal">
    <h3 id="modal-title">Modal</h3>
    <div id="modal-body"></div>
    <div class="modal-btns">
      <button class="btn btn-ghost" onclick="closeModal()">İptal</button>
      <button class="btn btn-primary" id="modal-ok" onclick="">Tamam</button>
    </div>
  </div>
</div>

<!-- Bildirimler -->
<div class="notif" id="notif"></div>

<script>
// ── Socket.IO ─────────────────────────────────────────────
const socket = io();
let currentPage = 'dashboard';
let currentFile = null;
let currentDir = '';
let serverRunning = false;

socket.on('console_line', data => {
  addConsoleLine(data);
});
socket.on('console_history', lines => {
  const el = document.getElementById('console-out');
  el.innerHTML = '';
  lines.forEach(l => addConsoleLine(l, false));
  el.scrollTop = el.scrollHeight;
});
socket.on('server_status', data => {
  updateStatus(data);
});
socket.on('players_update', players => {
  updatePlayersUI(players);
});
socket.on('stats_update', data => {
  if(data.ram_mb) { document.getElementById('tb-ram').textContent = data.ram_mb+'MB'; document.getElementById('d-ram').textContent = data.ram_mb; }
  if(data.tps)    { document.getElementById('tb-tps').textContent = data.tps; document.getElementById('d-tps').textContent = data.tps; }
  if(data.uptime) { const u=fmtUp(data.uptime); document.getElementById('tb-uptime').textContent=u; document.getElementById('d-uptime').textContent=u; }
});

// ── Sayfa geçişi ──────────────────────────────────────────
function goto(page) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.getElementById('page-'+page).classList.add('active');
  event.currentTarget.classList.add('active');
  currentPage = page;
  const titles = {dashboard:'📊 Dashboard',console:'💻 Konsol',players:'👥 Oyuncular',
    whitelist:'📋 Beyaz Liste',banlist:'🔨 Ban Listesi',plugins:'🔌 Pluginler',
    files:'📁 Dosyalar',worlds:'🌍 Dünyalar',settings:'⚙️ Ayarlar',performance:'📈 Performans'};
  document.getElementById('page-title').textContent = titles[page]||page;
  if(page==='players') refreshPlayers();
  if(page==='plugins') loadPlugins();
  if(page==='files') loadFiles(currentDir);
  if(page==='worlds') loadWorlds();
  if(page==='settings') loadSettings();
  if(page==='whitelist') loadWhitelist();
  if(page==='banlist') loadBanlist();
  if(page==='performance') updatePerformance();
}

// ── Konsol ─────────────────────────────────────────────────
function addConsoleLine(data, scroll=true) {
  const el = document.getElementById('console-out');
  const div = document.createElement('div');
  const line = data.line || '';
  let cls = 'log-default';
  if(line.includes('[Panel]')) cls='log-panel';
  else if(line.toLowerCase().includes('error') || line.toLowerCase().includes('exception')) cls='log-error';
  else if(line.toLowerCase().includes('warn')) cls='log-warn';
  else if(line.includes('INFO')) cls='log-info';
  div.className = cls;
  div.textContent = `[${data.ts}] ${line}`;
  el.appendChild(div);
  if(scroll) el.scrollTop = el.scrollHeight;
  // Dashboard son log
  const dl = document.getElementById('d-lastlog');
  if(dl) { const sp=document.createElement('div'); sp.textContent=div.textContent; sp.style.color=div.style.color||''; dl.appendChild(sp); if(dl.children.length>20) dl.removeChild(dl.firstChild); dl.scrollTop=dl.scrollHeight; }
}
function clearConsole() { document.getElementById('console-out').innerHTML=''; }
function scrollConsoleBottom() { const el=document.getElementById('console-out'); el.scrollTop=el.scrollHeight; }
function sendCmd() {
  const inp = document.getElementById('cmd-input');
  const cmd = inp.value.trim();
  if(!cmd) return;
  socket.emit('send_command', {cmd});
  inp.value='';
}
function sendCmd2(cmd) {
  socket.emit('send_command', {cmd});
  notify('Komut gönderildi: '+cmd, 'info');
}

// ── Sunucu kontrol ────────────────────────────────────────
async function serverAction(action) {
  const r = await fetch('/api/'+action, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  const d = await r.json();
  notify(d.msg||'İşlem yapıldı', d.ok?'ok':'err');
}

function updateStatus(data) {
  serverRunning = data.status === 'running';
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const badge = document.getElementById('d-status');
  const map = {stopped:['dot-red','Durduruldu','b-red'],
               starting:['dot-yellow','Başlıyor...','b-yellow'],
               running:['dot-green','Çalışıyor','b-green'],
               stopping:['dot-yellow','Duruyor...','b-yellow']};
  const [cls, label, bcls] = map[data.status]||map.stopped;
  dot.className = 'status-dot '+cls;
  txt.textContent = label;
  if(badge) { badge.className='badge '+bcls; badge.textContent=label; }
  if(data.version) { document.getElementById('mc-ver').textContent='Paper MC • '+data.version; document.getElementById('d-version').textContent=data.version; }
  const mr = document.getElementById('d-maxram');
  if(mr) mr.textContent = data.max_ram||'${MC_RAM}';
}

// ── Oyuncular ─────────────────────────────────────────────
function updatePlayersUI(players) {
  document.getElementById('tb-players').textContent = players.length;
  document.getElementById('d-players').textContent = players.length;
  const pl = document.getElementById('d-playerlist');
  if(pl) {
    if(players.length===0) pl.textContent='Online oyuncu yok';
    else pl.innerHTML=players.map(p=>`<div style="padding:4px 0;font-size:13px">🟢 ${p}</div>`).join('');
  }
  const tbody = document.getElementById('players-body');
  if(tbody) {
    if(players.length===0) { tbody.innerHTML='<tr><td colspan="3" style="color:var(--t2);text-align:center">Online oyuncu yok</td></tr>'; return; }
    tbody.innerHTML = players.map(p=>`
      <tr>
        <td><strong>${p}</strong></td>
        <td><span class="badge b-green">Online</span></td>
        <td style="display:flex;gap:4px;flex-wrap:wrap">
          <button class="btn btn-danger btn-sm" onclick="quickAction('kick','${p}')">Kick</button>
          <button class="btn btn-danger btn-sm" onclick="quickAction('ban','${p}')">Ban</button>
          <button class="btn btn-success btn-sm" onclick="quickAction('op','${p}')">OP</button>
          <button class="btn btn-ghost btn-sm" onclick="quickMsg('${p}')">💬</button>
        </td>
      </tr>`).join('');
  }
}

async function refreshPlayers() {
  const r = await fetch('/api/players');
  const d = await r.json();
  updatePlayersUI(d.players);
}

async function quickAction(action, player) {
  await fetch('/api/players/'+action, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player})});
  notify(`${player} → ${action}`, 'ok');
}
function quickMsg(player) {
  document.getElementById('msg-player').value=player;
  goto('players'); document.getElementById('msg-text').focus();
}
function playerAction(action) {
  const p = document.getElementById('bulk-player').value.trim();
  if(!p) return notify('Oyuncu adı girin','err');
  quickAction(action,p);
}
function setGamemode(mode) {
  const p = document.getElementById('bulk-player').value.trim();
  if(!p) return notify('Oyuncu adı girin','err');
  fetch('/api/players/gamemode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p,mode})});
  notify(`${p} → ${mode}`, 'ok');
}
async function sendMsg() {
  const p=document.getElementById('msg-player').value.trim();
  const m=document.getElementById('msg-text').value.trim();
  if(!p||!m) return;
  await fetch('/api/players/msg',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p,message:m})});
  notify('Mesaj gönderildi','ok');
}
function giveItem() {
  const p=document.getElementById('bulk-player').value.trim()||'@a';
  const item=document.getElementById('give-item').value.trim();
  const count=document.getElementById('give-count').value||1;
  if(!item) return notify('Item adı girin','err');
  fetch('/api/players/give',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p,item,count})});
  notify(`Give: ${count}x ${item} → ${p}`,'ok');
}

// ── Whitelist ─────────────────────────────────────────────
async function loadWhitelist() {
  const r=await fetch('/api/whitelist'); const d=await r.json();
  const tbody=document.getElementById('wl-body');
  if(!d.length) { tbody.innerHTML='<tr><td colspan="3" style="color:var(--t2);text-align:center">Beyaz liste boş</td></tr>'; return; }
  tbody.innerHTML=d.map(p=>`<tr><td>${p.name||p}</td><td style="font-family:var(--mono);font-size:10px;color:var(--t2)">${p.uuid||'—'}</td><td><button class="btn btn-danger btn-sm" onclick="wlRemove('${p.name||p}')">Kaldır</button></td></tr>`).join('');
}
async function wlAdd() { const p=document.getElementById('wl-player').value.trim(); if(!p)return; await fetch('/api/whitelist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p})}); loadWhitelist(); }
async function wlRemove(p) { await fetch('/api/whitelist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p})}); loadWhitelist(); }

// ── Ban ───────────────────────────────────────────────────
async function loadBanlist() {
  const r=await fetch('/api/banlist'); const d=await r.json();
  const tbody=document.getElementById('ban-body');
  if(!d.length){tbody.innerHTML='<tr><td colspan="4" style="color:var(--t2);text-align:center">Ban listesi boş</td></tr>';return;}
  tbody.innerHTML=d.map(p=>`<tr><td>${p.name}</td><td style="color:var(--t2);font-size:12px">${p.reason||'—'}</td><td style="font-size:11px;color:var(--t3)">${(p.created||'').slice(0,10)}</td><td><button class="btn btn-success btn-sm" onclick="pardon('${p.name}')">Affet</button></td></tr>`).join('');
}
async function banPlayer() { const p=document.getElementById('ban-player').value.trim(); if(!p)return; await fetch('/api/players/ban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p})}); loadBanlist(); }
async function pardon(p) { await fetch('/api/players/pardon',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player:p})}); loadBanlist(); }

// ── Pluginler ─────────────────────────────────────────────
async function loadPlugins() {
  const r=await fetch('/api/plugins'); const d=await r.json();
  const tbody=document.getElementById('plugins-body');
  if(!d.length){tbody.innerHTML='<tr><td colspan="3" style="color:var(--t2);text-align:center">Plugin yok</td></tr>';return;}
  tbody.innerHTML=d.map(p=>`<tr>
    <td><strong>${p.name}</strong><br><span style="font-size:10px;color:var(--t3)">${p.file}</span></td>
    <td style="font-size:11px;color:var(--t2)">${fmtSize(p.size)}</td>
    <td style="display:flex;gap:4px">
      <button class="btn btn-danger btn-sm" onclick="deletePlugin('${p.file}')">🗑</button>
    </td>
  </tr>`).join('');
}
async function uploadPlugin(input) {
  const fd=new FormData();
  for(const f of input.files) fd.append('file',f);
  const r=await fetch('/api/plugins/upload',{method:'POST',body:fd});
  const d=await r.json();
  notify(d.msg||'Yüklendi','ok');
  loadPlugins();
}
async function deletePlugin(file) {
  if(!confirm(`${file} silinsin mi?`)) return;
  await fetch('/api/plugins/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file})});
  notify('Plugin silindi','ok'); loadPlugins();
}
async function searchPlugins() {
  const q=document.getElementById('plugin-search-q').value.trim();
  if(!q) return;
  const res=document.getElementById('search-results');
  res.innerHTML='<div style="color:var(--t2);padding:10px">Aranıyor...</div>';
  const r=await fetch('/api/plugins/search?q='+encodeURIComponent(q));
  const d=await r.json();
  if(d.error||!d.length){res.innerHTML='<div style="color:var(--t2);padding:10px">Sonuç bulunamadı</div>';return;}
  res.innerHTML=d.map(p=>`<div class="search-item">
    <div class="si-info">
      <div class="si-name">${p.name}</div>
      <div class="si-desc">${p.description||''}</div>
      <div style="font-size:10px;color:var(--t3);margin-top:2px">⬇ ${(p.downloads||0).toLocaleString()}</div>
    </div>
    <a class="btn btn-primary btn-sm" href="${p.url}" target="_blank">Aç</a>
  </div>`).join('');
}

// ── Dosyalar ──────────────────────────────────────────────
async function loadFiles(path='') {
  currentDir=path;
  document.getElementById('file-path').textContent = '/'+path;
  const r=await fetch('/api/files?path='+encodeURIComponent(path));
  const items=await r.json();
  const el=document.getElementById('file-list');
  el.innerHTML=items.map(f=>`
    <div class="file-item" onclick="fileClick('${f.path}','${f.type}','${f.name}')">
      <span class="file-ico">${f.type==='dir'?'📁':fileIco(f.ext)}</span>
      <span class="file-name">${f.name}</span>
      <span class="file-size">${f.type==='dir'?'':fmtSize(f.size)}</span>
    </div>`).join('') || '<div style="padding:12px;color:var(--t2);font-size:12px">Klasör boş</div>';
}
function fileIco(ext) {
  const m={'.properties':'⚙','.json':'📋','.yml':'📋','.yaml':'📋','.jar':'☕',
    '.txt':'📄','.log':'📜','.sh':'🖥','.zip':'📦','.png':'🖼','.jpg':'🖼'};
  return m[ext]||'📄';
}
function fileGoUp() {
  const parts=currentDir.split('/').filter(Boolean);
  parts.pop();
  loadFiles(parts.join('/'));
}
function fileRefresh() { loadFiles(currentDir); }
async function fileClick(path, type, name) {
  document.querySelectorAll('.file-item').forEach(i=>i.classList.remove('selected'));
  event.currentTarget.classList.add('selected');
  currentFile=path;
  if(type==='dir') { loadFiles(path); return; }
  document.getElementById('editor-filename').textContent=name;
  const editable=['.properties','.json','.yml','.yaml','.txt','.log','.sh','.cfg','.conf','.toml'];
  const ext='.'+name.split('.').pop();
  if(editable.includes(ext)||name.includes('.')) {
    const r=await fetch('/api/files/read?path='+encodeURIComponent(path));
    const d=await r.json();
    document.getElementById('editor-area').value=d.content||'';
    document.getElementById('save-btn').disabled=false;
  } else {
    document.getElementById('editor-area').value='(Bu dosya türü düzenlenemez)';
    document.getElementById('save-btn').disabled=true;
  }
}
async function saveFile() {
  if(!currentFile) return;
  const content=document.getElementById('editor-area').value;
  await fetch('/api/files/write',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:currentFile,content})});
  notify('Kaydedildi','ok');
}
function downloadFile() {
  if(!currentFile) return;
  window.open('/api/files/download?path='+encodeURIComponent(currentFile));
}
async function deleteFile() {
  if(!currentFile) return;
  if(!confirm(currentFile+' silinsin mi?')) return;
  await fetch('/api/files/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentFile})});
  notify('Silindi','ok'); loadFiles(currentDir); currentFile=null;
  document.getElementById('editor-area').value='';
  document.getElementById('editor-filename').textContent='Dosya seçin';
}
async function uploadFile(input) {
  const fd=new FormData();
  fd.append('path',currentDir);
  for(const f of input.files) fd.append(f.name,f);
  await fetch('/api/files/upload',{method:'POST',body:fd});
  notify('Yüklendi','ok'); loadFiles(currentDir);
}
function showNewFileModal() {
  showModal('Yeni Dosya/Klasör','<input class="modal-input" id="nf-name" placeholder="isim.txt veya klasör-adı">',
    async ()=>{ const n=document.getElementById('nf-name').value.trim(); if(!n)return;
      if(n.includes('.')) await fetch('/api/files/write',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentDir+'/'+n,content:''})});
      else await fetch('/api/files/mkdir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentDir+'/'+n})});
      loadFiles(currentDir); closeModal(); });
}

// ── Dünyalar ──────────────────────────────────────────────
async function loadWorlds() {
  const r=await fetch('/api/worlds'); const d=await r.json();
  const el=document.getElementById('worlds-list');
  el.innerHTML=d.map(w=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid rgba(255,255,255,.05)">
    <div>
      <div style="font-size:14px;font-weight:600">🌍 ${w.name}</div>
      <div style="font-size:11px;color:var(--t2);margin-top:2px">Boyut: ${fmtSize(w.size)}</div>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-primary btn-sm" onclick="backupWorld('${w.name}')">💾 Yedekle</button>
      <button class="btn btn-danger btn-sm" onclick="deleteWorld('${w.name}')">🗑 Sil</button>
    </div>
  </div>`).join('')||'<div style="color:var(--t2)">Dünya bulunamadı</div>';
}
async function backupWorld(name) {
  notify('Yedekleniyor...','info');
  const r=await fetch('/api/worlds/backup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({world:name})});
  const d=await r.json();
  notify(d.ok?'Yedeklendi: '+d.file:'Hata','ok');
}
async function deleteWorld(name) {
  if(!confirm(name+' dünyası silinsin mi?')) return;
  await fetch('/api/worlds/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({world:name})});
  notify('Dünya silindi','ok'); loadWorlds();
}

// ── Ayarlar ───────────────────────────────────────────────
const SETTING_LABELS = {
  'server-port':'Port','max-players':'Max Oyuncu','online-mode':'Online Mode',
  'gamemode':'Oyun Modu','difficulty':'Zorluk','motd':'MOTD (Sunucu Adı)',
  'view-distance':'Görüş Mesafesi','simulation-distance':'Simülasyon Mesafesi',
  'spawn-protection':'Spawn Koruması','allow-flight':'Uçuşa İzin','white-list':'Beyaz Liste',
  'enable-command-block':'Komut Bloğu','max-tick-time':'Max Tick Süresi',
  'level-name':'Dünya Adı','pvp':'PvP','allow-nether':'Nether',
  'level-seed':'Dünya Seed'
};
async function loadSettings() {
  const r=await fetch('/api/settings'); const props=await r.json();
  const el=document.getElementById('settings-grid');
  el.innerHTML=Object.entries(props).map(([k,v])=>`
    <div class="setting-item">
      <div class="setting-label">${SETTING_LABELS[k]||k}</div>
      ${(v==='true'||v==='false')
        ?`<select class="setting-input" id="s-${k}"><option value="true" ${v==='true'?'selected':''}>true</option><option value="false" ${v==='false'?'selected':''}>false</option></select>`
        :`<input class="setting-input" id="s-${k}" value="${v}">`}
    </div>`).join('');
}
async function saveSettings() {
  const r=await fetch('/api/settings'); const props=await r.json();
  const updated={};
  for(const k of Object.keys(props)) {
    const el=document.getElementById('s-'+k);
    if(el) updated[k]=el.value;
  }
  await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(updated)});
  notify('Kaydedildi. Yeniden başlatılıyor...','ok');
  setTimeout(()=>serverAction('restart'),1000);
}

// ── Performans ────────────────────────────────────────────
async function updatePerformance() {
  const r=await fetch('/api/performance'); const d=await r.json();
  if(d.cpu!==undefined){document.getElementById('p-cpu').textContent=d.cpu+'%';document.getElementById('pb-cpu').style.width=d.cpu+'%';}
  if(d.ram_pct!==undefined){document.getElementById('p-ram').textContent=d.ram_used_mb+'MB / '+d.ram_total_mb+'MB';document.getElementById('pb-ram').style.width=d.ram_pct+'%';}
  if(d.disk_pct!==undefined){document.getElementById('p-disk').textContent=d.disk_pct+'%';document.getElementById('pb-disk').style.width=d.disk_pct+'%';}
  if(d.mc_ram_mb) document.getElementById('p-mc-ram').textContent=d.mc_ram_mb+' MB';
  if(d.tps) document.getElementById('p-tps').textContent=d.tps;
}
setInterval(()=>{ if(currentPage==='performance') updatePerformance(); }, 4000);

// ── Modal ─────────────────────────────────────────────────
function showModal(title, body, onok) {
  document.getElementById('modal-title').textContent=title;
  document.getElementById('modal-body').innerHTML=body;
  document.getElementById('modal-ok').onclick=onok;
  document.getElementById('modal').classList.add('show');
}
function closeModal() { document.getElementById('modal').classList.remove('show'); }
document.getElementById('modal').onclick=e=>{ if(e.target===document.getElementById('modal'))closeModal(); };

// ── Yardımcı ─────────────────────────────────────────────
function fmtSize(b) {
  if(b>1e9) return (b/1e9).toFixed(1)+'GB';
  if(b>1e6) return (b/1e6).toFixed(1)+'MB';
  if(b>1e3) return (b/1e3).toFixed(0)+'KB';
  return b+'B';
}
function fmtUp(s) {
  const h=Math.floor(s/3600), m=Math.floor((s%3600)/60);
  return h+'s '+m+'d';
}
function notify(msg, type='ok') {
  const el=document.getElementById('notif');
  const div=document.createElement('div');
  const cls={ok:'notif-ok',err:'notif-err',info:'notif-info'}[type]||'notif-info';
  div.className='notif-item '+cls;
  div.textContent=msg;
  el.appendChild(div);
  setTimeout(()=>div.remove(), 3500);
}

// ── Enter tuşu ───────────────────────────────────────────
document.getElementById('cmd-input').addEventListener('keydown', e=>{
  if(e.key==='Enter') sendCmd();
});
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════
#  BAŞLATMA
# ══════════════════════════════════════════════════════════════

def run_panel():
    threading.Thread(target=_monitor_ram, daemon=True).start()
    print(f"[MC Panel] 🚀 Port {PANEL_PORT} başlatılıyor...")
    socketio.run(app, host="0.0.0.0", port=PANEL_PORT,
                 debug=False, use_reloader=False, log_output=False)


if __name__ == "__main__":
    # Standalone çalıştırma
    MC_DIR.mkdir(parents=True, exist_ok=True)
    t = threading.Thread(target=lambda: (time.sleep(2), start_server()), daemon=True)
    t.start()
    run_panel()
