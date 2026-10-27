"""Built-in forges: plain git, GitHub (gh) and GitLab (glab or push options)."""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from dia.agents.base import find_executable
from dia.forges import CIStatus, Forge, Issue, Publication, ReviewComment, find_url
from dia.workspace import run


class GitForge(Forge):
    """Any git server: push the branch, nothing more."""

    kind = "git"
    has_ci = False

    async def publish(
        self, repo: Path, branch: str, base: str, title: str, body: str
    ) -> Publication:
        await self.push(repo, branch)
        return Publication(None, f"pushed {branch} to {self.remote}")


class GitHubForge(Forge):
    """Push, then open a pull request with the GitHub CLI (``gh auth login`` once)."""

    kind = "github"

    @property
    def command(self) -> str:
        return find_executable(self.options.get("command", "gh")) or "gh"

    def check(self) -> str | None:
        if not find_executable(self.command):
            return "GitHub CLI 'gh' not found (https://cli.github.com), then run: gh auth login"
        return None

    def argv(self, branch: str, base: str, title: str) -> list[str]:
        argv = [
            self.command,
            "pr",
            "create",
            "--head",
            branch,
            "--base",
            base,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        if self.options.get("draft"):
            argv.append("--draft")
        return argv

    async def publish(
        self, repo: Path, branch: str, base: str, title: str, body: str
    ) -> Publication:
        if problem := self.check():
            raise RuntimeError(problem)
        await self.push(repo, branch)
        code, out = await run(self.argv(branch, base, title), repo, stdin=body)
        if code != 0:
            raise RuntimeError(f"gh pr create failed: {out.strip()}")
        url = find_url(out, "/pull/")
        return Publication(url, f"opened pull request {url or ''}".strip())

    async def ci_status(self, repo: Path, branch: str) -> CIStatus:
        # gh exits non-zero while checks are pending or failing; the JSON is what matters.
        _, out = await run(
            [self.command, "pr", "checks", branch, "--json", "name,bucket,link"], repo
        )
        try:
            checks = json.loads(out)
        except json.JSONDecodeError:
            if "no checks" in out.lower():
                return CIStatus("none")
            raise RuntimeError(f"gh pr checks failed: {out.strip()}") from None
        if not checks:
            return CIStatus("none")
        buckets = {c.get("bucket") for c in checks}
        failed = [
            {"name": c["name"], "url": c.get("link")}
            for c in checks
            if c.get("bucket") in ("fail", "cancel")
        ]
        state = "failed" if failed else "pending" if "pending" in buckets else "success"
        return CIStatus(state, (failed[0]["url"] if failed else None), failed)

    async def review_comments(self, repo: Path, branch: str) -> list[ReviewComment]:
        code, out = await run(
            [self.command, "pr", "view", branch, "--json", "number,reviews,comments"], repo
        )
        if code != 0:
            raise RuntimeError(f"gh pr view failed: {out.strip()}")
        data = json.loads(out)
        comments = [
            ReviewComment(f"review-{r['id']}", r["author"]["login"], r["body"])
            for r in data.get("reviews", [])
            if (r.get("body") or "").strip()
        ]
        comments += [
            ReviewComment(f"comment-{c['id']}", c["author"]["login"], c["body"], url=c.get("url"))
            for c in data.get("comments", [])
        ]
        code, out = await run(
            [self.command, "api", f"repos/{{owner}}/{{repo}}/pulls/{data['number']}/comments"],
            repo,
        )
        if code != 0:
            raise RuntimeError(f"gh api (inline comments) failed: {out.strip()}")
        comments += [
            ReviewComment(
                f"inline-{c['id']}",
                c["user"]["login"],
                c["body"],
                path=c.get("path"),
                line=c.get("line") or c.get("original_line"),
                url=c.get("html_url"),
            )
            for c in json.loads(out)
        ]
        return comments

    async def issues(self, repo: Path, label: str) -> list[Issue]:
        fields = "number,title,body,url,author"
        code, out = await run(
            [self.command, "issue", "list", "--label", label, "--state", "open", "--json", fields],
            repo,
        )
        if code != 0:
            raise RuntimeError(f"gh issue list failed: {out.strip()}")
        return [
            Issue(i["number"], i["title"], i.get("body") or "", i["author"]["login"], i.get("url"))
            for i in json.loads(out)
        ]

    async def ci_log(self, repo: Path, status: CIStatus, max_chars: int = 6000) -> str:
        runs = {
            m.group(1)
            for f in status.failed
            if (m := re.search(r"/runs/(\d+)", f.get("url") or ""))
        }
        logs = []
        for run_id in sorted(runs)[:2]:
            _, out = await run([self.command, "run", "view", run_id, "--log-failed"], repo)
            logs.append(out)
        return _tail("\n".join(logs), max_chars)


def _tail(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else "[...]\n" + text[-max_chars:]


class GitLabForge(Forge):
    """Push and open a merge request: with ``glab`` if installed, otherwise with
    GitLab's push options, which need nothing but git."""

    kind = "gitlab"

    @property
    def command(self) -> str | None:
        return find_executable(self.options.get("command", "glab"))

    def argv(self, branch: str, base: str, title: str, body: str) -> list[str]:
        argv = [
            self.command or "glab",
            "mr",
            "create",
            "--source-branch",
            branch,
            "--target-branch",
            base,
            "--title",
            title,
            "--description",
            body,
            "--yes",
        ]
        if self.options.get("draft"):
            argv.append("--draft")
        if self.options.get("remove_source_branch", True):
            argv.append("--remove-source-branch")
        return argv

    def push_options(self, base: str, title: str, body: str) -> list[str]:
        options = [
            "merge_request.create",
            f"merge_request.target={base}",
            f"merge_request.title={'Draft: ' if self.options.get('draft') else ''}{title}",
            # push options cannot carry newlines
            f"merge_request.description={' '.join(body.split())[:1000]}",
        ]
        if self.options.get("remove_source_branch", True):
            options.append("merge_request.remove_source_branch")
        return options

    async def publish(
        self, repo: Path, branch: str, base: str, title: str, body: str
    ) -> Publication:
        if self.command and self.options.get("use_glab", True):
            await self.push(repo, branch)
            code, out = await run(self.argv(branch, base, title, body), repo)
            if code != 0:
                raise RuntimeError(f"glab mr create failed: {out.strip()}")
        else:
            out = await self.push(repo, branch, *self.push_options(base, title, body))
        url = find_url(out, "/merge_requests/")
        return Publication(url, f"opened merge request {url or ''}".strip())

    async def ci_status(self, repo: Path, branch: str) -> CIStatus:
        if not self.command:
            return CIStatus("none")  # reading pipelines needs glab (and its login)
        code, out = await run(
            [self.command, "ci", "get", "--branch", branch, "--output", "json"], repo
        )
        if code != 0:
            if "no pipeline" in out.lower() or "404" in out:
                return CIStatus("none")
            raise RuntimeError(f"glab ci get failed: {out.strip()}")
        pipeline = json.loads(out[out.index("{") :])
        status = pipeline.get("status", "")
        failed = [
            {"name": j.get("name"), "id": j.get("id"), "url": j.get("web_url")}
            for j in pipeline.get("jobs") or []
            if j.get("status") == "failed" and not j.get("allow_failure")
        ]
        if status in ("success", "skipped"):
            state = "success"
        elif status in ("failed", "canceled"):
            state = "failed"
        else:
            state = "pending"
        return CIStatus(state, pipeline.get("web_url"), failed)

    async def ci_log(self, repo: Path, status: CIStatus, max_chars: int = 6000) -> str:
        if not self.command:
            return ""
        logs = []
        for job in status.failed[:2]:
            if job.get("id"):
                _, out = await run([self.command, "ci", "trace", str(job["id"])], repo)
                logs.append(f"--- job {job['name']} ---\n{out}")
        return _tail("\n".join(logs), max_chars)

    async def issues(self, repo: Path, label: str) -> list[Issue]:
        if not self.command:
            return []  # reading issues needs glab (and its login)
        query = urllib.parse.urlencode({"labels": label, "state": "opened", "per_page": 50})
        code, out = await run([self.command, "api", f"projects/:id/issues?{query}"], repo)
        if code != 0:
            raise RuntimeError(f"glab api (issues) failed: {out.strip()}")
        return [
            Issue(
                i["iid"],
                i["title"],
                i.get("description") or "",
                i["author"]["username"],
                i.get("web_url"),
            )
            for i in json.loads(out[out.index("[") :])
        ]

    async def review_comments(self, repo: Path, branch: str) -> list[ReviewComment]:
        if not self.command:
            return []  # reading notes needs glab (and its login)
        code, out = await run([self.command, "mr", "view", branch, "--output", "json"], repo)
        if code != 0:
            raise RuntimeError(f"glab mr view failed: {out.strip()}")
        iid = json.loads(out[out.index("{") :])["iid"]
        code, out = await run(
            [self.command, "api", f"projects/:id/merge_requests/{iid}/notes?per_page=100"], repo
        )
        if code != 0:
            raise RuntimeError(f"glab api (notes) failed: {out.strip()}")
        comments = []
        for note in json.loads(out[out.index("[") :]):
            if note.get("system"):  # "added 1 commit", "approved this merge request", ...
                continue
            position = note.get("position") or {}
            comments.append(
                ReviewComment(
                    f"note-{note['id']}",
                    note["author"]["username"],
                    note["body"],
                    path=position.get("new_path"),
                    line=position.get("new_line"),
                )
            )
        return comments
