#!/usr/bin/env python3
"""
Scheduled Rule42 Fidelity Verify with smart logging.

- Runs the targeted verify command.
- On success (no error/anomaly): save result to Cloudflare R2 (babylon-generated bucket) under verifies/rule42-fidelity/{ts}.json
- On error or anomaly: print full logs to console, save full log to alerts/...
- Can run on schedule via internal loop (every 60s) or called periodically (cron, GH action, etc).
- Monitor/alert: on anomaly, prints ALERT and high visibility message.

Usage:
  python3 scripts/scheduled_rule42_verify.py --once   # single run
  python3 scripts/scheduled_rule42_verify.py          # runs forever, checks every 60s

Env:
  Same R2 creds as other scripts (R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
  Optional: BUCKET_NAME=... (default babylon-generated for derived logs)
"""

import subprocess
import os
import sys
import json
import time
from datetime import datetime, timezone
import boto3
from botocore.config import Config

# Command to execute (exact as per scheduled task)
VERIFY_CMD = '/Users/daboss/bin/verify-stack.sh "rule42 outputs fidelity" ; cd /Users/daboss/narrative-forge && node tests/data-fidelity.js | tail -3 ; echo "Recurring rule42 fidelity check complete."'

# R2 / Cloudflare setup (S3 compatible)
BUCKET = os.environ.get("BUCKET_NAME", "babylon-generated")
ENDPOINT = os.environ.get("R2_ENDPOINT")
ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID")
SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")

def get_r2_client():
    if not (ENDPOINT and ACCESS_KEY and SECRET_KEY):
        print("[ERROR] R2 credentials not set in env. Cannot save to Cloudflare.", file=sys.stderr)
        return None
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )

def is_anomaly(stdout: str, stderr: str, returncode: int) -> bool:
    """Detect error or anomaly conditions. Robust: look for success markers, tolerate partial output from tail."""
    combined = (stdout + "\n" + stderr).lower()
    if returncode != 0:
        return True
    if "fail" in combined or "error" in combined or "exception" in combined or "anomaly" in combined:
        return True
    has_pass = "all data fidelity tests passed" in combined
    has_complete = "recurring rule42 fidelity check complete" in stdout.lower()
    if has_pass and has_complete:
        return False
    return True

def run_verify():
    """Run the verify and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            VERIFY_CMD,
            shell=True,
            capture_output=True,
            text=True,
            timeout=180
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 1, e.stdout or "", (e.stderr or "") + "\nTIMEOUT"
    except Exception as e:
        return 1, "", str(e)

def save_to_cloudflare(client, prefix: str, filename: str, content: dict):
    """Save JSON content to R2."""
    if client is None:
        print(f"[WARN] Skipping Cloudflare save (no client). Would have saved {prefix}{filename}")
        return False
    key = f"{prefix}{filename}"
    try:
        client.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=json.dumps(content, indent=2),
            ContentType="application/json"
        )
        print(f"[INFO] Saved to Cloudflare R2: {BUCKET}/{key}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save to Cloudflare: {e}", file=sys.stderr)
        return False

def main(once: bool = False):
    client = get_r2_client()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filename_base = f"rule42-fidelity-{ts}"

    print(f"[INFO] Starting Rule42 verify at {ts}")

    returncode, stdout, stderr = run_verify()

    anomaly = is_anomaly(stdout, stderr, returncode)

    if anomaly:
        # Show logs (as requested)
        print("\n" + "="*60)
        print("!!! ANOMALY / ERROR DETECTED IN RULE42 FIDELITY VERIFY !!!")
        print("="*60)
        print("STDOUT:")
        print(stdout)
        if stderr:
            print("\nSTDERR:")
            print(stderr)
        print("RETURN CODE:", returncode)
        print("="*60 + "\n")

        # Alert system: save full to alerts/
        alert_content = {
            "timestamp": ts,
            "status": "anomaly",
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "command": VERIFY_CMD
        }
        save_to_cloudflare(client, "alerts/", f"{filename_base}.json", alert_content)

        # Additional monitor alert (visible in logs / can be picked by external)
        print("[ALERT] Rule42 fidelity check failed or had anomaly. See alerts/ in Cloudflare R2.")
        sys.exit(1)  # non-zero for monitoring systems

    else:
        # Success: do NOT show full logs. Save appropriately labeled file.
        success_content = {
            "timestamp": ts,
            "status": "success",
            "summary": "Recurring rule42 fidelity check complete. All tests passed.",
            "returncode": returncode,
            "command": VERIFY_CMD,
            # Optionally include tail only on success if small
            "tail": (stdout + "\n" + stderr).strip()
        }
        save_to_cloudflare(client, "verifies/rule42-fidelity/", f"{filename_base}.json", success_content)
        print(f"[INFO] Rule42 fidelity check successful. Log saved to Cloudflare (no full output shown).")

    if once:
        return

    # Internal scheduler / monitor loop
    print("[INFO] Entering scheduled mode (every 60s). Ctrl+C to stop.")
    while True:
        time.sleep(60)
        # recurse or loop the logic
        # For simplicity, call main logic again (but to avoid recursion depth, better inline)
        # Re-implement light to keep clean
        print(f"[INFO] Scheduled check at {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        returncode, stdout, stderr = run_verify()
        anomaly = is_anomaly(stdout, stderr, returncode)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        filename_base = f"rule42-fidelity-{ts}"

        if anomaly:
            print("\n" + "="*60)
            print("!!! ANOMALY / ERROR DETECTED IN RULE42 FIDELITY VERIFY !!!")
            print("="*60)
            print("STDOUT:")
            print(stdout)
            if stderr:
                print("\nSTDERR:")
                print(stderr)
            print("RETURN CODE:", returncode)
            print("="*60 + "\n")

            alert_content = {
                "timestamp": ts,
                "status": "anomaly",
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "command": VERIFY_CMD
            }
            save_to_cloudflare(client, "alerts/", f"{filename_base}.json", alert_content)
            print("[ALERT] Rule42 fidelity check failed or had anomaly.")
        else:
            success_content = {
                "timestamp": ts,
                "status": "success",
                "summary": "Recurring rule42 fidelity check complete. All tests passed.",
                "returncode": returncode,
                "command": VERIFY_CMD,
                "tail": (stdout + "\n" + stderr).strip()
            }
            save_to_cloudflare(client, "verifies/rule42-fidelity/", f"{filename_base}.json", success_content)
            print(f"[INFO] Scheduled check successful. Saved to Cloudflare.")

if __name__ == "__main__":
    once = "--once" in sys.argv or "-o" in sys.argv
    main(once=once)
