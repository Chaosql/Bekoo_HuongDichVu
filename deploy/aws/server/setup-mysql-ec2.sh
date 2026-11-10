#!/usr/bin/env bash
# Amazon Linux 2023 x86_64. Run once on EC2, never during application CD.
set -Eeuo pipefail
umask 077
MODE=${1:-}
[[ $(id -u) -eq 0 && ( "$MODE" == --install-fresh || "$MODE" == --configure-existing ) ]] || {
  echo 'Usage: sudo bash setup-mysql-ec2.sh --configure-existing | --install-fresh' >&2; exit 2;
}
source /etc/os-release
[[ "$ID" == amzn && "$VERSION_ID" == 2023 && "$(uname -m)" == x86_64 ]] || {
  echo 'This script targets Amazon Linux 2023 x86_64.' >&2; exit 2;
}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG=/etc/my.cnf.d/bekoo.cnf
if command -v mariadbd >/dev/null; then
  echo 'MariaDB detected. No installation/configuration performed.' >&2; exit 1
fi
if [[ "$MODE" == --install-fresh ]]; then
  if rpm -q mysql-community-server >/dev/null 2>&1 || [[ -n "$(find /var/lib/mysql -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    echo 'MySQL package/data already exists. Use --configure-existing for the Bekoo instance; never reinstall data.' >&2; exit 1
  fi
  # Fixed EL9 repo: dependency resolution was verified on this AL2023 x86_64 host.
  # Keep signature checks enabled. Do not change global Amazon Linux releasever.
  dnf -y --setopt=ip_resolve=4 --setopt=timeout=20 --setopt=retries=1 \
    --repofrompath=bekoo-mysql84,https://repo.mysql.com/yum/mysql-8.4-community/el/9/x86_64/ \
    --setopt=bekoo-mysql84.gpgcheck=1 \
    --setopt=bekoo-mysql84.gpgkey=https://repo.mysql.com/RPM-GPG-KEY-mysql-2025 \
    install mysql-community-server
else
  rpm -q mysql-community-server >/dev/null || { echo 'Install mysql-community-server first.' >&2; exit 1; }
fi
if systemctl is-active --quiet mysqld && [[ ! -f "$CONFIG" ]]; then
  echo 'An unmanaged MySQL instance is running. Configure manually in a maintenance window; no changes made.' >&2; exit 1
fi
command -v python3 >/dev/null
command -v docker >/dev/null
MYSQLD=$(command -v mysqld || true)
if [[ -z "$MYSQLD" && -x /usr/sbin/mysqld ]]; then MYSQLD=/usr/sbin/mysqld; fi
[[ -n "$MYSQLD" ]] || { echo 'mysqld binary missing' >&2; exit 1; }
"$MYSQLD" --version | grep -q 'Ver 8\.4\.' || { echo 'Expected MySQL 8.4; no configuration changed.' >&2; exit 1; }
bash "$SCRIPT_DIR/setup-network.sh" --create
install -d -m 755 /etc/my.cnf.d /etc/systemd/system/mysqld.service.d
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
HAD_CONFIG=false
if [[ -f "$CONFIG" ]]; then
  HAD_CONFIG=true
  cp -p "$CONFIG" "$CONFIG.before-$STAMP"
fi
[[ ! -f /etc/my.cnf ]] || cp -p /etc/my.cnf "/etc/my.cnf.before-bekoo-$STAMP"
install -m 644 "$SCRIPT_DIR/../mysql-demo.cnf" "$CONFIG"
# RPM versions differ: ensure the managed fragment is actually read.
if ! grep -Eq '^!includedir[[:space:]]+/etc/my\.cnf\.d/?([[:space:]]|$)|^!include[[:space:]]+/etc/my\.cnf\.d/bekoo\.cnf([[:space:]]|$)' /etc/my.cnf; then
  printf '\n!include /etc/my.cnf.d/bekoo.cnf\n' >> /etc/my.cnf
fi
if ! "$MYSQLD" --validate-config; then
  if "$HAD_CONFIG"; then cp -p "$CONFIG.before-$STAMP" "$CONFIG"; else rm -f "$CONFIG"; fi
  if [[ -f "/etc/my.cnf.before-bekoo-$STAMP" ]]; then cp -p "/etc/my.cnf.before-bekoo-$STAMP" /etc/my.cnf; fi
  echo 'MySQL rejected the demo configuration. Previous config restored; service not restarted.' >&2
  exit 1
fi
# MySQL binds to a Docker bridge IP; validate/recreate the managed bridge before startup after reboot.
install -d -m 755 /opt/bekoo
install -m 755 "$SCRIPT_DIR/setup-network.sh" /opt/bekoo/setup-network.sh
printf '%s\n' '[Unit]' 'Requires=docker.service' 'After=docker.service' \
  '[Service]' 'ExecStartPre=+/bin/bash /opt/bekoo/setup-network.sh --create' \
  > /etc/systemd/system/mysqld.service.d/bekoo-network.conf
chmod 644 /etc/systemd/system/mysqld.service.d/bekoo-network.conf
# Persist exactly the vetted MySQL 8.4 repository for subsequent security updates.
if [[ ! -e /etc/yum.repos.d/bekoo-mysql84.repo ]]; then
  printf '%s\n' '[bekoo-mysql84]' 'name=Bekoo MySQL 8.4 EL9 (AL2023 compatibility)' \
    'baseurl=https://repo.mysql.com/yum/mysql-8.4-community/el/9/x86_64/' \
    'enabled=1' 'gpgcheck=1' 'gpgkey=https://repo.mysql.com/RPM-GPG-KEY-mysql-2025' \
    > /etc/yum.repos.d/bekoo-mysql84.repo
  chmod 644 /etc/yum.repos.d/bekoo-mysql84.repo
fi
systemctl daemon-reload
systemctl enable mysqld
systemctl restart mysqld
systemctl is-active --quiet mysqld
# Do not print credentials or reset root. Initial RPM startup generates its temporary password in the log.
echo 'MySQL configured for Bekoo demo and running: loopback + 172.30.83.1, max_connections=20.'
echo 'Next: read the temporary root password privately from /var/log/mysqld.log; change it using mysql -u root -p.'
echo 'Create the application database/user using mysql.sql.example. No schema or user passwords were changed by this script.'
