"""Prompt assembly and role management for LLM inference."""
from prompt.assembler import PromptAssembler
from prompt.roles import RoleRegistry, get_role_prompt, get_role_registry
from prompt.templates import get_template, register_template, TemplateRegistry

__all__ = [
    "PromptAssembler",
    "RoleRegistry",
    "get_role_prompt",
    "get_role_registry",
    "get_template",
    "register_template",
    "TemplateRegistry",
]

