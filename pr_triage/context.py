"""Thread-local-ish global config for triage modules (set by CLI before run)."""

from pathlib import Path

from .config import TriageConfig, load_config

_active: TriageConfig | None = None


def get_config() -> TriageConfig:
    global _active
    if _active is None:
        _active = load_config(_find_default_config())
    return _active


def set_config(cfg: TriageConfig | None) -> None:
    global _active
    _active = cfg


def _find_default_config() -> Path:
    root = Path.cwd()
    dot = root / ".pr-triage.yml"
    if dot.is_file():
        import yaml

        data = yaml.safe_load(dot.read_text()) or {}
        rel = data.get("config") or data.get("profile")
        if rel:
            p = Path(rel)
            if p.is_file():
                return p
    for candidate in (root / "configs" / "ceph.yml", root / "configs" / "default.yml"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("No triage config; pass --config configs/<profile>.yml")


def activate_config(path: str | Path | None) -> TriageConfig:
    cfg = load_config(path) if path else load_config(_find_default_config())
    set_config(cfg)
    return cfg
