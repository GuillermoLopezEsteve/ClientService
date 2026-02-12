#!/usr/bin/env python3
import sys
import json
import subprocess
import urllib.request
import urllib.parse
import datetime
import ssl
from collections import Counter
from typing import Tuple, Dict, Any


def utc_ts() -> str:
    """
    Return the current UTC timestamp in ISO-8601 format.
    Used for cron-safe logging so each log line is timestamped
    and sortable.
    """
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_line(msg: str, log_path: str) -> None:
    """
    Append a single timestamped log line to the log file.

    If the log file cannot be written (permissions, disk full, etc),
    the message is printed to stdout as a fallback so cron still
    captures it.
    """
    line = f"{utc_ts()} {msg}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        print(line, end="")


def execute_commands(commands: Dict[str, Any], gid: str) -> Tuple[Dict[str, Any], Counter]:
    """
    Execute all commands found in the tasks JSON structure.

    - Replaces %GRUP% placeholders with the zero-padded group id
    - Executes each command with a timeout
    - Writes the execution status back into the task
    - Counts how many tasks ended in each status

    Returns:
        (updated_commands_json, status_counter)
    """
    zones = commands.get("zones", [])
    sanitized_id = gid.zfill(2)
    counts = Counter()

    for zone in zones:
        for task in zone.get("tasks", []):
            result = sanitize_execute_command(task.get("command"), sanitized_id)
            task["status"] = result
            counts[result] += 1

    return commands, counts


def sanitize_execute_command(cmd: str, gid: str) -> str:
    """
    Safely execute a single shell command.

    - Replaces %GRUP% with 'grupXX'
    - Suppresses stdout/stderr
    - Enforces a hard timeout
    - Normalizes execution result into a small set of states

    Returns:
        "OK"       -> command exited with return code 0
        "Pending"  -> command failed or returned non-zero
        "Timeout"  -> command exceeded execution timeout
        "Error"    -> unexpected execution error
    """
    if not cmd:
        return "Pending"

    s_cmd = cmd.replace("%GRUP%", f"grup{gid}")

    try:
        completed = subprocess.run(
            s_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return "OK" if completed.returncode == 0 else "Pending"
    except subprocess.TimeoutExpired:
        return "Timeout"
    except Exception:
        return "Error"


def normalize_url(webserver: str) -> str:
    """
    Ensure the provided server value is a valid HTTP(S) URL.

    Allows callers to pass either:
      - smx2-projecte.es
      - https://smx2-projecte.es/api/update-tasks
    """
    if not webserver.startswith(("http://", "https://")):
        webserver = "https://" + webserver
    return webserver


def send_post(
    url: str,
    group_id: str,
    payload: Dict[str, Any],
    timeout_s: int = 20,
    insecure: bool = False,
) -> Dict[str, Any]:
    """
    Send task execution results to the remote server using HTTP POST.

    - Adds group_id as a query parameter
    - Sends JSON body
    - Uses system CA trust store for TLS validation
    - Returns a structured summary of the request/response

    If insecure=True, TLS certificate validation is disabled.
    Intended ONLY for testing environments.
    """
    context = (
        ssl._create_unverified_context()
        if insecure
        else ssl.create_default_context()
    )

    url = normalize_url(url)

    parsed = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    q.append(("group_id", group_id))
    final_url = urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(q),
        parsed.fragment,
    ))

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        final_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )


    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")

            return {
                "requested_url": final_url,
                "method_sent": "POST",
                "status_code": resp.status,
                "group_id": group_id,
                "response_json": json.loads(raw) if ctype.startswith("application/json") else raw,
            }

    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "requested_url": final_url,
            "method_sent": "POST",
            "status_code": e.code,
            "group_id": group_id,
            "response_json": body,
        }
    except Exception as e:
        return {
            "requested_url": final_url,
            "method_sent": "POST",
            "status_code": -1,
            "group_id": group_id,
            "response_json": f"{type(e).__name__}: {e}",
        }


def main() -> None:
    """
    Program entry point.

    - Parses CLI arguments
    - Loads task definitions
    - Executes commands
    - Logs execution summary
    - Sends results to the server
    """
    if len(sys.argv) not in (4, 5, 6):
        print("Usage: clientservice.py <group_id> <tasks.json> <update_endpoint> <Test> [logfile]")
        sys.exit(1)

    group_id = sys.argv[1]
    task_path = sys.argv[2]
    update_end_point = sys.argv[3]
    TEST = sys.argv[4] if len(sys.argv) >= 5 else "False"

    log_path = sys.argv[5] if len(sys.argv) == 6 else "/var/log/clientservice.log"

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log_line(f"[ERROR] Failed to load tasks: {e}", log_path)
        sys.exit(2)

    command_data, counts = execute_commands(data, group_id)
    summary = " ".join(f"{k}={counts.get(k, 0)}" for k in ("OK", "Pending", "Timeout", "Error"))
    log_line(f"[RUN] group_id={group_id} execute_summary {summary}", log_path)

    resp = send_post(
        update_end_point,
        group_id,
        command_data,
        insecure=(TEST == "True"),
    )

    log_line(f"[POST] status={resp.get('status_code')} url={resp.get('requested_url')}", log_path)

    body = str(resp.get("response_json", ""))
    if len(body) > 300:
        body = body[:300] + "...(truncated)"
    log_line(
        f"[POST] status={resp.get('status_code')} url={resp.get('requested_url')} resp={body}",
        log_path,
    )


    print(resp.get("status_code", -1))


if __name__ == "__main__":
    main()
