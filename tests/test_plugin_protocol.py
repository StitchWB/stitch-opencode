"""Protocol smoke test — drives the plugin over raw stdin/stdout.

Spawns ``python -m stitch_opencode`` (no host dependency) and walks the
JSON-RPC 2.0 line protocol: init → _migrate_db → ping → get_opencode_config →
shutdown.  Mirrors the starter test in the plugin template repo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = "stitch_opencode"
PLUGIN_ID = "stitch-opencode"
TEST_COMMAND = "get_opencode_config"
TEST_PARAMS: dict = {}

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _request(rid: int, method: str, params: dict | None = None) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    )


def _init(rid: int, data_dir: str) -> str:
    return _request(
        rid,
        "plugin.init",
        {
            "engine_api": 2,
            "plugin_id": PLUGIN_ID,
            "db_path": str(Path(data_dir) / "plugin.db"),
            "data_dir": data_dir,
            "supported": [],
        },
    )


def _drive(lines: list[str], env: dict[str, str] | None = None) -> dict[int, dict]:
    """Feed JSON-RPC request lines, return responses keyed by id."""
    proc = subprocess.run(
        [sys.executable, "-m", MODULE],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PACKAGE_DIR),
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, f"plugin exited {proc.returncode}: {proc.stderr}"
    responses: dict[int, dict] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            obj = json.loads(line)
            responses[obj["id"]] = obj
    return responses


def test_lifecycle_init_migrate_ping_command_shutdown() -> None:
    """Full lifecycle over raw stdin: handshake, migration, liveness, one
    readonly command, and graceful shutdown."""
    with tempfile.TemporaryDirectory() as td:
        responses = _drive(
            [
                _init(1, td),
                _request(
                    2,
                    "plugin.call",
                    {
                        "name": "_migrate_db",
                        "params": {"from_version": 0, "to_version": 1},
                    },
                ),
                _request(3, "plugin.ping"),
                _request(
                    4, "plugin.call", {"name": TEST_COMMAND, "params": TEST_PARAMS}
                ),
                _request(5, "plugin.shutdown"),
            ]
        )

    init = responses[1]["result"]
    assert init["plugin_id"] == PLUGIN_ID
    assert "capabilities" in init

    assert responses[3]["result"] == "pong"

    command_response = responses[4]
    assert "result" in command_response, (
        f"{TEST_COMMAND} returned an error: {command_response.get('error')}"
    )

    assert responses[5]["result"] is None


def test_injected_config_dir_wins_over_sandbox_home(tmp_path: Path) -> None:
    """Given STITCH_OPENCODE_CONFIG_DIR (host shim), when set_opencode_config
    runs, then the config lands in the injected dir, not under Path.home()."""
    config_dir = tmp_path / "real-config"
    env = dict(os.environ)
    env["STITCH_OPENCODE_CONFIG_DIR"] = str(config_dir)
    with tempfile.TemporaryDirectory() as td:
        responses = _drive(
            [
                _init(1, td),
                _request(
                    2,
                    "plugin.call",
                    {
                        "name": "set_opencode_config",
                        "params": {"config": {"model": "injected"}},
                    },
                ),
                _request(
                    3,
                    "plugin.call",
                    {"name": "get_opencode_config", "params": {}},
                ),
                _request(4, "plugin.shutdown"),
            ],
            env=env,
        )
    assert responses[2]["result"]["success"] is True
    assert responses[3]["result"] == {"model": "injected"}
    written = json.loads((config_dir / "opencode.json").read_text(encoding="utf-8"))
    assert written == {"model": "injected"}
