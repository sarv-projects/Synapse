"""Integration tests for the prompt template & role registry.

These tests don't need external services. They verify the registry's
load/cached behaviour, the dynamic template rendering, and the role
scanning logic.
"""
from __future__ import annotations

import pytest

from prompt.roles import RoleRegistry, get_role_prompt, get_role_registry
from prompt.templates import TemplateRegistry, get_template, get_template_registry, register_template


pytestmark = pytest.mark.integration


class TestRoleRegistry:
    """Test role discovery and caching."""

    def test_lists_known_roles(self):
        rr = get_role_registry()
        roles = rr.list_roles()
        assert isinstance(roles, list)
        assert len(roles) > 0
        assert "analyzer" in roles
        assert "synthesizer" in roles
        assert "decomposition" in roles

    def test_get_returns_non_empty_prompt(self):
        rr = get_role_registry()
        prompt = rr.get("analyzer")
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "SYNAPSE" in prompt or "analyzer" in prompt.lower()

    def test_unknown_role_returns_empty(self):
        rr = RoleRegistry()
        # Manually pass an unknown role
        assert rr.get("definitely-does-not-exist-9999") == ""

    def test_cache_returns_same_string(self):
        rr = get_role_registry()
        p1 = rr.get("critic")
        p2 = rr.get("critic")
        assert p1 is p2  # Same object from cache

    def test_reload_picks_up_new_files(self, tmp_path, monkeypatch):
        """Adding a new role file should be picked up after reload()."""
        # Create a temporary roles directory with one role
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        (roles_dir / "custom_role.txt").write_text("You are a custom role for testing.")
        rr = RoleRegistry(role_dir=roles_dir)
        assert "custom_role" in rr.list_roles()
        assert "custom" in rr.get("custom_role").lower()
        # Add a new file
        (roles_dir / "another_role.txt").write_text("Another test role.")
        rr.reload()
        assert "another_role" in rr.list_roles()

    def test_convenience_function(self):
        p = get_role_prompt("extractor")
        assert "SYNAPSE" in p or "extract" in p.lower()


class TestTemplateRegistry:
    """Test the string template registry."""

    def test_builtin_templates_present(self):
        tr = get_template_registry()
        templates = tr.list_templates()
        assert "reasoning_default" in templates
        assert "json_output" in templates
        assert "qa_with_sources" in templates
        assert "summarize" in templates

    def test_render_substitutes_placeholders(self):
        tr = TemplateRegistry()
        out = tr.render("summarize", content="hello world")
        assert "hello world" in out
        assert "{content}" not in out

    def test_render_qa_with_sources(self):
        tr = TemplateRegistry()
        out = tr.render(
            "qa_with_sources",
            context="The capital of France is Paris.",
            query="What is the capital of France?",
        )
        assert "Paris" in out
        assert "capital of France" in out

    def test_missing_placeholder_raises_value_error(self):
        tr = TemplateRegistry()
        with pytest.raises(ValueError, match="Missing placeholder"):
            tr.render("summarize")  # No 'content' kwarg

    def test_unknown_template_raises_key_error(self):
        tr = TemplateRegistry()
        with pytest.raises(KeyError, match="Unknown template"):
            tr.render("nonexistent-template-xyz")

    def test_register_custom_template(self):
        tr = TemplateRegistry()
        tr.register("my_template", "Hello {name}, today is {day}.")
        result = tr.render("my_template", name="Alice", day="Monday")
        assert result == "Hello Alice, today is Monday."

    def test_module_level_helpers(self):
        # Verify module-level convenience functions work
        register_template("global_test", "test {x}")
        out = get_template("global_test")
        assert out == "test {x}"
