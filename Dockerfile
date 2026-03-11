# ═══════════════════════════════════════════════════════════
#  Tam Güç Linux Masaüstü — Render.com Docker
#  TurboVNC + Fluxbox + WebGL + GPU Accel
#  Kısıtlama YOK — Maksimum performans
# ═══════════════════════════════════════════════════════════
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/root
ENV USER=root
ENV DISPLAY=:1
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ── Tek katman — minimum disk kullanımı ─────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \

    # ── X11 ─────────────────────────────────────────────────
    xvfb \
    x11-utils \
    x11-xserver-utils \
    xdotool \
    dbus-x11 \
    mesa-utils \
    libgl1-mesa-dri \
    libgles2 \

    # ── TigerVNC (hızlı, Zlib+ZRLE encoding) ────────────────
    tigervnc-standalone-server \
    tigervnc-common \

    # ── noVNC + websockify ───────────────────────────────────
    novnc \
    websockify \
    python3-websockify \

    # ── Fluxbox — en hafif güçlü WM ──────────────────────────
    fluxbox \

    # ── Temel X uygulamaları ─────────────────────────────────
    xterm \
    rxvt-unicode \

    # ── GUI Uygulamalar ──────────────────────────────────────
    chromium-browser \
    pcmanfm \
    geany \
    mousepad \
    feh \
    scrot \
    xclip \
    xdg-utils \

    # ── Geliştirici araçları ─────────────────────────────────
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    git \
    curl \
    wget \
    vim \
    nano \
    htop \
    iotop \
    strace \
    lsof \
    tree \
    unzip \
    zip \
    tar \
    rsync \
    jq \
    bc \
    tmux \
    screen \

    # ── Node.js 20 LTS (hızlı) ───────────────────────────────
    nodejs \
    npm \

    # ── Network araçları ─────────────────────────────────────
    net-tools \
    iputils-ping \
    curl \
    netcat-openbsd \
    nmap \
    tcpdump \

    # ── Sistem ──────────────────────────────────────────────
    procps \
    psmisc \
    sysstat \
    locales \
    ca-certificates \
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-color-emoji \

    # ── Medya ────────────────────────────────────────────────
    ffmpeg \

    && locale-gen en_US.UTF-8 \

    # ── Node.js 20 LTS kur (daha güncel) ─────────────────────
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null || true \

    # ── Python paketleri ─────────────────────────────────────
    && pip3 install --no-cache-dir \
        requests \
        flask \
        fastapi \
        uvicorn \
        numpy \
        pandas \
        pillow \
        matplotlib \
        scipy \
        scikit-learn \
        psutil \
        aiohttp \
        httpx \
        rich \
        click \
        python-dotenv \
        pydantic \
        sqlalchemy \
        redis \
        celery \
        paramiko \
        cryptography \
        pyserial \
        websockets \

    # ── npm global paketler ──────────────────────────────────
    && npm install -g --silent \
        nodemon \
        pm2 \
        http-server \
        typescript \
        ts-node \
        yarn \
        pnpm \

    # ── TigerVNC şifresiz ────────────────────────────────────
    && mkdir -p /root/.vnc \
    && printf "" | vncpasswd -f > /root/.vnc/passwd \
    && chmod 600 /root/.vnc/passwd \

    # ── Fluxbox konfigürasyon dizini ─────────────────────────
    && mkdir -p /root/.fluxbox \

    # ── Çalışma dizinleri ─────────────────────────────────────
    && mkdir -p /root/Desktop /root/Projects /root/Downloads /root/Scripts \

    # ── Gereksiz dosyaları temizle (disk optimize) ───────────
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf \
        /var/lib/apt/lists/* \
        /tmp/* \
        /var/tmp/* \
        /usr/share/doc/* \
        /usr/share/man/* \
        /usr/share/info/* \
        /root/.cache \
        /root/.npm/_cacache \
    && pip3 cache purge \
    && npm cache clean --force

# ── Yapılandırma dosyaları ───────────────────────────────────
COPY config/xstartup           /root/.vnc/xstartup
COPY config/fluxbox-init       /root/.fluxbox/init
COPY config/fluxbox-keys       /root/.fluxbox/keys
COPY config/fluxbox-menu       /root/.fluxbox/menu
COPY config/fluxbox-apps       /root/.fluxbox/apps
COPY config/fluxbox-startup    /root/.fluxbox/startup
COPY scripts/welcome.sh        /root/welcome.sh
COPY scripts/sysinfo.sh        /root/Scripts/sysinfo.sh
COPY scripts/optimize.sh       /root/Scripts/optimize.sh

RUN chmod +x \
    /root/.vnc/xstartup \
    /root/.fluxbox/startup \
    /root/welcome.sh \
    /root/Scripts/sysinfo.sh \
    /root/Scripts/optimize.sh

# ── noVNC düzeltmesi ────────────────────────────────────────
RUN test -f /usr/share/novnc/vnc.html || \
    cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc.html 2>/dev/null || true

# ── Uygulama ─────────────────────────────────────────────────
COPY main.py /app/main.py
WORKDIR /app
EXPOSE 5000

CMD ["python3", "/app/main.py"]
