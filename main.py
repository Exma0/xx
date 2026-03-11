"""
Gerçek Linux Masaüstü — Web Üzerinden
Xvfb + Openbox + x11vnc + noVNC
"""
import os, subprocess, threading, time, json
from flask import Flask, Response, request, redirect
import urllib.request

app = Flask(__name__)
NOVNC_PORT = int(os.environ.get("NOVNC_PORT", 6080))
APP_PORT   = int(os.environ.get("PORT", 5000))
DISPLAY    = os.environ.get("DISPLAY", ":1")
RESOLUTION = os.environ.get("RESOLUTION", "1280x720")


def start_services():
    w, h = (RESOLUTION.split("x") + ["720"])[:2]
    env = {**os.environ, "DISPLAY": DISPLAY}

    # 1. Xvfb
    print("▶ Xvfb başlatılıyor...")
    subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", f"{w}x{h}x24",
                      "-ac", "+render", "-noreset"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # 2. Masaüstü arka planı
    subprocess.Popen(["xsetroot", "-solid", "#0e1117"], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Openbox
    print("▶ Openbox başlatılıyor...")
    subprocess.Popen(["openbox", "--display", DISPLAY], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    # 4. x11vnc
    print("▶ x11vnc başlatılıyor...")
    subprocess.Popen(["x11vnc", "-display", DISPLAY, "-forever", "-nopw",
                      "-shared", "-rfbport", "5900", "-quiet",
                      "-noxrecord", "-noxfixes", "-noxdamage"], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # 5. noVNC / websockify
    print("▶ noVNC başlatılıyor...")
    novnc_web = "/usr/share/novnc"
    subprocess.Popen(["websockify", "--web", novnc_web, "--heartbeat", "30",
                      str(NOVNC_PORT), "127.0.0.1:5900"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    # 6. Otomatik xterm
    subprocess.Popen(["xterm", "-bg", "#0e1117", "-fg", "#e2e8f0",
                      "-fa", "Monospace", "-fs", "12",
                      "-geometry", "100x30+50+50", "-title", "Terminal"], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"✅ Tüm servisler hazır! → http://0.0.0.0:{APP_PORT}/desktop")


def proxy(path, qs=""):
    url = f"http://127.0.0.1:{NOVNC_PORT}/{path}" + (f"?{qs}" if qs else "")
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return Response(r.read(), status=r.status,
                        content_type=r.headers.get("Content-Type","application/octet-stream"))
    except Exception as e:
        return Response(f"Proxy hatası: {e}", status=502)


INDEX = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linux Masaüstü</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#06070d;color:#e8eaf0;font-family:'Sora',sans-serif;min-height:100vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;padding:20px}
.bg{position:fixed;inset:0;z-index:-1;background:radial-gradient(ellipse at 30% 50%,#00e5ff08,transparent 60%),
  radial-gradient(ellipse at 80% 20%,#7c6aff08,transparent 60%)}
.logo{font-size:88px;filter:drop-shadow(0 0 30px #00e5ff60);animation:p 3s ease-in-out infinite alternate}
@keyframes p{0%{filter:drop-shadow(0 0 15px #00e5ff40)}100%{filter:drop-shadow(0 0 40px #00e5ff80)}}
h1{font-size:40px;font-weight:700;background:linear-gradient(135deg,#00e5ff,#7c6aff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center}
.sub{color:#8892a4;font-size:14px;text-align:center;max-width:440px;line-height:1.8}
.btns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.btn{padding:14px 36px;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;
  border:none;transition:all .2s;text-decoration:none;display:inline-flex;align-items:center;gap:8px;font-family:'Sora',sans-serif}
.primary{background:linear-gradient(135deg,#00e5ff,#7c6aff);color:#000}
.primary:hover{transform:translateY(-3px);box-shadow:0 16px 40px #00e5ff40}
.secondary{background:rgba(255,255,255,.07);color:#e8eaf0;border:1px solid rgba(255,255,255,.1)}
.secondary:hover{background:rgba(255,255,255,.12)}
.card{background:#0f1119;border:1px solid rgba(255,255,255,.07);border-radius:16px;
  padding:20px 24px;max-width:480px;width:100%}
.row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;
  border-bottom:1px solid rgba(255,255,255,.04);font-size:13px}
.row:last-child{border:none}
.k{color:#8892a4}.v{color:#00e5ff;font-weight:600}
.badge{background:rgba(46,213,115,.12);border:1px solid rgba(46,213,115,.25);
  color:#2ed573;border-radius:20px;padding:3px 12px;font-size:11px;font-weight:700}
.apps{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;max-width:480px}
.app-btn{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);
  color:#c9d1d9;border-radius:10px;padding:8px 14px;font-size:12px;cursor:pointer;
  transition:all .15s;font-family:inherit}
.app-btn:hover{background:rgba(255,255,255,.1);color:#fff}
</style></head><body>
<div class="bg"></div>
<div class="logo">🐧</div>
<h1>Linux Masaüstü</h1>
<p class="sub">Gerçek X11 Linux masaüstü ortamı.<br>
Ubuntu 22.04 · Openbox · Xvfb · x11vnc · noVNC</p>

<div class="btns">
  <a class="btn primary" href="/desktop">🖥️ Masaüstüne Bağlan</a>
  <a class="btn secondary" href="/desktop?view=1">👁 Sadece İzle</a>
</div>

<div class="card">
  <div class="row"><span class="k">OS</span><span class="v">Ubuntu 22.04 LTS</span></div>
  <div class="row"><span class="k">Pencere Yöneticisi</span><span class="v">Openbox</span></div>
  <div class="row"><span class="k">Protokol</span><span class="v">VNC → WebSocket</span></div>
  <div class="row"><span class="k">Çözünürlük</span><span class="v">1280 × 720</span></div>
  <div class="row"><span class="k">Durum</span><span class="badge">● Canlı</span></div>
</div>

<div class="apps">
  <button class="app-btn" onclick="openApp('xterm -bg \'#0e1117\' -fg \'#e2e8f0\' -fa Monospace -fs 12')">🖥️ Terminal</button>
  <button class="app-btn" onclick="openApp('thunar')">📁 Dosya Gezgini</button>
  <button class="app-btn" onclick="openApp('mousepad')">📝 Metin Editörü</button>
  <button class="app-btn" onclick="openApp('firefox')">🌐 Firefox</button>
  <button class="app-btn" onclick="openApp('htop')">📊 Sistem Monitörü</button>
</div>

<script>
async function openApp(cmd){
  await fetch('/api/exec',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cmd})});
  window.open('/desktop','_blank');
}
</script>
</body></html>"""

DESKTOP = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8">
<title>Linux Masaüstü — Canlı</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:#000;overflow:hidden}
#bar{position:fixed;top:0;left:0;right:0;height:36px;z-index:100;
  background:#0c0e18f0;backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(255,255,255,.07);
  display:flex;align-items:center;padding:0 12px;gap:8px;font-family:sans-serif}
#bar a,#bar button{color:#8892a4;font-size:11px;text-decoration:none;
  padding:3px 10px;border-radius:5px;border:1px solid rgba(255,255,255,.08);
  background:transparent;cursor:pointer;transition:all .15s}
#bar a:hover,#bar button:hover{color:#00e5ff;border-color:rgba(0,229,255,.3)}
.logo{color:#00e5ff;font-size:16px}
.spacer{flex:1}
.info{font-size:11px;color:#4a5568}
.full-btn{background:rgba(0,229,255,.1)!important;color:#00e5ff!important;
  border-color:rgba(0,229,255,.3)!important}
#frame{position:fixed;top:36px;left:0;right:0;bottom:0;border:none;width:100%;height:calc(100% - 36px)}
</style></head><body>
<div id="bar">
  <span class="logo">🐧</span>
  <a href="/">Ana Sayfa</a>
  <a href="javascript:location.reload()">↻ Yenile</a>
  <div class="spacer"></div>
  <span class="info">Ubuntu 22.04 LTS · Openbox</span>
  <button class="full-btn" onclick="fs()">⛶ Tam Ekran</button>
</div>
<iframe id="frame" allowfullscreen></iframe>
<script>
const h=location.hostname, p=location.port||(location.protocol==='https:'?'443':'80');
const sec=location.protocol==='https:';
const vo=new URLSearchParams(location.search).get('view')===1?'&view_only=true':'';
document.getElementById('frame').src=
  `/novnc/vnc.html?host=${h}&port=${p}&path=novnc/websockify&autoconnect=true&resize=scale&quality=7&compression=2&encrypt=${sec}${vo}`;
function fs(){
  const f=document.getElementById('frame');
  if(!document.fullscreenElement)f.requestFullscreen?.();
  else document.exitFullscreen?.();
}
</script></body></html>"""


@app.route("/")
def index(): return INDEX

@app.route("/desktop")
def desktop(): return DESKTOP

@app.route("/novnc/", defaults={"path": ""})
@app.route("/novnc/<path:path>")
def novnc(path):
    return proxy(path, request.query_string.decode())

@app.route("/api/status")
def status():
    def alive(n):
        try: return subprocess.run(["pgrep","-x",n],capture_output=True,timeout=2).returncode==0
        except: return False
    return {"xvfb":alive("Xvfb"),"openbox":alive("openbox"),
            "x11vnc":alive("x11vnc"),"display":DISPLAY,"res":RESOLUTION}

@app.route("/api/exec", methods=["POST"])
def exec_cmd():
    cmd = request.json.get("cmd","")
    if not cmd: return {"ok":False,"err":"Boş komut"}
    try:
        subprocess.Popen(cmd, shell=True,
            env={**os.environ,"DISPLAY":DISPLAY},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok":True}
    except Exception as e:
        return {"ok":False,"err":str(e)}


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════╗
║  🐧  Gerçek Linux Masaüstü Başlatılıyor          ║
║  Xvfb + Openbox + x11vnc + noVNC                 ║
╚══════════════════════════════════════════════════╝
""")
    threading.Thread(target=start_services, daemon=True).start()
    app.run(host="0.0.0.0", port=APP_PORT, debug=False, threaded=True)
