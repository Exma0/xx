FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/root
ENV USER=root
ENV DISPLAY=:1
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

# ── ADIM 1: Temel araçlar ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget ca-certificates gnupg lsb-release locales \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── ADIM 2: Cloudflare Tunnel ────────────────────────────────
RUN curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
    https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/cloudflared.list \
    && apt-get update \
    && apt-get install -y cloudflared \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── ADIM 3: Node.js 20 ──────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -

# ── ADIM 4: Sistem paketleri ────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11-utils x11-xserver-utils xdotool dbus-x11 \
    libgl1-mesa-dri libgles2 \
    tigervnc-standalone-server tigervnc-common \
    novnc websockify \
    fluxbox \
    xterm rxvt-unicode chromium-browser pcmanfm geany \
    feh scrot xclip xdg-utils \
    python3 python3-pip python3-dev python3-venv \
    openjdk-21-jdk-headless \
    build-essential gcc g++ make cmake \
    git vim nano htop strace lsof tree \
    unzip zip tar rsync jq bc tmux screen \
    nodejs \
    net-tools iputils-ping netcat-openbsd nmap socat \
    iptables iproute2 tcpdump dnsutils \
    procps psmisc sysstat sudo util-linux kmod \
    fonts-liberation fonts-noto fonts-noto-color-emoji \
    ffmpeg \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
       /usr/share/doc/* /usr/share/man/* /usr/share/info/*

# ── ADIM 5: Python paketleri ────────────────────────────────
RUN pip3 install --no-cache-dir \
    flask \
    flask-socketio \
    eventlet \
    requests \
    fastapi uvicorn \
    numpy pandas pillow \
    psutil \
    aiohttp httpx \
    rich click \
    python-dotenv \
    websockets \
    && pip3 cache purge

# ── ADIM 6: npm global ──────────────────────────────────────
RUN npm install -g --silent nodemon pm2 http-server typescript ts-node yarn \
    && npm cache clean --force \
    && rm -rf /root/.npm/_cacache

# ── ADIM 7: Dizinler ─────────────────────────────────────────
RUN mkdir -p /root/.vnc /root/.fluxbox \
    /root/Desktop /root/Projects /root/Downloads /root/Scripts \
    /minecraft /minecraft/plugins /minecraft/worlds \
    /minecraft/backups /minecraft/logs

# ── ADIM 8: noVNC düzeltme ───────────────────────────────────
RUN test -f /usr/share/novnc/vnc.html \
    || cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc.html 2>/dev/null \
    || true

# ── ADIM 9: Tam root ─────────────────────────────────────────
RUN echo "root ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ── ADIM 10: Config dosyaları ────────────────────────────────
COPY config/xstartup        /root/.vnc/xstartup
COPY config/fluxbox-init    /root/.fluxbox/init
COPY config/fluxbox-keys    /root/.fluxbox/keys
COPY config/fluxbox-menu    /root/.fluxbox/menu
COPY config/fluxbox-apps    /root/.fluxbox/apps
COPY config/fluxbox-startup /root/.fluxbox/startup
COPY scripts/welcome.sh     /root/welcome.sh
COPY scripts/sysinfo.sh     /root/Scripts/sysinfo.sh
COPY scripts/optimize.sh    /root/Scripts/optimize.sh

RUN chmod +x /root/.vnc/xstartup /root/.fluxbox/startup \
    /root/welcome.sh /root/Scripts/*.sh

# ── Uygulama ─────────────────────────────────────────────────
COPY main.py     /app/main.py
COPY mc_panel.py /app/mc_panel.py
WORKDIR /app
EXPOSE 5000

CMD ["python3", "/app/main.py"]
