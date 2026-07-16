"""Persistent assistant memory — MemoryManager + pluggable MemoryBackend."""

from .backend import MemoryBackend
from .in_memory import InMemoryBackend
from .json_backend import JsonMemoryBackend
from .manager import DEFAULT_MEMORY, AssistantMemory, MemoryManager

__all__ = [
    "AssistantMemory",
    "DEFAULT_MEMORY",
    "InMemoryBackend",
    "JsonMemoryBackend",
    "MemoryBackend",
    "MemoryManager",
]
