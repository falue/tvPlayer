#!/usr/bin/env python3
import os
import shutil
import zipfile
import subprocess
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# --- Dynamic paths based on script location ---
script_dir = Path(__file__).resolve().parent
ZIP_TARGET = script_dir / "update.zip"
EXTRACT_TO = script_dir / "update_tmp"
USB_MOUNT_DIR = os.path.join("/media", os.getlogin())
ZIP_PATTERN = "main.zip"
VERSION_FILE = script_dir / "webremote" / "update_metadata.json"

# Kill other tvPlayer-related Python processes except self
def kill_other_tvplayer_instances():
    my_pid = os.getpid()
    result = subprocess.run(
        ["pgrep", "-f", "python.*tvPlayer"],
        stdout=subprocess.PIPE,
        text=True
    )
    for pid in result.stdout.strip().splitlines():
        if pid and int(pid) != my_pid:
            print(f"[UPDATE] Killing tvPlayer process: PID {pid}")
            subprocess.run(["kill", "-9", pid])

def find_update_zip_on_usb():
    for device in Path(USB_MOUNT_DIR).iterdir():
        matches = list(device.glob(ZIP_PATTERN))
        if matches:
            return matches[0]
    return None

def hash_file(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_zip_hash():
    if VERSION_FILE.exists():
        try:
            with open(VERSION_FILE) as f:
                return json.load(f).get("zip_hash", "")
        except Exception:
            return ""
    return ""

def get_timestamp():
    return datetime.now(timezone.utc).isoformat()

def write_version_info(hash_value, timestamp):
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VERSION_FILE, "w") as f:
        json.dump({
            "zip_hash": hash_value,
            "installed_at": timestamp
        }, f, indent=2)

def prepare_update(zip_path):
    if EXTRACT_TO.exists():
        shutil.rmtree(EXTRACT_TO)

    shutil.copy(zip_path, ZIP_TARGET)

    with zipfile.ZipFile(ZIP_TARGET, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_TO)

    print(f"[UPDATE] Extracted to {EXTRACT_TO}")

def launch_update_script(hash_value, timestamp):
    script_path = script_dir / "run_update.sh"
    version_string = json.dumps({
        "zip_hash": hash_value,
        "installed_at": timestamp
    }, indent=2)

    with open(script_path, "w") as f:
        f.write(f"""#!/bin/bash
sleep 1
echo "[UPDATE SCRIPT] Applying update..."
cp -r "{EXTRACT_TO}/"* "{script_dir}/"
echo '[UPDATE SCRIPT] Writing version info...'
mkdir -p "{VERSION_FILE.parent}"
cat <<EOF > "{VERSION_FILE}"
{version_string}
EOF
echo '[UPDATE SCRIPT] Restarting tvPlayer.py...'
cd "{script_dir}"
DISPLAY=:0 python3 -u "{script_dir}/tvPlayer.py" &
echo '[UPDATE SCRIPT] Cleaning up...'
rm -rf "{EXTRACT_TO}"
rm -f "{ZIP_TARGET}"
rm -- "$0"
""")

    os.chmod(script_path, 0o755)
    subprocess.Popen(["bash", str(script_path)])

def main():
    kill_other_tvplayer_instances()
    try:
        zip_path = find_update_zip_on_usb()
        if not zip_path:
            print("[USB UPDATE] No matching ZIP found.")
            return

        new_hash = hash_file(zip_path)
        current_hash = get_zip_hash()

        if new_hash == current_hash:
            print("[USB UPDATE] ZIP already installed. Skipping.")
            return

        print("[USB UPDATE] New ZIP detected, updating.")
        timestamp = get_timestamp()
        prepare_update(zip_path)
        launch_update_script(new_hash, timestamp)
        print("[USB UPDATE] Update scheduled.")

    except Exception as e:
        print(f"[ERROR] Update failed: {e}")

if __name__ == "__main__":
    main()
