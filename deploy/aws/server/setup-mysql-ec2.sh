#!/usr/bin/env bash
# Fresh Ubuntu only. Provision once, independently from application deployment.
set -Eeuo pipefail
[[ "${1:-}" == --install-fresh && $EUID -eq 0 ]] || {
  echo 'Usage: sudo bash deploy/aws/server/setup-mysql-ec2.sh --install-fresh' >&2; exit 2;
}
source /etc/os-release
[[ "$ID" == ubuntu && ( "$VERSION_ID" == 22.04 || "$VERSION_ID" == 24.04 ) ]] || {
  echo 'This installer supports Ubuntu 22.04/24.04 only. Configure MySQL manually on other operating systems.' >&2; exit 2;
}
if command -v mysqld >/dev/null || command -v mariadbd >/dev/null || [[ -e /etc/mysql/mysql.conf.d/bekoo.cnf ]]; then
  echo 'Existing MySQL/MariaDB detected. Configure manually; no installation performed.' >&2; exit 1
fi
if [[ -d /var/lib/mysql ]] && [[ -n "$(find /var/lib/mysql -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo 'Existing database files detected. No installation performed.' >&2; exit 1
fi
[[ -z "$(ss -H -ltn 'sport = :3306')" ]] || { echo 'Port 3306 is already in use.' >&2; exit 1; }
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
bash "$SCRIPT_DIR/setup-network.sh" --create
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
printf '%s\n' '[mysqld]' 'bind-address=172.30.83.1' 'mysqlx=0' 'skip-name-resolve=ON' > /etc/mysql/mysql.conf.d/bekoo.cnf
install -d -m 755 /etc/systemd/system/mysql.service.d
printf '%s\n' '[Unit]' 'Requires=docker.service' 'After=docker.service' > /etc/systemd/system/mysql.service.d/bekoo-network.conf
systemctl daemon-reload
systemctl enable mysql
systemctl restart mysql
systemctl is-active --quiet mysql
echo 'MySQL installed. Create database/user using mysql.sql.example; never use root for the backend.'
