#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="${1:-$HOME/kol_lens_audit}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/kol_lens_server_audit_$(date +%F_%H%M%S).txt"

exec > >(tee -a "$REPORT_FILE") 2>&1

echo "===== kol_lens 共享服务器资源盘点 ====="
echo "TIME: $(date '+%F %T %Z')"
echo

echo "===== 1. OS / Kernel / Host ====="
hostnamectl || true
echo
cat /etc/os-release || true
echo
uname -a || true
echo

echo "===== 2. Uptime / Load ====="
uptime || true
echo
w || true
echo

echo "===== 3. CPU ====="
lscpu || true
echo
nproc || true
echo

echo "===== 4. Memory ====="
free -h || true
echo
cat /proc/meminfo | egrep 'MemTotal|MemAvailable|SwapTotal|SwapFree' || true
echo
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -n 30 || true
echo

echo "===== 5. Disk / Filesystem ====="
df -hT || true
echo
df -i || true
echo
lsblk || true
echo

echo "===== 6. I/O / Top directories ====="
which iostat >/dev/null 2>&1 && iostat -x 1 2 || echo 'iostat not installed'
echo
sudo du -xh --max-depth=1 /home 2>/dev/null | sort -h | tail -n 20 || true
echo
sudo du -xh --max-depth=1 /var/lib 2>/dev/null | sort -h | tail -n 20 || true
echo

echo "===== 7. Network ports of concern ====="
ss -lntp | egrep ':80|:443|:3007|:5432|:6379|:19530|:9000|:9001|:9091' || true
echo

echo "===== 8. Existing processes / services ====="
ps -ef | egrep 'nginx|python|uvicorn|gunicorn|node|redis|postgres|milvus|docker|containerd' | grep -v grep || true
echo
systemctl list-units --type=service --state=running | egrep 'nginx|redis|postgres|docker|containerd|milvus' || true
echo

echo "===== 9. Docker / Containers ====="
which docker >/dev/null 2>&1 && docker version || echo 'docker not installed'
echo
which docker >/dev/null 2>&1 && docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' || true
echo
which docker >/dev/null 2>&1 && docker stats --no-stream || true
echo
which docker >/dev/null 2>&1 && docker system df || true
echo

echo "===== 10. Nginx sites ====="
sudo nginx -T 2>/dev/null | grep -n 'server_name' || true
echo
sudo ls -la /etc/nginx/conf.d/ || true
echo

echo "===== 11. Runtime availability ====="
command -v python3 || true
python3 --version || true
echo
command -v python3.11 || true
python3.11 --version || true
echo
command -v node || true
node -v || true
echo
command -v pnpm || true
pnpm -v || true
echo
command -v git || true
git --version || true
echo

echo "===== 12. SELinux / Firewall ====="
getenforce || true
echo
sudo systemctl status firewalld --no-pager || true
echo
sudo firewall-cmd --list-all || true

echo
printf 'REPORT_SAVED=%s\n' "$REPORT_FILE"
