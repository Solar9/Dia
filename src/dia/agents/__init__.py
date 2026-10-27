"""Coding-agent adapters. Each adapter wraps one agent CLI behind :class:`Agent`."""

from dia.agents.base import Agent, AgentRequest, AgentResult, CliAgent, Mode

__all__ = ["Agent", "AgentRequest", "AgentResult", "CliAgent", "Mode"]
