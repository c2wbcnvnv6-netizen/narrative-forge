#!/usr/bin/env python3
# [WATCH] Pipeline area: live indicators, backfill coordination, Rule42 data watch [SUBAGENT:PIPELINE]
"""
Local watcher for the data pipeline on macOS.

Polls GitHub Actions for the "Monitor & Auto-Ingest New Datasets (Continual Archive Builder)" workflow.
When a new successful run reports new download subsets (via "NOTIFY:" or "Ingested this run:"), 
sends an iMessage/SMS notification to the specified phone number using Messages app.

Run this on your Mac (where Messages is configured with your iPhone for SMS/iMessage).
It will keep running in a loop, checking every 5 minutes.

Usage:
  python3 scripts/watch_for_new_downloads.py

To run persistently:
  nohup python3 scripts/watch_for_new_downloads.py > ~/grok-notifier.log 2>&1 &
  or use launchd / cron.

State is kept in ~/.grok/last_notified_run.txt
"""

import subprocess
import time
import json
import os
from datetime import datetime
import re

PHONE_NUMBER = "+19377046074"  # User's number
REPO = "c2wbcnvnv6-netizen/narrative-forge"
WORKFLOW_NAME = "Monitor & Auto-Ingest New Datasets (Continual Archive Builder)"
CHECK_INTERVAL = 300  # 5 minutes
STATE_FILE = os.path.expanduser("~/.grok/last_notified_run.txt")

def get_last_notified_run():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return None

def save_last_notified_run(run_id):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(str(run_id))

def send_notification(message):
    """Send via AppleScript to Messages. Tries iMessage first, falls back gracefully."""
    script = f'''
    tell application "Messages"
        try
            set targetService to (first service whose service type is iMessage)
            set targetBuddy to buddy "{PHONE_NUMBER}" of targetService
            send "{message}" to targetBuddy
            return "SENT via iMessage"
        on error errMsg
            try
                -- Fallback: first available service (may be SMS if linked to iPhone)
                set targetService to first service
                set targetBuddy to buddy "{PHONE_NUMBER}" of targetService
                send "{message}" to targetBuddy
                return "SENT via fallback service"
            on error errMsg2
                return "FAILED: " & errMsg2
            end try
        end try
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30
        )
        print(f"[{datetime.now().isoformat()}] Notification send result: {result.stdout.strip()}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}")
        return "SENT" in result.stdout
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Notification send error: {e}")
        return False

def check_for_new_downloads():
    last_run = get_last_notified_run()
    
    # Get recent runs
    cmd = [
        "gh", "run", "list",
        "-R", REPO,
        "--workflow", WORKFLOW_NAME,
        "--limit", "5",
        "--json", "databaseId,conclusion,createdAt,headBranch,displayTitle"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"gh run list error: {result.stderr}")
            return
        
        runs = json.loads(result.stdout)
        
        new_notifications = []
        latest_run_id = last_run
        
        for run in runs:
            run_id = str(run["databaseId"])
            if last_run and run_id <= last_run:
                continue  # Already processed
            
            if run["conclusion"] != "success":
                continue
            
            # Get the run log or jobs to find "NOTIFY" or "Ingested this run"
            log_cmd = ["gh", "run", "view", run_id, "-R", REPO, "--log"]
            log_result = subprocess.run(log_cmd, capture_output=True, text=True, timeout=60)
            
            log_output = log_result.stdout + log_result.stderr
            
            # Look for notification triggers from the monitor script
            notify_matches = re.findall(r"NOTIFY:\s*(.+?)(?:\n|$)", log_output)
            ingested_matches = re.findall(r"Ingested this run:\s*(\d+)", log_output)
            
            if notify_matches or (ingested_matches and int(ingested_matches[0]) > 0):
                details = notify_matches[0] if notify_matches else f"{ingested_matches[0]} new subset(s)"
                msg = f"New download subset(s) from {REPO} monitor run #{run_id} ({run['createdAt']}):\n{details}\nCheck R2: raw/ prefixes and processed/ for summaries."
                new_notifications.append((run_id, msg))
            
            if run_id > (latest_run_id or "0"):
                latest_run_id = run_id
        
        # Send notifications for new ones
        for run_id, msg in new_notifications:
            print(f"[{datetime.now().isoformat()}] New data detected in run {run_id}. Sending notification...")
            if send_notification(msg):
                save_last_notified_run(run_id)
                print(f"  Notification sent and state updated for run {run_id}")
            else:
                print(f"  Failed to send notification for run {run_id}. Will retry next cycle.")
        
        if latest_run_id:
            save_last_notified_run(latest_run_id)  # Always advance to latest even if no notify
        
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error checking runs: {e}")

def main():
    print(f"Starting watcher for new data downloads. Notifying {PHONE_NUMBER}.")
    print(f"Checking every {CHECK_INTERVAL} seconds. State in {STATE_FILE}")
    print("Press Ctrl+C to stop.")
    
    # Initial check
    check_for_new_downloads()
    
    while True:
        time.sleep(CHECK_INTERVAL)
        check_for_new_downloads()

if __name__ == "__main__":
    main()
