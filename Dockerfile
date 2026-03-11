FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1
ENV RESOLUTION=1280x720
ENV HOME=/root
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ── Tüm paketleri tek seferde kur ───────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # X11 sanal ekran
    xvfb \
    x11-utils \
    x11-xserver-utils \
    xdotool \
    # VNC
    x11vnc \
    # Pencere yöneticisi
    openbox \
    # Uygulamalar
    xterm \
    mousepad \
    thunar \
    firefox \
    # Geliştirici araçları
    git curl wget vim nano htop tree unzip zip \
    build-essential \
    python3 python3-pip \
    nodejs npm \
    # Fontlar
    fonts-liberation \
    fonts-noto \
    fonts-noto-color-emoji \
    # noVNC (websockify dahil)
    novnc \
    websockify \
    # Sistem
    net-tools procps locales \
    && locale-gen en_US.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── noVNC bağlantı düzeltmesi ────────────────────────────
# vnc.html yoksa vnc_lite.html'i kopyala
RUN ls /usr/share/novnc/ && \
    (test -f /usr/share/novnc/vnc.html || \
     cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc.html 2>/dev/null || true)

# ── Openbox yapılandırması ───────────────────────────────
RUN mkdir -p /root/.config/openbox
COPY config/rc.xml    /root/.config/openbox/rc.xml
COPY config/menu.xml  /root/.config/openbox/menu.xml
COPY config/autostart /root/.config/openbox/autostart
RUN chmod +x /root/.config/openbox/autostart

# ── Uygulama ────────────────────────────────────────────
COPY main.py /app/main.py
WORKDIR /app

EXPOSE 5000

CMD ["python3", "/app/main.py"]
