#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
exec 9>/run/lock/bekoo-mysql-backup.lock
flock -n 9 || exit 1
source /etc/bekoo-mysql-backup.conf

[[ -n "$DATABASES" && -n "$AGE_RECIPIENT" ]] || exit 2
read -r -a DBS <<< "$DATABASES"
TMP="$(mktemp -d /var/tmp/bekoo-mysql-backup.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
NAME="mysql-${STAMP}.sql.gz.age"

mysqldump --defaults-extra-file=/root/.my-backup.cnf \
  --single-transaction --quick --routines --events --triggers \
  --no-tablespaces --databases "${DBS[@]}" \
  | gzip -c | age -r "$AGE_RECIPIENT" -o "$TMP/$NAME"

test -s "$TMP/$NAME"
(cd "$TMP" && sha256sum "$NAME" > "$NAME.sha256")

# EC2 Instance Role provides S3 credentials; no long-lived keys in this script.
aws s3 cp "$TMP/$NAME" "s3://$S3_BUCKET/mysql-monthly/$NAME" --region "$AWS_REGION" --only-show-errors
aws s3 cp "$TMP/$NAME.sha256" "s3://$S3_BUCKET/mysql-monthly/$NAME.sha256" --region "$AWS_REGION" --only-show-errors
echo "Monthly backup uploaded: $NAME"
