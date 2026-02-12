#!/usr/bin/env python3
import subprocess
import sys
import json
import os
import requests
import subprocess

headers = {"Content-Type": "application/json"}


def main():
    if len(sys.argv) != 4:
        print("Usage: send_task.py <group_id> <path_to_tasks.json> <update_end_point>")
        sys.exit(1)

    group_id = sys.argv[1]
    task_path = sys.argv[2]
    web_server = sys.argv[3]

    with open(task_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    command_data = execute_commands(data, group_id)
    send_data = send_post(web_server, group_id, command_data)
    print(send_data)

def execute_commands(commands, gid):
    zones = commands.get("zones", [])
    sanitized_id = gid.zfill(2)

    for zone in zones:
        for task in zone.get("tasks", []):
            #print(task.get("tarea"))
            #print(task.get("command"))

            result = sanitize_execute_command(
                task.get("command"),
                sanitized_id
            )

            task["status"] = result
            #print("Result:", result)

    return commands

def sanitize_execute_command(cmd, gid):
    if not cmd:
        return "Pending"

    s_cmd = cmd.replace("%GRUP%", f"grup{gid}")

    try:
        completed = subprocess.run(
            s_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )

        return "OK" if completed.returncode == 0 else "Pending"
    except subprocess.TimeoutExpired:
        return "Timeout"
    except Exception:
        return "Pending"

import requests

import requests

def send_post(webserver, group_id, jsonBlurb, headers=None):
    if headers is None:
        headers = {}

    if not webserver.startswith(("http://", "https://")):
        webserver = "https://" + webserver

    if "://" in webserver and webserver.rstrip("/").endswith(("localhost", "127.0.0.1")):
        pass

    response = requests.post(
        webserver,
        params={"group_id": group_id},
        json=jsonBlurb,
        headers=headers,
        timeout=20,
        allow_redirects=False,   # important: don’t turn POST into a GET via redirects
    )

    return {
        "requested_url": response.request.url,  # shows the real URL
        "method_sent": response.request.method, # should be POST
        "status_code": response.status_code,
        "group_id": group_id,
        "response_json": (
            response.json()
            if response.headers.get("Content-Type", "").startswith("application/json")
            else response.text
        )
    }


if __name__ == "__main__":
    main()

