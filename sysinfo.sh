#!/bin/bash
clear
echo ""
echo -e "\033[1;36m  ══ Sistem Bilgisi ══\033[0m"
echo ""
echo -e "\033[1;33m  OS:\033[0m        $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo -e "\033[1;33m  Kernel:\033[0m    $(uname -r)"
echo -e "\033[1;33m  Mimari:\033[0m    $(uname -m)"
echo -e "\033[1;33m  Host:\033[0m      $(hostname)"
echo -e "\033[1;33m  Uptime:\033[0m    $(uptime -p)"
echo ""
echo -e "\033[1;36m  ══ CPU ══\033[0m"
lscpu | grep -E "^(CPU\(s\)|Model name|CPU MHz|Thread|Core)" | sed 's/^/  /'
echo ""
echo -e "\033[1;36m  ══ Bellek ══\033[0m"
free -h | sed 's/^/  /'
echo ""
echo -e "\033[1;36m  ══ Disk ══\033[0m"
df -h | sed 's/^/  /'
echo ""
echo -e "\033[1;36m  ══ Sürümler ══\033[0m"
echo -e "  Python:  $(python3 --version 2>&1)"
echo -e "  Node.js: $(node --version 2>&1)"
echo -e "  npm:     $(npm --version 2>&1)"
echo -e "  Git:     $(git --version 2>&1)"
echo -e "  GCC:     $(gcc --version 2>&1 | head -1)"
echo ""
echo -e "\033[1;33m  Enter'a bas...\033[0m"
read
