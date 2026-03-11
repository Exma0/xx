#!/bin/bash
# Çalışma zamanı optimizasyon scripti

echo -e "\033[1;36m⚡ Sistem Optimizasyonu Uygulanıyor...\033[0m"
echo ""

# VM
echo -e "\033[0;33m[1/4] Bellek parametreleri...\033[0m"
echo 1    > /proc/sys/vm/swappiness             2>/dev/null && echo "  ✅ swappiness=1"
echo 50   > /proc/sys/vm/vfs_cache_pressure     2>/dev/null && echo "  ✅ vfs_cache=50"
echo 1    > /proc/sys/vm/drop_caches            2>/dev/null && echo "  ✅ cache temizlendi"

# CPU
echo -e "\033[0;33m[2/4] CPU performans modu...\033[0m"
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$cpu" 2>/dev/null && echo "  ✅ $(basename $(dirname $(dirname $cpu))): performance"
done

# Disk I/O
echo -e "\033[0;33m[3/4] I/O scheduler...\033[0m"
for dev in /sys/block/*/queue/scheduler; do
    for s in none mq-deadline noop; do
        echo $s > "$dev" 2>/dev/null && echo "  ✅ $(basename $(dirname $(dirname $dev))): $s" && break
    done
done

# Network
echo -e "\033[0;33m[4/4] Network buffer...\033[0m"
echo 134217728 > /proc/sys/net/core/rmem_max 2>/dev/null && echo "  ✅ rmem_max=128MB"
echo 134217728 > /proc/sys/net/core/wmem_max 2>/dev/null && echo "  ✅ wmem_max=128MB"

echo ""
echo -e "\033[1;32m✅ Optimizasyon tamamlandı!\033[0m"
echo ""

# Mevcut durum
echo -e "\033[1;36m══ Mevcut Durum ══\033[0m"
echo -e "  \033[0;33mRAM:\033[0m $(free -h | awk '/^Mem:/{print $3"/"$2}')"
echo -e "  \033[0;33mDisk:\033[0m $(df -h / | awk 'NR==2{print $3"/"$2" ("$5")"}')"
echo ""
read -p "Enter..."
