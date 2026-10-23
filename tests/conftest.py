from pathlib import Path

import pytest
from typer.testing import CliRunner

from rig.cli import app

runner = CliRunner()


@pytest.fixture(name="isolated_env")
def fixture_isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    res = runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(data_dir)])
    assert res.exit_code == 0, res.stdout
    return home_dir, config_dir, data_dir
