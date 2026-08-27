"""RPC entry point for the stitch-opencode service plugin.

Spawned by ``ServicePluginHost`` as ``python -m stitch_opencode``.
Implements the JSON-RPC 2.0 line protocol via ``RpcPluginServer``
(imported from ``autoreg.plugin.rpc`` when available, otherwise from
the vendored ``_vendor/rpc_server.py`` copy).

Protocol methods handled by ``RpcPluginServer``:
  - ``plugin.init``    → stores handshake params (db_path, data_dir).
  - ``plugin.call``    → dispatches to command handlers.
  - ``plugin.ping``    → returns ``"pong"``.
  - ``plugin.shutdown`` → returns ``None`` and exits.

Commands mirror the built-in ``opencode_config`` command names (identity
mapping — no prefix to strip) so the dual-format proxy can route to them
when the plugin is installed and healthy.
"""

# _generated_by: stitch_plugin_tools scaffold v3

from __future__ import annotations

from typing import Any

from . import service

try:
    from autoreg.plugin.rpc import RpcPluginServer
except ImportError:
    from ._vendor.rpc_server import RpcPluginServer


# ── State received in plugin.init handshake ───────────────────────────────


class _Ctx:
    """Mutable container for plugin.init handshake state."""

    db_path: str = ""
    data_dir: str = ""


ctx = _Ctx()


def _handle_init(params: dict[str, Any]) -> dict[str, Any]:
    """Store handshake params and return them as the init result."""
    ctx.db_path = str(params.get("db_path", ""))
    ctx.data_dir = str(params.get("data_dir", ""))
    return {
        "plugin_id": params.get("plugin_id", ""),
        "db_path": ctx.db_path,
        "data_dir": ctx.data_dir,
        # Capability negotiation: no reverse-RPC used.  Declared
        # explicitly for contract uniformity.
        "capabilities": [],
    }


def _handle_migrate_db(params: dict[str, Any]) -> dict[str, Any]:
    """No-op migration (storage.sqlite=false). Returns version ack."""
    return {
        "from_version": params.get("from_version", 0),
        "to_version": params.get("to_version", 1),
    }


# ── Mirrored opencode_config commands ──────────────────────────────────────


def _handle_get_opencode_config(params: dict[str, Any]) -> dict[str, Any]:
    """Read opencode.json configuration (mirrors get_opencode_config)."""
    return service.read_opencode_config()


def _handle_set_opencode_config(params: dict[str, Any]) -> dict[str, Any]:
    """Write opencode.json configuration (mirrors set_opencode_config)."""
    config = params.get("config", {})
    if not isinstance(config, dict):
        return {"success": False, "error": "config must be a JSON object"}
    service.write_opencode_config(config)
    return {"success": True}


def _handle_get_oh_my_openagent_config(params: dict[str, Any]) -> dict[str, Any]:
    """Read oh-my-openagent.json configuration (mirrors get_oh_my_openagent_config)."""
    return service.read_oh_my_openagent_config()


def _handle_set_oh_my_openagent_config(params: dict[str, Any]) -> dict[str, Any]:
    """Write oh-my-openagent.json configuration (mirrors set_oh_my_openagent_config)."""
    config = params.get("config", {})
    if not isinstance(config, dict):
        return {"success": False, "error": "config must be a JSON object"}
    service.write_oh_my_openagent_config(config)
    return {"success": True}


def _handle_test_opencode_api(params: dict[str, Any]) -> dict[str, Any]:
    """Test API endpoint and discover available models (mirrors test_opencode_api)."""
    base_url = str(params.get("baseUrl", params.get("base_url", "")))
    api_key = str(params.get("apiKey", params.get("api_key", "")))

    if not base_url or not api_key:
        return {"success": False, "error": "baseUrl and apiKey are required"}

    return service.test_api(base_url, api_key)


def _handle_bulk_test_opencode_api(params: dict[str, Any]) -> dict[str, Any]:
    """Test multiple API keys against the same base URL in parallel (mirrors bulk_test_opencode_api)."""
    base_url = str(params.get("baseUrl", params.get("base_url", "")))
    api_keys = params.get("apiKeys", params.get("api_keys", []))
    concurrency = params.get("concurrency", 10)

    if not base_url:
        return {"success": False, "error": "baseUrl is required"}
    if not api_keys or not isinstance(api_keys, list):
        return {"success": False, "error": "apiKeys must be a non-empty list"}

    return service.bulk_test_api(base_url, api_keys, concurrency=concurrency)


# ── Server entry point ────────────────────────────────────────────────────


def main() -> None:
    """Register handlers and serve the JSON-RPC loop."""
    server = RpcPluginServer()
    server.set_init_handler(_handle_init)
    server.register("_migrate_db", _handle_migrate_db)
    server.register("get_opencode_config", _handle_get_opencode_config)
    server.register("set_opencode_config", _handle_set_opencode_config)
    server.register("get_oh_my_openagent_config", _handle_get_oh_my_openagent_config)
    server.register("set_oh_my_openagent_config", _handle_set_oh_my_openagent_config)
    server.register("test_opencode_api", _handle_test_opencode_api)
    server.register("bulk_test_opencode_api", _handle_bulk_test_opencode_api)
    server.serve()


if __name__ == "__main__":
    main()
