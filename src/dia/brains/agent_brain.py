"""Use one of the configured coding agents (Claude Code, Codex, Cursor, ...) as the brain.

Works with the same subscription the agent is logged in with. Claude Code runs
without tools, so a routing call is quick and cheap; pick a small model::

    [brains.claude]
    type = "agent"
    agent = "claude"   # a name from [agents.*]; default: the default agent
    model = "haiku"    # optional, overrides the agent's model for routing only
"""

from __future__ import annotations

from dia.brains import LLMBrain


class AgentBrain(LLMBrain):
    kind = "agent"

    @property
    def agent_name(self) -> str | None:
        return self.options.get("agent") or self.config.default_agent

    def describe(self) -> str:
        model = self.options.get("model")
        return f"agent {self.agent_name}" + (f" ({model})" if model else "")

    def check(self) -> str | None:
        if not self.agent_name:
            return "no 'agent' set and no default_agent configured"
        if self.agent_name not in self.config.agents:
            return f"unknown agent '{self.agent_name}'"
        return None

    async def complete(self, system: str, user: str) -> str:
        if problem := self.check():
            raise RuntimeError(problem)
        agent = self.config.agent(self.agent_name)
        return await agent.complete(system, user, model=self.options.get("model"))
