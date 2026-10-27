# Security

## Agents in a sandbox

Coding agents read whatever is in a repository, an issue, a web page or a
note, and some of that may be written to turn them against you (prompt
injection). So agents do not run with your full account:

- **The sandbox** (bubblewrap, `[sandbox] enabled = "auto"`): the system is
  read-only, your home is replaced by an almost empty one, and only the
  agent's worktree, its own login and config (`~/.claude`, `~/.codex`,
  `~/.cursor`) and the tools it runs with come back. `~/.ssh`, `~/.gnupg`,
  `~/.config/dia` (your secrets), browsers, other projects and Dia's own data
  are simply not there. The repository's git data is read-only (an agent can
  commit on its task branch, but cannot move `main` or add hooks), and Dia's
  secrets are removed from its environment (its own API key stays). Your
  projects' tests run in the same sandbox, because they run code an agent
  wrote.
- **The guard** (`[sandbox] decoys = true`): the almost empty home holds fake
  keys and tokens with a one-off marker. An agent that reads one and repeats it
  or copies it into the code is stopped: its work is not kept, the task shows
  a security incident, and you get an urgent alert. Reaching for such paths
  and failing is recorded as a lesser incident.
- **The red team**: `dia redteam` gives each of your agents an ordinary task
  on a throwaway repository full of hostile instructions and reports, per
  agent, *resisted*, *contained* or *BREACH* (a bug in Dia: please report it).
  The automated tests run the same attack with a scripted agent that obeys
  every instruction, on every change.
- **The lab**: `dia lab [project] "command"` runs something in a throwaway
  container (podman or docker) on a copy of a project, without network or
  privileges by default.

```toml
[sandbox]
enabled = "auto"          # "auto" | true (required) | false
allow_read = ["~/Projekty/shared-assets"]   # extra, read-only
allow_write = []
hide = ["/mnt/backup"]    # extra places outside home to hide
network = true            # agents need their APIs
tests = true              # project tests in the sandbox too
decoys = true

[agents.claude]
sandbox = { allow_read = ["~/.config/some-tool"], pass_env = ["SOME_TOKEN"] }

[lab]
engine = "podman"
image = "docker.io/library/python:3.13-slim"
```

On Arch: `sudo pacman -S bubblewrap` (Arch kernels allow the user namespaces
it needs). `dia sandbox check` shows what each agent sees and whether it
starts there; if an agent needs a directory it cannot see, add it with
`allow_read`/`allow_write` for that agent. Without a working bubblewrap, "auto"
runs agents unconfined and Status says so; `enabled = true` refuses instead.

What it does not cover: the agents' network access (they need their APIs, so
a determined agent could still send what it can see, which is now only its
worktree), and Dia's brain calls, which run without tools in an empty directory.

# Security checks

Dia checks your own computer, network and projects. It reads; it never
changes firewall rules or system settings, and it scans only what you list
as yours.

```sh
dia security                  # the report (also: "raport bezpieczeństwa", Status → Security)
dia security ports            # what listens on this computer, and which process
dia security scan nas.local   # open ports of YOUR host (listed in [security] hosts)
dia security devices          # devices this computer has seen on the network (ARP, passive)
dia security discover         # devices on YOUR networks (nmap -sn or ping; [security] networks)
dia security logs             # failed logins and errors in the journal (24 h)
dia security deps nova        # vulnerable dependencies; --fix gives them to an agent
```

The report: ports open to the network (with the process), ports that are
**new** since last time, the active firewall service, failed logins with the
addresses they came from, system errors, and vulnerable dependencies of each
project. While `dia serve` runs, a newly exposed port raises an alert.

```toml
[security]
hosts = ["192.168.1.10", "nas.local"]   # yours; localhost is always allowed
networks = ["192.168.1.0/24"]           # yours: the report looks for devices on them
# discover = true                       # false: no device search in the report
ports = [22, 80, 443, 8080]             # extra ports to try when nmap isn't installed
log_hours = 24
```

Tools it uses when installed: `nmap` (service versions in scans),
`osv-scanner` (dependencies in every ecosystem; else `npm audit`, `cargo
audit`, `pip-audit`). Reading the journal of other units needs your user in
the `wheel` or `systemd-journal` group.

A daily report: `dia schedule add "0 8 * * *" "raport bezpieczeństwa"`.

Device discovery is a ping sweep (`nmap -sn`, no port scan; plain `ping`
without nmap) of private networks you list, at most a /22. The first sweep
records the devices; later reports name **new** devices on your network (with
the vendor when nmap knows it), which is also an alert while `dia serve` runs.

**Only scan systems you own or may test.** Dia refuses any host not in
`[security] hosts`.
