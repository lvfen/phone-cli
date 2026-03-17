from click.testing import CliRunner
from phone_cli.cli.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "phone-cli" in result.output


def test_cli_status_when_not_running():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "stopped" in result.output
