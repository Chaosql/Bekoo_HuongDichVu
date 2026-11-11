"""Check native MySQL from the application network; credentials passed via environment."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def check(directory):
    values = dict(line.split('=', 1) for line in (directory / 'command.env').read_text().splitlines()
                  if line and not line.startswith('#'))
    url = urlsplit(values['DB_URL'].removeprefix('jdbc:'))
    if url.hostname != 'bekoo.mysql.internal' or url.port not in (None, 3306) or url.path != '/booking_care_command' or values['DB_USER'].lower() == 'root':
        raise SystemExit('Invalid native MySQL target; check runtime configuration (values hidden)')
    env = dict(os.environ, MYSQL_PWD=values['DB_PASSWORD'], MYSQL_USER=values['DB_USER'])
    result = subprocess.run([
        'docker', 'run', '--rm', '--network', 'bekoo-backend',
        '--add-host', 'bekoo.mysql.internal:172.30.83.1',
        '--env', 'MYSQL_PWD', '--env', 'MYSQL_USER', '--entrypoint', 'sh', 'mysql:8.0', '-ec',
        'exec mysql --protocol=TCP --connect-timeout=10 -h bekoo.mysql.internal -P 3306 -u "$MYSQL_USER" booking_care_command -e "SELECT 1"'
    ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise SystemExit('Native MySQL preflight failed; check service, schema, grants and firewall (values hidden)')


if __name__ == '__main__':
    check(Path(sys.argv[1]))
