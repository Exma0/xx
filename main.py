"""
╔══════════════════════════════════════════════════════════════╗
║           WebOS — Tam Linux Web Masaüstü İşletim Sistemi     ║
║           Tek dosya: main.py                                  ║
║                                                              ║
║  Kurulum:  pip install flask flask-socketio eventlet psutil  ║
║  Çalıştır: python main.py                                    ║
║  Render:   gunicorn --worker-class eventlet -w 1 main:app    ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, pty, select, subprocess, threading, struct, fcntl, termios
import json, shutil, time, mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'webos-linux-2024')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet',
                    ping_timeout=60, ping_interval=25)

# ══════════════════════════════════════════════════════════════
#  PTY — Gerçek Terminal Oturumları
# ══════════════════════════════════════════════════════════════
_sessions = {}
_lock = threading.Lock()

def _make_session(sid, cols=220, rows=50):
    mfd, sfd = pty.openpty()
    env = {**os.environ,
           'TERM': 'xterm-256color', 'COLORTERM': 'truecolor',
           'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8',
           'HOME': os.path.expanduser('~'), 'SHELL': '/bin/bash',
           'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
                   ':/usr/local/games:/usr/games'}
    proc = subprocess.Popen(
        ['/bin/bash', '--login'],
        stdin=sfd, stdout=sfd, stderr=sfd,
        preexec_fn=os.setsid, env=env, close_fds=True)
    os.close(sfd)
    _winsz(mfd, cols, rows)
    s = {'proc': proc, 'fd': mfd, 'alive': True}
    threading.Thread(target=_reader, args=(sid, s), daemon=True).start()
    return s

def _winsz(fd, c, r):
    try: fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', r, c, 0, 0))
    except: pass

def _reader(sid, s):
    while s['alive']:
        try:
            if select.select([s['fd']], [], [], 0.04)[0]:
                d = os.read(s['fd'], 8192)
                if d: socketio.emit('o', {'d': d.decode('utf-8', 'replace')}, room=sid)
        except OSError: break
    s['alive'] = False
    socketio.emit('x', {}, room=sid)

def _kill(sid):
    with _lock: s = _sessions.pop(sid, None)
    if s:
        s['alive'] = False
        try: os.close(s['fd'])
        except: pass
        try: s['proc'].terminate(); s['proc'].wait(1)
        except: pass

@socketio.on('connect')
def on_connect():
    sid = request.sid
    c = int(request.args.get('c', 220))
    r = int(request.args.get('r', 50))
    with _lock: _sessions[sid] = _make_session(sid, c, r)

@socketio.on('disconnect')
def on_disconnect(): _kill(request.sid)

@socketio.on('i')
def on_input(data):
    with _lock: s = _sessions.get(request.sid)
    if s and s['alive']:
        try: os.write(s['fd'], data['d'].encode())
        except: pass

@socketio.on('r')
def on_resize(data):
    with _lock: s = _sessions.get(request.sid)
    if s: _winsz(s['fd'], int(data.get('c', 80)), int(data.get('r', 24)))

# ══════════════════════════════════════════════════════════════
#  Dosya Sistemi API
# ══════════════════════════════════════════════════════════════
def sp(p):
    return str(Path(str(p)).expanduser().resolve())

@app.route('/api/ls')
def api_ls():
    p = sp(request.args.get('path', '~'))
    try:
        ents = []
        for e in sorted(Path(p).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                st = e.stat()
                ents.append({'n': e.name, 'p': str(e), 'd': e.is_dir(),
                             's': st.st_size, 'x': e.suffix.lower(),
                             'm': int(st.st_mtime)})
            except: pass
        return jsonify({'ok': True, 'path': p, 'ents': ents, 'parent': str(Path(p).parent)})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/api/read')
def api_read():
    p = sp(request.args.get('path', ''))
    try:
        with open(p, 'r', errors='replace') as f:
            return jsonify({'ok': True, 'text': f.read(), 'path': p})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/api/write', methods=['POST'])
def api_write():
    d = request.json
    p = sp(d.get('path', ''))
    try:
        with open(p, 'w') as f: f.write(d.get('text', ''))
        return jsonify({'ok': True})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/api/del', methods=['POST'])
def api_del():
    p = sp(request.json.get('path', ''))
    try:
        shutil.rmtree(p) if Path(p).is_dir() else os.remove(p)
        return jsonify({'ok': True})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/api/mkdir', methods=['POST'])
def api_mkdir():
    p = sp(request.json.get('path', ''))
    try:
        os.makedirs(p, exist_ok=True)
        return jsonify({'ok': True})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/api/rename', methods=['POST'])
def api_rename():
    d = request.json
    try:
        os.rename(sp(d.get('src', '')), sp(d.get('dst', '')))
        return jsonify({'ok': True})
    except Exception as ex:
        return jsonify({'ok': False, 'err': str(ex)})

@app.route('/upload', methods=['POST'])
def upload():
    dest = request.form.get('path', os.path.expanduser('~'))
    res = []
    for f in request.files.getlist('files'):
        dst = Path(dest) / f.filename
        f.save(dst); res.append(str(dst))
    return jsonify({'ok': True, 'paths': res})

@app.route('/download')
def download():
    p = sp(request.args.get('path', ''))
    pp = Path(p)
    if not pp.exists() or not pp.is_file(): return 'Not found', 404
    return send_from_directory(str(pp.parent), pp.name, as_attachment=True)

# ══════════════════════════════════════════════════════════════
#  Sistem Bilgisi API
# ══════════════════════════════════════════════════════════════
@app.route('/api/sys')
def api_sys():
    info = {}
    if HAS_PSUTIL:
        info['cpu'] = psutil.cpu_percent(0.1)
        vm = psutil.virtual_memory()
        info.update({'rt': vm.total, 'ru': vm.used, 'rp': vm.percent})
        try:
            dk = psutil.disk_usage('/')
            info.update({'dt': dk.total, 'du': dk.used, 'dp': dk.percent})
        except: pass
        procs = []
        for p in sorted(psutil.process_iter(['pid','name','cpu_percent','memory_percent','status']),
                        key=lambda x: x.info.get('cpu_percent') or 0, reverse=True)[:25]:
            procs.append(p.info)
        info['procs'] = procs
        info['uptime'] = time.time() - psutil.boot_time()
        info['cores'] = psutil.cpu_count()
    else:
        try:
            with open('/proc/meminfo') as f:
                m = {l.split(':')[0]: int(l.split(':')[1].strip().split()[0]) for l in f if ':' in l}
            t = m.get('MemTotal', 0)*1024; av = m.get('MemAvailable', 0)*1024
            info.update({'rt': t, 'ru': t-av, 'rp': round((t-av)/t*100, 1) if t else 0})
        except: pass
        info['cpu'] = 0; info['uptime'] = 0
    try: info['kernel'] = subprocess.run(['uname','-r'], capture_output=True, text=True, timeout=2).stdout.strip()
    except: info['kernel'] = 'unknown'
    try: info['host'] = subprocess.run(['hostname'], capture_output=True, text=True, timeout=2).stdout.strip()
    except: info['host'] = 'webos'
    try:
        with open('/etc/os-release') as f:
            lines = dict(l.strip().split('=',1) for l in f if '=' in l)
        info['distro'] = lines.get('PRETTY_NAME','Linux').strip('"')
    except: info['distro'] = 'Linux'
    info['psutil'] = HAS_PSUTIL
    return jsonify(info)

# ══════════════════════════════════════════════════════════════
#  Ana HTML — Tam Masaüstü OS
# ══════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WebOS</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/xterm/5.3.0/xterm.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/xterm/5.3.0/xterm.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xterm/5.3.0/addon-fit.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xterm/5.3.0/addon-web-links.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root {
  --bg:#06070d;
  --desk:#080a12;
  --win:#0f1119;
  --win2:#131621;
  --bar:#0c0e18ee;
  --border:#ffffff0f;
  --border2:#ffffff18;
  --accent:#00e5ff;
  --accent2:#7c6aff;
  --accent3:#00ffaa;
  --red:#ff4757;
  --yellow:#ffa502;
  --green:#2ed573;
  --text:#e8eaf0;
  --text2:#8892a4;
  --text3:#4a5568;
  --r:12px;
  --shadow:0 32px 80px #00000090,0 0 0 1px #ffffff08;
  --font:'Sora',sans-serif;
  --mono:'JetBrains Mono',monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:var(--font);font-size:13px;user-select:none}

/* ── Aurora Background ── */
#aurora{position:fixed;inset:0;z-index:0;overflow:hidden}
#aurora::before,#aurora::after{content:'';position:absolute;border-radius:50%;filter:blur(80px);opacity:.15;animation:aurora 12s ease-in-out infinite alternate}
#aurora::before{width:700px;height:500px;top:-100px;left:-100px;background:radial-gradient(circle,#00e5ff,#7c6aff,transparent)}
#aurora::after{width:600px;height:500px;bottom:-100px;right:-100px;background:radial-gradient(circle,#00ffaa,#00e5ff,transparent);animation-delay:-6s}
@keyframes aurora{0%{transform:translate(0,0) scale(1)}100%{transform:translate(80px,60px) scale(1.15)}}

/* ── Desktop ── */
#desktop{position:fixed;inset:0;bottom:48px;z-index:1;display:grid;grid-template-columns:repeat(auto-fill,80px);grid-template-rows:repeat(auto-fill,90px);align-content:start;padding:20px;gap:6px}

.icon{display:flex;flex-direction:column;align-items:center;gap:6px;padding:10px 6px;border-radius:10px;cursor:pointer;transition:background .15s;width:80px}
.icon:hover{background:rgba(255,255,255,.07)}
.icon:active{background:rgba(255,255,255,.12)}
.icon .ico{font-size:32px;line-height:1;filter:drop-shadow(0 2px 8px rgba(0,200,255,.3))}
.icon .lbl{font-size:11px;font-weight:500;color:var(--text);text-align:center;text-shadow:0 1px 4px #000;word-break:break-word;line-height:1.3}

/* ── Taskbar ── */
#taskbar{position:fixed;bottom:0;left:0;right:0;height:48px;z-index:1000;background:var(--bar);backdrop-filter:blur(24px) saturate(180%);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 8px;gap:6px}
#tb-logo{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:18px;cursor:pointer;flex-shrink:0;transition:transform .2s;box-shadow:0 0 20px #00e5ff30}
#tb-logo:hover{transform:scale(1.08)}
#tb-sep{width:1px;height:24px;background:var(--border2);flex-shrink:0}
#tb-apps{flex:1;display:flex;align-items:center;gap:4px;overflow:hidden}
.tb-app{display:flex;align-items:center;gap:6px;padding:0 10px;height:32px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,.05);border:1px solid var(--border);transition:all .15s;max-width:160px;min-width:0}
.tb-app:hover{background:rgba(255,255,255,.1)}
.tb-app.focused{background:rgba(0,229,255,.12);border-color:rgba(0,229,255,.3)}
.tb-app.minimized{opacity:.5}
.tb-app .ta-ico{font-size:15px;flex-shrink:0}
.tb-app .ta-lbl{font-size:11px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)}
#tb-tray{display:flex;align-items:center;gap:10px;padding-left:8px;flex-shrink:0}
#tb-cpu-bar{width:48px;height:22px;background:rgba(255,255,255,.05);border-radius:6px;border:1px solid var(--border);overflow:hidden;position:relative;cursor:default}
#tb-cpu-fill{height:100%;background:linear-gradient(90deg,var(--accent3),var(--accent));transition:width .5s;border-radius:6px}
#tb-cpu-txt{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;color:var(--text)}
#tb-clock{font-size:12px;font-weight:600;color:var(--text);text-align:right;min-width:50px}
#tb-date{font-size:10px;color:var(--text2);text-align:right}

/* ── Window Manager ── */
#wm{position:fixed;inset:0;bottom:48px;z-index:10;pointer-events:none}
.win{position:absolute;background:var(--win);border:1px solid var(--border2);border-radius:var(--r);box-shadow:var(--shadow);display:flex;flex-direction:column;pointer-events:all;min-width:280px;min-height:180px;overflow:hidden;transition:box-shadow .2s}
.win.focused{border-color:rgba(0,229,255,.2);box-shadow:var(--shadow),0 0 0 1px rgba(0,229,255,.15)}
.win.minimized{display:none}
.win.maximized{top:0!important;left:0!important;width:100%!important;height:100%!important;border-radius:0;border:none}
.win.maximized .win-resize{display:none}

.win-title{height:38px;background:var(--win2);display:flex;align-items:center;padding:0 12px;gap:8px;cursor:move;flex-shrink:0;border-bottom:1px solid var(--border)}
.win-btns{display:flex;gap:6px;flex-shrink:0}
.wb{width:13px;height:13px;border-radius:50%;cursor:pointer;border:none;transition:filter .15s}
.wb:hover{filter:brightness(1.3)}
.wb.close{background:#ff5f57}
.wb.min{background:#febc2e}
.wb.max{background:#28c840}
.win-icon{font-size:15px;flex-shrink:0}
.win-name{font-size:12px;font-weight:600;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.win-body{flex:1;overflow:hidden;display:flex;flex-direction:column;position:relative}
.win-resize{position:absolute;bottom:0;right:0;width:18px;height:18px;cursor:se-resize;z-index:5}
.win-resize::after{content:'';position:absolute;bottom:4px;right:4px;width:6px;height:6px;border-right:2px solid var(--text3);border-bottom:2px solid var(--text3)}

/* ── Scrollbars ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--text3)}

/* ══ APP STYLES ══ */

/* Terminal */
.app-terminal{padding:4px;background:#0a0b10}
.xterm{height:100%}
.xterm-viewport{overflow-y:auto!important}

/* File Manager */
.app-fm{display:flex;flex-direction:column;height:100%}
.fm-toolbar{height:38px;background:var(--win2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 10px;gap:6px;flex-shrink:0}
.fm-path{flex:1;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:12px;font-family:var(--mono);color:var(--text);outline:none}
.fm-path:focus{border-color:var(--accent);background:rgba(0,229,255,.05)}
.fm-btn{background:rgba(255,255,255,.06);border:1px solid var(--border);color:var(--text2);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;transition:all .15s;white-space:nowrap;font-family:var(--font)}
.fm-btn:hover{background:rgba(255,255,255,.12);color:var(--text);border-color:var(--border2)}
.fm-grid{flex:1;overflow-y:auto;padding:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:4px;align-content:start}
.fm-item{display:flex;flex-direction:column;align-items:center;padding:8px 4px;border-radius:8px;cursor:pointer;transition:background .12s;gap:4px}
.fm-item:hover{background:rgba(255,255,255,.07)}
.fm-item.selected{background:rgba(0,229,255,.12);outline:1px solid rgba(0,229,255,.3)}
.fm-item .fi-ico{font-size:28px;line-height:1}
.fm-item .fi-name{font-size:11px;text-align:center;color:var(--text);word-break:break-all;line-height:1.3;max-width:80px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.fm-status{height:24px;background:var(--win2);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 12px;font-size:11px;color:var(--text2);flex-shrink:0;gap:8px}
.fm-empty{grid-column:1/-1;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:13px;padding:40px}

/* Context menu */
.ctx-menu{position:fixed;background:var(--win2);border:1px solid var(--border2);border-radius:10px;box-shadow:0 20px 50px #00000080;z-index:9000;padding:6px;min-width:160px;backdrop-filter:blur(16px)}
.ctx-item{padding:7px 14px;border-radius:6px;cursor:pointer;font-size:12px;display:flex;align-items:center;gap:8px;color:var(--text);transition:background .1s}
.ctx-item:hover{background:rgba(255,255,255,.08)}
.ctx-item.danger{color:var(--red)}
.ctx-item.danger:hover{background:rgba(255,71,87,.12)}
.ctx-sep{height:1px;background:var(--border);margin:4px 0}

/* Editor */
.app-editor{display:flex;flex-direction:column;height:100%}
.ed-toolbar{height:38px;background:var(--win2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 10px;gap:6px;flex-shrink:0}
.ed-fname{flex:1;font-size:11px;font-family:var(--mono);color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ed-btn{background:rgba(255,255,255,.06);border:1px solid var(--border);color:var(--text2);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;transition:all .15s;font-family:var(--font)}
.ed-btn:hover{background:rgba(255,255,255,.12);color:var(--text)}
.ed-btn.save{background:rgba(0,229,255,.15);border-color:rgba(0,229,255,.3);color:var(--accent)}
.ed-btn.save:hover{background:rgba(0,229,255,.25)}
.ed-area{flex:1;background:#080910;border:none;outline:none;resize:none;font-family:var(--mono);font-size:13px;line-height:1.7;color:#e2e8f0;padding:16px;tab-size:2}
.ed-status{height:24px;background:var(--win2);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 12px;font-size:10px;color:var(--text3);flex-shrink:0;gap:12px;font-family:var(--mono)}

/* System Monitor */
.app-mon{display:flex;flex-direction:column;height:100%;overflow:hidden}
.mon-top{padding:16px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;background:var(--win);border-bottom:1px solid var(--border);flex-shrink:0}
.mon-card{background:var(--win2);border:1px solid var(--border);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:8px}
.mon-card-hdr{display:flex;align-items:center;justify-content:space-between}
.mon-card-lbl{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.05em;text-transform:uppercase}
.mon-card-val{font-size:22px;font-weight:700;font-family:var(--mono);color:var(--text)}
.mon-bar-bg{height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}
.mon-bar-fg{height:100%;border-radius:3px;transition:width .5s}
.cpu-fg{background:linear-gradient(90deg,var(--accent),var(--accent2))}
.ram-fg{background:linear-gradient(90deg,var(--accent3),var(--accent))}
.dsk-fg{background:linear-gradient(90deg,var(--accent2),var(--red))}
.mon-hist{height:50px;width:100%;opacity:.7}
.mon-procs{flex:1;overflow-y:auto}
.proc-table{width:100%;border-collapse:collapse}
.proc-table th{background:var(--win2);padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:var(--text2);letter-spacing:.04em;text-transform:uppercase;position:sticky;top:0;border-bottom:1px solid var(--border)}
.proc-table td{padding:7px 12px;font-size:12px;font-family:var(--mono);border-bottom:1px solid rgba(255,255,255,.03)}
.proc-table tr:hover td{background:rgba(255,255,255,.03)}
.proc-status{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:600}
.ps-running{background:rgba(46,213,115,.15);color:var(--green)}
.ps-sleeping{background:rgba(255,255,255,.06);color:var(--text3)}

/* Settings */
.app-settings{overflow-y:auto;height:100%}
.set-section{padding:20px}
.set-title{font-size:18px;font-weight:700;margin-bottom:4px;color:var(--text)}
.set-sub{font-size:12px;color:var(--text2);margin-bottom:20px}
.set-label{font-size:12px;font-weight:600;color:var(--text2);margin-bottom:10px;display:block;text-transform:uppercase;letter-spacing:.06em}
.wallpapers{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px}
.wp{height:70px;border-radius:8px;cursor:pointer;border:2px solid transparent;transition:all .2s}
.wp:hover,.wp.active{border-color:var(--accent);transform:scale(1.03)}
.set-divider{height:1px;background:var(--border);margin:8px 0 24px}
.about-row{display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)}
.about-key{width:120px;font-size:12px;color:var(--text2);flex-shrink:0}
.about-val{font-size:12px;font-family:var(--mono);color:var(--text)}

/* Calculator */
.app-calc{height:100%;display:flex;flex-direction:column;padding:16px;gap:10px;background:var(--win)}
.calc-display{background:var(--bg);border-radius:10px;padding:16px 20px;text-align:right;border:1px solid var(--border)}
.calc-expr{font-size:12px;color:var(--text2);font-family:var(--mono);min-height:18px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.calc-result{font-size:32px;font-weight:700;font-family:var(--mono);color:var(--text);line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.calc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;flex:1}
.cb{background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:10px;font-size:16px;font-family:var(--mono);font-weight:600;color:var(--text);cursor:pointer;transition:all .12s;display:flex;align-items:center;justify-content:center}
.cb:hover{background:rgba(255,255,255,.12)}
.cb:active{transform:scale(.95)}
.cb.op{background:rgba(0,229,255,.1);border-color:rgba(0,229,255,.2);color:var(--accent)}
.cb.op:hover{background:rgba(0,229,255,.18)}
.cb.eq{background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#000;font-size:20px}
.cb.eq:hover{opacity:.9}
.cb.clear{background:rgba(255,71,87,.12);border-color:rgba(255,71,87,.2);color:var(--red)}
.cb.zero{grid-column:span 2}

/* Browser */
.app-browser{height:100%;display:flex;flex-direction:column}
.br-bar{height:42px;background:var(--win2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 10px;gap:8px;flex-shrink:0}
.br-url{flex:1;background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:8px;padding:5px 12px;font-size:12px;color:var(--text);outline:none;font-family:var(--mono)}
.br-url:focus{border-color:var(--accent);background:rgba(0,229,255,.05)}
.br-go{background:rgba(0,229,255,.15);border:1px solid rgba(0,229,255,.3);color:var(--accent);border-radius:8px;padding:5px 14px;font-size:12px;cursor:pointer;font-family:var(--font);font-weight:600}
.br-go:hover{background:rgba(0,229,255,.25)}
.br-frame{flex:1;border:none;background:#fff}
.br-note{flex:1;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:var(--text3);font-size:13px;text-align:center;padding:20px}

/* Input dialog */
.dialog-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:8000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.dialog{background:var(--win2);border:1px solid var(--border2);border-radius:14px;padding:24px;width:360px;box-shadow:0 30px 80px #00000090}
.dialog h4{font-size:15px;font-weight:700;margin-bottom:6px}
.dialog p{font-size:12px;color:var(--text2);margin-bottom:16px}
.dialog input{width:100%;background:var(--win);border:1px solid var(--border2);border-radius:8px;padding:9px 12px;font-size:13px;color:var(--text);outline:none;font-family:var(--mono);margin-bottom:14px}
.dialog input:focus{border-color:var(--accent)}
.dialog-btns{display:flex;gap:8px;justify-content:flex-end}
.d-btn{background:rgba(255,255,255,.06);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:7px 16px;font-size:12px;cursor:pointer;font-family:var(--font)}
.d-btn.primary{background:var(--accent);border:none;color:#000;font-weight:700}
.d-btn:hover{filter:brightness(1.15)}

/* Toast notifications */
#toast-container{position:fixed;bottom:60px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.toast{background:var(--win2);border:1px solid var(--border2);border-radius:10px;padding:10px 16px;font-size:12px;color:var(--text);box-shadow:0 8px 24px #00000060;animation:toastIn .3s ease;max-width:260px}
.toast.success{border-color:rgba(46,213,115,.3);background:rgba(46,213,115,.1)}
.toast.error{border-color:rgba(255,71,87,.3);background:rgba(255,71,87,.1)}
@keyframes toastIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}

/* Startup animation */
#boot{position:fixed;inset:0;background:var(--bg);z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:20px;transition:opacity .5s}
#boot.fade{opacity:0;pointer-events:none}
.boot-logo{font-size:48px;animation:bootPulse 1s ease-in-out infinite}
.boot-text{font-size:14px;color:var(--text2);letter-spacing:.1em}
.boot-bar{width:200px;height:3px;background:var(--border);border-radius:2px;overflow:hidden}
.boot-prog{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:2px;animation:bootLoad 1.8s ease forwards}
@keyframes bootPulse{0%,100%{filter:drop-shadow(0 0 8px var(--accent))}50%{filter:drop-shadow(0 0 24px var(--accent))}}
@keyframes bootLoad{0%{width:0}100%{width:100%}}

/* Upload drag */
.upload-dropzone{border:2px dashed var(--border2);border-radius:8px;padding:20px;text-align:center;cursor:pointer;font-size:12px;color:var(--text2);margin-top:8px;transition:all .2s}
.upload-dropzone:hover,.upload-dropzone.drag{border-color:var(--accent);color:var(--accent)}
</style>
</head>
<body>

<!-- Boot Screen -->
<div id="boot">
  <div class="boot-logo">🐧</div>
  <div class="boot-text">WebOS Linux başlatılıyor...</div>
  <div class="boot-bar"><div class="boot-prog"></div></div>
</div>

<!-- Aurora Background -->
<div id="aurora"></div>

<!-- Desktop Icons -->
<div id="desktop">
  <div class="icon" ondblclick="OS.open('terminal')">
    <div class="ico">🖥️</div><div class="lbl">Terminal</div>
  </div>
  <div class="icon" ondblclick="OS.open('files')">
    <div class="ico">📁</div><div class="lbl">Dosyalar</div>
  </div>
  <div class="icon" ondblclick="OS.open('editor')">
    <div class="ico">📝</div><div class="lbl">Editör</div>
  </div>
  <div class="icon" ondblclick="OS.open('monitor')">
    <div class="ico">📊</div><div class="lbl">Sistem</div>
  </div>
  <div class="icon" ondblclick="OS.open('browser')">
    <div class="ico">🌐</div><div class="lbl">Tarayıcı</div>
  </div>
  <div class="icon" ondblclick="OS.open('calc')">
    <div class="ico">🧮</div><div class="lbl">Hesap Makinesi</div>
  </div>
  <div class="icon" ondblclick="OS.open('settings')">
    <div class="ico">⚙️</div><div class="lbl">Ayarlar</div>
  </div>
</div>

<!-- Window Manager -->
<div id="wm"></div>

<!-- Taskbar -->
<div id="taskbar">
  <div id="tb-logo" onclick="OS.open('settings')" title="WebOS">🐧</div>
  <div id="tb-sep"></div>
  <div id="tb-apps"></div>
  <div id="tb-tray">
    <div id="tb-cpu-bar" title="CPU Kullanımı">
      <div id="tb-cpu-fill" style="width:0%"></div>
      <div id="tb-cpu-txt">0%</div>
    </div>
    <div>
      <div id="tb-clock">--:--</div>
      <div id="tb-date"></div>
    </div>
  </div>
</div>

<!-- Context Menu -->
<div id="ctx" class="ctx-menu" style="display:none"></div>

<!-- Toast Container -->
<div id="toast-container"></div>

<script>
// ═══════════════════════════════════════════════════════
//  WebOS Core
// ═══════════════════════════════════════════════════════
const OS = {
  wins: {},
  topZ: 100,
  nextId: 1,

  open(app, opts={}) {
    const cfg = OS.apps[app];
    if (!cfg) return;
    const id = OS.nextId++;
    const w = OS._createWin(id, cfg, opts);
    OS.wins[id] = w;
    OS.focus(id);
    OS._addTaskbar(id, cfg);
    if (cfg.init) cfg.init(id, w.el, opts);
    return id;
  },

  _createWin(id, cfg, opts) {
    const el = document.createElement('div');
    el.className = 'win';
    el.id = `win-${id}`;

    const dw = Math.min(cfg.w || 800, window.innerWidth - 80);
    const dh = Math.min(cfg.h || 500, window.innerHeight - 100);
    const x = 40 + (id % 6) * 30;
    const y = 30 + (id % 4) * 25;

    el.style.cssText = `width:${dw}px;height:${dh}px;left:${x}px;top:${y}px`;

    el.innerHTML = `
      <div class="win-title" data-id="${id}">
        <div class="win-btns">
          <button class="wb close" onclick="OS.close(${id})"></button>
          <button class="wb min"   onclick="OS.minimize(${id})"></button>
          <button class="wb max"   onclick="OS.toggleMax(${id})"></button>
        </div>
        <span class="win-icon">${cfg.icon}</span>
        <span class="win-name">${cfg.title}</span>
      </div>
      <div class="win-body">${cfg.html || ''}</div>
      <div class="win-resize" data-id="${id}"></div>`;

    document.getElementById('wm').appendChild(el);
    OS._makeDraggable(el);
    OS._makeResizable(el);
    el.addEventListener('mousedown', () => OS.focus(id));
    return { el, cfg, minimized: false, maximized: false };
  },

  close(id) {
    const w = OS.wins[id];
    if (!w) return;
    if (w.cfg.onClose) w.cfg.onClose(id);
    w.el.remove();
    document.getElementById(`tbapp-${id}`)?.remove();
    delete OS.wins[id];
  },

  minimize(id) {
    const w = OS.wins[id];
    if (!w) return;
    w.minimized = !w.minimized;
    w.el.classList.toggle('minimized', w.minimized);
    document.getElementById(`tbapp-${id}`)?.classList.toggle('minimized', w.minimized);
  },

  toggleMax(id) {
    const w = OS.wins[id];
    if (!w) return;
    w.maximized = !w.maximized;
    if (w.maximized) {
      w._prev = { l:w.el.style.left,t:w.el.style.top,wi:w.el.style.width,h:w.el.style.height };
    } else if (w._prev) {
      Object.assign(w.el.style, {left:w._prev.l,top:w._prev.t,width:w._prev.wi,height:w._prev.h});
    }
    w.el.classList.toggle('maximized', w.maximized);
  },

  focus(id) {
    Object.entries(OS.wins).forEach(([wid, w]) => {
      w.el.classList.toggle('focused', +wid === id);
      w.el.style.zIndex = +wid === id ? ++OS.topZ : w.el.style.zIndex;
      document.getElementById(`tbapp-${wid}`)?.classList.toggle('focused', +wid === id);
    });
    if (OS.wins[id]?.minimized) OS.minimize(id);
  },

  _addTaskbar(id, cfg) {
    const el = document.createElement('div');
    el.className = 'tb-app';
    el.id = `tbapp-${id}`;
    el.innerHTML = `<span class="ta-ico">${cfg.icon}</span><span class="ta-lbl">${cfg.title}</span>`;
    el.onclick = () => {
      if (OS.wins[id]?.minimized) { OS.minimize(id); OS.focus(id); }
      else if (OS.wins[id]?.el.classList.contains('focused')) OS.minimize(id);
      else OS.focus(id);
    };
    document.getElementById('tb-apps').appendChild(el);
  },

  _makeDraggable(el) {
    let ox, oy, dragging=false, titlebar;
    el.addEventListener('mousedown', e => {
      titlebar = e.target.closest('.win-title');
      if (!titlebar || e.target.closest('.win-btns')) return;
      dragging=true; ox=e.clientX-el.offsetLeft; oy=e.clientY-el.offsetTop;
      document.body.style.cursor='move';
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const nx = Math.max(0, Math.min(e.clientX-ox, window.innerWidth-el.offsetWidth));
      const ny = Math.max(0, Math.min(e.clientY-oy, window.innerHeight-100));
      el.style.left=nx+'px'; el.style.top=ny+'px';
    });
    document.addEventListener('mouseup', () => { dragging=false; document.body.style.cursor=''; });
  },

  _makeResizable(el) {
    const h = el.querySelector('.win-resize');
    let rx, ry, rw, rh, resizing=false;
    h.addEventListener('mousedown', e => {
      resizing=true; e.stopPropagation();
      rx=e.clientX; ry=e.clientY; rw=el.offsetWidth; rh=el.offsetHeight;
    });
    document.addEventListener('mousemove', e => {
      if (!resizing) return;
      el.style.width=Math.max(300,rw+e.clientX-rx)+'px';
      el.style.height=Math.max(200,rh+e.clientY-ry)+'px';
      // Notify terminal resize
      const id = +el.id.replace('win-','');
      OS.wins[id]?.cfg.onResize?.(id);
    });
    document.addEventListener('mouseup', () => { resizing=false; });
  },

  // App definitions
  apps: {}
};

// ─── Desktop right-click ──────────────────────────────
document.getElementById('desktop').addEventListener('contextmenu', e => {
  e.preventDefault();
  showCtx(e.clientX, e.clientY, [
    {ico:'🖥️', label:'Terminal Aç',    fn:()=>OS.open('terminal')},
    {ico:'📁', label:'Dosyalar',        fn:()=>OS.open('files')},
    {ico:'📝', label:'Editör',          fn:()=>OS.open('editor')},
    {ico:'📊', label:'Sistem Monitörü', fn:()=>OS.open('monitor')},
    'sep',
    {ico:'⚙️', label:'Ayarlar',         fn:()=>OS.open('settings')},
    {ico:'🔄', label:'Sayfayı Yenile',  fn:()=>location.reload()},
  ]);
});

function showCtx(x, y, items) {
  const ctx = document.getElementById('ctx');
  ctx.innerHTML = '';
  items.forEach(item => {
    if (item === 'sep') { const s=document.createElement('div'); s.className='ctx-sep'; ctx.appendChild(s); return; }
    const d = document.createElement('div');
    d.className = 'ctx-item' + (item.danger?' danger':'');
    d.innerHTML = `<span>${item.ico}</span><span>${item.label}</span>`;
    d.onclick = () => { hideCtx(); item.fn(); };
    ctx.appendChild(d);
  });
  ctx.style.cssText = `display:block;left:${Math.min(x,window.innerWidth-180)}px;top:${Math.min(y,window.innerHeight-ctx.scrollHeight-60)}px`;
}
function hideCtx() { document.getElementById('ctx').style.display='none'; }
document.addEventListener('click', hideCtx);
document.addEventListener('contextmenu', e => { if (!e.target.closest('#ctx')) hideCtx(); });

// ─── Toast ────────────────────────────────────────────
function toast(msg, type='') {
  const d = document.createElement('div');
  d.className = 'toast ' + type;
  d.textContent = msg;
  document.getElementById('toast-container').appendChild(d);
  setTimeout(() => d.remove(), 3000);
}

// ─── Dialog ───────────────────────────────────────────
function prompt(title, msg, def='') {
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'dialog-overlay';
    ov.innerHTML = `<div class="dialog">
      <h4>${title}</h4><p>${msg}</p>
      <input id="dinput" value="${def}" placeholder="${def}">
      <div class="dialog-btns">
        <button class="d-btn" id="dcancel">İptal</button>
        <button class="d-btn primary" id="dok">Tamam</button>
      </div></div>`;
    document.body.appendChild(ov);
    const inp = ov.querySelector('#dinput');
    inp.focus(); inp.select();
    const done = v => { ov.remove(); resolve(v); };
    ov.querySelector('#dok').onclick = () => done(inp.value);
    ov.querySelector('#dcancel').onclick = () => done(null);
    inp.addEventListener('keydown', e => { if(e.key==='Enter') done(inp.value); if(e.key==='Escape') done(null); });
  });
}

// ─── Clock ────────────────────────────────────────────
function updateClock() {
  const n = new Date();
  document.getElementById('tb-clock').textContent =
    n.toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'});
  document.getElementById('tb-date').textContent =
    n.toLocaleDateString('tr-TR',{day:'numeric',month:'short'});
}
setInterval(updateClock, 1000); updateClock();

// ─── System tray CPU ─────────────────────────────────
async function updateSysTray() {
  try {
    const d = await fetch('/api/sys').then(r=>r.json());
    const pct = d.cpu || 0;
    document.getElementById('tb-cpu-fill').style.width = pct+'%';
    document.getElementById('tb-cpu-txt').textContent = Math.round(pct)+'%';
  } catch{}
}
setInterval(updateSysTray, 5000); updateSysTray();

// Wallpapers
const wallpapers = [
  'radial-gradient(ellipse at 20% 50%, #1a0533 0%, #050510 60%)',
  'linear-gradient(135deg, #0a0f2e 0%, #051020 50%, #0a1a10 100%)',
  'radial-gradient(ellipse at 80% 20%, #0d1a2e 0%, #050a0e 70%)',
  'linear-gradient(180deg, #0a0512 0%, #060612 50%, #030808 100%)',
  'radial-gradient(circle at 50% 50%, #12080a 0%, #06060f 100%)',
];
function setWallpaper(idx) {
  document.getElementById('aurora').style.background = wallpapers[idx] || '';
  document.getElementById('desktop').style.background = wallpapers[idx] || '';
  localStorage.setItem('wp', idx);
}

// ═══════════════════════════════════════════════════════
//  APP: TERMINAL
// ═══════════════════════════════════════════════════════
const terminalSessions = {};

OS.apps.terminal = {
  icon: '🖥️', title: 'Terminal', w: 800, h: 480,
  html: `<div class="app-terminal" id="tterm-WFILL" style="flex:1;height:100%"></div>`,

  init(id, el) {
    const wid = id;
    const container = el.querySelector('.win-body');
    container.querySelector('[id^="tterm"]').id = `tterm-${wid}`;

    const term = new Terminal({
      theme: {
        background:'#080910', foreground:'#e2e8f0',
        black:'#0a0b10', brightBlack:'#3a4155',
        red:'#ff4757', brightRed:'#ff7070',
        green:'#2ed573', brightGreen:'#57f287',
        yellow:'#ffa502', brightYellow:'#ffd04a',
        blue:'#00e5ff', brightBlue:'#55e8ff',
        magenta:'#a855f7', brightMagenta:'#d087ff',
        cyan:'#00b4d8', brightCyan:'#47d4f5',
        white:'#c8d0e0', brightWhite:'#f1f5f9',
        cursor:'#00e5ff', cursorAccent:'#080910',
        selectionBackground:'rgba(0,229,255,.2)',
      },
      fontFamily:"'JetBrains Mono',monospace",
      fontSize:13.5, lineHeight:1.25,
      cursorBlink:true, cursorStyle:'block',
      scrollback:10000,
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon.WebLinksAddon());

    const div = document.getElementById(`tterm-${wid}`);
    div.style.height = '100%';
    term.open(div);
    fit.fit();

    const sock = io({ query: { c: term.cols, r: term.rows } });
    sock.on('connect', () => term.write('\x1b[2J\x1b[H'));
    sock.on('o', d => term.write(d.d));
    sock.on('x', () => term.write('\r\n\x1b[31m[Oturum kapandı]\x1b[0m\r\n'));
    term.onData(d => sock.emit('i', { d }));

    terminalSessions[wid] = { term, fit, sock };

    // resize observer
    const ro = new ResizeObserver(() => {
      fit.fit();
      sock.emit('r', { c: term.cols, r: term.rows });
    });
    ro.observe(div);
  },

  onClose(id) {
    const s = terminalSessions[id];
    if (s) { s.sock.disconnect(); delete terminalSessions[id]; }
  },

  onResize(id) {
    const s = terminalSessions[id];
    if (s) { setTimeout(() => { s.fit.fit(); s.sock.emit('r',{c:s.term.cols,r:s.term.rows}); }, 50); }
  }
};

// ═══════════════════════════════════════════════════════
//  APP: FILE MANAGER
// ═══════════════════════════════════════════════════════
const fmState = {};

OS.apps.files = {
  icon: '📁', title: 'Dosyalar', w: 820, h: 540,
  html: `<div class="app-fm">
    <div class="fm-toolbar">
      <button class="fm-btn" id="fm-back">◀</button>
      <button class="fm-btn" id="fm-up">↑ Yukarı</button>
      <input class="fm-path" id="fm-pathbar">
      <button class="fm-btn" id="fm-newfolder">+ Klasör</button>
      <button class="fm-btn" id="fm-upload">⬆ Yükle</button>
      <button class="fm-btn" id="fm-refresh">↻</button>
    </div>
    <div class="fm-grid" id="fm-grid"></div>
    <div class="fm-status" id="fm-status"></div>
    <input type="file" id="fm-file-input" multiple style="display:none">
  </div>`,

  init(id, el, opts) {
    const state = fmState[id] = { path: opts.path || os_home(), history: [] };
    const $ = s => el.querySelector(s);

    const load = async (path, addHistory=true) => {
      const res = await fetch(`/api/ls?path=${encodeURIComponent(path)}`).then(r=>r.json());
      if (!res.ok) { toast('Dizin açılamadı: '+res.err, 'error'); return; }
      if (addHistory && state.path !== path) state.history.push(state.path);
      state.path = res.path;
      $('#fm-pathbar').value = res.path;
      const grid = $('#fm-grid');
      grid.innerHTML = '';
      res.ents.forEach(e => {
        const d = document.createElement('div');
        d.className = 'fm-item';
        d.dataset.path = e.p;
        d.dataset.isdir = e.d;
        d.innerHTML = `<div class="fi-ico">${fileIcon(e)}</div><div class="fi-name">${e.n}</div>`;
        d.ondblclick = () => e.d ? load(e.p) : OS.open('editor', {path: e.p});
        d.addEventListener('contextmenu', ev => {
          ev.preventDefault(); ev.stopPropagation();
          grid.querySelectorAll('.fm-item').forEach(x=>x.classList.remove('selected'));
          d.classList.add('selected');
          showCtx(ev.clientX, ev.clientY, [
            {ico:'📂', label:'Aç',          fn:()=>e.d?load(e.p):OS.open('editor',{path:e.p})},
            {ico:'✏️', label:'Yeniden Adlandır', fn:()=>fmRename(e.p, state.path, load)},
            {ico:'💾', label:'İndir',        fn:()=>fmDownload(e.p)},
            'sep',
            {ico:'🗑️', label:'Sil',  danger:true, fn:()=>fmDelete(e.p, ()=>load(state.path,false))},
          ]);
        });
        grid.appendChild(d);
      });
      $('#fm-status').innerHTML = `<span>${res.ents.length} öğe</span><span>${res.path}</span>`;
    };

    $('#fm-back').onclick = () => { if(state.history.length) load(state.history.pop(), false); };
    $('#fm-up').onclick   = () => load(fmParent(state.path));
    $('#fm-refresh').onclick = () => load(state.path, false);
    $('#fm-pathbar').addEventListener('keydown', e => { if(e.key==='Enter') load(e.target.value); });
    $('#fm-newfolder').onclick = async () => {
      const name = await prompt('Yeni Klasör', 'Klasör adı:', 'Yeni Klasör');
      if (!name) return;
      const res = await fetch('/api/mkdir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:state.path+'/'+name})}).then(r=>r.json());
      if(res.ok) load(state.path,false); else toast('Hata: '+res.err,'error');
    };
    $('#fm-upload').onclick = () => $('#fm-file-input').click();
    $('#fm-file-input').onchange = async ev => {
      const fd = new FormData();
      [...ev.target.files].forEach(f=>fd.append('files',f));
      fd.append('path', state.path);
      await fetch('/upload',{method:'POST',body:fd});
      toast('Dosyalar yüklendi ✓','success');
      load(state.path,false);
    };

    load(state.path);
  }
};

function fileIcon(e) {
  if (e.d) return '📁';
  const x = e.x;
  if (['.py','.js','.ts','.jsx','.tsx','.html','.css','.sh','.c','.cpp','.rs','.go'].includes(x)) return '📄';
  if (['.png','.jpg','.jpeg','.gif','.webp','.svg','.ico'].includes(x)) return '🖼️';
  if (['.mp4','.mkv','.avi','.mov','.webm'].includes(x)) return '🎬';
  if (['.mp3','.wav','.flac','.ogg','.aac'].includes(x)) return '🎵';
  if (['.zip','.tar','.gz','.bz2','.xz','.7z'].includes(x)) return '📦';
  if (['.pdf'].includes(x)) return '📕';
  if (['.txt','.md','.rst','.log'].includes(x)) return '📃';
  if (['.json','.yaml','.toml','.ini','.cfg','.conf'].includes(x)) return '⚙️';
  return '📄';
}

function fmParent(p) {
  const pp = p.split('/');
  if(pp.length<=2) return '/';
  pp.pop(); return pp.join('/') || '/';
}

async function fmRename(p, dir, reload) {
  const base = p.split('/').pop();
  const name = await prompt('Yeniden Adlandır', 'Yeni isim:', base);
  if (!name || name===base) return;
  const res = await fetch('/api/rename',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({src:p, dst:dir+'/'+name})}).then(r=>r.json());
  if(res.ok) reload(dir,false); else toast('Hata: '+res.err,'error');
}

async function fmDelete(p, reload) {
  if (!confirm(`"${p.split('/').pop()}" silinsin mi?`)) return;
  const res = await fetch('/api/del',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})}).then(r=>r.json());
  if(res.ok){toast('Silindi','success');reload();}else toast('Hata: '+res.err,'error');
}

function fmDownload(p) {
  window.open('/download?path='+encodeURIComponent(p));
}

function os_home() { return '/root'; }

// ═══════════════════════════════════════════════════════
//  APP: TEXT EDITOR
// ═══════════════════════════════════════════════════════
const editorState = {};

OS.apps.editor = {
  icon: '📝', title: 'Editör', w: 820, h: 580,
  html: `<div class="app-editor">
    <div class="ed-toolbar">
      <button class="ed-btn" id="ed-new">+ Yeni</button>
      <button class="ed-btn" id="ed-open">📂 Aç</button>
      <button class="ed-btn save" id="ed-save">💾 Kaydet</button>
      <span class="ed-fname" id="ed-fname">Yeni Dosya</span>
    </div>
    <textarea class="ed-area" id="ed-area" spellcheck="false" placeholder="Kod yaz veya dosya aç..."></textarea>
    <div class="ed-status">
      <span id="ed-lang">Düz Metin</span>
      <span id="ed-pos">Satır 1, Sütun 1</span>
      <span id="ed-lines">0 satır</span>
      <span id="ed-saved" style="color:var(--green)">● Kaydedildi</span>
    </div>
  </div>`,

  init(id, el, opts) {
    const state = editorState[id] = { path: opts.path || null, saved: true };
    const $ = s => el.querySelector(s);

    const setTitle = () => {
      const name = state.path ? state.path.split('/').pop() : 'Yeni Dosya';
      $('#ed-fname').textContent = state.path || 'Yeni Dosya';
      const win = OS.wins[id];
      if (win) win.el.querySelector('.win-name').textContent = '📝 '+name;
    };

    const setLang = path => {
      const ext = (path||'').split('.').pop().toLowerCase();
      const langs = {py:'Python',js:'JavaScript',ts:'TypeScript',html:'HTML',css:'CSS',
        sh:'Shell',json:'JSON',md:'Markdown',c:'C',cpp:'C++',rs:'Rust',go:'Go',
        yaml:'YAML',toml:'TOML',txt:'Düz Metin'};
      $('#ed-lang').textContent = langs[ext] || 'Düz Metin';
    };

    const markDirty = () => {
      state.saved = false;
      $('#ed-saved').textContent = '● Kaydedilmedi';
      $('#ed-saved').style.color = 'var(--yellow)';
    };
    const markSaved = () => {
      state.saved = true;
      $('#ed-saved').textContent = '● Kaydedildi';
      $('#ed-saved').style.color = 'var(--green)';
    };

    const area = $('#ed-area');
    area.addEventListener('input', () => {
      markDirty();
      const lines = area.value.split('\n').length;
      $('#ed-lines').textContent = lines + ' satır';
    });
    area.addEventListener('keyup', () => {
      const txt = area.value.substring(0, area.selectionStart);
      const line = txt.split('\n').length;
      const col  = txt.split('\n').pop().length + 1;
      $('#ed-pos').textContent = `Satır ${line}, Sütun ${col}`;
    });
    area.addEventListener('keydown', e => {
      if (e.key==='Tab') {
        e.preventDefault();
        const s=area.selectionStart, en=area.selectionEnd;
        area.value=area.value.substring(0,s)+'  '+area.value.substring(en);
        area.selectionStart=area.selectionEnd=s+2;
      }
      if ((e.ctrlKey||e.metaKey) && e.key==='s') { e.preventDefault(); save(); }
    });

    const load = async path => {
      const res = await fetch(`/api/read?path=${encodeURIComponent(path)}`).then(r=>r.json());
      if (!res.ok) { toast('Dosya açılamadı: '+res.err,'error'); return; }
      area.value = res.text;
      state.path = res.path;
      const lines = res.text.split('\n').length;
      $('#ed-lines').textContent = lines+' satır';
      setTitle(); setLang(res.path); markSaved();
    };

    const save = async () => {
      if (!state.path) {
        const p = await prompt('Kaydet', 'Dosya yolu:', '/root/dosya.txt');
        if (!p) return;
        state.path = p;
      }
      const res = await fetch('/api/write',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({path:state.path,text:area.value})}).then(r=>r.json());
      if(res.ok){markSaved();setTitle();toast('Kaydedildi ✓','success');}
      else toast('Kayıt hatası: '+res.err,'error');
    };

    $('#ed-new').onclick = () => { area.value=''; state.path=null; setTitle(); markSaved(); };
    $('#ed-open').onclick = async () => {
      const p = await prompt('Dosya Aç','Dosya yolu:','/root/');
      if(p) load(p);
    };
    $('#ed-save').onclick = save;

    if (opts.path) load(opts.path);
    setTitle();
  }
};

// ═══════════════════════════════════════════════════════
//  APP: SYSTEM MONITOR
// ═══════════════════════════════════════════════════════
const monState = {};

OS.apps.monitor = {
  icon: '📊', title: 'Sistem Monitörü', w: 860, h: 560,
  html: `<div class="app-mon">
    <div class="mon-top">
      <div class="mon-card">
        <div class="mon-card-hdr"><span class="mon-card-lbl">CPU</span><span style="font-size:11px;color:var(--text2)" id="mon-cores">-</span></div>
        <div class="mon-card-val" id="mon-cpu">0%</div>
        <div class="mon-bar-bg"><div class="mon-bar-fg cpu-fg" id="mon-cpu-bar" style="width:0%"></div></div>
        <canvas class="mon-hist" id="mon-cpu-hist"></canvas>
      </div>
      <div class="mon-card">
        <div class="mon-card-hdr"><span class="mon-card-lbl">RAM</span><span style="font-size:11px;color:var(--text2)" id="mon-ramtot">-</span></div>
        <div class="mon-card-val" id="mon-ram">0%</div>
        <div class="mon-bar-bg"><div class="mon-bar-fg ram-fg" id="mon-ram-bar" style="width:0%"></div></div>
        <canvas class="mon-hist" id="mon-ram-hist"></canvas>
      </div>
      <div class="mon-card">
        <div class="mon-card-hdr"><span class="mon-card-lbl">Disk</span><span style="font-size:11px;color:var(--text2)" id="mon-disktot">-</span></div>
        <div class="mon-card-val" id="mon-disk">0%</div>
        <div class="mon-bar-bg"><div class="mon-bar-fg dsk-fg" id="mon-disk-bar" style="width:0%"></div></div>
        <div style="font-size:11px;color:var(--text2);margin-top:4px" id="mon-info"></div>
      </div>
    </div>
    <div class="mon-procs">
      <table class="proc-table">
        <thead><tr><th>PID</th><th>Ad</th><th>CPU%</th><th>RAM%</th><th>Durum</th></tr></thead>
        <tbody id="mon-tbody"></tbody>
      </table>
    </div>
  </div>`,

  init(id, el) {
    const cpuHist=[], ramHist=[];
    let interval;

    const drawHist = (canvas, hist, color) => {
      const ctx=canvas.getContext('2d'); const W=canvas.width,H=canvas.height;
      ctx.clearRect(0,0,W,H);
      ctx.strokeStyle=color; ctx.lineWidth=1.5;
      ctx.beginPath();
      hist.forEach((v,i) => {
        const x=i/(hist.length-1||1)*W, y=H-(v/100)*H;
        i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
      });
      ctx.stroke();
      // Fill
      ctx.lineTo(W,H); ctx.lineTo(0,H); ctx.closePath();
      ctx.fillStyle=color+'22'; ctx.fill();
    };

    const update = async () => {
      try {
        const d = await fetch('/api/sys').then(r=>r.json());
        const cpu=d.cpu||0, ram=d.rp||0, dsk=d.dp||0;
        cpuHist.push(cpu); if(cpuHist.length>40) cpuHist.shift();
        ramHist.push(ram); if(ramHist.length>40) ramHist.shift();

        el.querySelector('#mon-cpu').textContent=cpu.toFixed(1)+'%';
        el.querySelector('#mon-cpu-bar').style.width=cpu+'%';
        el.querySelector('#mon-ram').textContent=ram.toFixed(1)+'%';
        el.querySelector('#mon-ram-bar').style.width=ram+'%';
        el.querySelector('#mon-disk').textContent=(dsk||0).toFixed(1)+'%';
        el.querySelector('#mon-disk-bar').style.width=(dsk||0)+'%';
        el.querySelector('#mon-cores').textContent=(d.cores||'?')+' çekirdek';
        el.querySelector('#mon-ramtot').textContent=fmt(d.rt||0)+' toplam';
        el.querySelector('#mon-disktot').textContent=fmt(d.dt||0)+' toplam';
        el.querySelector('#mon-info').textContent=d.host+' | '+d.kernel;

        const ch=el.querySelector('#mon-cpu-hist'); ch.width=ch.offsetWidth||200; ch.height=50;
        const rh=el.querySelector('#mon-ram-hist'); rh.width=rh.offsetWidth||200; rh.height=50;
        drawHist(ch,cpuHist,'#00e5ff'); drawHist(rh,ramHist,'#00ffaa');

        const tb=el.querySelector('#mon-tbody');
        tb.innerHTML=(d.procs||[]).slice(0,20).map(p=>`<tr>
          <td>${p.pid}</td>
          <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name||'-'}</td>
          <td style="color:${(p.cpu_percent||0)>10?'var(--red)':'var(--text)'}">${(p.cpu_percent||0).toFixed(1)}</td>
          <td>${(p.memory_percent||0).toFixed(1)}</td>
          <td><span class="proc-status ${p.status==='running'?'ps-running':'ps-sleeping'}">${p.status||'-'}</span></td>
        </tr>`).join('');
      } catch{}
    };

    interval=setInterval(update,2000); update();
    monState[id]=interval;
  },

  onClose(id) { clearInterval(monState[id]); delete monState[id]; }
};

function fmt(b) {
  if(b>1e9) return (b/1e9).toFixed(1)+' GB';
  if(b>1e6) return (b/1e6).toFixed(1)+' MB';
  return (b/1024).toFixed(0)+' KB';
}

// ═══════════════════════════════════════════════════════
//  APP: CALCULATOR
// ═══════════════════════════════════════════════════════
OS.apps.calc = {
  icon: '🧮', title: 'Hesap Makinesi', w: 300, h: 460,
  html: `<div class="app-calc">
    <div class="calc-display">
      <div class="calc-expr" id="calc-expr"></div>
      <div class="calc-result" id="calc-res">0</div>
    </div>
    <div class="calc-grid" id="calc-grid"></div>
  </div>`,

  init(id, el) {
    let expr='', val='0';
    const res=el.querySelector('#calc-res'), expr_el=el.querySelector('#calc-expr');
    const update=()=>{ res.textContent=val; expr_el.textContent=expr; };

    const btns = [
      ['C','clear'],['±','sign'],['%','mod'],['/','op'],
      ['7','num'],['8','num'],['9','num'],['×','op'],
      ['4','num'],['5','num'],['6','num'],['-','op'],
      ['1','num'],['2','num'],['3','num'],['+','op'],
      ['0','num zero'],['.','.']  ,['=','eq'],
    ];

    const grid=el.querySelector('#calc-grid');
    btns.forEach(([lbl,cls])=>{
      const b=document.createElement('button');
      b.className='cb '+cls; b.textContent=lbl;
      b.onclick=()=>{
        if(cls==='num'||cls==='num zero'){
          if(val==='0'||val==='Error') val=lbl; else val+=lbl;
        } else if(lbl==='.'){
          if(!val.includes('.')) val+='.';
        } else if(cls==='clear'){
          val='0'; expr='';
        } else if(cls==='sign'){
          val=val.startsWith('-')?val.slice(1):'-'+val;
        } else if(cls==='mod'){
          val=String(parseFloat(val)/100);
        } else if(cls==='op'){
          expr=val+(lbl==='×'?'*':lbl); val='0';
        } else if(cls==='eq'){
          try {
            const e=expr+(lbl==='='?val:'');
            const r=Function('"use strict";return ('+e+')')();
            expr=e+'='; val=String(Math.round(r*1e10)/1e10);
          } catch{ val='Error'; expr=''; }
        }
        update();
      };
      grid.appendChild(b);
    });

    document.addEventListener('keydown', function handler(e) {
      if(!OS.wins[id]?.el.classList.contains('focused')) return;
      const map={'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9',
        '+':'+','-':'-','*':'×','/':'/'};
      const btn=grid.querySelector(`.cb[value="${map[e.key]||e.key}"]`) ||
                [...grid.querySelectorAll('.cb')].find(b=>b.textContent===e.key||(e.key==='Enter'&&b.textContent==='=')||(e.key==='Escape'&&b.textContent==='C'));
      if(btn) btn.click();
    });
  }
};

// ═══════════════════════════════════════════════════════
//  APP: WEB BROWSER
// ═══════════════════════════════════════════════════════
OS.apps.browser = {
  icon: '🌐', title: 'Tarayıcı', w: 900, h: 600,
  html: `<div class="app-browser">
    <div class="br-bar">
      <button class="fm-btn" id="br-back">◀</button>
      <button class="fm-btn" id="br-fwd">▶</button>
      <button class="fm-btn" id="br-reload">↻</button>
      <input class="br-url" id="br-url" placeholder="URL girin (örn: https://example.com)">
      <button class="br-go" id="br-go">Git →</button>
    </div>
    <div id="br-content" style="flex:1;display:flex;flex-direction:column">
      <div class="br-note">
        🌐<br><br>URL girin ve Git'e tıklayın<br>
        <span style="font-size:11px;color:var(--text3);margin-top:8px">Not: Bazı siteler iframe'i engelleyebilir.</span>
      </div>
    </div>
  </div>`,

  init(id, el) {
    let frame=null;
    const content=el.querySelector('#br-content');
    const urlInput=el.querySelector('#br-url');

    const go=()=>{
      let url=urlInput.value.trim();
      if(!url) return;
      if(!url.startsWith('http')) url='https://'+url;
      urlInput.value=url;
      content.innerHTML='';
      frame=document.createElement('iframe');
      frame.className='br-frame'; frame.src=url;
      frame.style.flex='1'; frame.style.border='none';
      frame.onerror=()=>{
        content.innerHTML=`<div class="br-note">❌<br><br>Sayfa yüklenemedi<br><span style="font-size:11px;color:var(--text3)">${url}</span></div>`;
      };
      content.appendChild(frame);
    };

    el.querySelector('#br-go').onclick=go;
    el.querySelector('#br-back').onclick=()=>frame?.contentWindow.history.back();
    el.querySelector('#br-fwd').onclick=()=>frame?.contentWindow.history.forward();
    el.querySelector('#br-reload').onclick=()=>{ if(frame) frame.src=frame.src; };
    urlInput.addEventListener('keydown',e=>{ if(e.key==='Enter') go(); });
  }
};

// ═══════════════════════════════════════════════════════
//  APP: SETTINGS
// ═══════════════════════════════════════════════════════
OS.apps.settings = {
  icon: '⚙️', title: 'Ayarlar', w: 660, h: 520,
  html: `<div class="app-settings">
    <div class="set-section">
      <div class="set-title">⚙️ Sistem Ayarları</div>
      <div class="set-sub">WebOS görünümünü özelleştirin</div>

      <span class="set-label">Duvar Kağıdı</span>
      <div class="wallpapers" id="wp-grid"></div>

      <div class="set-divider"></div>

      <span class="set-label">Hızlı Erişim</span>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px">
        <button class="fm-btn" onclick="OS.open('terminal')">🖥️ Terminal</button>
        <button class="fm-btn" onclick="OS.open('files')">📁 Dosyalar</button>
        <button class="fm-btn" onclick="OS.open('editor')">📝 Editör</button>
        <button class="fm-btn" onclick="OS.open('monitor')">📊 Sistem Monitörü</button>
        <button class="fm-btn" onclick="OS.open('calc')">🧮 Hesap Makinesi</button>
        <button class="fm-btn" onclick="OS.open('browser')">🌐 Tarayıcı</button>
      </div>

      <div class="set-divider"></div>

      <span class="set-label">Sistem Hakkında</span>
      <div id="set-about"></div>
    </div>
  </div>`,

  init(id, el) {
    const wps = [
      {bg:'radial-gradient(ellipse at 20% 50%, #1a0533, #050510)', lbl:'Nebula'},
      {bg:'linear-gradient(135deg, #0a0f2e, #051020, #0a1a10)', lbl:'Okyanus'},
      {bg:'radial-gradient(ellipse at 80% 20%, #0d1a2e, #050a0e)', lbl:'Derin Gece'},
      {bg:'linear-gradient(180deg, #0a0512, #060612, #030808)', lbl:'Kuzey Işıkları'},
      {bg:'radial-gradient(circle at 50% 50%, #12080a, #06060f)', lbl:'Kırmızı Cüce'},
    ];
    const saved = localStorage.getItem('wp') || '0';
    const grid=el.querySelector('#wp-grid');
    wps.forEach((w,i)=>{
      const d=document.createElement('div');
      d.className='wp'+(i==saved?' active':'');
      d.style.background=w.bg;
      d.title=w.lbl;
      d.onclick=()=>{
        grid.querySelectorAll('.wp').forEach(x=>x.classList.remove('active'));
        d.classList.add('active');
        document.getElementById('desktop').style.background=w.bg;
        localStorage.setItem('wp',i);
      };
      grid.appendChild(d);
    });

    const about=el.querySelector('#set-about');
    fetch('/api/sys').then(r=>r.json()).then(d=>{
      const rows=[
        ['İşletim Sistemi', d.distro||'Linux'],
        ['Kernel', d.kernel||'-'],
        ['Hostname', d.host||'-'],
        ['CPU Çekirdek', (d.cores||'?')+' çekirdek'],
        ['Bellek', fmt(d.rt||0)],
        ['Disk', fmt(d.dt||0)],
        ['Çalışma Süresi', fmtUptime(d.uptime||0)],
        ['psutil', d.psutil?'✅ Aktif':'❌ Yüklü değil (pip install psutil)'],
      ];
      about.innerHTML=rows.map(([k,v])=>`
        <div class="about-row">
          <div class="about-key">${k}</div>
          <div class="about-val">${v}</div>
        </div>`).join('');
    });
  }
};

function fmtUptime(s) {
  const h=Math.floor(s/3600), m=Math.floor((s%3600)/60);
  return `${h} saat ${m} dakika`;
}

// ═══════════════════════════════════════════════════════
//  Boot Sequence
// ═══════════════════════════════════════════════════════
window.addEventListener('load', () => {
  // Restore wallpaper
  const wi = localStorage.getItem('wp');
  if (wi) {
    const wps=['radial-gradient(ellipse at 20% 50%, #1a0533, #050510)',
               'linear-gradient(135deg, #0a0f2e, #051020, #0a1a10)',
               'radial-gradient(ellipse at 80% 20%, #0d1a2e, #050a0e)',
               'linear-gradient(180deg, #0a0512, #060612, #030808)',
               'radial-gradient(circle at 50% 50%, #12080a, #06060f)'];
    document.getElementById('desktop').style.background = wps[wi] || '';
  }

  // Boot animation → open terminal
  setTimeout(() => {
    const boot = document.getElementById('boot');
    boot.classList.add('fade');
    setTimeout(() => {
      boot.remove();
      OS.open('terminal');
      toast('WebOS başlatıldı 🐧', 'success');
    }, 500);
  }, 2000);
});
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return HTML

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'''
╔══════════════════════════════════════════════╗
║  🐧  WebOS Linux — Başlatılıyor              ║
║  🌐  http://0.0.0.0:{port:<5}                   ║
╚══════════════════════════════════════════════╝
Uygulamalar: Terminal, Dosyalar, Editör, Sistem Monitörü,
             Hesap Makinesi, Tarayıcı, Ayarlar
''')
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
