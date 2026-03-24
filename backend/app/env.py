import os
import json
from pathlib import Path
from typing import Any


def _load_env_file() -> None:
    """Load key/value pairs from backend/.env into os.environ if missing."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        # Fail silently; required keys will be validated on access.
        return


_load_env_file()


def get_env(key: str) -> str:
    val = os.environ.get(key)
    if val is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


def get_int(key: str) -> int:
    val = get_env(key)
    try:
        return int(val)
    except Exception as exc:
        raise RuntimeError(f"Invalid int for env var {key}: {val}") from exc


def get_bool(key: str) -> bool:
    val = get_env(key).strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid bool for env var {key}: {val}")


def get_json_list(key: str) -> list[str]:
    raw = get_env(key)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON for env var {key}: {raw}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"Expected JSON array for env var {key}: {raw}")
    return [str(item) for item in data]
