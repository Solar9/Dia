"""Cross-review: one agent reviews another agent's changes; the author fixes what it finds.

The diff is put into the reviewer's prompt, so any agent can review, even
one that cannot run commands in read-only mode. The reviewer's answer starts
with a verdict line that Dia parses; everything after it is the findings,
which go back to the implementing agent when changes are requested.
"""

from __future__ import annotations

import re

APPROVED = "approved"
CHANGES_REQUESTED = "changes_requested"
UNCLEAR = "unclear"

_VERDICT = re.compile(
    r"VERDICT\W*(APPROVED?|CHANGES[_ ]REQUESTED|REQUEST[_ ]CHANGES)", re.IGNORECASE
)


def review_prompt(task_prompt: str, diff: str, base: str, max_chars: int = 60000) -> str:
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n[... diff truncated; inspect the files for the rest]"
    return f"""\
You are reviewing changes another coding agent made for this task:

<task>
{task_prompt}
</task>

The changes are committed in the current directory (compared to '{base}').
Read the surrounding code as needed, but do not modify any files.

Check, in this order: does it do what the task asks; bugs and edge cases;
broken or missing tests; security problems; consistency with the existing
code. Ignore pure style preferences.

Start your answer with exactly one of these lines:
VERDICT: APPROVE
VERDICT: CHANGES_REQUESTED
Then list concrete findings (file, problem, suggested fix). Request changes
only for real problems, not for optional polish.

<diff>
{diff}
</diff>
"""


def fix_prompt(task_prompt: str, reviewer: str, findings: str) -> str:
    return f"""\
You implemented this task earlier (your changes are committed here):

<task>
{task_prompt}
</task>

A reviewer ({reviewer}) requested changes:

<review>
{findings}
</review>

Address every finding you agree with, directly in the code. If you disagree
with one, leave the code as is and explain why in your final message.
"""


def parse_verdict(text: str) -> str:
    match = _VERDICT.search(text)
    if not match:
        return UNCLEAR
    return APPROVED if match.group(1).upper().startswith("APPROVE") else CHANGES_REQUESTED
