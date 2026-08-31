import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from crew_broker import DEFAULT_OPERATION_DOCUMENTS, build_parser, main, parse_args

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install_crew_broker_launchagent.sh"


def test_cli_defaults_are_deterministic_and_loopback_only(tmp_path):
    args = parse_args([], home=tmp_path)

    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.data_dir == tmp_path / "Library/Application Support/SimpleCrew"
    assert args.database == args.data_dir / "simplecrew.db"
    assert args.capability_file == args.data_dir / "crew-broker.capability"

    with pytest.raises(SystemExit):
        parse_args(["--host", "0.0.0.0"], home=tmp_path)


def test_cli_has_no_secret_arguments():
    option_names = {
        option
        for action in build_parser()._actions
        for option in action.option_strings
    }

    assert not option_names.intersection(
        {"--capability", "--token", "--password", "--cookie", "--encryption-key"}
    )


def test_production_broker_owns_exact_operation_documents():
    assert DEFAULT_OPERATION_DOCUMENTS
    assert set(DEFAULT_OPERATION_DOCUMENTS) == {"CrewConnectionHealth", "CurrentUser", "InitiateTransferScottie"}
    assert DEFAULT_OPERATION_DOCUMENTS["CrewConnectionHealth"][1] is False
    assert DEFAULT_OPERATION_DOCUMENTS["InitiateTransferScottie"][1] is True


def test_runner_revalidates_loopback_before_serving(monkeypatch, tmp_path):
    class App:
        def run(self, **kwargs): raise AssertionError("server must not start")

    monkeypatch.setattr("crew_broker.parse_args", lambda argv: type("Args", (), {
        "host": "0.0.0.0", "port": 8765, "data_dir": tmp_path,
        "database": tmp_path / "db", "capability_file": tmp_path / "cap",
    })())
    monkeypatch.setattr("crew_broker.create_app", lambda args: App())

    with pytest.raises(ValueError, match="loopback"):
        main([])


def test_installer_renders_valid_launchagent_without_secrets(tmp_path):
    install_root = tmp_path / "Library/LaunchAgents"
    data_dir = tmp_path / "Application Support/SimpleCrew"
    python = Path(sys.executable)

    result = subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--install-dir",
            str(install_root),
            "--data-dir",
            str(data_dir),
            "--python",
            str(python),
            "--no-load",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    destination = install_root / "com.simplecrew.crew-broker.plist"
    payload = plistlib.loads(destination.read_bytes())
    assert payload["ProgramArguments"] == [
        str(python),
        str(ROOT / "crew_broker.py"),
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--data-dir",
        str(data_dir),
    ]
    serialized = destination.read_text()
    assert "CAPABILITY" not in serialized
    assert "TOKEN" not in serialized
    assert os.stat(destination).st_mode & 0o777 == 0o600
