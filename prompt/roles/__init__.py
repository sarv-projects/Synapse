"""Role registry — scans and caches system role prompts from `.txt` files."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class RoleRegistry:
    """Singleton registry that scans ``roles/`` for ``.txt`` role prompt files.

    Each file is loaded by name (without ``.txt`` extension) and cached
    in-memory for fast lookup.
    """

    _role_dir: Path

    def __init__(self, role_dir: Path | None = None) -> None:
        self._role_dir = role_dir or (Path(__file__).parent)
        self._cache: dict[str, str] = {}
        self._scan()

    # ── public API ──────────────────────────────────────────────────────────

    def get(self, role_name: str) -> str:
        """Return the cached prompt text for *role_name*.

        Returns an empty string if the role file does not exist.
        """
        role_name = role_name.removesuffix(".txt")
        if role_name not in self._cache:
            path = self._role_dir / f"{role_name}.txt"
            if path.exists():
                self._cache[role_name] = path.read_text(encoding="utf-8")
                logger.debug("Loaded role prompt: %s", role_name)
            else:
                logger.warning("Role file not found: %s", path)
                self._cache[role_name] = ""
        return self._cache[role_name]

    def list_roles(self) -> List[str]:
        """Return the list of available role names (without ``.txt``)."""
        return sorted(self._cache.keys())

    def reload(self) -> None:
        """Re-scan the roles directory and refresh the cache."""
        self._cache.clear()
        self._scan()

    # ── internals ───────────────────────────────────────────────────────────

    def _scan(self) -> None:
        """Scan the roles directory and pre-load every ``.txt`` file."""
        if not self._role_dir.is_dir():
            logger.warning("Roles directory does not exist: %s", self._role_dir)
            return
        for txt_path in sorted(self._role_dir.glob("*.txt")):
            name = txt_path.stem  # filename without .txt
            self._cache[name] = txt_path.read_text(encoding="utf-8")
            logger.debug("Scanned role prompt: %s", name)


# ── global singleton ────────────────────────────────────────────────────────

_registry: RoleRegistry | None = None


def get_role_registry() -> RoleRegistry:
    """Return the global :class:`RoleRegistry` singleton."""
    global _registry
    if _registry is None:
        _registry = RoleRegistry()
    return _registry


def get_role_prompt(role_name: str) -> str:
    """Convenience: return the cached prompt for *role_name*."""
    return get_role_registry().get(role_name)


__all__ = ["RoleRegistry", "get_role_registry", "get_role_prompt"]

