#!/usr/bin/env python3
"""One-shot Android startup helper for the phone-automation skill."""

import argparse
import json
import os
import sys

from phone_cli.cli.daemon import PhoneCLIDaemon


def _print(payload):
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare Android device/emulator and start the adb daemon.",
    )
    parser.add_argument("--avd", help="Preferred AVD name when emulator restart is needed")
    parser.add_argument(
        "--skip-companion",
        action="store_true",
        help="Skip companion_setup after daemon startup",
    )
    parser.add_argument(
        "--force-restart",
        action="store_true",
        help="Restart the adb daemon even when it is already connected",
    )
    args = parser.parse_args()

    if args.avd:
        os.environ["PHONE_CLI_ANDROID_AVD"] = args.avd

    daemon = PhoneCLIDaemon(instance_name="adb", resolve_instances=False)
    actions = []

    status = daemon.status()
    reusable = (
        status.get("status") == "running"
        and status.get("device_type") == "adb"
        and status.get("device_status") == "connected"
    )

    if args.force_restart and status.get("status") == "running":
        stop_result = daemon.stop()
        actions.append(f"force-stop:{stop_result.get('status', 'unknown')}")
        status = daemon.status()
        reusable = False

    if not reusable and status.get("status") == "running":
        stop_result = daemon.stop()
        actions.append(f"stop-existing:{stop_result.get('status', 'unknown')}")

    if reusable:
        actions.append("reuse-running-adb-daemon")
        start_result = status
    else:
        start_result = daemon.start(device_type="adb")
        if start_result.get("error_code"):
            _print(
                {
                    "status": "error",
                    "stage": "start",
                    "actions": actions,
                    "error_code": start_result["error_code"],
                    "error_msg": start_result["error_msg"],
                }
            )
            return 1
        actions.append(start_result.get("status", "started"))

    final_status = daemon.status()
    companion_result = None
    if not args.skip_companion:
        if final_status.get("companion_status") == "ready":
            companion_result = {"status": "skipped", "reason": "already_ready"}
        else:
            companion_result = json.loads(daemon.send_command("companion_setup"))
            if companion_result.get("status") == "ok":
                actions.append("companion-setup")
            else:
                actions.append("companion-setup-failed")
            final_status = daemon.status()

    _print(
        {
            "status": "ok",
            "actions": actions,
            "daemon": final_status,
            "companion": companion_result,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
