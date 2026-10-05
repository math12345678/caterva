"""The assistant's settings, its consent record and its in-memory keys.

SETTINGS LIVE IN THEIR OWN FILE
-------------------------------
`<data dir>/assistant.json`, not `settings.json`: the studio's Settings
contract (`CONTRACT.md` section 8) is the three original keys plus a few the
engine's screens read, and the assistant's are a separate surface with their
own validation. Every key is off or empty by default; nothing is sent until a
person switches the assistant on, a feature on, and agrees to what that
feature sends.

THE KEY IS NOT HERE
-------------------
`KeyStore` holds keys in process memory only. Nothing in this file, in
`assistant.json`, in a run record, in a bundle or in a log ever holds one.
Where a key comes from:

  * the macOS shell, which keeps it in the login Keychain and writes it to
    this server's stdin as one JSON line at launch and when it changes
    (`__main__.watch_parent`, docs/studio/CONTRACT.md "SECURITY");
  * in a plain-browser or development run, the environment variable
    `CATERVA_ASSISTANT_KEY`, read once at startup. The page says which.

There is deliberately no HTTP route that accepts a key: a key that crossed
the page's JavaScript on its way to the server could be read by anything the
page runs. (The Settings field hands it to the shell's Keychain bridge and
clears itself.)
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from caterva.assistant.prompts import FEATURES
from caterva.assistant.providers import DEFAULT_MODELS, PROVIDERS, AssistantError, validate_local_url

ENV_KEY = "CATERVA_ASSISTANT_KEY"
MAX_CALLS_RANGE = (1, 500)
MAX_TOKENS_RANGE = (64, 4096)
MAX_MODELS = 12

DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "provider": "anthropic",
    "models": {"anthropic": DEFAULT_MODELS["anthropic"]},          # chosen model per provider
    "model_lists": {"anthropic": [DEFAULT_MODELS["anthropic"]]},   # the list the person edits
    "local_url": PROVIDERS["local"].base_url,
    "local_only": False,
    "features": {f: False for f in FEATURES},
    "max_calls_per_hour": 20,
    "max_tokens": 1024,
}
_KEYS = frozenset(DEFAULTS)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ConfigError(ValueError):
    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field


def _model_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ConfigError("a model name is plain text of at most 120 characters", field)
    return value.strip()


def validate(body: Any, stored: Mapping[str, Any]) -> Dict[str, Any]:
    """The full settings after applying a partial `body` to `stored`, or ConfigError naming the field."""
    if not isinstance(body, dict):
        raise ConfigError("the assistant settings must be a JSON object")
    unknown = sorted(set(body) - _KEYS)
    if unknown:
        raise ConfigError(f"{unknown[0]!r} is not an assistant setting", unknown[0])
    out = json.loads(json.dumps({**DEFAULTS, **stored}))
    for key in ("enabled", "local_only"):
        if key in body:
            if not isinstance(body[key], bool):
                raise ConfigError(f"{key} must be true or false", key)
            out[key] = body[key]
    if "provider" in body:
        if body["provider"] not in PROVIDERS:
            raise ConfigError(f"provider must be one of {', '.join(PROVIDERS)}", "provider")
        out["provider"] = body["provider"]
    if "models" in body:
        if not isinstance(body["models"], dict):
            raise ConfigError("models maps a provider to the model name to use", "models")
        for prov, name in body["models"].items():
            if prov not in PROVIDERS:
                raise ConfigError(f"{prov!r} is not a provider", "models")
            out["models"][prov] = _model_name(name, "models")
    if "model_lists" in body:
        if not isinstance(body["model_lists"], dict):
            raise ConfigError("model_lists maps a provider to a list of model names", "model_lists")
        for prov, names in body["model_lists"].items():
            if prov not in PROVIDERS or not isinstance(names, list) or len(names) > MAX_MODELS:
                raise ConfigError(f"model_lists[{prov!r}] must be a list of at most {MAX_MODELS} names", "model_lists")
            out["model_lists"][prov] = [n for n in dict.fromkeys(_model_name(x, "model_lists") for x in names) if n]
    if "local_url" in body:
        try:
            out["local_url"] = validate_local_url(str(body["local_url"]))
        except AssistantError as exc:
            raise ConfigError(exc.message, "local_url") from None
    if "features" in body:
        feats = body["features"]
        if not isinstance(feats, dict) or set(feats) - set(FEATURES) or not all(isinstance(v, bool) for v in feats.values()):
            raise ConfigError(f"features maps {', '.join(FEATURES)} to true or false", "features")
        out["features"].update(feats)
    for key, (low, high) in (("max_calls_per_hour", MAX_CALLS_RANGE), ("max_tokens", MAX_TOKENS_RANGE)):
        if key in body:
            v = body[key]
            if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
                raise ConfigError(f"{key} must be a whole number from {low} to {high}", key)
            out[key] = v
    if out["local_only"] and out["provider"] != "local":
        raise ConfigError("local only is on: choose the model on this computer, or switch local only off",
                          "provider")
    return out


class ConfigStore:
    """`assistant.json`: settings plus the per-feature consent record. Atomic writes, one lock."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "assistant.json"
        self._lock = threading.Lock()
        self._settings: Dict[str, Any] = json.loads(json.dumps(DEFAULTS))
        self._consent: Dict[str, str] = {}
        self.note: Optional[str] = None
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            self.note = f"{self.path.name} was not used ({type(exc).__name__}); the assistant is off"
            return
        try:
            consent = raw.pop("consent", {}) if isinstance(raw, dict) else {}
            self._settings = validate(raw, DEFAULTS)
            self._consent = {k: v for k, v in consent.items() if k in FEATURES and isinstance(v, str)}
        except ConfigError as exc:
            self.note = f"{self.path.name} was not used ({exc}); the assistant is off"

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({**self._settings, "consent": self._consent}, indent=1, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".assistant-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._settings))

    def update(self, body: Any) -> Dict[str, Any]:
        with self._lock:
            self._settings = validate(body, self._settings)
            self._save()
            return json.loads(json.dumps(self._settings))

    def consented(self, feature: str) -> Optional[str]:
        with self._lock:
            return self._consent.get(feature)

    def grant(self, feature: str) -> None:
        with self._lock:
            self._consent[feature] = _now()
            self._save()

    def withdraw(self) -> None:
        with self._lock:
            self._consent = {}
            self._save()

    def consent(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._consent)


class KeyStore:
    """API keys, in memory, per provider. Never written anywhere."""

    def __init__(self, environ: Optional[Mapping[str, str]] = None) -> None:
        self._lock = threading.Lock()
        self._keys: Dict[str, str] = {}
        self._env = (os.environ if environ is None else environ).get(ENV_KEY) or None

    def set(self, provider: str, key: str) -> None:
        if provider not in PROVIDERS or not PROVIDERS[provider].needs_key:
            raise ValueError("that provider takes no key")
        if not isinstance(key, str) or not 8 <= len(key.strip()) <= 512 or any(c.isspace() for c in key.strip()):
            raise ValueError("that is not a usable key")
        with self._lock:
            self._keys[provider] = key.strip()

    def clear(self, provider: Optional[str] = None) -> None:
        with self._lock:
            if provider is None:
                self._keys.clear()
            else:
                self._keys.pop(provider, None)

    def get(self, provider: str) -> Optional[str]:
        with self._lock:
            return self._keys.get(provider) or (self._env if PROVIDERS[provider].needs_key else None)

    def status(self, provider: str) -> Dict[str, Any]:
        """present/absent and where it came from: never the value."""
        spec = PROVIDERS[provider]
        if not spec.needs_key:
            return {"present": True, "needed": False, "source": None}
        with self._lock:
            if self._keys.get(provider):
                return {"present": True, "needed": True, "source": "keychain"}
            if self._env:
                return {"present": True, "needed": True, "source": "environment"}
        return {"present": False, "needed": True, "source": None}

    def secrets(self) -> List[str]:
        with self._lock:
            return [k for k in [*self._keys.values(), self._env] if k]


__all__ = ["ConfigError", "ConfigStore", "DEFAULTS", "ENV_KEY", "KeyStore", "validate"]
