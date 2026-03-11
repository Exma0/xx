FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/root
ENV USER=root
ENV DISPLAY=:1
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# Render.com'da tam root yetkisi için
# docker run --privileged veya Settings > Environment > Privileged mode

# ── ADIM 1: Temel araçlar ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget ca-certificates gnupg lsb-release locales \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── ADIM 2: Node.js 20 LTS repo ─────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -

# ── ADIM 3: Tüm paketler ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11-utils x11-xserver-utils xdotool dbus-x11 \
    libgl1-mesa-dri libgles2 \
    tigervnc-standalone-server tigervnc-common \
    novnc websockify \
    fluxbox \
    xterm rxvt-unicode chromium-browser pcmanfm geany \
    feh scrot xclip xdg-utils \
    python3 python3-pip python3-dev python3-venv \
    build-essential gcc g++ make cmake \
    git vim nano htop strace lsof tree \
    unzip zip tar rsync jq bc tmux screen \
    nodejs \
    net-tools iputils-ping netcat-openbsd nmap \
    procps psmisc sysstat \
    fonts-liberation fonts-noto fonts-noto-color-emoji \
    ffmpeg \
    sudo \
    util-linux \
    iproute2 \
    kmod \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
       /usr/share/doc/* /usr/share/man/* /usr/share/info/*

# ── ADIM 4: Python paketleri ────────────────────────────────
RUN pip3 install --no-cache-dir \
    requests flask fastapi uvicorn \
    numpy pandas pillow matplotlib scipy scikit-learn \
    psutil aiohttp httpx rich click \
    python-dotenv pydantic sqlalchemy websockets \
    && pip3 cache purge

# ── ADIM 5: npm global paketler ─────────────────────────────
RUN npm install -g --silent nodemon pm2 http-server typescript ts-node yarn \
    && npm cache clean --force \
    && rm -rf /root/.npm/_cacache

# ── ADIM 6: Dizinler ─────────────────────────────────────────
RUN mkdir -p /root/.vnc /root/.fluxbox \
    /root/Desktop /root/Projects /root/Downloads /root/Scripts

# ── ADIM 7: noVNC düzeltme ───────────────────────────────────
RUN test -f /usr/share/novnc/vnc.html \
    || cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc.html 2>/dev/null \
    || true

# ── ADIM 8: Tam root yetkisi — sudoers ──────────────────────
RUN echo "root ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && echo "ALL ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ── ADIM 9: Konfigürasyon dosyaları ─────────────────────────
COPY config/xstartup        /root/.vnc/xstartup
COPY config/fluxbox-init    /root/.fluxbox/init
COPY config/fluxbox-keys    /root/.fluxbox/keys
COPY config/fluxbox-menu    /root/.fluxbox/menu
COPY config/fluxbox-apps    /root/.fluxbox/apps
COPY config/fluxbox-startup /root/.fluxbox/startup
COPY scripts/welcome.sh     /root/welcome.sh
COPY scripts/sysinfo.sh     /root/Scripts/sysinfo.sh
COPY scripts/optimize.sh    /root/Scripts/optimize.sh

RUN chmod +x \
    /root/.vnc/xstartup \
    /root/.fluxbox/startup \
    /root/welcome.sh \
    /root/Scripts/sysinfo.sh \
    /root/Scripts/optimize.sh

# ── Uygulama ─────────────────────────────────────────────────
COPY main.py /app/main.py
WORKDIR /app
EXPOSE 5000

CMD ["python3", "/app/main.py"]
