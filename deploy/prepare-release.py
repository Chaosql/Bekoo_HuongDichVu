"""Prepare an EC2 release from GitHub Secrets without printing credentials."""
import os
from pathlib import Path
import shutil
import sys


def main():
    destination = Path(sys.argv[1])
    raw = os.environ.get("BEKOO_ENV", "")
    if not raw.strip():
        raise SystemExit("Configure GitHub Secret BEKOO_ENV before deployment")
    if "\x00" in raw:
        raise SystemExit("BEKOO_ENV contains invalid null characters")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = destination / ".env"
    environment.write_text(raw, encoding="utf-8")
    environment.chmod(0o600)
    for filename in ("compose.aws.yml", "deploy-ec2.sh"):
        shutil.copyfile(Path("deploy") / filename, destination / filename)


if __name__ == "__main__":
    main()
