"""Subagent management for parallel LangGraph execution."""
from reasoning.subagents.manager import SubagentManager, get_subagent_manager
from reasoning.subagents.web_research import WebResearchAgent

__all__ = ["SubagentManager", "get_subagent_manager", "WebResearchAgent"]

