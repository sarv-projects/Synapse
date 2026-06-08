"""Template registry — named string templates with ``{placeholders}``."""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ── built-in templates ──────────────────────────────────────────────────────

_BUILTIN_TEMPLATES: Dict[str, str] = {
    "reasoning_default": (
        "You are a helpful AI assistant analyzing the following context:\n\n"
        "{context}\n\n"
        "Question: {query}"
    ),
    "json_output": (
        "Return your response as valid JSON only. No markdown. No explanatory text.\n\n"
        "{task}"
    ),
    "qa_with_sources": (
        "Answer the question based ONLY on the provided context. "
        "If the context doesn't contain enough information, say so.\n\n"
        "Context:\n{context}\n\n"
        "Question: {query}\n\n"
        "Answer with citations."
    ),
    "summarize": (
        "Summarize the following content in a concise manner:\n\n"
        "{content}"
    ),
}


class TemplateRegistry:
    """Registry of named string templates with ``{placeholder}`` support.

    Templates are rendered via :meth:`str.format`.  Four built-in templates
    are pre-registered on construction.
    """

    def __init__(self) -> None:
        self._templates: Dict[str, str] = dict(_BUILTIN_TEMPLATES)

    # ── public API ──────────────────────────────────────────────────────────

    def register(self, name: str, template_text: str) -> None:
        """Register (or overwrite) a template named *name*."""
        self._templates[name] = template_text
        logger.debug("Registered template: %s", name)

    def get(self, name: str) -> str | None:
        """Return the template text for *name*, or ``None`` if not found."""
        return self._templates.get(name)

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render the template named *template_name* with the provided keyword arguments.

        Raises :class:`KeyError` if the template is unknown.
        Raises :class:`ValueError` if placeholders are missing.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Unknown template: {template_name!r}")
        try:
            return template.format(**kwargs)
        except KeyError as exc:
            raise ValueError(
                f"Missing placeholder {exc} for template {template_name!r}"
            ) from exc

    def list_templates(self) -> list[str]:
        """Return the list of registered template names."""
        return sorted(self._templates.keys())


# ── global singleton ────────────────────────────────────────────────────────

_registry: TemplateRegistry | None = None


def get_template_registry() -> TemplateRegistry:
    """Return the global :class:`TemplateRegistry` singleton."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry


def get_template(name: str) -> str | None:
    """Convenience: return template text for *name* from the global registry."""
    return get_template_registry().get(name)


def register_template(name: str, template_text: str) -> None:
    """Convenience: register a template in the global registry."""
    get_template_registry().register(name, template_text)


__all__ = [
    "TemplateRegistry",
    "get_template_registry",
    "get_template",
    "register_template",
]

