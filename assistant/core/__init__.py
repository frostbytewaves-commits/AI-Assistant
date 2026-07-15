"""Core interfaces — thin Orchestrator building blocks (see docs/JARVIS_ARCHITECTURE.md)."""

from .context import AssistantContext, ContextBuilder, ContextManager

__all__ = ["AssistantContext", "ContextBuilder", "ContextManager"]
