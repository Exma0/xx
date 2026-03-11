FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1
ENV RESOLUTION=1280x720
ENV HOME=/root
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ── Sistem paketleri ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc x11-utils x11-xserver-utils dbus-x11 xdotool \
    openbox obconf \
    xterm mousepad thunar \
    firefox \
    git curl wget vim nano htop tree unzip zip \
    build-essential python3 python3-pip python3-dev \
    nodejs npm \
    fonts-liberation fonts-noto fonts-noto-color-emoji \
    novnc websockify \
    net-tools procps \
    locales \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python bağımlılıkları ────────────────────────────────────
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# ── Openbox konfigürasyonu ───────────────────────────────────
RUN mkdir -p /root/.config/openbox

COPY config/rc.xml       /root/.config/openbox/rc.xml
COPY config/menu.xml     /root/.config/openbox/menu.xml
COPY config/autostart    /root/.config/openbox/autostart

# ── noVNC index ──────────────────────────────────────────────
RUN ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html 2>/dev/null || true

# ── Uygulama ────────────────────────────────────────────────
COPY main.py  /app/main.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

WORKDIR /app
EXPOSE 5000

CMD ["/app/start.sh"]
