"""OpenCode config service logic — ported from stitch_backend.domains.opencode_config.

The plugin owns a copy of the file-I/O + API-test logic so it can serve
the 6 opencode_config commands when installed and healthy.  The original
domain files stay untouched as the dual-format fallback.

Self-contained: no ``stitch_backend`` imports — the plugin is a separate
process with its own sys.path.  Uses stdlib ``json``/``pathlib`` for file
I/O (sync handlers) and ``httpx`` for the API tester (same dep as core).
"""

# _generated_by: stitch_plugin_tools scaffold v3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """OpenCode stores configs in ~/.config/opencode on all platforms."""
    return Path.home() / ".config" / "opencode"


def _read_json(filename: str) -> dict[str, Any]:
    """Read a JSON file from the config dir. Returns ``{}`` if not found."""
    path = _config_dir() / filename
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)  # type: ignore[no-any-return]
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(filename: str, config: dict[str, Any]) -> None:
    """Write a JSON file to the config dir with indent=2."""
    # Validate config is JSON-serializable via roundtrip (ponytail guard).
    raw = json.dumps(config, indent=2, ensure_ascii=False)
    json.loads(raw)  # raises ValueError/JSONDecodeError on corrupt data
    _config_dir().mkdir(parents=True, exist_ok=True)
    path = _config_dir() / filename
    path.write_text(raw, encoding="utf-8")


def read_opencode_config() -> dict[str, Any]:
    """Read ``opencode.json``. Returns ``{}`` if not found."""
    return _read_json("opencode.json")


def write_opencode_config(config: dict[str, Any]) -> None:
    """Write ``opencode.json`` with indent=2."""
    _write_json("opencode.json", config)


def read_oh_my_openagent_config() -> dict[str, Any]:
    """Read ``oh-my-openagent.json``. Returns ``{}`` if not found."""
    return _read_json("oh-my-openagent.json")


def write_oh_my_openagent_config(config: dict[str, Any]) -> None:
    """Write ``oh-my-openagent.json`` with indent=2."""
    _write_json("oh-my-openagent.json", config)


# ── API tester ──────────────────────────────────────────────────────────────


def normalize_base_url(base_url: str) -> str:
    """Strip trailing /v1, /v1/models, and slashes from base URL."""
    url = base_url.strip()
    url = url.rstrip("/")
    url = re.sub(r"/v1/models$", "", url)
    url = re.sub(r"/v1$", "", url)
    return url


def test_api(base_url: str, api_key: str) -> dict[str, Any]:
    """GET {base_url}/v1/models with Bearer auth, return model list or error.

    Returns:
        {"success": True, "models": [...], "normalized_url": "..."} on success.
        {"success": False, "error": "message"} on failure.
    """
    import httpx

    normalized = normalize_base_url(base_url)
    url = f"{normalized}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id:
                    continue

                model_info: dict[str, Any] = {"id": model_id}
                owned_by = item.get("owned_by", "")
                model_info["owned_by"] = owned_by

                model_lower = model_id.lower()
                if any(kw in model_lower for kw in ["vision", "vl", "multimodal"]):
                    model_info["vision"] = True
                else:
                    model_info["vision"] = False

                if any(kw in model_lower for kw in ["deprecated", "alpha", "beta", "preview"]):
                    model_info["status"] = "experimental"
                else:
                    model_info["status"] = "stable"

                reasoning_keywords = ["o1", "o3", "o4", "reasoning", "thinking", "deepseek-r1", "qwq", "r1"]
                model_info["reasoning"] = any(kw in model_lower for kw in reasoning_keywords)

                tool_call_keywords = ["gpt-4", "gpt-3.5", "claude", "gemini", "deepseek", "qwen", "llama-3"]
                model_info["tool_call"] = any(kw in model_lower for kw in tool_call_keywords)

                context = 128000
                if any(kw in model_lower for kw in ["200k", "200-k"]):
                    context = 200000
                elif any(kw in model_lower for kw in ["1m", "1000k", "1-m"]):
                    context = 1000000
                elif any(kw in model_lower for kw in ["32k"]):
                    context = 32000
                elif any(kw in model_lower for kw in ["16k"]):
                    context = 16000
                elif any(kw in model_lower for kw in ["8k"]):
                    context = 8000
                elif any(kw in model_lower for kw in ["4k"]):
                    context = 4000
                if "claude-3" in model_lower or "claude-sonnet-4" in model_lower or "claude-opus-4" in model_lower:
                    context = 200000
                elif "gpt-4o" in model_lower or "gpt-4-turbo" in model_lower:
                    context = 128000
                elif "gpt-4-" in model_lower and "32k" not in model_lower:
                    context = 8192
                elif "deepseek" in model_lower:
                    context = 65536
                elif "gemini-2" in model_lower:
                    context = 1048576
                elif "gemini" in model_lower:
                    context = 32768

                output = 4096
                if "o1" in model_lower or "o3" in model_lower or "o4" in model_lower:
                    output = 100000
                elif "claude" in model_lower:
                    output = 8192
                elif "gpt-4o" in model_lower:
                    output = 16384
                elif "deepseek" in model_lower:
                    output = 8192

                model_info["limit"] = {"context": context, "output": output}

                input_modalities = ["text"]
                if model_info["vision"]:
                    input_modalities.append("image")
                model_info["modalities"] = {"input": input_modalities, "output": ["text"]}

                if item.get("context_length"):
                    model_info["limit"]["context"] = item["context_length"]
                if item.get("max_output_tokens") or item.get("max_tokens"):
                    model_info["limit"]["output"] = item.get("max_output_tokens") or item.get("max_tokens")
                if item.get("architecture") and isinstance(item["architecture"], dict):
                    arch = item["architecture"]
                    if arch.get("modality") == "text+image->text":
                        model_info["vision"] = True
                        if "image" not in model_info["modalities"]["input"]:
                            model_info["modalities"]["input"].append("image")

                models.append(model_info)

            return {
                "success": True,
                "models": models,
                "normalized_url": normalized,
            }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out"}
    except httpx.ConnectError:
        return {"success": False, "error": "Connection failed"}
    except (json.JSONDecodeError, ValueError, KeyError):
        return {"success": False, "error": "Invalid response format"}


def bulk_test_api(base_url: str, api_keys: list[str], concurrency: int = 10) -> dict[str, Any]:
    """Test multiple API keys against the same base URL in parallel.

    Returns:
        {
            "success": True,
            "results": [
                {"key": "...", "status": "ok|rate_limited|invalid|error", "models": [...], "error": "..."},
                ...
            ],
            "normalized_url": "..."
        }
    """
    import asyncio

    import httpx

    normalized = normalize_base_url(base_url)
    url = f"{normalized}/v1/models"

    async def test_single_key(key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [item["id"] for item in data.get("data", [])]
                    return {"key": key, "status": "ok", "models": models}
                elif response.status_code == 429:
                    return {"key": key, "status": "rate_limited"}
                elif response.status_code in (401, 403):
                    return {"key": key, "status": "invalid"}
                else:
                    return {"key": key, "status": "error", "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            return {"key": key, "status": "error", "error": "Timeout"}
        except httpx.ConnectError:
            return {"key": key, "status": "error", "error": "Connection failed"}
        except Exception as e:  # noqa: BLE001 — mirror core behaviour
            return {"key": key, "status": "error", "error": str(e)}

    semaphore = asyncio.Semaphore(concurrency)

    async def limited_test(key: str) -> dict[str, Any]:
        async with semaphore:
            return await test_single_key(key)

    results = asyncio.run(asyncio.gather(*[limited_test(key) for key in api_keys]))

    return {
        "success": True,
        "results": list(results),
        "normalized_url": normalized,
    }
