"""Click CLI entry point for phone-cli."""

import json
import os
import sys

import click

from phone_cli.cli.daemon import PhoneCLIDaemon
from phone_cli.cli.output import ok_response, error_response, ErrorCode

VERSION = "0.1.0"


def _print_json(json_str: str) -> None:
    """Print JSON response and set exit code."""
    parsed = json.loads(json_str)
    click.echo(json_str)
    if parsed.get("status") == "error":
        code = parsed.get("error_code", "")
        if code in (ErrorCode.DEVICE_DISCONNECTED, ErrorCode.DEVICE_LOCKED):
            sys.exit(2)
        elif code == ErrorCode.DAEMON_NOT_RUNNING:
            sys.exit(3)
        else:
            sys.exit(1)


def _print_result(result: dict) -> None:
    """Print a daemon method result as ok/error JSON."""

    if result.get("error_code"):
        _print_json(error_response(result["error_code"], result["error_msg"]))
    else:
        _print_json(ok_response(result))


def _get_selected_instance() -> str | None:
    """Read the selected CLI instance from the root Click context."""

    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return None
    root = ctx.find_root()
    obj = getattr(root, "obj", None) or {}
    return obj.get("instance")


def _get_daemon() -> PhoneCLIDaemon:
    """Create a daemon client for the selected instance, or auto-resolve."""

    selected_instance = _get_selected_instance()
    if selected_instance:
        return PhoneCLIDaemon(instance_name=selected_instance)
    return PhoneCLIDaemon()


def _get_start_daemon(device_type: str) -> PhoneCLIDaemon:
    """Create the daemon used by `start`, validating explicit instance choice."""

    selected_instance = _get_selected_instance()
    if selected_instance and selected_instance != device_type:
        raise click.UsageError(
            "--instance must match start --device-type when both are provided."
        )
    if selected_instance:
        return PhoneCLIDaemon(instance_name=selected_instance)
    return PhoneCLIDaemon()


@click.group()
@click.option(
    "--instance",
    default=None,
    type=click.Choice(["adb", "hdc", "ios"]),
    help="Target daemon instance for this command.",
)
@click.pass_context
def cli(ctx, instance):
    """phone-cli — AI-powered phone automation CLI."""
    ctx.ensure_object(dict)
    ctx.obj["instance"] = instance


@cli.command()
def version():
    """Show version."""
    click.echo(f"phone-cli {VERSION}")


@cli.command()
@click.option("--device-type", default="adb", type=click.Choice(["adb", "hdc", "ios"]))
@click.option("--device-id", default=None)
@click.option(
    "--runtime",
    "ios_runtime",
    default=None,
    type=click.Choice(["device", "simulator", "app-on-mac"]),
)
@click.option("--foreground", is_flag=True, hidden=True)
def start(device_type, device_id, ios_runtime, foreground):
    """Start the phone-cli daemon."""
    daemon = _get_start_daemon(device_type)
    result = daemon.start(
        device_type=device_type,
        device_id=device_id,
        ios_runtime=ios_runtime,
        foreground=foreground,
    )
    if not foreground:
        _print_result(result)


@cli.command()
@click.option("--all", "stop_all", is_flag=True, help="Stop all running daemon instances.")
def stop(stop_all):
    """Stop the phone-cli daemon."""
    daemon = _get_daemon()
    result = daemon.stop(all_instances=stop_all)
    _print_result(result)


@cli.command()
def status():
    """Check daemon status."""
    daemon = _get_daemon()
    result = daemon.status()
    _print_result(result)


@cli.command()
def devices():
    """List connected devices."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("devices"))


@cli.command(name="detect-runtimes")
@click.option("--device-type", default="ios", type=click.Choice(["ios"]))
def detect_runtimes(device_type):
    """Detect available runtime candidates before starting the daemon."""
    from phone_cli.ios.runtime.discovery import detect_ios_runtimes, resolve_runtime_selection

    result = detect_ios_runtimes()
    payload = result.to_dict()
    payload["selection"] = resolve_runtime_selection(result).to_dict()
    _print_json(ok_response(payload))


@cli.command()
@click.option("--resize", default=None, type=int, help="Resize width in pixels")
@click.option("--task-id", default="default")
@click.option("--step", default=None, type=int, help="Step number for naming")
def screenshot(resize, task_id, step):
    """Take a screenshot."""
    daemon = _get_daemon()
    args = {"task_id": task_id}
    if resize:
        args["resize"] = resize
    if step is not None:
        args["step"] = step
    _print_json(daemon.send_command("screenshot", args))


@cli.command()
@click.argument("x", type=int)
@click.argument("y", type=int)
def tap(x, y):
    """Tap at coordinates (0-999 relative)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("tap", {"x": x, "y": y}))


@cli.command(name="double-tap")
@click.argument("x", type=int)
@click.argument("y", type=int)
def double_tap(x, y):
    """Double tap at coordinates (0-999 relative)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("double_tap", {"x": x, "y": y}))


@cli.command(name="long-press")
@click.argument("x", type=int)
@click.argument("y", type=int)
def long_press(x, y):
    """Long press at coordinates (0-999 relative)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("long_press", {"x": x, "y": y}))


@cli.command()
@click.argument("x1", type=int)
@click.argument("y1", type=int)
@click.argument("x2", type=int)
@click.argument("y2", type=int)
def swipe(x1, y1, x2, y2):
    """Swipe from (x1,y1) to (x2,y2) (0-999 relative)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("swipe", {"start_x": x1, "start_y": y1, "end_x": x2, "end_y": y2}))


@cli.command(name="type")
@click.argument("text")
def type_text(text):
    """Type text into focused input."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("type", {"text": text}))


@cli.command()
def back():
    """Press back button."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("back"))


@cli.command()
def home():
    """Press home button."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("home"))


@cli.command()
@click.argument("app_name", required=False)
@click.option("--bundle-id", default=None, help="Launch by bundle identifier")
@click.option("--app-path", default=None, type=click.Path(exists=True), help="Launch by .app path")
def launch(app_name, bundle_id, app_path):
    """Launch an app by name, bundle ID, or .app path."""
    daemon = _get_daemon()
    args = {
        "app_name": app_name,
        "bundle_id": bundle_id,
        "app_path": os.path.abspath(app_path) if app_path else None,
    }
    _print_json(daemon.send_command("launch", args))


@cli.command(name="get-current-app")
def get_current_app():
    """Get current foreground app."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("get_current_app"))


@cli.command(name="ui-tree")
def ui_tree():
    """Dump UI accessibility tree."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("ui_tree"))


@cli.command(name="set-device")
@click.argument("device_id")
def set_device(device_id):
    """Set target device by ID."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("set_device", {"device_id": device_id}))


@cli.command(name="device-info")
def device_info():
    """Show current device info."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("device_info"))


@cli.command(name="clean-screenshots")
@click.option("--all", "clean_all", is_flag=True, help="Remove all screenshots")
def clean_screenshots(clean_all):
    """Clean old screenshots."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("clean_screenshots", {"all": clean_all}))


@cli.command()
@click.option("--tail", default=50, type=int, help="Number of lines to show")
@click.option("--task", "task_id", default=None, help="Filter by task ID")
def log(tail, task_id):
    """View operation logs."""
    daemon = _get_daemon()
    args = {"tail": tail}
    if task_id:
        args["task_id"] = task_id
    _print_json(daemon.send_command("log", args))


# ── New commands: reduce screenshot frequency ─────────────────────────

@cli.command(name="app-state")
@click.option("--package", "-p", default=None, help="Target package name")
@click.option("--bundle-id", default=None, help="Target iOS bundle identifier")
def app_state(package, bundle_id):
    """Get app foreground state (replaces screenshot-based verification)."""
    daemon = _get_daemon()
    args = {}
    if package:
        args["package"] = package
    if bundle_id:
        args["bundle_id"] = bundle_id
    _print_json(daemon.send_command("app_state", args))


@cli.command(name="wait-for-app")
@click.argument("package", required=False)
@click.option("--bundle-id", default=None, help="Target iOS bundle identifier")
@click.option("--timeout", "-t", default=30, type=int, help="Max wait seconds")
@click.option("--state", "-s", default="resumed",
              type=click.Choice(["resumed", "running"]),
              help="Target state to wait for")
def wait_for_app(package, bundle_id, timeout, state):
    """Wait for an app to reach target state (replaces sleep + screenshot polling)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("wait_for_app", {
        "package": package,
        "bundle_id": bundle_id,
        "timeout": timeout,
        "state": state,
    }))


@cli.command(name="check-screen")
@click.option("--threshold", default=0.95, type=float,
              help="Ratio threshold for all-black/all-white detection")
def check_screen(threshold):
    """Check screen health (all-black/all-white detection)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("check_screen", {
        "threshold": threshold,
    }))


@cli.command(name="app-log")
@click.option("--package", "-p", default=None, help="Target package name")
@click.option("--filter", "-f", "filter_type", default="all",
              type=click.Choice(["crash", "lifecycle", "all"]),
              help="Log filter type")
@click.option("--lines", "-n", default=20, type=int, help="Number of log lines")
def app_log(package, filter_type, lines):
    """Get app logs (replaces manual adb logcat)."""
    daemon = _get_daemon()
    args = {"filter": filter_type, "lines": lines}
    if package:
        args["package"] = package
    _print_json(daemon.send_command("app_log", args))


@cli.command()
@click.argument("apk_path", type=click.Path(exists=True))
@click.option("--launch", is_flag=True, help="Launch app after installation")
def install(apk_path, launch):
    """Install APK and optionally launch it."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("install", {
        "apk_path": os.path.abspath(apk_path),
        "launch": launch,
    }))


# ── Companion commands (Android-only) ────────────────────────────────

@cli.command(name="companion-status")
def companion_status():
    """Check companion accessibility service status (Android-only)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("companion_status"))


@cli.command(name="companion-setup")
def companion_setup():
    """Build, install, enable, and set up companion service (Android-only)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("companion_setup"))


@cli.command(name="find-nodes")
@click.option("--text", default=None, help="Exact text match")
@click.option("--text-contains", default=None, help="Partial text match")
@click.option("--resource-id", default=None, help="Resource ID match")
@click.option("--class-name", default=None, help="Class name match")
@click.option("--clickable", is_flag=True, default=None, help="Only clickable nodes")
def find_nodes(text, text_contains, resource_id, class_name, clickable):
    """Search UI nodes by criteria via companion (Android-only)."""
    daemon = _get_daemon()
    args = {}
    if text is not None:
        args["text"] = text
    if text_contains is not None:
        args["text_contains"] = text_contains
    if resource_id is not None:
        args["resource_id"] = resource_id
    if class_name is not None:
        args["class_name"] = class_name
    if clickable:
        args["clickable"] = True
    _print_json(daemon.send_command("find_nodes", args))


@cli.command(name="click-node")
@click.argument("node_id")
@click.option("--fallback-x", default=None, type=int, help="Fallback X coordinate")
@click.option("--fallback-y", default=None, type=int, help="Fallback Y coordinate")
def click_node(node_id, fallback_x, fallback_y):
    """Click a UI node by nodeId (Android-only)."""
    daemon = _get_daemon()
    args = {"node_id": node_id}
    if fallback_x is not None:
        args["fallback_x"] = fallback_x
    if fallback_y is not None:
        args["fallback_y"] = fallback_y
    _print_json(daemon.send_command("click_node", args))


@cli.command(name="screen-context")
def screen_context():
    """Get interactive elements summary via companion (Android-only)."""
    daemon = _get_daemon()
    _print_json(daemon.send_command("screen_context"))


if __name__ == "__main__":
    cli()
