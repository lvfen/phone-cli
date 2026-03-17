"""Click CLI entry point for phone-cli."""

import json
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


@click.group()
def cli():
    """phone-cli — AI-powered phone automation CLI."""
    pass


@cli.command()
def version():
    """Show version."""
    click.echo(f"phone-cli {VERSION}")


@cli.command()
@click.option("--device-type", default="adb", type=click.Choice(["adb", "hdc", "ios"]))
@click.option("--device-id", default=None)
@click.option("--foreground", is_flag=True, hidden=True)
def start(device_type, device_id, foreground):
    """Start the phone-cli daemon."""
    daemon = PhoneCLIDaemon()
    result = daemon.start(device_type=device_type, device_id=device_id, foreground=foreground)
    if not foreground:
        _print_json(ok_response(result))


@cli.command()
def stop():
    """Stop the phone-cli daemon."""
    daemon = PhoneCLIDaemon()
    result = daemon.stop()
    _print_json(ok_response(result))


@cli.command()
def status():
    """Check daemon status."""
    daemon = PhoneCLIDaemon()
    result = daemon.status()
    _print_json(ok_response(result))


@cli.command()
def devices():
    """List connected devices."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("devices"))


@cli.command()
@click.option("--resize", default=None, type=int, help="Resize width in pixels")
@click.option("--task-id", default="default")
@click.option("--step", default=None, type=int, help="Step number for naming")
def screenshot(resize, task_id, step):
    """Take a screenshot."""
    daemon = PhoneCLIDaemon()
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
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("tap", {"x": x, "y": y}))


@cli.command(name="double-tap")
@click.argument("x", type=int)
@click.argument("y", type=int)
def double_tap(x, y):
    """Double tap at coordinates (0-999 relative)."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("double_tap", {"x": x, "y": y}))


@cli.command(name="long-press")
@click.argument("x", type=int)
@click.argument("y", type=int)
def long_press(x, y):
    """Long press at coordinates (0-999 relative)."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("long_press", {"x": x, "y": y}))


@cli.command()
@click.argument("x1", type=int)
@click.argument("y1", type=int)
@click.argument("x2", type=int)
@click.argument("y2", type=int)
def swipe(x1, y1, x2, y2):
    """Swipe from (x1,y1) to (x2,y2) (0-999 relative)."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}))


@cli.command(name="type")
@click.argument("text")
def type_text(text):
    """Type text into focused input."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("type", {"text": text}))


@cli.command()
def back():
    """Press back button."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("back"))


@cli.command()
def home():
    """Press home button."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("home"))


@cli.command()
@click.argument("app_name")
def launch(app_name):
    """Launch an app by name."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("launch", {"app": app_name}))


@cli.command(name="get-current-app")
def get_current_app():
    """Get current foreground app."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("get_current_app"))


@cli.command(name="ui-tree")
def ui_tree():
    """Dump UI accessibility tree."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("ui_tree"))


@cli.command(name="set-device")
@click.argument("device_id")
def set_device(device_id):
    """Set target device by ID."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("set_device", {"device_id": device_id}))


@cli.command(name="device-info")
def device_info():
    """Show current device info."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("device_info"))


@cli.command(name="clean-screenshots")
@click.option("--all", "clean_all", is_flag=True, help="Remove all screenshots")
def clean_screenshots(clean_all):
    """Clean old screenshots."""
    daemon = PhoneCLIDaemon()
    _print_json(daemon.send_command("clean_screenshots", {"all": clean_all}))


@cli.command()
@click.option("--tail", default=50, type=int, help="Number of lines to show")
@click.option("--task", "task_id", default=None, help="Filter by task ID")
def log(tail, task_id):
    """View operation logs."""
    daemon = PhoneCLIDaemon()
    args = {"tail": tail}
    if task_id:
        args["task_id"] = task_id
    _print_json(daemon.send_command("log", args))


if __name__ == "__main__":
    cli()
