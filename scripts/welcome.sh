#!/bin/bash
export PS1='\[\033[1;36m\]\u\[\033[0;37m\]@\[\033[1;35m\]linux\[\033[0m\]:\[\033[1;33m\]\w\[\033[0m\]\$ '
export TERM=xterm-256color

clear
echo ""
printf "\033[1;36m"
echo "  ██████╗ ██╗     ██╗███╗   ██╗██╗   ██╗██╗  ██╗"
echo "  ██╔══██╗██║     ██║████╗  ██║██║   ██║╚██╗██╔╝"
echo "  ██████╔╝██║     ██║██╔██╗ ██║██║   ██║ ╚███╔╝ "
echo "  ██╔══██╗██║     ██║██║╚██╗██║██║   ██║ ██╔██╗ "
echo "  ██████╔╝███████╗██║██║ ╚████║╚██████╔╝██╔╝ ██╗"
echo "  ╚═════╝ ╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝"
printf "\033[0m"
echo ""
printf "\033[1;37m  🚀 Tam Güç Linux Masaüstü — Ubuntu 22.04 LTS\033[0m\n"
echo ""

# Sistem bilgisi
CPU_CORES=$(nproc 2>/dev/null || echo "?")
MEM_GB=$(free -h 2>/dev/null | awk '/^Mem:/{print $2}' || echo "?")
DISK=$(df -h / 2>/dev/null | awk 'NR==2{print $4}' || echo "?")
KERNEL=$(uname -r 2>/dev/null || echo "?")
PY_VER=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo "?")
NODE_VER=$(node --version 2>/dev/null || echo "?")

printf "\033[0;36m  ┌──────────────────────────────────────────────┐\033[0m\n"
printf "\033[0;36m  │\033[0m  \033[0;33mKernel:\033[0m  %-38s \033[0;36m│\033[0m\n" "$KERNEL"
printf "\033[0;36m  │\033[0m  \033[0;33mCPU:   \033[0m  %-38s \033[0;36m│\033[0m\n" "$CPU_CORES çekirdek"
printf "\033[0;36m  │\033[0m  \033[0;33mRAM:   \033[0m  %-38s \033[0;36m│\033[0m\n" "$MEM_GB toplam"
printf "\033[0;36m  │\033[0m  \033[0;33mDisk:  \033[0m  %-38s \033[0;36m│\033[0m\n" "$DISK boşta"
printf "\033[0;36m  └──────────────────────────────────────────────┘\033[0m\n"
echo ""
printf "  \033[0;32m🐍 Python\033[0m %-10s  \033[0;32m🟢 Node.js\033[0m %-10s\n" "$PY_VER" "$NODE_VER"
echo ""
printf "\033[1;33m  Kısayollar:\033[0m\n"
printf "  \033[0;37mCtrl+Alt+T\033[0m → Yeni terminal    \033[0;37mCtrl+Alt+B\033[0m → Chromium\n"
printf "  \033[0;37mCtrl+Alt+F\033[0m → Dosya gezgini    \033[0;37mCtrl+Alt+E\033[0m → Geany IDE\n"
printf "  \033[0;37mCtrl+Alt+H\033[0m → htop             \033[0;37mCtrl+Alt+P\033[0m → Python 3\n"
printf "  \033[0;37mSağ Tık   \033[0m → Uygulama menüsü  \033[0;37mCtrl+Alt+N\033[0m → Node.js\n"
echo ""
printf "  \033[0;36m~/Projects\033[0m  ~/Desktop  ~/Downloads  ~/Scripts\n"
echo ""

exec bash
