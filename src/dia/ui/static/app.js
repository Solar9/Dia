// Dia web UI: tasks and review, chat, status and settings, voice.
// Plain ES modules with Preact + htm, so there is no build step.
import { h, render } from "preact";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import htm from "htm";

const html = htm.bind(h);

// ------------------------------------------------------------------ i18n ---

const STRINGS = {
  en: {
    tasks: "Tasks", chat: "Chat", status: "Status", settings: "Settings",
    connected: "Connected", offline: "Reconnecting…", change_server: "Change server",
    voice_idle: "Talk to Dia", voice_listening: "Listening… click to stop",
    voice_processing: "Thinking…", voice_speaking: "Speaking…",
    new_task: "New task", project: "Project", agent: "Agent", default_agent: "Default agent",
    edit: "Edit", read_only: "Read-only", review: "Review", run: "Run", plan: "Plan",
    pipeline: "Pipeline", planner: "Planner agent", what: "What should be done?",
    all_projects: "All projects", all_statuses: "All statuses", no_tasks: "No tasks yet.",
    pick_task: "Select a task to see the details.", prompt: "Request", summary: "Summary",
    steps: "Steps", reviews: "Reviews", tests: "Tests", changes: "Changes", ci: "CI",
    comments: "Review comments", plan_steps: "Plan", show_diff: "Show diff",
    show_log: "Full test log", hide: "Hide", merge: "Merge", publish: "PR / MR",
    discard: "Discard", fix_ci: "Fix CI", address: "Address comments", run_plan: "Run plan",
    open_pr: "Open PR/MR", branch: "Branch", created: "Created", mode: "Mode",
    chat_hint: "Ask or tell Dia anything: “what does the save system in nova do?”, “status”…",
    send: "Send", yes: "yes", no: "no", open_task: "Open task",
    version: "Version", sessions: "Conversations", talk_to: "Talk to", model: "Model", default_model: "default",
    provider_help: "Dia runs tasks and skills; a model answers directly (cheaper for plain questions).", new_session: "New conversation", main_session: "Main conversation", main_session_help: "Shared with voice, the phone and Discord",
    untitled: "New conversation", rename: "Rename", rename_prompt: "Name of this conversation:", delete_session: "Delete",
    delete_session_confirm: "Delete this conversation and its history?", clear_main_confirm: "Clear the main conversation's history?",
    agents: "Agents", projects: "Projects", brains: "Brain chain", memory: "Memory",
    channels: "Channels", off: "off", refresh: "Refresh", theme: "Theme",
    custom_themes: "Your themes", themes_help: "Copy a built-in theme into this folder, change the colours and reload:",
    config: "Configuration", save: "Save", saved_restart: "Saved. Restart Dia to apply (dia service restart, or restart dia serve).",
    login_title: "Connect to Dia", login_help: "Open the UI with `dia app` or `dia ui`, or paste the API token (`dia ui --token`).",
    token: "API token", connect: "Connect", started: "Task started", failed: "Failed",
    language: "Language", passed: "passed", not_run: "not run",
    notifications: "Notifications", push_enable: "Notify me on this device", push_disable: "Turn off here",
    push_test: "Send a test", push_on: "Notifications are on for this device.", push_denied: "Notifications are blocked in this browser's settings.",
    push_missing: "Push needs pywebpush on the computer running Dia: pip install 'dia[push]'.",
    push_https: "Notifications need the app opened over HTTPS (e.g. tailscale serve, see docs/MOBILE.md) or on this computer.",
    devices: "Devices", device_name: "Device name, e.g. phone", pair: "Pair",
    revoke: "Revoke", never: "never used",
    remote_off: "Remote access is off: set [ui] remote = true (see docs/MOBILE.md), then restart Dia.",
    pair_scan: "Scan this with the phone's camera, or open the link on it:",
    pair_no_url: "Set [ui] public_url to get a link and a QR code. The device's token:",
    pair_once: "Shown only now. Anyone with this link can use Dia: revoke the device if it leaks.",
    device_note: "Connected as the paired device “{name}”. The configuration and devices can be changed only on the computer running Dia.",
    col_done: "Done", col_failed: "Failed",
    memory_search: "Search your notes…", search: "Search", results: "Results", no_results: "Nothing found.",
    notes_profile: "About you", notes_project: "Projects", notes_journal: "Journal", notes_other: "Other notes",
    pick_note: "Pick a note to read or edit it.", memory_off_help: "Memory is off. Add [memory] with your vault to the config (docs/ASSISTANT.md).",
    memory_edit_help: "Agents read these notes before working. Remove a learned fact by deleting its line.",
    screen_on: "Sees the screen", screen_off: "Screen: off", screen_looking: "Dia is looking at the screen",
    screen_help: "Screen awareness: Dia may take a screenshot when you ask about the screen. Click to switch.",
    quiet_on: "Quiet mode", quiet_off: "Speaking", quiet_help: "Quiet mode: Dia answers in text only (say “quiet mode” / “you can talk”)",
    integrations_tab: "Integrations", f_mail_host: "Mail: IMAP server (e.g. imap.gmail.com)", f_mail_user: "Mail: user",
    f_home_url: "Home Assistant address", f_security_hosts: "Your hosts Dia may scan", f_screen_agent: "Agent that looks at the screen",
    f_itch: "itch.io target (you/game)", f_presets: "Build presets (default: all)",
    f_cpu_temp: "Alert: CPU temperature (°C)", f_disk_used: "Alert: disk full (%)", f_battery_low: "Alert: battery low (%)",
    f_check_urls: "Alert when these addresses stop answering",
    integrations_help: "Passwords and tokens go to Secrets: DIA_CALENDAR_URL (your calendar's iCal address), DIA_MAIL_PASSWORD (for Gmail an app password), HA_TOKEN, BUTLER_API_KEY.",
    council_answers: "The council's answers", proposals: "Dia proposes", apply: "Apply",
    proposal_text: "Make {agent} the default agent of {project} (now {current})", agent_skill: "How agents do",
    review_ok: "Approved at first review", quality: "Quality",
    goals: "Goals", goal_new: "A goal over weeks, e.g. Starfall to Early Access", goal_weeks: "weeks", goal_create: "Set the goal", goal_review: "Review now", goal_approve: "Approve: next mission",
    goal_next: "Next mission", blockers: "Blockers", simulation: "Before it runs", sim_files: "Likely files", sim_cost: "Expected", sim_risks: "Risks", sim_waits: "Waits for you",
    work: "Work", work_start: "Start", work_stop: "Finish for today", work_note: "a note for next time", suggestions: "Dia suggests", accept: "Do it", dismiss: "Not needed",
    agents_models_hint: "agents, e.g. claude:opus, codex", auto: "auto", cli: "CLI sessions", cli_sessions_help: "Every Claude Code, Codex and Cursor Agent running on this computer, also those you started yourself in a terminal. Pick one to read its conversation.", cli_no_transcript: "No conversation file found for this session.", cli_empty: "Nothing said yet.", cli_capture: "Take over", cli_capture_help: "Take this session over: it quits in its terminal and continues here. Resume it in a terminal later with the command shown on Release.", cli_capture_confirm: "End this session in its terminal and continue the conversation here? Its history stays; you can resume it in a terminal later.", cli_captured: "Taken over", cli_release: "Release", cli_released: "Released; in a terminal", cli_in_app: "in Dia", cli_reply: "Reply in this conversation…", cli_from_dia: "from Dia", cli_external: "outside Dia", cli_none: "No agent is running.", model_label: "model",
    health: "Dia's own health", restarting: "restarting",
    violations: "Architecture rules broken", verification: "Assumptions checked", check_held: "held", failed_check: "FAILED",
    blocked: "Merging is blocked by the quality guards", override_prompt: "Merge anyway? Say why it is fine (kept in the decision log):", overridden: "Overridden",
    hypotheses: "Hypotheses (settled by tests)", fix_bug: "Fix the confirmed cause", debug: "Find a bug's cause",
    debug_help: "Agents look at it from the logs, the code and the history; each likely cause is checked by a test, not by vote.",
    debug_placeholder: "e.g. after a dash the player sometimes goes through walls", debug_start: "Find the cause", debug_started: "Agents are on it; the result will appear in Tasks.",
    debt: "Technical debt", debt_fix: "Fix item", debt_fixing: "Paying it off as a task.",
    reason_prompt: "Why? (optional: kept in the decision log, so \"why did we…\" finds it)",
    decisions: "Decisions", why_placeholder: "e.g. why did we drop ECS?", why_ask: "Why?",
    profile: "Your working style", profile_help: "Learnt from what you merge, reject and fix after agents. Agents get it with every task. Edit it freely.",
    profile_update: "Propose an update", profile_accept: "Use the proposal", profile_proposed: "Proposed update", profile_empty: "No profile yet.",
    impact: "What could break?", impact_placeholder: "a file or name, e.g. dash", check_notes: "Check notes against code", check_started: "Checking; the result will appear in Tasks.",
    experiment: "Experiment", experiment_help: "The same change several ways (one per agent, or one per approach below), each tested and measured with the project's benchmark. Nothing is merged: you pick the variant.",
    experiment_question: "e.g. rewrite the inventory as ECS: is it faster?", experiment_approaches: "Approaches, one per line (empty: one variant per agent)",
    experiment_start: "Run the experiment", experiment_started: "Experiment started; the comparison will appear in Tasks.",
    benchmarks: "Benchmark", no_benchmarks: "No results yet: dia bench PROJECT",
    scorecard: "Dia's scorecard (per week)", sc_week: "Week", sc_rolled_back: "Rolled back", sc_rescue: "Retry rescue",
    sc_rounds: "Review rounds", sc_minutes: "min/task", sc_regressions: "Regressions", col_discarded: "Discarded",
    publish_itch: "Publish on itch.io", publish_itch_confirm: "Upload this build to itch.io now (butler push)?",
    rollback: "Roll back", rollback_confirm: "Prepare a revert of this merged task? It becomes a new task; merging that one undoes this.", reverted_by: "Rolled back by", reverts: "Reverts",
    f_routing_auto: "Pick the agent with the best record on the project", f_task_minutes: "Agent minutes per task (0: no limit)",
    f_task_calls: "Agent calls per task (0: no limit)", f_agent_timeout: "Seconds per agent call (0: the agent's own)", f_nice: "CPU priority of agents and tests (0 normal, 19 lowest)",
    incidents: "Security incidents", sandbox: "Agent sandbox", sandbox_on: "on: agents see only their worktree", sandbox_off: "OFF", sandbox_unavailable: "unavailable: install bubblewrap",
    f_sandbox: "Agent sandbox (bubblewrap)", f_sandbox_decoys: "Decoy secrets (stop agents that go looking)", f_lab_engine: "Lab container engine",
    analyze: "Analyse", balance: "Balance", routed: "Chosen because", tidy: "Tidy Downloads", tidy_help: "Dia shows what would move where; nothing moves until you approve. Never deletes; can be undone.",
    tidy_preview: "Preview", tidy_apply: "Move them", tidy_undo: "Undo the last tidying", tidy_done: "Moved {n} files",
    research: "Research", research_help: "An agent with web access writes a report with sources (takes minutes). It appears in Tasks and, with memory on, in Memory → Research.",
    research_topic: "e.g. how do roguelikes do 4-player co-op networking?", research_start: "Research it", research_started: "Researching; the report will appear in Tasks.",
    quiet_hours_on: "Quiet hours", f_quiet_hours: "Quiet hours (e.g. 22:00-07:30)", f_budget: "Push notifications a day (0: no limit)",
    f_app_titlebar: "Dia's own title bar (instead of the system's; after reopening)", f_app_tray: "Icon in the tray", f_app_minimize: "Minimize to the tray", f_app_close: "The window's X hides it to the tray",
    app_window: "Desktop window", app_window_help: "For Dia's own window (dia app). Quit from the tray icon's menu; Dia keeps running in the background (dia service stop ends it).",
    f_tidy_folders: "Folders Dia may tidy (default: Downloads)", f_research_agent: "Agent for research (needs web access)",
    publish_steam: "Publish on Steam", publish_steam_confirm: "Upload this build to Steam now (steamcmd)? It goes live only on the branch set in [builds.steam].",
    camera_on: "Camera on", camera_off: "Camera: off", camera_help: "Dia takes one photo only when you ask (“what do you see on the camera?”). Off by default.",
    save_howto: "Remember how", howto: "How-to for next time", keep: "Keep", notes_howto: "How-tos",
    scenario_works: "Works", scenario_broken: "Doesn't work", scenario_unknown: "Not checked", retries: "Retries",
    preferences: "Your preferences", preferences_help: "Dia follows these in every answer and every agent gets them. Say “remember that I prefer…”, or add one here.",
    pref_add: "e.g. short answers, no emoji", pref_proposed: "Dia noticed (keep?)", from_config: "from the config", remove: "Remove",
    f_retry_errors: "Retries when an agent fails", f_retry_switch: "…by another agent", f_retry_tests: "Rounds of fixing failed tests",
    f_learn_prefs: "Notice my preferences in conversations", f_networks: "Your networks (devices are looked for)",
    f_camera_device: "Camera device", f_notion_parent: "Notion page for new notes (id)", f_steam_app: "Steam app id",
    f_steam_user: "Steam build account", f_steam_branch: "Steam branch to set live (never the default)",
    f_speaker_unknown: "A voice Dia doesn't know", f_speaker_model: "Speaker model (sherpa-onnx .onnx)",
    build: "Build", build_started: "Build started: tests first, then every export preset. It will appear in Tasks.",
    security: "Security", security_check: "Run a security check", port: "Port", net_address: "Address",
    security_help: "Ports open to the network, firewall, failed logins and vulnerable dependencies of your projects. Read-only.",
    computer: "Computer", disk: "Disk", free: "free", battery: "Battery", process: "Process", user: "User",
    missions: "Missions", mission_goal: "The goal, e.g. “get Nova ready for the closed playtest”",
    budget_calls: "Agent calls", budget_minutes: "Agent minutes", plan_mission: "Plan mission", planning: "Planning…",
    prio_low: "low priority", prio_normal: "normal priority", prio_high: "high priority",
    no_missions: "No missions yet. Give Dia a goal; it plans, delegates, tests and waits for your decision.",
    start_mission: "Start mission", continue_mission: "Continue", cancel_mission: "Start no more steps",
    review_changes: "Review changes", after: "after", mission_log: "Log", activity: "Activity", no_activity: "Nothing yet.",
    stop: "Stop", stop_help: "Emergency stop: end every running agent and start nothing new",
    stop_confirm: "Stop every running agent now? Nothing new starts until you resume.",
    stopped_all: "Everything stopped.", resumed: "Resumed.", halted: "Dia is stopped: no agent runs and nothing new starts.",
    resume_btn: "Resume",
    saved: "Saved.", needs_restart: "applies after restarting Dia", add: "Add", remove: "Remove",
    assistant: "Assistant", voice_brain: "Voice & brain", agents_tab: "Agents", automation: "Automation",
    schedule: "Schedule", secrets: "Secrets", devices_tab: "Devices", look: "Appearance", config_file: "Config file",
    f_name: "Assistant's name", f_user_name: "Call me", f_personality: "Personality",
    p_friendly: "Friendly", p_butler: "Butler (JARVIS-like)", p_concise: "Concise", p_buddy: "Buddy", p_mentor: "Mentor",
    p_custom: "Your own…", p_custom_hint: "Describe the personality, e.g. calm, ironic, speaks like a ship's captain",
    f_weather_place: "Weather: city", f_news_feeds: "News: RSS feeds (one per line)",
    f_stocks: "Markets: symbols (AAPL, CDR.WA, ^GSPC)", f_stocks_source: "Markets: source",
    f_crypto: "Crypto: coins (btc, eth, sol)", f_crypto_currency: "Crypto: currency",
    f_briefing: "Briefing sections (weather, work, news, stocks, crypto)",
    f_parallel: "Tasks at once", f_fallback: "Fallback agents on usage limits", f_limit_wait: "Wait for limits to reset",
    f_max_wait: "Wait at most (hours)", f_auto_review: "Review every task", f_reviewer: "Reviewer",
    f_watch: "Test new commits", f_watch_interval: "…every (seconds)", f_issues: "Import issues labelled for Dia",
    f_issues_label: "Issue label", f_issues_planner: "Plan issues with the planner agent", f_ci_autofix: "Fix failed CI by itself",
    f_push_events: "Push notifications for", f_learn: "Propose facts to remember", f_learn_model: "Model for learning",
    f_memory_search: "Search notes in", f_semantic: "Semantic search: embedding model (e.g. nomic-embed-text)",
    f_tts: "Voice engine", f_voice_id: "ElevenLabs voice ID", f_eleven_model: "ElevenLabs model",
    f_stability: "Stability (0–1)", f_similarity: "Similarity (0–1)", f_tts_fallback: "When ElevenLabs is unavailable",
    f_piper_voice: "Piper voice", f_wake: "Wake word model",
    f_local_brain: "Local brain (Ollama)", f_ollama_model: "Ollama model",
    local_brain_help: "Understands your requests on this computer, free and private; Claude stays as the fallback. Install: sudo pacman -S ollama; ollama pull qwen2.5:3b",
    voice_off: "Voice is not configured: add [channels.voice] in the config file (docs/VOICE.md).",
    not_set: "not set", secrets_help: "Kept in ~/.config/dia/env (mode 600). Values can't be read back here. Restart Dia after a change.",
    when: "When", sched_what: "What", next_run: "Next", run_now: "Run now", pause: "Pause", resume: "Resume",
    from_config: "config file", no_schedules: "Nothing scheduled yet.", schedule_what: "What to ask Dia, e.g. briefing",
    cron_help: "When: minute hour day month weekday, e.g. 30 7 * * 1-5 = weekdays 7:30. You can also just tell Dia: “every morning at 7 give me the weather”.",
    overlay_note: "Settings made in the forms are kept separately and override this file:",
    usage: "Usage", calls: "Agent calls", agent_time: "Agent time", success: "Succeeded",
    limits_hit: "Limits hit", calls_per_agent: "Calls per agent", calls_per_day: "Calls per day",
    last_days: "{days} days", no_usage: "No agent calls in this period yet.",
    fix_build: "Fix", learn: "Worth remembering", remember: "Remember", forget: "Skip",
    tools: "Tools", tools_help: "Dia's commands with their output: what has no button of its own. Type any of them below (e.g. doctor, bench nova, lab nova \"godot --version\", why \"ECS\").",
    tool_doctor: "Check everything (doctor)", tool_doctor_fix: "Repair (doctor --fix)", tool_sandbox: "Check the sandbox",
    tool_limits: "Usage limits", tool_issues: "Import issues now", tool_agents: "Agent plugins", tool_redteam: "Red-team test",
    redteam_confirm: "The red-team test gives each agent one hostile task in a throwaway repository (one agent call each). Run it?",
    tool_run: "Run", tool_running: "Running {name}…", tool_done: "Done.", tool_failed: "It failed (no output).",
    tool_placeholder: "doctor --fix", skills: "Skills", skill_run: "Run",
    held_notes: "Held during quiet hours", bench_now: "Measure now", launch: "Launch", check_now: "Test now",
    lab: "In a lab", lab_placeholder: "a command in a throwaway container, e.g. godot --version",
    f_skills: "Skills on offer (empty: all)", f_history_turns: "Conversation memory (exchanges)", f_history_minutes: "... for how long (minutes)",
    f_one_conversation: "One conversation across devices", f_owner_ids: "Your ids on other channels (e.g. Discord user id)", f_log_intents: "Log requests (to compare brains)",
    f_cooldown: "Rest after a usage limit (minutes)", f_planner: "Planner agent", f_plan_steps: "Most steps in a plan", f_fix_rounds: "Review fix rounds",
    f_mission_planner: "Mission planner", f_mission_steps: "Most steps in a mission", f_mission_calls: "Mission budget: agent calls", f_mission_minutes: "Mission budget: minutes",
    f_mission_tests: "Test after every mission step", f_council_members: "AI council members", f_council_moderator: "Council moderator",
    f_experiment_agents: "Experiment agents", f_experiment_variants: "Most variants in an experiment", f_debug_agents: "Debugging swarm agents", f_debug_checks: "Most hypotheses checked",
    f_profile_agent: "Agent that drafts your profile", f_contradictions_agent: "Agent that checks notes against code",
    f_watch_projects: "Watched projects (empty: all)", f_watch_branch: "Watched branch", f_issues_interval: "How often to look for issues (s)",
    f_ci_watch: "Watch CI of published tasks", f_ci_interval: "CI check every (s)", f_ci_fix_rounds: "CI fix rounds", f_ci_comments: "Watch review comments",
    f_ci_autofix_comments: "Address review comments automatically", f_goal_days: "Goal review every (days)", f_suggest_per_day: "Suggestions a day, at most",
    f_suggest_repeat: "Repeat a suggestion after (days)", f_verify_lines: "Verification for changes from (lines)", f_verify_always: "Always verify assumptions",
    f_debt_function: "Debt: long function (lines)", f_debt_nesting: "Debt: deep nesting", f_debt_file: "Debt: long file (lines)", f_push_subject: "Push contact (mailto:...)",
    f_sandbox_read: "Extra read-only paths in the sandbox", f_memory_type: "Memory type", f_vault: "Vault / notes folder", f_memory_folder: "Dia's folder in it",
    f_projects_dir: "Project notes folder", f_journal_dir: "Journal folder", f_profile_note: "Note about you", f_context_chars: "Most characters of context",
    f_memory_exclude: "Never read (patterns)", f_search_results: "Notes found per search", f_learn_agent: "Agent that proposes facts",
    f_ui_port: "Port", f_ui_remote: "Reachable from other devices", f_public_url: "Public address (e.g. Tailscale)", f_ui_hosts: "Allowed host names",
    f_discord_users: "Discord users allowed (ids)", f_discord_guild: "Server (guild) id", f_discord_notify: "Channel for notifications (id)",
    f_voice_language: "Speech language", f_stt_model: "Whisper model (tiny, base, small, medium)",
    f_project_path: "Path", f_base_branch: "Base branch", f_test_command: "Test command", f_benchmark: "Benchmark command", f_forge: "Publish to",
    f_note: "Memory note", f_toolchain: "Toolchain", f_agent_type: "Type", f_model: "Model", f_role: "Role (for the planner)", f_command: "Command",
    projects_tab: "Projects", memory_tab: "Memory", your_agents: "Your agents", entity_name: "name",
    entity_invalid: "A name (letters, digits, - _) and the first field, please.", entity_remove_confirm: "Remove {name} from the settings?",
    projects_help: "Git repositories Dia works on. Changes apply at once; one defined in the config file stays there (edit it in Config file).",
    memory_help: "Markdown or Obsidian notes Dia reads and writes. dia memory index builds the semantic index.",
    remote_access: "Access from other devices", brain_test: "Test", brain_replay: "Replay the last 50",
    brain_test_help: "What each brain makes of a message and how long it takes, or how often a brain agrees with your last real requests. Nothing is executed.",
    brain_test_placeholder: "e.g. jaka jutro pogoda w Gdańsku?",
    desktop_integration: "On this computer", shortcuts: "Shortcuts", in_menu: "in the menu", not_in_menu: "not in the menu", on_desktop: "on the desktop",
    at_login: "starts at login", add_shortcuts: "Add to the menu and desktop", refresh_shortcuts: "Refresh shortcuts", autostart: "Start at login",
    no_autostart: "Don't start at login", service: "Background service (systemd)", installed: "installed", not_installed: "not installed",
    install: "Install", update: "Update", kde_widget: "KDE panel widget",
    service_remove_confirm: "Remove the service? If Dia runs as this service, it stops now; start it again with dia app.",
    desktop_help: "The same as dia shortcut install, dia service install and dia plasmoid install.",
    full_access: "full access", full_access_help: "This phone may also change settings and run Dia's tools; never secrets or pairing.",
    full_access_confirm: "Give this phone full access? It can then change Dia's settings and run its tools (not secrets or pairing). Only for your own phone.",
    win_minimize: "Minimize", win_maximize: "Maximize", win_restore: "Restore", win_close: "Close",
    clear_limit: "Forget the limit", scenario: "Does it work?", council: "AI council",
    scenario_help: "An agent writes a test for this behaviour and Dia runs it", council_help: "Several agents answer, a moderator weighs them",
    council_started: "The council is meeting; the answer shows up as a task.",
    limited: "limit", limited_until: "Usage limit until {time}", waiting_until: "Waiting for a usage limit until {time}",
  },
  pl: {
    tasks: "Zadania", chat: "Czat", status: "Status", settings: "Ustawienia",
    connected: "Połączono", offline: "Łączenie…", change_server: "Zmień serwer",
    voice_idle: "Mów do Dia", voice_listening: "Słucham… kliknij, by zakończyć",
    voice_processing: "Myślę…", voice_speaking: "Mówię…",
    new_task: "Nowe zadanie", project: "Projekt", agent: "Agent", default_agent: "Domyślny agent",
    edit: "Edycja", read_only: "Tylko odczyt", review: "Recenzja", run: "Uruchom", plan: "Plan",
    pipeline: "Potok", planner: "Planista", what: "Co trzeba zrobić?",
    all_projects: "Wszystkie projekty", all_statuses: "Wszystkie statusy",
    no_tasks: "Nie ma jeszcze zadań.", pick_task: "Wybierz zadanie, aby zobaczyć szczegóły.",
    prompt: "Polecenie", summary: "Podsumowanie", steps: "Kroki", reviews: "Recenzje",
    tests: "Testy", changes: "Zmiany", ci: "CI", comments: "Uwagi z recenzji",
    plan_steps: "Plan", show_diff: "Pokaż zmiany", show_log: "Pełny log testów", hide: "Ukryj",
    merge: "Scal", publish: "PR / MR", discard: "Odrzuć", fix_ci: "Napraw CI",
    address: "Uwzględnij uwagi", run_plan: "Uruchom plan", open_pr: "Otwórz PR/MR",
    branch: "Gałąź", created: "Utworzono", mode: "Tryb",
    chat_hint: "Zapytaj albo zleć cokolwiek: „jak działa zapis gry w nova?”, „status”…",
    send: "Wyślij", yes: "tak", no: "nie", open_task: "Otwórz zadanie",
    version: "Wersja", sessions: "Rozmowy", talk_to: "Rozmowa z", model: "Model", default_model: "domyślny",
    provider_help: "Dia wykonuje zadania i umiejętności; model odpowiada wprost (taniej przy zwykłych pytaniach).", new_session: "Nowa rozmowa", main_session: "Główna rozmowa", main_session_help: "Wspólna z głosem, telefonem i Discordem",
    untitled: "Nowa rozmowa", rename: "Zmień nazwę", rename_prompt: "Nazwa tej rozmowy:", delete_session: "Usuń",
    delete_session_confirm: "Usunąć tę rozmowę razem z historią?", clear_main_confirm: "Wyczyścić historię głównej rozmowy?",
    agents: "Agenci", projects: "Projekty", brains: "Łańcuch mózgów", memory: "Pamięć",
    channels: "Kanały", off: "wyłączona", refresh: "Odśwież", theme: "Motyw",
    custom_themes: "Twoje motywy", themes_help: "Skopiuj wbudowany motyw do tego folderu, zmień kolory i odśwież:",
    config: "Konfiguracja", save: "Zapisz", saved_restart: "Zapisano. Uruchom Dia ponownie, aby zastosować (dia service restart albo restart dia serve).",
    login_title: "Połącz z Dia", login_help: "Otwórz interfejs przez `dia app` albo `dia ui` lub wklej token API (`dia ui --token`).",
    token: "Token API", connect: "Połącz", started: "Zadanie uruchomione", failed: "Błąd",
    language: "Język", passed: "przeszły", not_run: "nie uruchomione",
    notifications: "Powiadomienia", push_enable: "Powiadamiaj na tym urządzeniu", push_disable: "Wyłącz tutaj",
    push_test: "Wyślij test", push_on: "Powiadomienia na tym urządzeniu są włączone.", push_denied: "Powiadomienia są zablokowane w ustawieniach przeglądarki.",
    push_missing: "Powiadomienia wymagają pywebpush na komputerze z Dia: pip install 'dia[push]'.",
    push_https: "Powiadomienia działają, gdy aplikacja jest otwarta przez HTTPS (np. tailscale serve, zob. docs/MOBILE.md) albo na tym komputerze.",
    devices: "Urządzenia", device_name: "Nazwa urządzenia, np. telefon", pair: "Sparuj",
    revoke: "Odbierz dostęp", never: "jeszcze nieużywane",
    remote_off: "Dostęp zdalny jest wyłączony: ustaw [ui] remote = true (zob. docs/MOBILE.md) i uruchom Dia ponownie.",
    pair_scan: "Zeskanuj aparatem telefonu albo otwórz na nim ten link:",
    pair_no_url: "Ustaw [ui] public_url, aby dostać link i kod QR. Token urządzenia:",
    pair_once: "Widoczne tylko teraz. Każdy z tym linkiem może używać Dia: jeśli wycieknie, odbierz urządzeniu dostęp.",
    device_note: "Połączono jako sparowane urządzenie „{name}”. Konfigurację i urządzenia można zmieniać tylko na komputerze, na którym działa Dia.",
    col_done: "Gotowe", col_failed: "Nieudane",
    memory_search: "Szukaj w notatkach…", search: "Szukaj", results: "Wyniki", no_results: "Nic nie znaleziono.",
    notes_profile: "O Tobie", notes_project: "Projekty", notes_journal: "Dziennik", notes_other: "Inne notatki",
    pick_note: "Wybierz notatkę, aby ją przeczytać albo poprawić.", memory_off_help: "Pamięć jest wyłączona. Dodaj [memory] ze ścieżką do vaulta w konfiguracji (docs/ASSISTANT.md).",
    memory_edit_help: "Agenci czytają te notatki przed pracą. Wyuczony fakt usuniesz, kasując jego linię.",
    screen_on: "Widzi ekran", screen_off: "Ekran: wyłączony", screen_looking: "Dia patrzy na ekran",
    screen_help: "Świadomość ekranu: Dia może zrobić zrzut, gdy pytasz o ekran. Kliknij, aby przełączyć.",
    quiet_on: "Tryb cichy", quiet_off: "Mówi na głos", quiet_help: "Tryb cichy: Dia odpowiada tylko tekstem (powiedz „tryb cichy” / „możesz mówić”)",
    integrations_tab: "Integracje", f_mail_host: "Poczta: serwer IMAP (np. imap.gmail.com)", f_mail_user: "Poczta: użytkownik",
    f_home_url: "Adres Home Assistanta", f_security_hosts: "Twoje hosty, które Dia może skanować", f_screen_agent: "Agent, który patrzy na ekran",
    f_itch: "Cel na itch.io (ty/gra)", f_presets: "Presety buildów (domyślnie wszystkie)",
    f_cpu_temp: "Alert: temperatura CPU (°C)", f_disk_used: "Alert: pełny dysk (%)", f_battery_low: "Alert: słaba bateria (%)",
    f_check_urls: "Alert, gdy te adresy przestaną odpowiadać",
    integrations_help: "Hasła i tokeny wpisz w Sekretach: DIA_CALENDAR_URL (adres iCal kalendarza), DIA_MAIL_PASSWORD (dla Gmaila hasło aplikacji), HA_TOKEN, BUTLER_API_KEY.",
    council_answers: "Odpowiedzi rady", proposals: "Dia proponuje", apply: "Zastosuj",
    proposal_text: "Ustaw {agent} jako domyślnego agenta {project} (teraz {current})", agent_skill: "Skuteczność agentów",
    review_ok: "Zatwierdzone w 1. recenzji", quality: "Jakość",
    goals: "Cele", goal_new: "Cel na tygodnie, np. Starfall do Early Access", goal_weeks: "tygodnie", goal_create: "Ustal cel", goal_review: "Przegląd teraz", goal_approve: "Zatwierdź: następna misja",
    goal_next: "Następna misja", blockers: "Blokery", simulation: "Zanim ruszy", sim_files: "Prawdopodobne pliki", sim_cost: "Szacunek", sim_risks: "Ryzyka", sim_waits: "Czeka na Ciebie",
    work: "Praca", work_start: "Zaczynam", work_stop: "Kończę na dziś", work_note: "notatka na następny raz", suggestions: "Dia podpowiada", accept: "Zrób to", dismiss: "Niepotrzebne",
    agents_models_hint: "agenci, np. claude:opus, codex", auto: "auto", cli: "Sesje CLI", cli_sessions_help: "Każdy działający Claude Code, Codex i Cursor Agent na tym komputerze, także uruchomiony ręcznie w terminalu. Wybierz sesję, by przeczytać jej rozmowę.", cli_no_transcript: "Nie znaleziono pliku rozmowy tej sesji.", cli_empty: "Jeszcze nic nie padło.", cli_capture: "Przejmij", cli_capture_help: "Przejmij tę sesję: zamknie się w terminalu i będzie trwać tutaj. Później wznowisz ją w terminalu poleceniem pokazanym przy Zwolnij.", cli_capture_confirm: "Zakończyć tę sesję w terminalu i prowadzić rozmowę tutaj? Historia zostaje; później możesz wznowić ją w terminalu.", cli_captured: "Przejęta", cli_release: "Zwolnij", cli_released: "Zwolniona; w terminalu", cli_in_app: "w Dia", cli_reply: "Odpowiedz w tej rozmowie…", cli_from_dia: "z Dia", cli_external: "spoza Dia", cli_none: "Żaden agent nie działa.", model_label: "model",
    health: "Stan samej Dia", restarting: "restartuje się",
    violations: "Złamane reguły architektury", verification: "Sprawdzone założenia", check_held: "się zgadza", failed_check: "NIE ZGADZA SIĘ",
    blocked: "Scalanie blokują strażnicy jakości", override_prompt: "Scalić mimo to? Napisz, dlaczego to w porządku (trafi do dziennika decyzji):", overridden: "Nadpisane",
    hypotheses: "Hipotezy (rozstrzygane testami)", fix_bug: "Napraw potwierdzoną przyczynę", debug: "Znajdź przyczynę błędu",
    debug_help: "Agenci patrzą na błąd od strony logów, kodu i historii; każda prawdopodobna przyczyna jest sprawdzana testem, nie głosowaniem.",
    debug_placeholder: "np. po dashu postać czasem przelatuje przez ścianę", debug_start: "Szukaj przyczyny", debug_started: "Agenci szukają; wynik pojawi się w Zadaniach.",
    debt: "Dług techniczny", debt_fix: "Napraw pozycję", debt_fixing: "Spłacam jako zadanie.",
    reason_prompt: "Dlaczego? (opcjonalnie: trafi do dziennika decyzji, żeby „dlaczego…” to znalazło)",
    decisions: "Decyzje", why_placeholder: "np. dlaczego zrezygnowaliśmy z ECS?", why_ask: "Dlaczego?",
    profile: "Twój styl pracy", profile_help: "Wyuczony z tego, co scalasz, odrzucasz i poprawiasz po agentach. Agenci dostają go przy każdym zadaniu. Możesz go dowolnie edytować.",
    profile_update: "Zaproponuj aktualizację", profile_accept: "Użyj propozycji", profile_proposed: "Proponowana aktualizacja", profile_empty: "Brak profilu.",
    impact: "Co się może zepsuć?", impact_placeholder: "plik albo nazwa, np. dash", check_notes: "Sprawdź notatki z kodem", check_started: "Sprawdzam; wynik pojawi się w Zadaniach.",
    experiment: "Eksperyment", experiment_help: "Ta sama zmiana na kilka sposobów (po jednej na agenta albo na każde podejście poniżej), każda przetestowana i zmierzona benchmarkiem projektu. Nic nie jest scalane: wariant wybierasz Ty.",
    experiment_question: "np. przepisz ekwipunek na ECS: czy będzie szybciej?", experiment_approaches: "Podejścia, po jednym w linii (puste: wariant na agenta)",
    experiment_start: "Uruchom eksperyment", experiment_started: "Eksperyment ruszył; porównanie pojawi się w Zadaniach.",
    benchmarks: "Benchmark", no_benchmarks: "Brak wyników: dia bench PROJEKT",
    scorecard: "Wyniki Dia (tygodniowo)", sc_week: "Tydzień", sc_rolled_back: "Cofnięte", sc_rescue: "Uratowane ponowieniem",
    sc_rounds: "Rundy recenzji", sc_minutes: "min/zadanie", sc_regressions: "Regresje", col_discarded: "Odrzucone",
    publish_itch: "Opublikuj na itch.io", publish_itch_confirm: "Wysłać teraz ten build na itch.io (butler push)?",
    rollback: "Cofnij", rollback_confirm: "Przygotować cofnięcie tego scalonego zadania? Powstanie nowe zadanie; jego scalenie cofa to.", reverted_by: "Cofnięte przez", reverts: "Cofa",
    f_routing_auto: "Wybieraj agenta z najlepszym wynikiem w projekcie", f_task_minutes: "Minuty agentów na zadanie (0: bez limitu)",
    f_task_calls: "Wywołania agentów na zadanie (0: bez limitu)", f_agent_timeout: "Sekundy na jedno wywołanie (0: ustawienie agenta)", f_nice: "Priorytet CPU agentów i testów (0 normalny, 19 najniższy)",
    incidents: "Incydenty bezpieczeństwa", sandbox: "Piaskownica agentów", sandbox_on: "włączona: agenci widzą tylko swój worktree", sandbox_off: "WYŁĄCZONA", sandbox_unavailable: "niedostępna: zainstaluj bubblewrap",
    f_sandbox: "Piaskownica agentów (bubblewrap)", f_sandbox_decoys: "Fałszywe sekrety (zatrzymują agentów, którzy ich szukają)", f_lab_engine: "Silnik kontenerów laboratorium",
    analyze: "Analizuj", balance: "Balans", routed: "Wybrany, bo", tidy: "Porządki w Pobranych", tidy_help: "Dia pokazuje, co gdzie przeniesie; nic się nie rusza bez Twojej zgody. Nic nie usuwa, da się cofnąć.",
    tidy_preview: "Podgląd", tidy_apply: "Przenieś", tidy_undo: "Cofnij ostatnie porządki", tidy_done: "Przeniesione: {n}",
    research: "Research", research_help: "Agent z dostępem do internetu pisze raport ze źródłami (to trwa kilka minut). Pojawi się w Zadaniach, a z pamięcią także w Pamięć → Research.",
    research_topic: "np. jak gry roguelike robią sieć dla co-opa na 4 graczy?", research_start: "Zbadaj", research_started: "Szukam; raport pojawi się w Zadaniach.",
    quiet_hours_on: "Ciche godziny", f_quiet_hours: "Ciche godziny (np. 22:00-07:30)", f_budget: "Powiadomień push dziennie (0: bez limitu)",
    f_app_titlebar: "Własny pasek tytułu Dia (zamiast systemowego; po ponownym otwarciu)", f_app_tray: "Ikona w zasobniku (tray)", f_app_minimize: "Minimalizuj do zasobnika", f_app_close: "X okna chowa je do zasobnika",
    app_window: "Okno aplikacji", app_window_help: "Dotyczy okna Dia (dia app). Zakończysz je z menu ikony w zasobniku; Dia działa dalej w tle (dia service stop ją zatrzymuje).",
    f_tidy_folders: "Foldery, które Dia może porządkować (domyślnie Pobrane)", f_research_agent: "Agent do researchu (potrzebuje internetu)",
    publish_steam: "Opublikuj na Steam", publish_steam_confirm: "Wysłać teraz ten build na Steam (steamcmd)? Na żywo trafi tylko na gałąź z [builds.steam].",
    camera_on: "Kamera włączona", camera_off: "Kamera: wyłączona", camera_help: "Dia robi jedno zdjęcie tylko na Twoją prośbę („co widzisz w kamerze?”). Domyślnie wyłączona.",
    save_howto: "Zapamiętaj sposób", howto: "Sposób na następny raz", keep: "Zachowaj", notes_howto: "Sposoby (how-to)",
    scenario_works: "Działa", scenario_broken: "Nie działa", scenario_unknown: "Nie sprawdzono", retries: "Ponowienia",
    preferences: "Twoje preferencje", preferences_help: "Dia stosuje je w każdej odpowiedzi, dostaje je też każdy agent. Powiedz „zapamiętaj, że wolę…” albo dodaj tutaj.",
    pref_add: "np. krótkie odpowiedzi, bez emoji", pref_proposed: "Dia zauważyła (zachować?)", from_config: "z konfiguracji", remove: "Usuń",
    f_retry_errors: "Ponowienia, gdy agent zawiedzie", f_retry_switch: "…przez innego agenta", f_retry_tests: "Rundy poprawiania testów",
    f_learn_prefs: "Zauważaj moje preferencje w rozmowach", f_networks: "Twoje sieci (Dia szuka w nich urządzeń)",
    f_camera_device: "Urządzenie kamery", f_notion_parent: "Strona Notion na nowe notatki (id)", f_steam_app: "Id aplikacji Steam",
    f_steam_user: "Konto Steam do buildów", f_steam_branch: "Gałąź Steam do ustawienia na żywo (nigdy domyślna)",
    f_speaker_unknown: "Głos, którego Dia nie zna", f_speaker_model: "Model rozpoznawania głosu (sherpa-onnx .onnx)",
    build: "Zbuduj", build_started: "Build ruszył: najpierw testy, potem każdy preset eksportu. Pojawi się w Zadaniach.",
    security: "Bezpieczeństwo", security_check: "Sprawdź bezpieczeństwo", port: "Port", net_address: "Adres",
    security_help: "Porty otwarte na sieć, zapora, nieudane logowania i podatne zależności projektów. Tylko odczyt.",
    computer: "Komputer", disk: "Dysk", free: "wolne", battery: "Bateria", process: "Proces", user: "Użytkownik",
    missions: "Misje", mission_goal: "Cel, np. „przygotuj Nova do zamkniętych testów”",
    budget_calls: "Wywołania agentów", budget_minutes: "Minuty agentów", plan_mission: "Zaplanuj misję", planning: "Planuję…",
    prio_low: "niski priorytet", prio_normal: "zwykły priorytet", prio_high: "wysoki priorytet",
    no_missions: "Nie ma jeszcze misji. Daj Dia cel: zaplanuje, rozdzieli, przetestuje i poczeka na Twoją decyzję.",
    start_mission: "Rozpocznij misję", continue_mission: "Kontynuuj", cancel_mission: "Nie zaczynaj kolejnych kroków",
    review_changes: "Przejrzyj zmiany", after: "po", mission_log: "Dziennik", activity: "Aktywność", no_activity: "Na razie nic.",
    stop: "Stop", stop_help: "Awaryjny stop: kończy wszystkich agentów i nie zaczyna niczego nowego",
    stop_confirm: "Zatrzymać teraz wszystkich agentów? Nic nowego nie ruszy, dopóki nie wznowisz.",
    stopped_all: "Wszystko zatrzymane.", resumed: "Wznowiono.", halted: "Dia jest zatrzymana: żaden agent nie pracuje i nic nowego nie rusza.",
    resume_btn: "Wznów",
    saved: "Zapisano.", needs_restart: "zadziała po ponownym uruchomieniu Dia", add: "Dodaj", remove: "Usuń",
    assistant: "Asystent", voice_brain: "Głos i mózg", agents_tab: "Agenci", automation: "Automatyzacje",
    schedule: "Harmonogram", secrets: "Sekrety", devices_tab: "Urządzenia", look: "Wygląd", config_file: "Plik konfiguracji",
    f_name: "Imię asystentki", f_user_name: "Jak się do mnie zwracać", f_personality: "Osobowość",
    p_friendly: "Przyjazna", p_butler: "Lokaj (jak JARVIS)", p_concise: "Zwięzła", p_buddy: "Kumpelka", p_mentor: "Mentorka",
    p_custom: "Własna…", p_custom_hint: "Opisz osobowość, np. spokojna, ironiczna, mówi jak kapitan statku",
    f_weather_place: "Pogoda: miasto", f_news_feeds: "Wiadomości: kanały RSS (jeden w linii)",
    f_stocks: "Giełda: symbole (AAPL, CDR.WA, ^GSPC)", f_stocks_source: "Giełda: źródło",
    f_crypto: "Krypto: monety (btc, eth, sol)", f_crypto_currency: "Krypto: waluta",
    f_briefing: "Sekcje briefingu (weather, work, news, stocks, crypto)",
    f_parallel: "Zadań naraz", f_fallback: "Zastępcy przy wyczerpanym limicie", f_limit_wait: "Czekaj na odnowienie limitu",
    f_max_wait: "Czekaj najwyżej (godzin)", f_auto_review: "Recenzuj każde zadanie", f_reviewer: "Recenzent",
    f_watch: "Testuj nowe commity", f_watch_interval: "…co (sekund)", f_issues: "Importuj issues z etykietą dla Dia",
    f_issues_label: "Etykieta issues", f_issues_planner: "Planuj issues agentem-planistą", f_ci_autofix: "Sama naprawiaj CI",
    f_push_events: "Powiadomienia push o", f_learn: "Proponuj fakty do zapamiętania", f_learn_model: "Model do uczenia się",
    f_memory_search: "Szukaj w notatkach", f_semantic: "Wyszukiwanie semantyczne: model embeddingów (np. nomic-embed-text)",
    f_tts: "Silnik głosu", f_voice_id: "ID głosu ElevenLabs", f_eleven_model: "Model ElevenLabs",
    f_stability: "Stabilność (0–1)", f_similarity: "Podobieństwo (0–1)", f_tts_fallback: "Gdy ElevenLabs nie działa",
    f_piper_voice: "Głos Piper", f_wake: "Model słowa aktywującego",
    f_local_brain: "Lokalny mózg (Ollama)", f_ollama_model: "Model Ollamy",
    local_brain_help: "Rozumie Twoje polecenia na tym komputerze, za darmo i prywatnie; Claude zostaje jako zapas. Instalacja: sudo pacman -S ollama; ollama pull qwen2.5:3b",
    voice_off: "Głos nie jest skonfigurowany: dodaj [channels.voice] w pliku konfiguracji (docs/VOICE.md).",
    not_set: "nie ustawiono", secrets_help: "Trzymane w ~/.config/dia/env (prawa 600). Wartości nie da się tu odczytać. Po zmianie uruchom Dia ponownie.",
    when: "Kiedy", sched_what: "Co", next_run: "Najbliżej", run_now: "Uruchom teraz", pause: "Wstrzymaj", resume: "Wznów",
    from_config: "plik konfiguracji", no_schedules: "Nic jeszcze nie zaplanowano.", schedule_what: "O co poprosić Dia, np. briefing",
    cron_help: "Kiedy: minuta godzina dzień miesiąc dzień-tygodnia, np. 30 7 * * 1-5 = dni robocze 7:30. Możesz też po prostu powiedzieć Dia: „codziennie o 7 mów mi pogodę”.",
    overlay_note: "Ustawienia z formularzy są trzymane osobno i nadpisują ten plik:",
    usage: "Zużycie", calls: "Wywołania agentów", agent_time: "Czas agentów", success: "Udane",
    limits_hit: "Trafione limity", calls_per_agent: "Wywołania na agenta", calls_per_day: "Wywołania dziennie",
    last_days: "{days} dni", no_usage: "W tym okresie nie było jeszcze wywołań agentów.",
    fix_build: "Napraw", learn: "Warto zapamiętać", remember: "Zapamiętaj", forget: "Pomiń",
    tools: "Narzędzia", tools_help: "Polecenia Dia z ich wynikiem: to, co nie ma osobnego przycisku. Wpisz poniżej dowolne (np. doctor, bench nova, lab nova \"godot --version\", why \"ECS\").",
    tool_doctor: "Sprawdź wszystko (doctor)", tool_doctor_fix: "Napraw (doctor --fix)", tool_sandbox: "Sprawdź piaskownicę",
    tool_limits: "Limity użycia", tool_issues: "Pobierz zgłoszenia teraz", tool_agents: "Wtyczki agentów", tool_redteam: "Test red-team",
    redteam_confirm: "Test red-team daje każdemu agentowi jedno wrogie zadanie w jednorazowym repozytorium (po jednym wywołaniu). Uruchomić?",
    tool_run: "Uruchom", tool_running: "Działa {name}…", tool_done: "Gotowe.", tool_failed: "Nie udało się (brak wyniku).",
    tool_placeholder: "doctor --fix", skills: "Umiejętności", skill_run: "Uruchom",
    held_notes: "Wstrzymane w godzinach ciszy", bench_now: "Zmierz teraz", launch: "Uruchom projekt", check_now: "Testuj teraz",
    lab: "W labie", lab_placeholder: "polecenie w jednorazowym kontenerze, np. godot --version",
    f_skills: "Dostępne umiejętności (puste: wszystkie)", f_history_turns: "Pamięć rozmowy (wymiany)", f_history_minutes: "... przez ile minut",
    f_one_conversation: "Jedna rozmowa na wszystkich urządzeniach", f_owner_ids: "Twoje identyfikatory w innych kanałach (np. Discord)", f_log_intents: "Zapisuj prośby (do porównań mózgów)",
    f_cooldown: "Przerwa po limicie (minuty)", f_planner: "Agent-planista", f_plan_steps: "Najwięcej kroków w planie", f_fix_rounds: "Rundy poprawek po recenzji",
    f_mission_planner: "Planista misji", f_mission_steps: "Najwięcej kroków w misji", f_mission_calls: "Budżet misji: wywołania agentów", f_mission_minutes: "Budżet misji: minuty",
    f_mission_tests: "Testy po każdym kroku misji", f_council_members: "Członkowie rady AI", f_council_moderator: "Moderator rady",
    f_experiment_agents: "Agenci eksperymentów", f_experiment_variants: "Najwięcej wariantów w eksperymencie", f_debug_agents: "Agenci roju debugującego", f_debug_checks: "Najwięcej sprawdzanych hipotez",
    f_profile_agent: "Agent, który szkicuje Twój profil", f_contradictions_agent: "Agent, który porównuje notatki z kodem",
    f_watch_projects: "Obserwowane projekty (puste: wszystkie)", f_watch_branch: "Obserwowana gałąź", f_issues_interval: "Jak często szukać zgłoszeń (s)",
    f_ci_watch: "Obserwuj CI opublikowanych zadań", f_ci_interval: "Sprawdzanie CI co (s)", f_ci_fix_rounds: "Rundy poprawek CI", f_ci_comments: "Obserwuj komentarze recenzji",
    f_ci_autofix_comments: "Uwzględniaj komentarze automatycznie", f_goal_days: "Przegląd celów co (dni)", f_suggest_per_day: "Najwięcej podpowiedzi dziennie",
    f_suggest_repeat: "Powtórz podpowiedź po (dniach)", f_verify_lines: "Weryfikacja zmian od (linii)", f_verify_always: "Zawsze weryfikuj założenia",
    f_debt_function: "Dług: długa funkcja (linie)", f_debt_nesting: "Dług: głębokie zagnieżdżenie", f_debt_file: "Dług: długi plik (linie)", f_push_subject: "Kontakt dla push (mailto:...)",
    f_sandbox_read: "Dodatkowe ścieżki tylko do odczytu w piaskownicy", f_memory_type: "Rodzaj pamięci", f_vault: "Vault / folder notatek", f_memory_folder: "Folder Dia w nim",
    f_projects_dir: "Folder notatek projektów", f_journal_dir: "Folder dziennika", f_profile_note: "Notatka o Tobie", f_context_chars: "Najwięcej znaków kontekstu",
    f_memory_exclude: "Nigdy nie czytaj (wzorce)", f_search_results: "Notatek na wyszukiwanie", f_learn_agent: "Agent, który proponuje fakty",
    f_ui_port: "Port", f_ui_remote: "Dostępna z innych urządzeń", f_public_url: "Adres publiczny (np. Tailscale)", f_ui_hosts: "Dozwolone nazwy hostów",
    f_discord_users: "Dozwoleni użytkownicy Discorda (id)", f_discord_guild: "Id serwera", f_discord_notify: "Kanał powiadomień (id)",
    f_voice_language: "Język mowy", f_stt_model: "Model Whisper (tiny, base, small, medium)",
    f_project_path: "Ścieżka", f_base_branch: "Gałąź bazowa", f_test_command: "Polecenie testów", f_benchmark: "Polecenie benchmarku", f_forge: "Publikuj do",
    f_note: "Notatka w pamięci", f_toolchain: "Narzędzia", f_agent_type: "Rodzaj", f_model: "Model", f_role: "Rola (dla planisty)", f_command: "Polecenie",
    projects_tab: "Projekty", memory_tab: "Pamięć", your_agents: "Twoi agenci", entity_name: "nazwa",
    entity_invalid: "Podaj nazwę (litery, cyfry, - _) i pierwsze pole.", entity_remove_confirm: "Usunąć {name} z ustawień?",
    projects_help: "Repozytoria git, na których pracuje Dia. Zmiany działają od razu; projekt z pliku konfiguracji zostaje tam (edytuj go w Pliku konfiguracji).",
    memory_help: "Notatki Markdown lub Obsidian, które Dia czyta i pisze. dia memory index buduje indeks semantyczny.",
    remote_access: "Dostęp z innych urządzeń", brain_test: "Testuj", brain_replay: "Powtórz ostatnie 50",
    brain_test_help: "Co każdy mózg rozumie z wiadomości i ile mu to zajmuje, albo jak często zgadza się z Twoimi ostatnimi prośbami. Nic nie jest wykonywane.",
    brain_test_placeholder: "np. jaka jutro pogoda w Gdańsku?",
    desktop_integration: "Na tym komputerze", shortcuts: "Skróty", in_menu: "w menu", not_in_menu: "brak w menu", on_desktop: "na pulpicie",
    at_login: "start po zalogowaniu", add_shortcuts: "Dodaj do menu i na pulpit", refresh_shortcuts: "Odśwież skróty", autostart: "Uruchamiaj po zalogowaniu",
    no_autostart: "Nie uruchamiaj po zalogowaniu", service: "Usługa w tle (systemd)", installed: "zainstalowana", not_installed: "nie zainstalowana",
    install: "Zainstaluj", update: "Zaktualizuj", kde_widget: "Widget panelu KDE",
    service_remove_confirm: "Usunąć usługę? Jeśli Dia działa jako ta usługa, zatrzyma się teraz; uruchomisz ją znowu przez dia app.",
    desktop_help: "To samo co dia shortcut install, dia service install i dia plasmoid install.",
    full_access: "pełny dostęp", full_access_help: "Ten telefon może też zmieniać ustawienia i używać narzędzi Dia; nigdy sekretów ani parowania.",
    full_access_confirm: "Dać temu telefonowi pełny dostęp? Będzie mógł zmieniać ustawienia Dia i używać jej narzędzi (bez sekretów i parowania). Tylko dla Twojego telefonu.",
    win_minimize: "Minimalizuj", win_maximize: "Maksymalizuj", win_restore: "Przywróć", win_close: "Zamknij",
    clear_limit: "Zapomnij limit", scenario: "Czy działa?", council: "Rada AI",
    scenario_help: "Agent pisze test tego zachowania, a Dia go uruchamia", council_help: "Kilku agentów odpowiada, moderator to waży",
    council_started: "Rada obraduje; odpowiedź pojawi się jako zadanie.",
    limited: "limit", limited_until: "Limit użycia do {time}", waiting_until: "Czeka na odnowienie limitu do {time}",
  },
};
let lang = "en";
const t = (key, vars) => {
  const text = (STRINGS[lang] || STRINGS.en)[key] || STRINGS.en[key] || key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? vars[name] : m)) : text;
};
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// ------------------------------------------------------------------- api ---

const TOKEN_KEY = "dia-token";
// Inside the Android/iOS app (mobile/): its pairing screen, to switch to another Dia.
const IN_APP = navigator.userAgent.includes("DiaApp");
const APP_HOME = /iPhone|iPad|iPod/.test(navigator.userAgent)
  ? "capacitor://localhost/index.html?reset=1" : "https://localhost/index.html?reset=1";
const THEME_KEY = "dia-theme";

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* storage may be unavailable; the UI still works */ }
  return value;
}

// What the address asks for (#token=...&view=chat&task=ID), read before the
// token is wiped from it: the desktop window and its tray open a given tab.
const VIEWS = ["tasks", "missions", "chat", "cli", "memory", "status", "usage", "settings"];
const hashParam = (name) => (location.hash.match(new RegExp(`[#&]${name}=([\\w-]+)`)) || [])[1] || null;
const START_VIEW = VIEWS.includes(hashParam("view")) ? hashParam("view") : null;
const START_TASK = hashParam("task");

function readToken() {
  const match = location.hash.match(/token=([^&]+)/);
  if (match) {
    store(TOKEN_KEY, decodeURIComponent(match[1]));
    history.replaceState(null, "", location.pathname);
  }
  return store(TOKEN_KEY) || "";
}

let token = readToken();

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const type = response.headers.get("Content-Type") || "";
  const data = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error((data && data.error) || data || response.statusText);
  return data;
}

function applyTheme(name) {
  document.getElementById("theme").href = `/themes/${encodeURIComponent(name)}.css`;
  store(THEME_KEY, name);
}

// --------------------------------------------------------------- helpers ---

const STATUS_ORDER = ["running", "waiting", "queued", "planned", "done", "failed", "published", "merged", "discarded"];

function ago(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

const firstLine = (text) => (text || "").split("\n")[0];
const Pill = ({ status, label }) => html`<span class="pill s-${status}">${label || status}</span>`;

// ------------------------------------------------------- highlighting ---
// Prism (vendor/prism.bundle.js) colours code; the colours come from the theme.

const LANGUAGES = {
  gd: "gdscript", gdscript: "gdscript", py: "python", python: "python", cs: "csharp",
  csharp: "csharp", js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
  javascript: "javascript", ts: "typescript", tsx: "typescript", typescript: "typescript",
  rs: "rust", rust: "rust", toml: "toml", json: "json", md: "markdown", markdown: "markdown",
  sh: "bash", bash: "bash", shell: "bash", yml: "yaml", yaml: "yaml", ini: "ini", cfg: "ini",
  godot: "ini", tscn: "ini", tres: "ini", import: "ini", css: "css", html: "markup",
  xml: "markup", svg: "markup", c: "c", h: "c", cpp: "cpp", hpp: "cpp", cc: "cpp",
  java: "java", go: "go",
};

function languageOf(nameOrPath) {
  const key = (nameOrPath || "").toLowerCase().split("/").pop().split(".").pop();
  const lang = LANGUAGES[key];
  return lang && window.Prism?.languages[lang] ? lang : null;
}

// Highlighted HTML for one piece of code; Prism escapes the text itself.
function Code({ code, lang }) {
  if (!lang) return code || " ";
  return html`<span dangerouslySetInnerHTML=${{ __html: window.Prism.highlight(code, window.Prism.languages[lang], lang) }} />`;
}

// Text with ```fenced``` code blocks shown as highlighted code.
function RichText({ text, class: cls = "card prose", style }) {
  const parts = (text || "").split(/```([\w+#.-]*)[^\n]*\n([\s\S]*?)```/g);
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    // `inline code` outside the fenced blocks
    parts[i].split(/`([^`\n]+)`/g).forEach((piece, j) => {
      if (piece) out.push(j % 2 ? html`<code class="inline">${piece}</code>` : piece);
    });
    if (i + 2 < parts.length) {
      out.push(html`<pre class="code mono"><${Code} code=${parts[i + 2].replace(/\n$/, "")} lang=${languageOf(parts[i + 1])} /></pre>`);
    }
  }
  return html`<div class=${cls} style=${style}>${out}</div>`;
}

function Diff({ text }) {
  let lang = null;
  const lines = text.split("\n").map((line, i) => {
    if (line.startsWith("diff --git")) lang = languageOf(line.split(" ").pop());
    const meta = line.startsWith("diff --git") || line.startsWith("+++") || line.startsWith("---")
      || line.startsWith("index ") || line.startsWith("new file") || line.startsWith("deleted file");
    if (meta) return html`<div key=${i} class="file">${line}</div>`;
    if (line.startsWith("@@")) return html`<div key=${i} class="hunk">${line}</div>`;
    const sign = line[0] === "+" || line[0] === "-" || line[0] === " " ? line[0] : "";
    const cls = sign === "+" ? "add" : sign === "-" ? "del" : "";
    return html`<div key=${i} class=${cls}><span class="sign">${sign || " "}</span><${Code} code=${line.slice(sign ? 1 : 0)} lang=${lang} /></div>`;
  });
  return html`<pre class="diff mono">${lines}</pre>`;
}

// ---------------------------------------------------------------- tasks ---

function Composer({ status, onCreated, toast }) {
  const projects = status?.projects || [];
  const [project, setProject] = useState("");
  const [agent, setAgent] = useState("");
  const [model, setModel] = useState("");
  const agentInfo = (status?.agents || []).find((a) => a.name === agent);
  const spec = agent && model ? `${agent}:${model}` : agent;
  const [mode, setMode] = useState("edit");
  const [review, setReview] = useState(false);
  const [pipeline, setPipeline] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const chosen = project || projects[0]?.name || "";

  const submit = async (kind) => {
    if (!text.trim() || !chosen) return;
    setBusy(true);
    try {
      if (kind === "council") {
        await api("/api/council", { method: "POST", body: { question: text, project: chosen } });
        setText(""); toast(t("council_started")); setBusy(false);
        return;
      }
      if (kind === "scenario") {
        const task = await api("/api/scenarios", { method: "POST", body: { project: chosen, scenario: text, agent: spec || undefined } });
        setText(""); onCreated(task); toast(t("started")); setBusy(false);
        return;
      }
      const task = kind === "plan"
        ? await api("/api/plans", { method: "POST", body: { project: chosen, goal: text, pipeline, planner: spec || undefined } })
        : await api("/api/tasks", { method: "POST", body: { project: chosen, prompt: text, agent, mode, review: review || undefined, model: (agent && model) || undefined } });
      setText("");
      onCreated(task);
      toast(t("started"));
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };

  return html`
    <div class="composer">
      <div class="row">
        <select class="select" value=${chosen} onChange=${(e) => setProject(e.target.value)}>
          ${projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}
        </select>
        <select class="select" value=${agent} onChange=${(e) => { setAgent(e.target.value); setModel(""); }}>
          <option value="">${t("default_agent")}</option>
          ${(status?.agents || []).map((a) => html`<option value=${a.name}>${a.name}</option>`)}
        </select>
        ${agentInfo ? html`<input class="input" style="width:130px" list="task-models" placeholder=${`${t("model")}: ${agentInfo.model || t("auto")}`}
            value=${model} onInput=${(e) => setModel(e.target.value)} />
          <datalist id="task-models">${agentInfo.models.map((m) => html`<option value=${m}></option>`)}</datalist>` : null}
        <select class="select" value=${mode} onChange=${(e) => setMode(e.target.value)}>
          <option value="edit">${t("edit")}</option>
          <option value="read-only">${t("read_only")}</option>
        </select>
        <label class="row muted"><input type="checkbox" checked=${review}
          onChange=${(e) => setReview(e.target.checked)} /> ${t("review")}</label>
      </div>
      <textarea class="textarea" placeholder=${t("what")} value=${text}
        onInput=${(e) => setText(e.target.value)}
        onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit("run"); }}></textarea>
      <div class="row">
        <button class="btn primary" disabled=${busy || !text.trim()} onClick=${() => submit("run")}>${t("run")} <span class="faint">Ctrl+↵</span></button>
        <button class="btn" disabled=${busy || !text.trim()} onClick=${() => submit("plan")}>${t("plan")}</button>
        <button class="btn ghost" title=${t("scenario_help")} disabled=${busy || !text.trim()} onClick=${() => submit("scenario")}>${t("scenario")}</button>
        <button class="btn ghost" title=${t("council_help")} disabled=${busy || !text.trim()} onClick=${() => submit("council")}>${t("council")}</button>
        ${status?.pipelines?.length ? html`
          <select class="select" value=${pipeline} onChange=${(e) => setPipeline(e.target.value)}>
            <option value="">${t("planner")}</option>
            ${status.pipelines.map((p) => html`<option value=${p}>${t("pipeline")}: ${p}</option>`)}
          </select>` : null}
      </div>
    </div>`;
}

function TaskDetail({ id, toast, onChanged, onBack }) {
  const [task, setTask] = useState(null);
  const [diff, setDiff] = useState(null);
  const [log, setLog] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api(`/api/tasks/${id}`).then(setTask).catch((e) => toast(e.message, "error")), [id]);
  useEffect(() => { setDiff(null); setLog(null); load(); }, [id]);
  useEffect(() => {
    const onUpdate = (e) => { if (e.detail.id === id) load(); };
    window.addEventListener("dia-task", onUpdate);
    return () => window.removeEventListener("dia-task", onUpdate);
  }, [id]);

  if (!task) return html`<div class="empty">…</div>`;
  const d = task.details || {};
  const act = async (action, body) => {
    setBusy(true);
    try {
      const result = await api(`/api/tasks/${id}/${action}`, { method: "POST", body });
      toast(result.message || result.status || action);
      if (result.url) window.open(result.url, "_blank");
      load(); onChanged();
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const blockers = [
    ...(d.violations || []).map((v) => `${v.rule} (${v.where})`),
    ...((d.verification?.checks || []).filter((c) => c.held === false).map((c) => c.assumption)),
  ];
  const decide = (action) => {
    let override;
    if (action === "merge" && blockers.length && !d.override) {
      override = prompt(t("override_prompt"), "");
      if (!override) return;
    }
    const reason = prompt(t("reason_prompt"), "");
    if (reason !== null) act(action, { reason, override });
  };
  const toggleDiff = async () => {
    if (diff !== null) return setDiff(null);
    try { setDiff(await api(`/api/tasks/${id}/diff`)); } catch (e) { toast(e.message, "error"); }
  };
  const toggleLog = async () => {
    if (log !== null) return setLog(null);
    try { setLog(await api(`/api/tasks/${id}/tests`)); } catch (e) { toast(e.message, "error"); }
  };
  const reviewable = task.commit_sha && ["done", "failed"].includes(task.status);
  const ci = d.ci || {};
  const pending = d.comments_pending || [];
  const tests = task.tests_ok === null ? t("not_run") : task.tests_ok ? t("passed") : "FAILED";

  return html`
    <div class="detail">
      <button class="btn ghost back" onClick=${onBack}>← ${t("tasks")}</button>
      <div class="row"><${Pill} status=${task.status} />${task.status === "waiting" && d.waiting_until
        ? html`<span class="muted">${t("waiting_until", { time: clock(d.waiting_until) })}</span>` : null}
        <span class="faint mono">${task.id}</span></div>
      <h2>${d.scenario ? d.scenario : firstLine(task.prompt)}</h2>
      ${d.scenario_result ? html`<div class="row"><${Pill} status=${d.scenario_result === "works" ? "done" : d.scenario_result === "broken" ? "failed" : "planned"} label=${t(`scenario_${d.scenario_result}`)} /></div>` : null}
      <div class="kv section">
        <span>${t("project")}</span><span>${task.project}</span>
        <span>${t("agent")}</span><span>${task.agent}</span>
        <span>${t("mode")}</span><span>${task.mode}</span>
        ${task.branch ? html`<span>${t("branch")}</span><span class="mono">${task.branch}${task.commit_sha ? ` @ ${task.commit_sha.slice(0, 10)}` : ""}</span>` : null}
        ${task.tests_ok !== null ? html`<span>${t("tests")}</span><span>${tests}</span>` : null}
        ${d.published ? html`<span>${t("ci")}</span><span>${ci.state || "-"} ${d.published.url ? html`· <a href=${d.published.url} target="_blank">${t("open_pr")}</a>` : null}</span>` : null}
        <span>${t("created")}</span><span>${ago(task.created_at)}</span>
        ${d.routed ? html`<span>${t("routed")}</span><span>${d.routed}</span>` : null}
        ${d.reverts ? html`<span>${t("reverts")}</span><span class="mono">${d.reverts}</span>` : null}
        ${d.reverted_by ? html`<span>${t("reverted_by")}</span><span class="mono">${d.reverted_by}</span>` : null}
      </div>

      <div class="row section">
        ${task.status === "planned" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("run-plan")}>${t("run_plan")}</button>` : null}
        ${task.commit_sha && !["merged", "discarded"].includes(task.status) ? html`<button class="btn" onClick=${toggleDiff}>${diff === null ? t("show_diff") : t("hide")}</button>` : null}
        ${reviewable ? html`
          <button class="btn" disabled=${busy} onClick=${() => act("review")}>${t("review")}</button>
          <button class="btn primary" disabled=${busy || task.status !== "done"} onClick=${() => decide("merge")}>${t("merge")}</button>
          <button class="btn" disabled=${busy || task.status !== "done"} onClick=${() => act("publish")}>${t("publish")}</button>
          <button class="btn danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
        ${task.status === "planned" ? html`<button class="btn danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
        ${task.status === "published" && ci.state === "failed" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-ci")}>${t("fix_ci")}</button>` : null}
        ${task.status === "published" && pending.length ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("address-comments")}>${t("address")} (${pending.length})</button>` : null}
        ${task.mode === "build" && task.status === "done" && !d.published?.itch ? html`<button class="btn primary" disabled=${busy} onClick=${() => confirm(t("publish_itch_confirm")) && act("publish-itch")}>${t("publish_itch")}</button>` : null}
        ${task.mode === "build" && task.status === "done" && !d.published?.steam ? html`<button class="btn" disabled=${busy} onClick=${() => confirm(t("publish_steam_confirm")) && act("publish-steam")}>${t("publish_steam")}</button>` : null}
        ${task.status === "merged" && d.merge_commit && !d.reverted_by ? html`<button class="btn danger" disabled=${busy} onClick=${() => confirm(t("rollback_confirm")) && decide("rollback")}>${t("rollback")}</button>` : null}
        ${task.mode === "edit" && ["done", "merged", "published"].includes(task.status) && !d.howto ? html`<button class="btn ghost" disabled=${busy} onClick=${() => act("howto")}>${t("save_howto")}</button>` : null}
        ${task.mode === "check" && task.tests_ok === false && !d.fix_task ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-build")}>${t("fix_build")}</button>` : null}
        ${task.has_test_log ? html`<button class="btn ghost" onClick=${toggleLog}>${log === null ? t("show_log") : t("hide")}</button>` : null}
      </div>
      ${diff !== null ? html`<div class="section"><${Diff} text=${diff} /></div>` : null}
      ${log !== null ? html`<div class="section"><pre class="log mono">${log}</pre></div>` : null}

      <div class="section"><div class="label">${t("prompt")}</div><div class="card prose">${task.prompt}</div></div>
      ${d.plan && task.status === "planned" ? html`
        <div class="section"><div class="label">${t("plan_steps")}</div>
          ${d.plan.map((s, i) => html`<div class="card" style="margin-bottom:8px">
            <div class="row"><strong>${i + 1}. ${s.title || s.agent}</strong><span class="pill">${s.agent}</span></div>
            <${RichText} text=${s.prompt} class="prose muted" style="margin-top:6px" /></div>`)}
        </div>` : null}
      ${d.simulation && task.status === "planned" ? html`<div class="section"><div class="label">${t("simulation")}</div><div class="card">
        ${d.simulation.files.length ? html`<div><span class="faint">${t("sim_files")}:</span> <span class="mono">${d.simulation.files.map((f) => f.file).join(", ")}</span></div>` : null}
        <div><span class="faint">${t("sim_cost")}:</span> ${d.simulation.cost.minutes != null ? `~${d.simulation.cost.minutes} min, ` : ""}${d.simulation.cost.calls}–${d.simulation.cost.calls_worst} calls</div>
        ${d.simulation.risks.map((r) => html`<div style="color:var(--warn)">⚠ ${r}</div>`)}
        <div class="faint">${t("sim_waits")}: ${d.simulation.approvals.join("; ")}</div></div></div>` : null}
      ${task.summary ? html`<div class="section"><div class="label">${t("summary")}</div><${RichText} text=${task.summary} /></div>` : null}
      ${task.error ? html`<div class="section"><div class="label">${t("failed")}</div><div class="card prose" style="color:var(--danger)">${task.error}</div></div>` : null}
      ${d.council ? html`<div class="section"><div class="label">${t("council_answers")}</div>
        ${d.council.map((a) => html`<div class="card" style="margin-bottom:8px">
          <div class="row"><strong>${a.agent}</strong>${a.success ? null : html`<${Pill} status="failed" />`}</div>
          <${RichText} text=${a.answer} class="prose muted" /></div>`)}</div>` : null}
      ${d.howto?.status === "proposed" ? html`<div class="section"><div class="label">${t("howto")}</div>
        <div class="card"><strong>${d.howto.title}</strong> <span class="faint">${d.howto.when}</span>
          <${RichText} text=${d.howto.steps} class="prose muted" style="margin-top:6px" />
          <div class="row" style="margin-top:8px"><button class="btn primary" disabled=${busy} onClick=${() => act("howto-accept")}>${t("keep")}</button></div></div></div>` : null}
      ${blockers.length && !["merged", "discarded"].includes(task.status) ? html`<div class="section"><div class="label" style="color:${d.override ? "var(--muted)" : "var(--warn)"}">${d.override ? `${t("overridden")}: ${d.override}` : `⚠ ${t("blocked")}`}</div></div>` : null}
      ${d.violations?.length ? html`<div class="section"><div class="label">${t("violations")}</div>
        ${d.violations.map((v) => html`<div class="card" style="margin-bottom:8px"><strong>${v.rule}</strong><div class="faint">${v.where} · ${v.by}</div></div>`)}</div>` : null}
      ${d.verification?.checks?.length ? html`<div class="section"><div class="label">${t("verification")}: ${d.verification.held}/${d.verification.total}</div>
        ${d.verification.checks.map((c) => html`<div class="card" style="margin-bottom:8px"><div class="row"><${Pill} status=${c.held ? "done" : "failed"} label=${c.held ? t("check_held") : t("failed_check")} /><span>${c.assumption}</span></div>
          <div class="mono faint" style="margin-top:6px;word-break:break-all">$ ${c.check}</div></div>`)}</div>` : null}
      ${d.hypotheses?.length ? html`<div class="section"><div class="label">${t("hypotheses")}</div>
        ${d.hypotheses.map((h) => html`<div class="card" style="margin-bottom:8px"><div class="row"><${Pill} status=${h.result === "confirmed" ? "failed" : h.result === "ruled out" ? "done" : "planned"} label=${h.result} /><strong>${h.cause}</strong></div>
          <div class="faint">${h.where} · ${h.proposed_by.join(", ")}</div></div>`)}
        ${d.hypotheses.some((h) => h.result === "confirmed") ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-bug")}>${t("fix_bug")}</button>` : null}</div>` : null}
      ${d.incidents?.length ? html`<div class="section"><div class="label" style="color:var(--danger)">⚠ ${t("incidents")}</div>
        ${d.incidents.map((i) => html`<div class="card" style="margin-bottom:8px;border-color:var(--danger)">
          <div class="row"><${Pill} status=${i.severity === "high" ? "failed" : "waiting"} label=${i.severity} /><strong>${i.kind}</strong><span class="faint">${i.agent || ""}</span></div>
          <div class="mono faint" style="margin-top:6px;word-break:break-all">${i.detail}</div></div>`)}</div>` : null}
      ${d.retries?.length ? html`<div class="section"><div class="label">${t("retries")}</div>
        ${d.retries.map((r) => html`<div class="row faint">${r.kind === "tests" ? `tests → ${r.agent} (${r.round})` : `${r.agent} → ${r.next}: ${(r.error || "").slice(0, 120)}`}</div>`)}</div>` : null}
      ${d.steps ? html`<div class="section"><div class="label">${t("steps")}</div>
        ${d.steps.map((s) => html`<div class="row"><${Pill} status=${s.success ? "done" : "failed"} /> ${s.title} <span class="faint">${s.agent} · ${s.duration_s}s</span></div>`)}</div>` : null}
      ${d.reviews?.length ? html`<div class="section"><div class="label">${t("reviews")}</div>
        ${d.reviews.map((r) => html`<div class="card" style="margin-bottom:8px">
          <div class="row"><strong>${r.reviewer}</strong><span class="pill">${r.verdict.replace("_", " ")}</span><span class="faint">#${r.round}</span></div>
          <${RichText} text=${r.findings} class="prose muted" style="margin-top:6px" /></div>`)}</div>` : null}
      ${d.learn?.some((f) => f.status === "proposed") ? html`<div class="section"><div class="label">${t("learn")}</div>
        ${d.learn.map((f, i) => f.status === "proposed" ? html`<div class="card row" style="margin-bottom:8px">
          <span style="flex:1">${f.fact}</span>
          <button class="btn primary" disabled=${busy} onClick=${() => act("learn", { accept: [i] })}>${t("remember")}</button>
          <button class="btn ghost" disabled=${busy} onClick=${() => act("learn", { reject: [i] })}>${t("forget")}</button></div>` : null)}</div>` : null}
      ${pending.length ? html`<div class="section"><div class="label">${t("comments")}</div>
        ${pending.map((c) => html`<div class="card" style="margin-bottom:8px"><strong>${c.author}</strong>
          ${c.path ? html` <span class="faint mono">${c.path}${c.line ? `:${c.line}` : ""}</span>` : null}
          <${RichText} text=${c.body} class="prose muted" /></div>`)}</div>` : null}
    </div>`;
}

function TasksView({ tasks, status, selected, select, toast, reload }) {
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const shown = tasks.filter((x) => (!project || x.project === project) && (!state || x.status === state));
  return html`
    <div class="split ${selected ? "has-selected" : ""}">
      <div class="list">
        <${Composer} status=${status} toast=${toast} onCreated=${(task) => { reload(); select(task.id); }} />
        <div class="list-head">
          <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
            <option value="">${t("all_projects")}</option>
            ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}
          </select>
          <select class="select" value=${state} onChange=${(e) => setState(e.target.value)}>
            <option value="">${t("all_statuses")}</option>
            ${STATUS_ORDER.map((s) => html`<option value=${s}>${s}</option>`)}
          </select>
        </div>
        ${shown.length ? shown.map((x) => html`
          <button key=${x.id} class="task-row ${x.id === selected ? "active" : ""}" onClick=${() => select(x.id)}>
            <span class="task-title">${firstLine(x.prompt)}</span><${Pill} status=${x.status} />
            <span class="task-meta">${x.project} · ${x.agent} · ${ago(x.created_at)}</span>
          </button>`) : html`<div class="empty">${t("no_tasks")}</div>`}
      </div>
      ${selected ? html`<${TaskDetail} id=${selected} toast=${toast} onChanged=${reload} onBack=${() => select(null)} />`
        : html`<div class="empty">${t("pick_task")}</div>`}
    </div>`;
}

// ----------------------------------------------------------------- chat ---

const SESSION_KEY = "dia-chat-session";

function ChatView({ open, toast }) {
  const [sessions, setSessions] = useState([]);
  const [current, setCurrent] = useState(() => store(SESSION_KEY) || "owner");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [showList, setShowList] = useState(false);
  const [providers, setProviders] = useState([]);
  const end = useRef(null);
  useEffect(() => { api("/api/chat/providers").then(setProviders).catch(() => setProviders([])); }, []);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  const loadSessions = () => api("/api/sessions").then(setSessions).catch((e) => toast(e.message, "error"));
  const loadMessages = (id) => api(`/api/sessions/${id}`).then((s) => setMessages(s.messages))
    .catch(() => { setCurrent("owner"); store(SESSION_KEY, "owner"); });
  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { loadMessages(current); }, [current]);
  useEffect(() => {
    // a long task's answer is recorded when it finishes: show it then
    const onTask = (e) => { if (["done", "failed"].includes(e.detail.status)) loadMessages(current); };
    window.addEventListener("dia-task", onTask);
    return () => window.removeEventListener("dia-task", onTask);
  }, [current]);

  const choose = (id) => { setCurrent(id); store(SESSION_KEY, id); setShowList(false); };
  const create = async () => {
    try { const { id } = await api("/api/sessions", { method: "POST", body: {} }); await loadSessions(); choose(id); }
    catch (e) { toast(e.message, "error"); }
  };
  const rename = async (s) => {
    const title = prompt(t("rename_prompt"), s.title || "");
    if (title === null) return;
    try { await api(`/api/sessions/${s.id}`, { method: "PATCH", body: { title } }); loadSessions(); }
    catch (e) { toast(e.message, "error"); }
  };
  const remove = async (s) => {
    if (!confirm(s.main ? t("clear_main_confirm") : t("delete_session_confirm"))) return;
    try {
      await api(`/api/sessions/${s.id}`, { method: "DELETE" });
      await loadSessions();
      if (s.id === current) { s.main ? loadMessages("owner") : choose("owner"); }
    } catch (e) { toast(e.message, "error"); }
  };

  const send = async (say) => {
    const content = (say ?? text).trim();
    if (!content) return;
    setText("");
    setMessages((m) => [...m, { from: "me", text: content }]);
    setBusy(true);
    try {
      const answer = await api("/api/chat", { method: "POST", body: { text: content, session: current } });
      setMessages((m) => [...m, { from: "dia", text: answer.reply || "", task: answer.task?.id, plan: answer.plan?.id }]);
      loadSessions();
    } catch (e) {
      setMessages((m) => [...m, { from: "dia", text: `${t("failed")}: ${e.message}` }]);
    }
    setBusy(false);
  };

  const session = sessions.find((s) => s.id === current);
  const title = (s) => (s.main ? t("main_session") : s.title || t("untitled"));
  const provider = providers.find((p) => p.id === (session?.provider || "dia"));
  const setEngine = async (providerId, model) => {
    try {
      await api(`/api/sessions/${current}`, { method: "PATCH", body: { provider: providerId, model: model || "" } });
      loadSessions();
    } catch (e) { toast(e.message, "error"); }
  };
  return html`
    <div class="chat-split ${showList ? "show-list" : ""}">
      <div class="chat-sessions">
        <button class="btn primary" style="width:100%" onClick=${create}>+ ${t("new_session")}</button>
        ${sessions.map((s) => html`<div class="session-row ${s.id === current ? "active" : ""}" onClick=${() => choose(s.id)}>
          ${s.provider && s.provider !== "dia" ? html`<span class="faint" title=${s.provider}>◆</span>` : null}
          <span class="session-title" title=${s.main ? t("main_session_help") : title(s)}>${title(s)}</span>
          ${s.pending_plan ? html`<span class="pill" title=${t("run_plan")}>?</span>` : null}
          <span class="session-actions">
            ${s.main ? null : html`<button class="btn ghost" title=${t("rename")} onClick=${(e) => { e.stopPropagation(); rename(s); }}>✎</button>`}
            <button class="btn ghost" title=${t("delete_session")} onClick=${(e) => { e.stopPropagation(); remove(s); }}>×</button>
          </span></div>`)}
      </div>
      <div class="chat">
        <div class="chat-head"><button class="btn ghost sessions-toggle" onClick=${() => setShowList(!showList)}>☰ ${t("sessions")}</button>
          <strong style="flex:1">${session ? title(session) : ""}</strong>
          ${session && !session.main && providers.length > 1 ? html`<span class="chat-engine" title=${t("provider_help")}>
            <select class="select" value=${session.provider || "dia"} onChange=${(e) => setEngine(e.target.value, "")}>
              ${providers.map((p) => html`<option value=${p.id}>${p.label}</option>`)}</select>
            ${provider && provider.models.length ? html`<select class="select" value=${session.model || provider.models[0]}
              onChange=${(e) => setEngine(provider.id, e.target.value)}>
              ${provider.models.map((m) => html`<option value=${m}>${m === "default" ? t("default_model") : m}</option>`)}</select>` : null}
          </span>` : null}</div>
        <div class="messages">
          ${messages.length ? null : html`<div class="empty">${t("chat_hint")}</div>`}
          ${messages.map((m, i) => html`
            <div key=${i} class="msg ${m.from}"><${RichText} text=${m.text} class="" />
              ${m.task ? html`<div class="chip"><button class="btn" onClick=${() => open(m.task)}>${t("open_task")}</button></div>` : null}
              ${m.plan && i === messages.length - 1 && session?.pending_plan === m.plan ? html`<div class="chip row">
                <button class="btn primary" onClick=${() => send(t("yes"))}>${t("run_plan")}</button>
                <button class="btn" onClick=${() => send(t("no"))}>${t("discard")}</button></div>` : null}
            </div>`)}
          <div ref=${end}></div>
        </div>
        <div class="chat-input">
          <input class="input" placeholder=${t("chat_hint")} value=${text} disabled=${busy}
            onInput=${(e) => setText(e.target.value)} onKeyDown=${(e) => e.key === "Enter" && send()} />
          <button class="btn primary" disabled=${busy || !text.trim()} onClick=${() => send()}>${t("send")}</button>
        </div>
      </div>
    </div>`;
}

// --------------------------------------------------------------- status ---

function SystemCard() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const load = () => api("/api/system").then(setInfo).catch(() => {});
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);
  if (!info) return null;
  return html`
    <div class="label">${t("computer")}</div>
    <div class="grid section" style="margin-top:8px">
      <${Meter} label=${`CPU${info.cpu_temp != null ? ` · ${Math.round(info.cpu_temp)}°C` : ""}`} used=${info.cpu_percent} limit=${100} unit="%" />
      <${Meter} label=${`RAM · ${info.memory.used_gb}/${info.memory.total_gb} GB`} used=${info.memory.percent} limit=${100} unit="%" />
      ${info.disks.slice(0, 3).map((d) => html`<${Meter} label=${`${t("disk")} ${d.mount} · ${(d.total_gb - d.used_gb).toFixed(0)} GB ${t("free")}`} used=${d.percent} limit=${100} unit="%" />`)}
      ${info.battery ? html`<${Meter} label=${`${t("battery")} · ${info.battery.status}`} used=${info.battery.percent} limit=${100} unit="%" />` : null}
    </div>
    <div class="card section"><table class="table">
      <tr><th>${t("process")}</th><th>CPU</th><th>RAM</th><th>${t("user")}</th></tr>
      ${info.top.map((p) => html`<tr title=${p.command}><td>${p.name} <span class="faint">${p.pid}</span></td>
        <td>${p.cpu_percent}%</td><td>${Math.round(p.memory_mb)} MB</td><td class="faint">${p.user}</td></tr>`)}
    </table></div>`;
}

function SecurityCard({ toast }) {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try { setReport(await api("/api/security")); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  return html`
    <div class="label section">${t("security")}</div>
    <div class="card" style="margin-top:8px">
      ${report ? html`<pre class="prose" style="white-space:pre-wrap;margin:0">${report.text}</pre>
        ${report.listening.filter((s) => s.exposed).length ? html`<table class="table section">
          <tr><th>${t("port")}</th><th>${t("net_address")}</th><th>${t("process")}</th></tr>
          ${report.listening.filter((s) => s.exposed).map((s) => html`<tr><td>${s.port}</td><td class="mono">${s.address}</td><td>${s.process}</td></tr>`)}
        </table>` : null}` : html`<p class="muted">${t("security_help")}</p>`}
      <div class="row" style="margin-top:8px"><button class="btn" disabled=${busy} onClick=${check}>${busy ? "…" : t("security_check")}</button></div>
    </div>`;
}

function TidyCard({ toast }) {
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn) => { setBusy(true); try { await fn(); } catch (e) { toast(e.message, "error"); } setBusy(false); };
  const preview = () => run(async () => setPlan(await api("/api/tidy")));
  const apply = () => run(async () => {
    const done = await api(`/api/tidy/${plan.id}/apply`, { method: "POST" });
    toast(t("tidy_done", { n: done.moved.length })); setPlan({ ...done, text: t("tidy_done", { n: done.moved.length }) });
  });
  const undo = () => run(async () => { await api(`/api/tidy/${plan.id}/undo`, { method: "POST" }); setPlan(null); });
  return html`
    <div class="label section">${t("tidy")}</div>
    <div class="card" style="margin-top:8px">
      ${plan ? html`<p>${plan.text}</p>
        ${plan.status === "proposed" ? html`<table class="table">${plan.moves.slice(0, 50).map((m) => html`<tr><td class="mono">${m.from}</td><td class="mono">→ ${m.to}</td></tr>`)}</table>` : null}`
        : html`<p class="muted">${t("tidy_help")}</p>`}
      <div class="row" style="margin-top:8px">
        <button class="btn" disabled=${busy} onClick=${preview}>${t("tidy_preview")}</button>
        ${plan?.status === "proposed" && plan.moves.length ? html`<button class="btn primary" disabled=${busy} onClick=${apply}>${t("tidy_apply")}</button>` : null}
        ${plan?.status === "applied" ? html`<button class="btn ghost" disabled=${busy} onClick=${undo}>${t("tidy_undo")}</button>` : null}
      </div>
    </div>`;
}

// An agent and, optionally, its model for this one job: sent as "agent:model".
function AgentPick({ status, value, onChange }) {
  const [agent, model] = [value.split(":")[0], value.split(":").slice(1).join(":")];
  const info = (status?.agents || []).find((a) => a.name === agent);
  const id = `dl-pick-${useRef(Math.random().toString(36).slice(2)).current}`;
  return html`<span class="row">
    <select class="select" value=${agent} onChange=${(e) => onChange(e.target.value)}>
      <option value="">${t("default_agent")}</option>
      ${(status?.agents || []).map((a) => html`<option value=${a.name}>${a.name}</option>`)}</select>
    ${info ? html`<input class="input" style="width:130px" list=${id} placeholder=${`${t("model")}: ${info.model || t("auto")}`}
        value=${model} onInput=${(e) => onChange(e.target.value ? `${agent}:${e.target.value}` : agent)} />
      <datalist id=${id}>${info.models.map((m) => html`<option value=${m}></option>`)}</datalist>` : null}</span>`;
}

function ResearchCard({ status, toast }) {
  const [topic, setTopic] = useState("");
  const [project, setProject] = useState("");
  const [agent, setAgent] = useState("");
  const start = async (e) => {
    e.preventDefault();
    if (!topic.trim()) return;
    try { await api("/api/research", { method: "POST", body: { topic, project: project || null, agent: agent || undefined } }); toast(t("research_started")); setTopic(""); }
    catch (err) { toast(err.message, "error"); }
  };
  return html`
    <div class="label section">${t("research")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${start}>
      <p class="muted">${t("research_help")}</p>
      <textarea class="textarea" style="min-height:60px" placeholder=${t("research_topic")} value=${topic} onInput=${(e) => setTopic(e.target.value)}></textarea>
      <div class="row" style="margin-top:8px">
        <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
          <option value="">—</option>${status.projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
        <${AgentPick} status=${status} value=${agent} onChange=${setAgent} />
        <button class="btn primary">${t("research_start")}</button></div>
    </form>`;
}

function ExperimentCard({ status, toast }) {
  const [question, setQuestion] = useState("");
  const [approaches, setApproaches] = useState("");
  const [agents, setAgents] = useState("");
  const [project, setProject] = useState(status.projects[0]?.name || "");
  const start = async (e) => {
    e.preventDefault();
    if (!question.trim() || !project) return;
    const list = approaches.split("\n").map((a) => a.trim()).filter(Boolean);
    try {
      await api("/api/experiments", { method: "POST", body: { project, question, approaches: list, agents: agents.split(/[,\s]+/).filter(Boolean) } });
      toast(t("experiment_started")); setQuestion(""); setApproaches("");
    } catch (err) { toast(err.message, "error"); }
  };
  return html`
    <div class="label section">${t("experiment")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${start}>
      <p class="muted">${t("experiment_help")}</p>
      <textarea class="textarea" style="min-height:50px" placeholder=${t("experiment_question")} value=${question} onInput=${(e) => setQuestion(e.target.value)}></textarea>
      <textarea class="textarea" style="min-height:50px;margin-top:8px" placeholder=${t("experiment_approaches")} value=${approaches} onInput=${(e) => setApproaches(e.target.value)}></textarea>
      <div class="row" style="margin-top:8px">
        <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
          ${status.projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
        <input class="input" style="flex:1" list="agent-specs" placeholder=${t("agents_models_hint")} value=${agents} onInput=${(e) => setAgents(e.target.value)} />
        <button class="btn primary">${t("experiment_start")}</button></div>
    </form>`;
}

function WorkCard({ toast }) {
  const [data, setData] = useState(null);
  const [note, setNote] = useState("");
  const [text, setText] = useState("");
  const load = () => api("/api/work").then(setData).catch(() => setData(null));
  useEffect(() => { load(); }, []);
  const call = async (action, body) => {
    try { setText((await api(`/api/work/${action}`, { method: "POST", body })).text); setNote(""); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!data) return null;
  return html`<div class="label section">${t("work")}</div><div class="card" style="margin:8px 0 16px">
    <div class="row">${Object.keys(data.profiles).map((name) => html`<button class="btn ${data.current === name ? "primary" : ""}" onClick=${() => call("start", { name })}>${t("work_start")}: ${name}</button>`)}</div>
    ${data.current ? html`<div class="row" style="margin-top:8px"><input class="input" style="flex:1" placeholder=${t("work_note")} value=${note} onInput=${(e) => setNote(e.target.value)} />
      <button class="btn" onClick=${() => call("stop", { note })}>${t("work_stop")}</button></div>` : null}
    ${text ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${text}</pre>` : null}</div>`;
}

function SuggestionsCard({ toast }) {
  const [items, setItems] = useState([]);
  const load = () => api("/api/suggestions").then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const call = async (key, action) => {
    try { await api(`/api/suggestions/${encodeURIComponent(key)}/${action}`, { method: "POST" }); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!items.length) return null;
  return html`<div class="label">${t("suggestions")}</div>${items.map((s) => html`<div class="card row" style="margin:8px 0">
    <span style="flex:1">${s.text}</span>${s.action ? html`<button class="btn primary" onClick=${() => call(s.key, "accept")}>${t("accept")}</button>` : null}
    <button class="btn ghost" onClick=${() => call(s.key, "dismiss")}>${t("dismiss")}</button></div>`)}`;
}

function HealthCard() {
  const [items, setItems] = useState({});
  useEffect(() => { api("/api/health").then(setItems).catch(() => setItems({})); }, []);
  const bad = Object.entries(items).filter(([, h]) => h.state === "restarting" || h.restarts);
  if (!bad.length) return null;
  return html`<div class="label">${t("health")}</div>${bad.map(([name, h]) => html`<div class="card" style="margin:8px 0">
    <div class="row"><${Pill} status=${h.state === "restarting" ? "failed" : "done"} label=${h.state === "restarting" ? t("restarting") : h.state} /><strong>${name}</strong><span class="faint">${h.restarts}×</span></div>
    ${h.error ? html`<div class="mono faint">${h.error}</div>` : null}</div>`)}`;
}

function CliView({ toast }) {
  const [live, setLive] = useState([]);
  const [held, setHeld] = useState([]);
  const [key, setKey] = useState(null);
  const [talk, setTalk] = useState({ messages: [], available: true });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const loadHeld = () => api("/api/cli-captured").then(setHeld).catch(() => setHeld([]));
  useEffect(() => {
    const load = () => api("/api/cli-sessions").then(setLive).catch(() => setLive([]));
    load(); loadHeld();
    const timer = setInterval(() => { load(); loadHeld(); }, 5000);
    return () => clearInterval(timer);
  }, []);
  const rows = [...held.map((c) => ({ ...c, key: `c:${c.id}`, captured: true })),
    ...live.map((s) => ({ ...s, key: `p:${s.pid}` }))];
  const chosen = rows.find((r) => r.key === key) || rows[0];
  const path = chosen ? (chosen.captured ? `/api/cli-captured/${chosen.id}/transcript` : `/api/cli-sessions/${chosen.pid}/transcript`) : null;
  const refresh = () => (path ? api(path).then(setTalk).catch(() => setTalk({ messages: [], available: false })) : null);
  useEffect(() => {
    if (!path) return undefined;
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [path]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [talk.messages.length, chosen?.key]);
  const age = (s) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  const folder = (s) => (s.cwd || "").split("/").filter(Boolean).slice(-2).join("/");
  const capture = async () => {
    if (!confirm(t("cli_capture_confirm"))) return;
    try {
      const item = await api(`/api/cli-sessions/${chosen.pid}/capture`, { method: "POST" });
      setKey(`c:${item.id}`); await loadHeld(); toast(t("cli_captured"));
    } catch (e) { toast(e.message, "error"); }
  };
  const release = async () => {
    try {
      const r = await api(`/api/cli-captured/${chosen.id}`, { method: "DELETE" });
      setKey(null); await loadHeld(); toast(`${t("cli_released")}: ${r.resume}`);
    } catch (e) { toast(e.message, "error"); }
  };
  const send = async (e) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    try {
      const r = await api(`/api/cli-captured/${chosen.id}/send`, { method: "POST", body: { text: message } });
      setText(""); if (r.id !== chosen.id) { await loadHeld(); setKey(`c:${r.id}`); } else await refresh();
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  return html`<div class="chat-split">
    <div class="chat-sessions">
      <p class="muted" style="padding:8px">${t("cli_sessions_help")}</p>
      ${rows.length ? rows.map((r) => html`<div key=${r.key} class="session-row ${chosen?.key === r.key ? "active" : ""}" style="flex-direction:column;align-items:flex-start" onClick=${() => setKey(r.key)}>
        <span class="session-title" style="max-width:100%"><strong>${r.kind}</strong> · ${folder(r)}</span>
        <span class="faint">${r.captured ? t("cli_in_app") : `${r.from_dia ? t("cli_from_dia") : t("cli_external")} · ${r.model || t("auto")} · ${age(r.age_s)}`}</span></div>`)
        : html`<p class="faint" style="padding:8px">${t("cli_none")}</p>`}
    </div>
    <div class="chat">
      <div class="chat-head"><strong style="flex:1">${chosen ? `${chosen.kind} · ${chosen.cwd || ""}` : ""}</strong>
        ${chosen && !chosen.captured ? html`<button class="btn" title=${t("cli_capture_help")} onClick=${capture}>${t("cli_capture")}</button>` : null}
        ${chosen?.captured ? html`<button class="btn ghost" title=${chosen.resume} onClick=${release}>${t("cli_release")}</button>` : null}</div>
      <div class="messages">
        ${chosen && !talk.available ? html`<div class="empty">${t("cli_no_transcript")}</div>` : null}
        ${chosen && talk.available && !talk.messages.length ? html`<div class="empty">${t("cli_empty")}</div>` : null}
        ${talk.messages.map((m, i) => html`<div key=${i} class="msg ${m.role === "user" ? "me" : "dia"}"><${RichText} text=${m.text} class="" /></div>`)}
        ${busy ? html`<div class="msg dia">…</div>` : null}
        <div ref=${end}></div>
      </div>
      ${chosen?.captured ? html`<form class="chat-input" onSubmit=${send}>
        <input class="input" placeholder=${t("cli_reply")} value=${text} disabled=${busy} onInput=${(e) => setText(e.target.value)} />
        <button class="btn primary" disabled=${busy || !text.trim()}>${t("send")}</button></form>`
        : chosen ? html`<div class="chat-input"><span class="faint">${t("cli_capture_help")}</span></div>` : null}
    </div></div>`;
}

function DebugCard({ status, toast }) {
  const [bug, setBug] = useState("");
  const [agents, setAgents] = useState("");
  const [project, setProject] = useState(status.projects[0]?.name || "");
  const start = async (e) => {
    e.preventDefault();
    if (!bug.trim() || !project) return;
    try { await api("/api/debug", { method: "POST", body: { project, bug, agents: agents.split(/[,\s]+/).filter(Boolean) } }); toast(t("debug_started")); setBug(""); }
    catch (err) { toast(err.message, "error"); }
  };
  return html`
    <div class="label section">${t("debug")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${start}>
      <p class="muted">${t("debug_help")}</p>
      <textarea class="textarea" style="min-height:50px" placeholder=${t("debug_placeholder")} value=${bug} onInput=${(e) => setBug(e.target.value)}></textarea>
      <div class="row" style="margin-top:8px">
        <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
          ${status.projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
        <input class="input" style="flex:1" list="agent-specs" placeholder=${t("agents_models_hint")} value=${agents} onInput=${(e) => setAgents(e.target.value)} />
        <button class="btn primary">${t("debug_start")}</button></div>
    </form>`;
}

function benchmarkText(data) {
  if (!data.results.length) return t("no_benchmarks");
  return data.results.slice(0, 15).map((r) => `${r.at.slice(0, 16).replace("T", " ")}  ${r.sha.slice(0, 8)}  ${(r.ref || "-").padEnd(12)} `
    + Object.entries(r.metrics).map(([k, v]) => `${k}=${v}`).join("  ")).join("\n");
}

// ---------------------------------------------------------------- tools ---

// Dia's CLI commands with their output (POST /api/tools): whatever has no button
// of its own still works from the app.
const splitArgs = (line) => [...line.matchAll(/"([^"]*)"|'([^']*)'|(\S+)/g)].map((m) => m[1] ?? m[2] ?? m[3]);
async function runTool(command, args = []) {
  const r = await api("/api/tools", { method: "POST", body: { command, args } });
  return r.output.replace(/^\s*\n/, "").trimEnd() || t(r.code ? "tool_failed" : "tool_done");
}

const TOOL_BUTTONS = [
  ["tool_doctor", "doctor", []], ["tool_doctor_fix", "doctor", ["--fix"]],
  ["tool_sandbox", "sandbox", ["check"]], ["tool_limits", "limits", []],
  ["tool_issues", "issues", []], ["tool_agents", "agents", []], ["tool_redteam", "redteam", []],
];

function ToolsCard({ toast }) {
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState("");
  const [line, setLine] = useState("");
  const run = async (command, args) => {
    if (command === "redteam" && !confirm(t("redteam_confirm"))) return;
    setBusy(command); setOut("");
    try { setOut(await runTool(command, args)); } catch (e) { toast(e.message, "error"); }
    setBusy("");
  };
  const custom = (e) => {
    e.preventDefault();
    const words = splitArgs(line.replace(/^\s*dia\s+/, ""));
    if (words.length) run(words[0], words.slice(1));
  };
  return html`<div class="label section">${t("tools")}</div>
    <div class="card" style="margin:8px 0 16px">
      <p class="muted">${t("tools_help")}</p>
      <div class="row">${TOOL_BUTTONS.map(([key, command, args]) => html`
        <button class="btn ghost" disabled=${!!busy} onClick=${() => run(command, args)}>${t(key)}</button>`)}</div>
      <form class="row" style="margin-top:8px" onSubmit=${custom}><span class="mono faint">dia</span>
        <input class="input mono" style="flex:1" placeholder=${t("tool_placeholder")} value=${line} onInput=${(e) => setLine(e.target.value)} />
        <button class="btn" disabled=${!!busy || !line.trim()}>${t("tool_run")}</button></form>
      ${busy ? html`<p class="muted">${t("tool_running", { name: busy })}</p>` : null}
      ${out ? html`<pre class="mono" style="white-space:pre-wrap;margin-top:8px;max-height:420px;overflow:auto">${out}</pre>` : null}
    </div>`;
}

function SkillsCard({ toast }) {
  const [skills, setSkills] = useState([]);
  const [name, setName] = useState("");
  const [args, setArgs] = useState({});
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("/api/skills").then((list) => { setSkills(list); setName(list[0]?.name || ""); }).catch(() => {}); }, []);
  const skill = skills.find((s) => s.name === name);
  const run = async (e, yes = false) => {
    if (e) e.preventDefault();
    setBusy(true);
    try {
      const r = await api(`/api/skills/${name}`, { method: "POST", body: { args, confirm: yes } });
      if (r.question) {
        setBusy(false);
        if (confirm(r.question)) run(null, true);
        return;
      }
      setOut(r.text);
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  if (!skills.length) return null;
  return html`<div class="label section">${t("skills")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${run}>
      <div class="row">
        <select class="select" value=${name} onChange=${(e) => { setName(e.target.value); setArgs({}); setOut(""); }}>
          ${skills.map((s) => html`<option value=${s.name}>${s.name}</option>`)}</select>
        <span class="muted" style="flex:1">${skill?.description}</span></div>
      ${Object.entries(skill?.args || {}).map(([key, help]) => html`<label class="field" style="margin-top:8px"><span>${key} <span class="faint">${help}</span></span>
        <input class="input" value=${args[key] || ""} onInput=${(e) => setArgs({ ...args, [key]: e.target.value })} /></label>`)}
      <div class="row" style="margin-top:8px"><button class="btn primary" disabled=${busy}>${busy ? "…" : t("skill_run")}</button></div>
      ${out ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${out}</pre>` : null}
    </form>`;
}

function HeldCard() {
  const [data, setData] = useState(null);
  useEffect(() => { api("/api/notifications").then(setData).catch(() => {}); }, []);
  if (!data?.held?.length) return null;
  return html`<div class="label">${t("held_notes")} (${data.held.length})</div>
    <div class="card" style="margin:8px 0 16px">${data.held.map((h) => html`<div style="margin-bottom:6px">
      <span class="faint mono">${clock(h.at)}</span> <strong>${h.title}</strong> <span class="muted">${h.body}</span></div>`)}</div>`;
}

function StatusView({ status, reload, toast }) {
  const [analysis, setAnalysis] = useState({});
  if (!status) return html`<div class="empty">…</div>`;
  const analyze = async (project, kind = "analysis") => {
    try {
      const a = await api(`/api/projects/${project}/${kind}`);
      setAnalysis({ ...analysis, [project]: kind === "benchmarks" ? benchmarkText(a) : a.text });
    }
    catch (e) { toast(e.message, "error"); }
  };
  const impactOf = async (project, q) => {
    try { const a = await api(`/api/projects/${project}/impact?q=${encodeURIComponent(q)}`); setAnalysis({ ...analysis, [project]: a.text }); }
    catch (e) { toast(e.message, "error"); }
  };
  const fixDebt = async (project, n) => {
    if (!n) return;
    try { await api(`/api/projects/${project}/debt/${n}/fix`, { method: "POST" }); toast(t("debt_fixing")); }
    catch (e) { toast(e.message, "error"); }
  };
  const checkNotes = async (project) => {
    try { await api(`/api/projects/${project}/contradictions`, { method: "POST" }); toast(t("check_started")); }
    catch (e) { toast(e.message, "error"); }
  };
  const build = async (project) => {
    try { await api("/api/builds", { method: "POST", body: { project, write_changelog: true } }); toast(t("build_started")); }
    catch (e) { toast(e.message, "error"); }
  };
  const tool = async (project, command, args) => {
    setAnalysis({ ...analysis, [project]: t("tool_running", { name: command }) });
    try { const out = await runTool(command, args); setAnalysis((all) => ({ ...all, [project]: out })); }
    catch (e) { setAnalysis((all) => ({ ...all, [project]: "" })); toast(e.message, "error"); }
  };
  return html`
    <div class="page">
      <div class="row" style="margin-bottom:16px"><button class="btn" onClick=${reload}>${t("refresh")}</button></div>
      <${SuggestionsCard} toast=${toast} />
      <${HealthCard} />
      <${WorkCard} toast=${toast} />
      <${SystemCard} />
      <${SecurityCard} toast=${toast} />
      <${TidyCard} toast=${toast} />
      <${ResearchCard} status=${status} toast=${toast} />
      ${status.projects.length ? html`<${ExperimentCard} status=${status} toast=${toast} />` : null}
      ${status.projects.length ? html`<${DebugCard} status=${status} toast=${toast} />` : null}
      <${HeldCard} />
      <${SkillsCard} toast=${toast} />
      ${status.device && !status.device_full ? null : html`<${ToolsCard} toast=${toast} />`}
      <div class="label">${t("agents")}</div>
      <div class="grid section" style="margin-top:8px">
        ${status.agents.map((a) => html`<div class="card">
          <div class="stat-title">${a.name}${a.limited_until
            ? html`<${Pill} status="limited" label=${t("limited")} />`
            : html`<${Pill} status=${a.ok ? "done" : "failed"} label=${a.ok ? "ok" : t("failed")} />`}</div>
          <div class="muted">${a.type}${a.role ? ` · ${a.role}` : ""} · ${t("model_label")}: ${a.model || t("auto")}</div>
          ${a.limited_until ? html`<div style="color:var(--warn);margin-top:6px">${t("limited_until", { time: clock(a.limited_until) })}
            ${status.device && !status.device_full ? null : html` <button class="btn ghost" onClick=${() => runTool("limits", ["--clear", a.name]).then(reload).catch((e) => toast(e.message, "error"))}>${t("clear_limit")}</button>`}</div>` : null}
          ${a.problem ? html`<div style="color:var(--danger);margin-top:6px">${a.problem}</div>` : null}</div>`)}
      </div>
      <datalist id="agent-specs">${status.agents.flatMap((a) => [a.name, ...a.models.map((m) => `${a.name}:${m}`)]).map((o) => html`<option value=${o}></option>`)}</datalist>
      <div class="label section">${t("projects")}</div>
      <div class="grid" style="margin-top:8px">
        ${status.projects.map((p) => html`<div class="card">
          <div class="stat-title">${p.name}<${Pill} status=${p.ok ? "done" : "failed"} label=${p.ok ? "ok" : t("failed")} /></div>
          <div class="muted mono" style="word-break:break-all">${p.path}</div>
          ${p.toolchain ? html`<div class="faint">${p.toolchain}</div>` : null}
          ${p.presets?.length ? html`<div class="row" style="margin-top:8px">
            <button class="btn" onClick=${() => build(p.name)}>${t("build")}</button>
            <span class="faint">${p.presets.join(", ")}</span></div>` : null}
          ${p.toolchain?.startsWith("godot") ? html`<div class="row" style="margin-top:8px">
            <button class="btn ghost" onClick=${() => analyze(p.name)}>${t("analyze")}</button>
            <button class="btn ghost" onClick=${() => analyze(p.name, "balance")}>${t("balance")}</button></div>` : null}
          <form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); const q = e.target.elements.q.value.trim(); if (q) impactOf(p.name, q); }}>
            <input class="input" name="q" style="flex:1" placeholder=${t("impact_placeholder")} />
            <button class="btn ghost">${t("impact")}</button></form>
          <div class="row" style="margin-top:8px"><button class="btn ghost" onClick=${() => checkNotes(p.name)}>${t("check_notes")}</button>
            <button class="btn ghost" onClick=${() => analyze(p.name, "debt?refresh=1")}>${t("debt")}</button></div>
          ${(analysis[p.name] || "").match(/^\s*\d+\. \[/) ? html`<form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); fixDebt(p.name, e.target.elements.n.value); }}>
            <input class="input" name="n" type="number" min="1" style="width:80px" placeholder="#" /><button class="btn">${t("debt_fix")}</button></form>` : null}
          ${p.benchmark ? html`<div class="row" style="margin-top:8px">
            <button class="btn ghost" onClick=${() => analyze(p.name, "benchmarks")}>${t("benchmarks")}</button>
            ${status.device && !status.device_full ? null : html`<button class="btn ghost" onClick=${() => tool(p.name, "bench", [p.name])}>${t("bench_now")}</button>`}</div>` : null}
          ${status.device && !status.device_full ? null : html`<div class="row" style="margin-top:8px">
            <button class="btn ghost" onClick=${() => tool(p.name, "launch", [p.name])}>${t("launch")}</button>
            <button class="btn ghost" onClick=${() => tool(p.name, "check", [p.name])}>${t("check_now")}</button></div>
          <form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); const c = e.target.elements.c.value.trim(); if (c) tool(p.name, "lab", [p.name, c]); }}>
            <input class="input mono" name="c" style="flex:1" placeholder=${t("lab_placeholder")} />
            <button class="btn ghost">${t("lab")}</button></form>`}
          ${analysis[p.name] ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${analysis[p.name]}</pre>` : null}</div>`)}
      </div>
      <div class="kv card section">
        <span>${t("brains")}</span><span>${status.brains.join(" → ")}</span>
        <span>${t("memory")}</span><span>${status.memory || t("off")}</span>
        <span>${t("sandbox")}</span><span style=${status.sandbox === "on" ? "" : "color:var(--danger)"}>${t(`sandbox_${status.sandbox || "unavailable"}`)}</span>
        <span>${t("channels")}</span><span>${status.channels.join(", ") || "-"}</span>
        <span>${t("language")}</span><span>${status.language}</span>
        <span>${t("version")}</span><span>Dia ${status.version || "?"}</span>
      </div>
    </div>`;
}

// ------------------------------------------------------------- settings ---

// Settings forms: each field is [path in the config, label key, type, options].
// Saved to settings.json (laid over the config file), applied without a restart
// except where noted.
const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split(".");
  let o = obj;
  keys.slice(0, -1).forEach((k) => { o = o[k] = o[k] && typeof o[k] === "object" ? o[k] : {}; });
  o[keys[keys.length - 1]] = value;
}
const toForm = (value, type) => {
  if (type === "bool") return Boolean(value);
  if (type === "list") return (value || []).join(", ");
  if (type === "lines") return (value || []).join("\n");
  return value == null ? "" : String(value);
};
const fromForm = (value, type) => {
  if (type === "bool") return value;
  if (value === "") return null; // removed from the settings: the config file's value applies
  if (type === "number") return Number(value);
  if (type === "list") return value.split(/[,\s]+/).filter(Boolean);
  if (type === "lines") return value.split("\n").map((x) => x.trim()).filter(Boolean);
  return value;
};

function settingsForms(meta) {
  const v = meta.values;
  const forms = {
    assistant: [
      ["assistant.name", "f_name", "text"],
      ["assistant.user_name", "f_user_name", "text"],
      ["assistant.personality", "f_personality", "personality"],
      ["dia.language", "language", "select", ["pl", "en"]],
      ["skills.weather.place", "f_weather_place", "text"],
      ["skills.news.feeds", "f_news_feeds", "lines"],
      ["skills.stocks.symbols", "f_stocks", "list"],
      ["skills.stocks.source", "f_stocks_source", "select", ["", "yahoo", "stooq"]],
      ["skills.crypto.coins", "f_crypto", "list"],
      ["skills.crypto.currency", "f_crypto_currency", "select", ["", "usd", "pln", "eur"]],
      ["skills.briefing.sections", "f_briefing", "list"],
      ["assistant.learn_preferences", "f_learn_prefs", "bool"],
      ["assistant.skills", "f_skills", "list"],
      ["assistant.history_turns", "f_history_turns", "number"],
      ["assistant.history_minutes", "f_history_minutes", "number"],
      ["assistant.one_conversation", "f_one_conversation", "bool", null, false, true],
      ["assistant.owner_ids", "f_owner_ids", "list"],
      ["assistant.log_intents", "f_log_intents", "bool", null, false, true],
    ],
    agents: [
      ["dia.default_agent", "default_agent", "select", ["", ...meta.agents]],
      ["dia.max_parallel_tasks", "f_parallel", "number"],
      ["limits.fallback", "f_fallback", "list"],
      ["limits.wait", "f_limit_wait", "bool"],
      ["limits.max_wait_hours", "f_max_wait", "number"],
      ["review.auto", "f_auto_review", "bool"],
      ["review.reviewer", "f_reviewer", "select", ["", ...meta.agents]],
      ["retry.agent_errors", "f_retry_errors", "number"],
      ["retry.switch_agent", "f_retry_switch", "bool"],
      ["retry.test_fixes", "f_retry_tests", "number"],
      ["routing.auto", "f_routing_auto", "bool"],
      ["task_limits.minutes", "f_task_minutes", "number"],
      ["task_limits.calls", "f_task_calls", "number"],
      ["task_limits.agent_timeout", "f_agent_timeout", "number"],
      ["task_limits.nice", "f_nice", "number"],
      ["limits.cooldown_minutes", "f_cooldown", "number"],
      ["plans.planner", "f_planner", "select", ["", ...meta.agents]],
      ["plans.max_steps", "f_plan_steps", "number"],
      ["review.fix_rounds", "f_fix_rounds", "number"],
      ["missions.planner", "f_mission_planner", "select", ["", ...meta.agents]],
      ["missions.max_steps", "f_mission_steps", "number"],
      ["missions.budget_calls", "f_mission_calls", "number"],
      ["missions.budget_minutes", "f_mission_minutes", "number"],
      ["missions.step_tests", "f_mission_tests", "bool", null, false, true],
      ["council.members", "f_council_members", "list"],
      ["council.moderator", "f_council_moderator", "select", ["", ...meta.agents]],
      ["experiments.agents", "f_experiment_agents", "list"],
      ["experiments.max_variants", "f_experiment_variants", "number"],
      ["debug.agents", "f_debug_agents", "list"],
      ["debug.max_checks", "f_debug_checks", "number"],
      ["profile.agent", "f_profile_agent", "select", ["", ...meta.agents]],
      ["contradictions.agent", "f_contradictions_agent", "select", ["", ...meta.agents]],
    ],
    automation: [
      ["watch.enabled", "f_watch", "bool", null, true],
      ["watch.interval", "f_watch_interval", "number", null, true],
      ["issues.enabled", "f_issues", "bool", null, true],
      ["issues.label", "f_issues_label", "text", null, true],
      ["issues.planner", "f_issues_planner", "bool"],
      ["ci.autofix", "f_ci_autofix", "bool"],
      ["push.events", "f_push_events", "list"],
      ["system.cpu_temp", "f_cpu_temp", "number"],
      ["system.disk_used", "f_disk_used", "number"],
      ["system.battery_low", "f_battery_low", "number"],
      ["system.check_urls", "f_check_urls", "lines"],
      ["notifications.quiet_hours", "f_quiet_hours", "text"],
      ["notifications.budget", "f_budget", "number"],
      ["tidy.folders", "f_tidy_folders", "list"],
      ["watch.projects", "f_watch_projects", "list", null, true],
      ["watch.branch", "f_watch_branch", "text", null, true],
      ["issues.interval", "f_issues_interval", "number", null, true],
      ["ci.watch", "f_ci_watch", "bool", null, false, true],
      ["ci.interval", "f_ci_interval", "number"],
      ["ci.fix_rounds", "f_ci_fix_rounds", "number"],
      ["ci.watch_comments", "f_ci_comments", "bool"],
      ["ci.autofix_comments", "f_ci_autofix_comments", "bool"],
      ["goals.review_days", "f_goal_days", "number"],
      ["suggestions.per_day", "f_suggest_per_day", "number"],
      ["suggestions.repeat_days", "f_suggest_repeat", "number"],
      ["verification.min_lines", "f_verify_lines", "number"],
      ["verification.always", "f_verify_always", "bool"],
      ["debt.function_lines", "f_debt_function", "number"],
      ["debt.nesting", "f_debt_nesting", "number"],
      ["debt.file_lines", "f_debt_file", "number"],
      ["push.subject", "f_push_subject", "text"],
    ],
    integrations: [
      ["skills.mail.host", "f_mail_host", "text"],
      ["skills.mail.user", "f_mail_user", "text"],
      ["skills.home.url", "f_home_url", "text"],
      ["security.hosts", "f_security_hosts", "list"],
      ["security.networks", "f_networks", "list"],
      ["screen.agent", "f_screen_agent", "select", ["", ...meta.agents]],
      ["sandbox.enabled", "f_sandbox", "select", ["", "auto", "true", "false"]],
      ["sandbox.decoys", "f_sandbox_decoys", "bool"],
      ["sandbox.allow_read", "f_sandbox_read", "list"],
      ["lab.engine", "f_lab_engine", "select", ["", "podman", "docker"]],
      ["camera.device", "f_camera_device", "text"],
      ["research.agent", "f_research_agent", "select", ["", ...meta.agents]],
      ["skills.notion.parent", "f_notion_parent", "text"],
      ["builds.itch", "f_itch", "text"],
      ["builds.steam.app_id", "f_steam_app", "number"],
      ["builds.steam.username", "f_steam_user", "text"],
      ["builds.steam.branch", "f_steam_branch", "text"],
      ["builds.presets", "f_presets", "list"],
    ],
  };
  forms.memory = [
    ["memory.type", "f_memory_type", "select", ["", "obsidian", "markdown"]],
    ["memory.vault", "f_vault", "text"],
    ["memory.folder", "f_memory_folder", "text"],
    ["memory.projects_dir", "f_projects_dir", "text"],
    ["memory.journal_dir", "f_journal_dir", "text"],
    ["memory.profile_note", "f_profile_note", "text"],
    ["memory.max_context_chars", "f_context_chars", "number"],
    ["memory.exclude", "f_memory_exclude", "list"],
    ["memory.search_results", "f_search_results", "number"],
    ["memory.learn_agent", "f_learn_agent", "select", ["", ...meta.agents]],
  ];
  forms.remote = [
    ["ui.port", "f_ui_port", "number", null, true],
    ["ui.remote", "f_ui_remote", "bool", null, true],
    ["ui.public_url", "f_public_url", "text", null, true],
    ["ui.hosts", "f_ui_hosts", "list", null, true],
  ];
  if (v.channels?.discord) {
    forms.discord = [
      ["channels.discord.allowed_users", "f_discord_users", "list", null, true],
      ["channels.discord.guild_id", "f_discord_guild", "text", null, true],
      ["channels.discord.notify_channel_id", "f_discord_notify", "text", null, true],
    ];
  }
  forms.app = [
    ["app.tray", "f_app_tray", "bool", null, false, true],
    ["app.minimize_to_tray", "f_app_minimize", "bool", null, false, true],
    ["app.close_to_tray", "f_app_close", "bool", null, false, true],
    ["app.custom_titlebar", "f_app_titlebar", "bool", null, false, true],
  ];
  if (v.memory) {
    forms.automation.push(
      ["memory.learn", "f_learn", "bool"],
      ["memory.learn_model", "f_learn_model", "text"],
      ["memory.search", "f_memory_search", "select", ["", "folder", "vault", "off"]],
      ["memory.semantic.model", "f_semantic", "text"],
    );
  }
  if (v.channels?.voice) {
    const engine = getPath(v, "channels.voice.tts.type") || "piper";
    forms.voice = [
      ["channels.voice.language", "f_voice_language", "select", ["", "pl", "en"], true],
      ["channels.voice.stt.model", "f_stt_model", "text", null, true],
      ["channels.voice.tts.type", "f_tts", "select", meta.tts, true],
      ...(engine === "elevenlabs" ? [
        ["channels.voice.tts.voice_id", "f_voice_id", "text", null, true],
        ["channels.voice.tts.model", "f_eleven_model", "text", null, true],
        ["channels.voice.tts.stability", "f_stability", "number", null, true],
        ["channels.voice.tts.similarity_boost", "f_similarity", "number", null, true],
        ["channels.voice.tts.fallback", "f_tts_fallback", "select", ["", "piper"], true],
      ] : [["channels.voice.tts.voice", "f_piper_voice", "text", null, true]]),
      ["channels.voice.wake.model", "f_wake", "text", null, true],
      ["channels.voice.speaker.model", "f_speaker_model", "text", null, true],
      ["channels.voice.speaker.unknown", "f_speaker_unknown", "select", ["", "limited", "ignore", "allow"], true],
    ];
  }
  return forms;
}

function Form({ fields, meta, onSaved, toast }) {
  // A field's sixth element is its default, shown when the config leaves it out.
  const initial = Object.fromEntries(fields.map(([path, , type, , , fallback]) => [path, toForm(getPath(meta.values, path) ?? fallback, type)]));
  const [form, setForm] = useState(initial);
  const [custom, setCustom] = useState(false);
  useEffect(() => setForm(initial), [meta]);
  const set = (path, value) => setForm({ ...form, [path]: value });
  const save = async () => {
    const changes = {};
    for (const [path, , type] of fields) {
      if (form[path] !== initial[path]) setPath(changes, path, fromForm(form[path], type));
    }
    if (!Object.keys(changes).length) return;
    try {
      const result = await api("/api/settings", { method: "PUT", body: { changes } });
      toast(result.restart_required.length ? t("saved_restart") : t("saved"));
      onSaved();
    } catch (e) { toast(e.message, "error"); }
  };
  const input = ([path, , type, options]) => {
    const value = form[path];
    if (type === "bool") return html`<input type="checkbox" checked=${value} onChange=${(e) => set(path, e.target.checked)} />`;
    if (type === "select") return html`<select class="select" value=${value} onChange=${(e) => set(path, e.target.value)}>
      ${options.map((o) => html`<option value=${o}>${o || "–"}</option>`)}</select>`;
    if (type === "combo") {
      const id = `dl-${path.replace(/\W/g, "-")}`;
      return html`<span><input class="input" list=${id} placeholder=${t("auto")} value=${value ?? ""} onInput=${(e) => set(path, e.target.value)} />
        <datalist id=${id}>${options.map((o) => html`<option value=${o}></option>`)}</datalist></span>`;
    }
    if (type === "lines") return html`<textarea class="textarea" rows="3" value=${value} onInput=${(e) => set(path, e.target.value)}></textarea>`;
    if (type === "personality") {
      const preset = meta.personalities.includes(value) || value === "";
      return html`<div class="stack">
        <select class="select" value=${preset && !custom ? value : "__custom"} onChange=${(e) => {
          if (e.target.value === "__custom") { setCustom(true); set(path, preset ? "" : value); } else { setCustom(false); set(path, e.target.value); }
        }}>${["", ...meta.personalities].map((o) => html`<option value=${o}>${o ? t(`p_${o}`) : "–"}</option>`)}
          <option value="__custom">${t("p_custom")}</option></select>
        ${!preset || custom ? html`<textarea class="textarea" rows="3" placeholder=${t("p_custom_hint")} value=${value} onInput=${(e) => set(path, e.target.value)}></textarea>` : null}
      </div>`;
    }
    return html`<input class="input" type=${type === "number" ? "number" : "text"} step="any" value=${value} onInput=${(e) => set(path, e.target.value)} />`;
  };
  return html`<div class="card form">
    ${fields.map((field) => html`<label class="field"><span>${t(field[1])}${field[4] ? html` <span class="faint">↻</span>` : null}</span>${input(field)}</label>`)}
    <div class="row"><button class="btn primary" onClick=${save}>${t("save")}</button>
      ${fields.some((f) => f[4]) ? html`<span class="faint">↻ ${t("needs_restart")}</span>` : null}</div>
  </div>`;
}

function LocalBrain({ meta, onSaved, toast }) {
  const local = meta.values.brains?.local;
  const [on, setOn] = useState(Boolean(local));
  const [model, setModel] = useState(local?.model || "qwen2.5:3b");
  const save = async () => {
    const order = meta.values.dia?.default_agent ? ["rules", "local", "default-agent"] : ["rules", "local"];
    const changes = on
      ? { brains: { local: { type: "ollama", model } }, dia: { brain: order } }
      : { brains: { local: null }, dia: { brain: null } };
    try { await api("/api/settings", { method: "PUT", body: { changes } }); toast(t("saved")); onSaved(); }
    catch (e) { toast(e.message, "error"); }
  };
  return html`<div class="card form">
    <label class="field"><span>${t("f_local_brain")}</span><input type="checkbox" checked=${on} onChange=${(e) => setOn(e.target.checked)} /></label>
    ${on ? html`<label class="field"><span>${t("f_ollama_model")}</span><input class="input" value=${model} onInput=${(e) => setModel(e.target.value)} /></label>` : null}
    <p class="muted">${t("local_brain_help")}</p>
    <div class="row"><button class="btn primary" onClick=${save}>${t("save")}</button></div>
  </div>`;
}

function Secrets({ toast }) {
  const [items, setItems] = useState([]);
  const [values, setValues] = useState({});
  const [name, setName] = useState("");
  const load = () => api("/api/secrets").then(setItems).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const save = async (key) => {
    try { await api(`/api/secrets/${key}`, { method: "PUT", body: { value: values[key] || "" } }); setValues({ ...values, [key]: "" }); toast(t("saved_restart")); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const remove = async (key) => { await api(`/api/secrets/${key}`, { method: "DELETE" }); load(); };
  return html`<div class="card form">
    ${items.map((s) => html`<div class="field"><span>${s.label || s.name}<div class="faint mono">${s.name}</div></span>
      <div class="row">
        <input class="input" type="password" autocomplete="off" placeholder=${s.set ? "••••••••" : t("not_set")}
          value=${values[s.name] || ""} onInput=${(e) => setValues({ ...values, [s.name]: e.target.value })} />
        <button class="btn" onClick=${() => save(s.name)}>${t("save")}</button>
        ${s.set ? html`<button class="btn ghost" onClick=${() => remove(s.name)}>${t("remove")}</button>` : null}
      </div></div>`)}
    <div class="row"><input class="input mono" placeholder="OTHER_API_KEY" value=${name} onInput=${(e) => setName(e.target.value.toUpperCase())} />
      <button class="btn" onClick=${() => { if (name) { setItems([...items, { name, label: "", set: false }]); setName(""); } }}>${t("add")}</button></div>
    <p class="muted">${t("secrets_help")}</p>
  </div>`;
}

function ScheduleList({ toast }) {
  const [jobs, setJobs] = useState([]);
  const [cron, setCron] = useState("30 7 * * 1-5");
  const [text, setText] = useState("");
  const [speak, setSpeak] = useState(false);
  const load = () => api("/api/schedules").then(setJobs).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const call = async (path, method, body) => {
    try { const r = await api(path, { method, body }); if (r?.message) toast(r.message); load(); } catch (e) { toast(e.message, "error"); }
  };
  const add = async () => { await call("/api/schedules", "POST", { cron, text, speak }); setText(""); };
  return html`<div class="card form">
    ${jobs.length ? html`<table class="table"><tr><th>${t("when")}</th><th>${t("sched_what")}</th><th>${t("next_run")}</th><th></th></tr>
      ${jobs.map((j) => html`<tr class=${j.enabled ? "" : "faint"}>
        <td class="mono">${j.cron}</td><td>${j.name || j.text || j.prompt || j.skill}${j.speak ? " 🔊" : ""}</td>
        <td>${j.next ? new Date(j.next).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "–"}</td>
        <td class="row" style="justify-content:flex-end">
          <button class="btn ghost" onClick=${() => call(`/api/schedules/${j.id}/run`, "POST")}>${t("run_now")}</button>
          ${j.source === "store" ? html`
            <button class="btn ghost" onClick=${() => call(`/api/schedules/${j.id}`, "PATCH", { enabled: !j.enabled })}>${j.enabled ? t("pause") : t("resume")}</button>
            <button class="btn danger" onClick=${() => call(`/api/schedules/${j.id}`, "DELETE")}>${t("remove")}</button>` : html`<span class="faint">${t("from_config")}</span>`}
        </td></tr>`)}</table>` : html`<p class="muted">${t("no_schedules")}</p>`}
    <div class="row">
      <input class="input mono" style="width:150px" value=${cron} onInput=${(e) => setCron(e.target.value)} />
      <input class="input" style="flex:1" placeholder=${t("schedule_what")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <label class="row"><input type="checkbox" checked=${speak} onChange=${(e) => setSpeak(e.target.checked)} /> 🔊</label>
      <button class="btn primary" onClick=${add}>${t("add")}</button>
    </div>
    <p class="muted">${t("cron_help")}</p>
  </div>`;
}

// Projects and agents: edited in the settings overlay, like the forms; those the
// forms added can be removed here (the config file's own stay).
const PROJECT_FIELDS = (meta) => [
  ["path", "f_project_path", "text"], ["base_branch", "f_base_branch", "text"],
  ["test_command", "f_test_command", "text"], ["default_agent", "default_agent", "select", ["", ...meta.agents]],
  ["reviewer", "f_reviewer", "select", ["", ...meta.agents]], ["auto_review", "f_auto_review", "bool"],
  ["benchmark", "f_benchmark", "text"], ["forge", "f_forge", "select", ["", "auto", "github", "gitlab", "git"]],
  ["note", "f_note", "text"], ["toolchain", "f_toolchain", "select", ["", "auto", "godot", "none"]],
];
const AGENT_FIELDS = (meta) => [
  ["type", "f_agent_type", "select", meta.agent_types || []], ["model", "f_model", "combo", meta.agent_models || []],
  ["role", "f_role", "text"], ["command", "f_command", "text"],
];

function EntityEditor({ kind, fields, meta, onSaved, toast }) {
  const items = meta.values[kind] || {};
  const overlay = meta.overlay?.[kind] || {};
  const [name, setName] = useState("");
  const [first, setFirst] = useState("");
  const add = async (e) => {
    e.preventDefault();
    const key = name.trim();
    if (!/^[\w-]+$/.test(key) || !first.trim()) return toast(t("entity_invalid"), "error");
    try {
      await api("/api/settings", { method: "PUT", body: { changes: { [kind]: { [key]: { [fields[0][0]]: first.trim() } } } } });
      setName(""); setFirst(""); toast(t("saved")); onSaved();
    } catch (err) { toast(err.message, "error"); }
  };
  const remove = async (key) => {
    if (!confirm(t("entity_remove_confirm", { name: key }))) return;
    try { await api("/api/settings", { method: "PUT", body: { changes: { [kind]: { [key]: null } } } }); toast(t("saved")); onSaved(); }
    catch (err) { toast(err.message, "error"); }
  };
  return html`
    ${Object.keys(items).map((key) => html`<div class="card" style="margin:8px 0">
      <div class="row"><strong style="flex:1">${key}</strong>
        ${overlay[key] ? html`<button class="btn ghost" onClick=${() => remove(key)}>${t("remove")}</button>` : html`<span class="faint">${t("from_config")}</span>`}</div>
      <${Form} fields=${fields.map(([f, label, type, opts]) => [`${kind}.${key}.${f}`, label, type, opts])} meta=${meta} onSaved=${onSaved} toast=${toast} />
    </div>`)}
    <form class="row card" style="margin:8px 0" onSubmit=${add}>
      <input class="input" style="width:140px" placeholder=${t("entity_name")} value=${name} onInput=${(e) => setName(e.target.value)} />
      ${fields[0][2] === "select"
        ? html`<select class="select" value=${first} onChange=${(e) => setFirst(e.target.value)}><option value="">${t(fields[0][1])}</option>
            ${fields[0][3].map((o) => html`<option value=${o}>${o}</option>`)}</select>`
        : html`<input class="input" style="flex:1" placeholder=${t(fields[0][1])} value=${first} onInput=${(e) => setFirst(e.target.value)} />`}
      <button class="btn primary">${t("add")}</button></form>`;
}

function BrainTest({ toast }) {
  const [text, setText] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (args) => {
    setBusy(true); setOut("");
    try { setOut(await runTool("brains", args)); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  return html`<div class="card form" style="margin-top:8px">
    <p class="muted">${t("brain_test_help")}</p>
    <form class="row" onSubmit=${(e) => { e.preventDefault(); if (text.trim()) run(["--test", text]); }}>
      <input class="input" style="flex:1" placeholder=${t("brain_test_placeholder")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <button class="btn" disabled=${busy}>${t("brain_test")}</button>
      <button type="button" class="btn ghost" disabled=${busy} onClick=${() => run(["--replay", "50"])}>${t("brain_replay")}</button></form>
    ${busy ? html`<p class="muted">…</p>` : null}
    ${out ? html`<pre class="mono" style="white-space:pre-wrap;margin-top:8px">${out}</pre>` : null}
  </div>`;
}

function RuntimeCard({ state, act, busy }) {
  const tr = (en, pl) => lang === "pl" ? pl : en;
  if (!state?.available) return null;
  const p = state.policy;
  const configure = (patch) => act("startup", { ...p, ...patch });
  const run = (component, verb) => {
    if (verb !== "start" && !confirm(tr("This can interrupt active tasks. Continue?", "To może przerwać aktywne zadania. Kontynuować?"))) return;
    act("runtime", { component, verb, confirmed: true });
  };
  return html`<div class="label section">${tr("Startup and services", "Uruchamianie i usługi")}</div>
    <div class="card form">
      ${state.operation ? html`<p class="muted">${tr("Last service action", "Ostatnia operacja")}: ${state.operation.component} · ${state.operation.verb} · ${state.operation.state}${state.operation.error ? `: ${state.operation.error}` : ""}</p>` : null}
      <label class="row"><input type="checkbox" checked=${state.login_entry} disabled=${busy}
        onChange=${(e) => configure({ autostart: e.target.checked })} />
        ${tr("Start Dia at login (tray only)", "Uruchamiaj Dia po zalogowaniu (tylko tray)")}</label>
      <label class="field"><span>Ollama</span><select class="input" value=${p.ollama} disabled=${busy}
        onChange=${(e) => configure({ ollama: e.target.value })}>
        <option value="with-dia">${tr("Together with Dia", "Razem z Dia")}</option>
        <option value="independent">${tr("Start independently", "Uruchamiaj niezależnie od Dia")}</option>
        <option value="manual">${tr("Manual only", "Tylko ręcznie")}</option>
      </select></label>
      <label class="row"><input type="checkbox" checked=${p.warmup} disabled=${busy || state.warmup.load === "not-found"}
        onChange=${(e) => configure({ warmup: e.target.checked })} />
        ${tr("Warm up the model on startup", "Rozgrzewaj model przy uruchomieniu")}</label>
      <p class="muted">${tr("Login settings take effect at the next login. System Ollama may ask for authorization.", "Ustawienia startu dotyczą następnego logowania. Systemowa Ollama może poprosić o uwierzytelnienie.")}</p>
      ${["dia", "ollama"].map((c) => html`<div class="row">
        <span style="flex:1">${c === "dia" ? "Dia" : "Ollama"}: ${state[c].active} · ${state[c].enabled}</span>
        ${["start", "stop", "restart"].map((v, i) => html`<button class="btn ghost" disabled=${busy || state[c].load === "not-found"}
          onClick=${() => run(c, v)}>${tr(["Start", "Stop", "Restart"][i], ["Uruchom", "Zatrzymaj", "Restart"][i])}</button>`)}
        <button class="btn ghost" onClick=${() => act("logs", { component: c })}>${tr("Logs", "Logi")}</button>
      </div>`)}
    </div>`;
}

function DesktopCard({ toast }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [logs, setLogs] = useState("");
  const load = () => api("/api/desktop").then(setState).catch(() => setState(null));
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, []);
  const act = async (action, body) => {
    setBusy(true);
    try { const r = await api(`/api/desktop/${action}`, { method: "POST", body: body || {} }); if (action === "logs") setLogs(r.message); else toast(r.message || r.error); }
    catch (e) { toast(e.message, "error"); }
    setBusy(false); load();
  };
  if (!state) return null;
  const sc = state.shortcuts;
  return html`<${RuntimeCard} state=${state.runtime} act=${act} busy=${busy} />
    ${logs ? html`<pre class="card mono" style="white-space:pre-wrap">${logs}</pre>` : null}
    <div class="label section">${t("desktop_integration")}</div>
    <div class="card form" style="margin-top:8px">
      <div class="row"><span style="flex:1">${t("shortcuts")}: ${sc.menu ? t("in_menu") : t("not_in_menu")}${sc.desktop ? ` · ${t("on_desktop")}` : ""}${sc.autostart ? ` · ${t("at_login")}` : ""}</span>
        <button class="btn" disabled=${busy} onClick=${() => act("shortcuts", { desktop: true, autostart: sc.autostart })}>${sc.menu ? t("refresh_shortcuts") : t("add_shortcuts")}</button>
        
        ${sc.menu ? html`<button class="btn ghost" disabled=${busy} onClick=${() => act("remove-shortcuts")}>${t("remove")}</button>` : null}</div>
      ${state.widget !== null ? html`<div class="row" style="margin-top:8px"><span style="flex:1">${t("kde_widget")}: ${state.widget ? t("installed") : t("not_installed")}</span>
        <button class="btn" disabled=${busy} onClick=${() => act("widget")}>${state.widget ? t("update") : t("install")}</button></div>` : null}
      <p class="muted">${t("desktop_help")}</p>
    </div>`;
}

const SETTINGS_TABS = ["assistant", "voice_brain", "agents_tab", "projects_tab", "memory_tab", "automation", "integrations_tab", "schedule", "secrets", "devices_tab", "look", "config_file"];

function SettingsView({ toast, device: remote, full }) {
  // A paired phone sees its look and schedule; one with full access nearly everything.
  const device = remote && !full ? remote : null;
  const [tab, setTab] = useState(device ? "look" : "assistant");
  const [meta, setMeta] = useState(null);
  const [themes, setThemes] = useState(null);
  const [current, setCurrent] = useState(store(THEME_KEY) || "dark");
  const [config, setConfig] = useState(null);
  const loadMeta = () => api("/api/settings").then(setMeta).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    api("/api/themes").then(setThemes).catch((e) => toast(e.message, "error"));
    if (!device) { loadMeta(); api("/api/config").then(setConfig).catch((e) => toast(e.message, "error")); }
  }, [device]);
  const pick = (name) => { applyTheme(name); setCurrent(name); };
  const saveFile = async () => {
    try { await api("/api/config", { method: "PUT", body: { text: config.text } }); toast(t("saved_restart")); }
    catch (e) { toast(e.message, "error"); }
  };
  const tabs = device ? ["look", "schedule"] : remote ? SETTINGS_TABS.filter((k) => !["secrets", "devices_tab"].includes(k)) : SETTINGS_TABS;
  const forms = meta ? settingsForms(meta) : null;
  const form = (key) => (forms ? html`<${Form} fields=${forms[key]} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : "…");
  return html`
    <div class="page">
      <div class="tabs">${tabs.map((k) => html`<button class="tab ${tab === k ? "active" : ""}" onClick=${() => setTab(k)}>${t(k)}</button>`)}</div>
      ${tab === "assistant" ? form("assistant") : null}
      ${tab === "voice_brain" ? html`
        ${forms?.voice ? form("voice") : html`<p class="muted">${t("voice_off")}</p>`}
        <div class="label section">${t("brains")}</div>
        ${meta ? html`<${LocalBrain} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}
        <${BrainTest} toast=${toast} />` : null}
      ${tab === "agents_tab" ? html`${form("agents")}
        <div class="label section">${t("your_agents")}</div>
        ${meta ? html`<${EntityEditor} kind="agents" fields=${AGENT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}` : null}
      ${tab === "projects_tab" ? html`<p class="muted">${t("projects_help")}</p>
        ${meta ? html`<${EntityEditor} kind="projects" fields=${PROJECT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}` : null}
      ${tab === "memory_tab" ? html`${form("memory")}<p class="muted">${t("memory_help")}</p>` : null}
      ${tab === "automation" ? form("automation") : null}
      ${tab === "integrations_tab" ? html`${form("integrations")}<p class="muted">${t("integrations_help")}</p>` : null}
      ${tab === "schedule" ? html`<${ScheduleList} toast=${toast} />` : null}
      ${tab === "secrets" ? html`<${Secrets} toast=${toast} />` : null}
      ${tab === "devices_tab" ? html`<${Notifications} toast=${toast} /><${Devices} toast=${toast} />
        <div class="label section">${t("remote_access")}</div>${form("remote")}
        ${forms?.discord ? html`<div class="label section">Discord</div>${form("discord")}` : null}` : null}
      ${tab === "look" ? html`
        <div class="label">${t("theme")}</div>
        <div class="row" style="margin-top:8px">
          ${(themes?.built_in || []).map((name) => html`<button class="btn ${current === name ? "primary" : ""}" onClick=${() => pick(name)}>${name}</button>`)}
        </div>
        <div class="label section">${t("custom_themes")}</div>
        <div class="row" style="margin-top:8px">
          ${(themes?.custom || []).map((name) => html`<button class="btn ${current === name ? "primary" : ""}" onClick=${() => pick(name)}>${name}</button>`)}
        </div>
        <p class="muted">${t("themes_help")} <code>${themes?.dir || "~/.config/dia/themes"}</code></p>
        ${!device && forms ? html`<div class="label section">${t("app_window")}</div>${form("app")}<p class="muted">${t("app_window_help")}</p>
          ${remote ? null : html`<${DesktopCard} toast=${toast} />`}` : null}
        ${device ? html`<${Notifications} toast=${toast} /><p class="muted section">${t("device_note", { name: device })}</p>` : null}` : null}
      ${tab === "config_file" ? (config ? html`
        <p class="faint mono">${config.path}</p>
        ${meta?.settings_path ? html`<p class="muted">${t("overlay_note")} <code>${meta.settings_path}</code></p>` : null}
        <textarea class="textarea config-editor" value=${config.text}
          onInput=${(e) => setConfig({ ...config, text: e.target.value })}></textarea>
        <div class="row" style="margin-top:8px"><button class="btn primary" onClick=${saveFile}>${t("save")}</button></div>` : "…") : null}
    </div>`;
}

function urlKey(base64) {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

function Notifications({ toast }) {
  const [info, setInfo] = useState(null);
  const [on, setOn] = useState(false);
  const supported = "serviceWorker" in navigator && "PushManager" in window && window.isSecureContext;
  useEffect(() => {
    api("/api/push").then(setInfo).catch(() => {});
    if (supported) navigator.serviceWorker.ready.then((r) => r.pushManager.getSubscription()).then((s) => setOn(Boolean(s)));
  }, []);
  const enable = async () => {
    try {
      if (await Notification.requestPermission() !== "granted") throw new Error(t("push_denied"));
      const registration = await navigator.serviceWorker.ready;
      const sub = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlKey(info.key) });
      await api("/api/push/subscribe", { method: "POST", body: sub.toJSON() });
      setOn(true);
      toast(t("push_on"));
    } catch (e) { toast(e.message, "error"); }
  };
  const disable = async () => {
    const registration = await navigator.serviceWorker.ready;
    const sub = await registration.pushManager.getSubscription();
    if (sub) { await api("/api/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }); await sub.unsubscribe(); }
    setOn(false);
  };
  const test = async () => { try { toast((await api("/api/push/test", { method: "POST" })).message); } catch (e) { toast(e.message, "error"); } };
  if (!info) return null;
  return html`
    <div class="label section">${t("notifications")}</div>
    ${!info.available ? html`<p class="muted">${t("push_missing")}</p>`
      : !supported ? html`<p class="muted">${t("push_https")}</p>`
      : html`<div class="row" style="margin-top:8px">
          ${on ? html`<button class="btn" onClick=${disable}>${t("push_disable")}</button>
                   <button class="btn ghost" onClick=${test}>${t("push_test")}</button>`
               : html`<button class="btn primary" onClick=${enable}>${t("push_enable")}</button>`}
        </div>`}`;
}

function Devices({ toast }) {
  const [info, setInfo] = useState(null);
  const [name, setName] = useState("");
  const [paired, setPaired] = useState(null);
  const load = () => api("/api/devices").then(setInfo).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const pair = async () => {
    try { setPaired(await api("/api/devices", { method: "POST", body: { name: name.trim() || "phone" } })); setName(""); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const revoke = async (id) => {
    try { await api(`/api/devices/${id}`, { method: "DELETE" }); load(); } catch (e) { toast(e.message, "error"); }
  };
  const setFull = async (id, full) => {
    if (full && !confirm(t("full_access_confirm"))) return;
    try { await api(`/api/devices/${id}`, { method: "PATCH", body: { full } }); load(); } catch (e) { toast(e.message, "error"); }
  };
  if (!info) return null;
  return html`
    <div class="label section">${t("devices")}</div>
    ${!info.remote ? html`<p class="muted">${t("remote_off")}</p>` : null}
    ${info.devices.map((d) => html`<div class="row card" style="margin:8px 0">
      <strong style="flex:1">${d.name}</strong>
      <span class="faint">${d.last_seen ? ago(d.last_seen) : t("never")}</span>
      <label class="row muted" title=${t("full_access_help")}><input type="checkbox" checked=${d.full} onChange=${(e) => setFull(d.id, e.target.checked)} /> ${t("full_access")}</label>
      <button class="btn danger" onClick=${() => revoke(d.id)}>${t("revoke")}</button></div>`)}
    <div class="row" style="margin-top:8px">
      <input class="input" placeholder=${t("device_name")} value=${name} onInput=${(e) => setName(e.target.value)} />
      <button class="btn primary" onClick=${pair}>${t("pair")}</button>
    </div>
    ${paired ? html`<div class="card pairing section">
      ${paired.qr_svg ? html`<div class="qr" dangerouslySetInnerHTML=${{ __html: paired.qr_svg }}></div>` : null}
      <div style="min-width:0">
        <p>${t(paired.url ? "pair_scan" : "pair_no_url")}</p>
        ${paired.url ? html`<p class="mono break">${paired.url}</p>` : html`<p class="mono break">${paired.token}</p>`}
        <p class="faint">${t("pair_once")}</p>
        <button class="btn" onClick=${() => setPaired(null)}>${t("hide")}</button>
      </div></div>` : null}`;
}

// ------------------------------------------------------ mission control ---

function stepLevels(steps) {
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const level = {};
  const visit = (id) => (level[id] ??= 1 + Math.max(-1, ...byId[id].depends_on.map(visit)));
  steps.forEach((s) => visit(s.id));
  const columns = [];
  steps.forEach((s) => (columns[level[s.id]] ||= []).push(s));
  return columns;
}

function Meter({ label, used, limit, unit }) {
  const pct = limit ? Math.min(100, (100 * used) / limit) : 0;
  return html`<div class="meter"><div class="row" style="justify-content:space-between">
      <span class="muted">${label}</span><span>${Math.round(used)}${limit ? ` / ${limit}` : ""} ${unit}</span></div>
    <div class="meter-track"><span class=${`meter-fill ${pct >= 100 ? "over" : ""}`} style=${`width:${pct}%`}></span></div></div>`;
}

function Activity() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api("/api/audit?limit=40").then(setRows).catch(() => {});
    const add = (e) => setRows((all) => [e.detail, ...all].slice(0, 60));
    window.addEventListener("dia-audit", add);
    return () => window.removeEventListener("dia-audit", add);
  }, []);
  return html`<div class="activity">${rows.map((r) => html`<div class="activity-row">
    <span class="faint">${clock(r.at)}</span><span class="mono">${r.action}</span>
    <span class="muted">${r.actor}</span><span class="activity-detail">${r.detail || r.target || ""}</span></div>`)}
    ${rows.length ? null : html`<p class="muted">${t("no_activity")}</p>`}</div>`;
}

function GoalsCard({ status, toast }) {
  const [goals, setGoals] = useState([]);
  const [text, setText] = useState("");
  const [weeks, setWeeks] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api("/api/goals").then(setGoals).catch(() => setGoals([]));
  useEffect(() => { load(); }, []);
  const call = async (path, body) => {
    setBusy(true);
    try { await api(path, { method: "POST", body }); await load(); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const project = status?.projects[0]?.name;
  return html`<div class="memory-group"><div class="label">${t("goals")}</div>
    <div class="row"><input class="input" style="flex:1" placeholder=${t("goal_new")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <input class="input" style="width:90px" type="number" placeholder=${t("goal_weeks")} value=${weeks} onInput=${(e) => setWeeks(e.target.value)} />
      <button class="btn" disabled=${busy || !text.trim() || !project} onClick=${() => { call("/api/goals", { project, goal: text, weeks }); setText(""); }}>${t("goal_create")}</button></div>
    ${goals.filter((g) => g.status !== "failed").map((g) => {
      const review = (g.details.reviews || []).slice(-1)[0];
      const ms = g.details.milestones || [];
      return html`<div class="card" style="margin-top:8px"><div class="row"><strong style="flex:1">${g.prompt}</strong><${Pill} status=${g.status === "active" ? "running" : "done"} label=${g.status} /></div>
        <div class="faint">${g.project}${g.details.deadline ? ` · ${g.details.deadline}` : ""} · ${ms.filter((m) => m.status === "done").length}/${ms.length}</div>
        ${ms.map((m, i) => html`<div>${m.status === "done" ? "✓" : "○"} ${i + 1}. ${m.title}</div>`)}
        ${review ? html`<p class="muted" style="margin:6px 0">${review.progress}</p>
          ${review.blockers.length ? html`<div class="faint">${t("blockers")}: ${review.blockers.join("; ")}</div>` : null}
          ${review.next ? html`<div>${t("goal_next")}: ${review.next.mission}</div>` : null}` : null}
        ${g.status === "active" ? html`<div class="row" style="margin-top:8px"><button class="btn ghost" disabled=${busy} onClick=${() => call(`/api/goals/${g.id}/review`)}>${t("goal_review")}</button>
          ${review?.status === "proposed" ? html`<button class="btn primary" disabled=${busy} onClick=${() => call(`/api/goals/${g.id}/approve`)}>${t("goal_approve")}</button>` : null}</div>` : null}
      </div>`;
    })}</div>`;
}

function MissionsView({ status, toast, open }) {
  const [missions, setMissions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ project: "", goal: "", calls: "", minutes: "", priority: "normal" });
  const [busy, setBusy] = useState(false);
  const load = () => api("/api/missions").then(setMissions).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
    const onTask = (e) => { if (e.detail.mode === "mission" || e.detail.details?.mission) load(); };
    window.addEventListener("dia-task", onTask);
    return () => window.removeEventListener("dia-task", onTask);
  }, []);
  const create = async () => {
    setBusy(true);
    try {
      const m = await api("/api/missions", { method: "POST", body: { ...form, project: form.project || status.projects[0]?.name } });
      setForm({ ...form, goal: "" }); await load(); setSelected(m.id);
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const act = async (path, body) => {
    try { const r = await api(path, { method: "POST", body }); if (r?.message) toast(r.message); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const mission = missions.find((m) => m.id === selected);
  return html`
    <div class="split ${selected ? "has-selected" : ""}">
      <div class="list">
        <div class="composer">
          <div class="row">
            <select class="select" value=${form.project || status?.projects[0]?.name} onChange=${(e) => setForm({ ...form, project: e.target.value })}>
              ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
            <select class="select" value=${form.priority} onChange=${(e) => setForm({ ...form, priority: e.target.value })}>
              ${["low", "normal", "high"].map((p) => html`<option value=${p}>${t(`prio_${p}`)}</option>`)}</select>
          </div>
          <textarea class="textarea" rows="3" placeholder=${t("mission_goal")} value=${form.goal}
            onInput=${(e) => setForm({ ...form, goal: e.target.value })}></textarea>
          <div class="row">
            <input class="input" style="width:150px" type="number" placeholder=${t("budget_calls")} value=${form.calls} onInput=${(e) => setForm({ ...form, calls: e.target.value })} />
            <input class="input" style="width:150px" type="number" placeholder=${t("budget_minutes")} value=${form.minutes} onInput=${(e) => setForm({ ...form, minutes: e.target.value })} />
            <button class="btn primary" disabled=${busy || !form.goal.trim()} onClick=${create}>${busy ? t("planning") : t("plan_mission")}</button>
          </div>
        </div>
        <${GoalsCard} status=${status} toast=${toast} />
        ${missions.map((m) => {
          const steps = m.details.mission.steps;
          const done = steps.filter((s) => s.status === "done").length;
          return html`<button class="task-row ${m.id === selected ? "active" : ""}" onClick=${() => setSelected(m.id)}>
            <span class="task-title">${firstLine(m.prompt)}</span><${Pill} status=${m.status} />
            <span class="task-meta">${m.project} · ${done}/${steps.length} · ${t(`prio_${m.details.mission.priority || "normal"}`)} · ${ago(m.created_at)}</span>
            <span class="progress"><span style=${`width:${(100 * done) / steps.length}%`}></span></span>
          </button>`;
        })}
        ${missions.length ? null : html`<div class="empty">${t("no_missions")}</div>`}
      </div>
      ${mission ? html`<div class="detail">
        <button class="btn ghost back" onClick=${() => setSelected(null)}>← ${t("missions")}</button>
        <div class="row"><${Pill} status=${mission.status} /><span class="faint mono">${mission.id}</span></div>
        <h2>${firstLine(mission.prompt)}</h2>
        ${mission.error ? html`<div class="card" style="color:var(--danger)">${mission.error}</div>` : null}
        <div class="row section">
          ${["planned", "paused", "failed"].includes(mission.status) ? html`<button class="btn primary" onClick=${() => act(`/api/tasks/${mission.id}/run-plan`)}>${mission.status === "planned" ? t("start_mission") : t("continue_mission")}</button>` : null}
          ${mission.status === "running" ? html`<button class="btn" onClick=${() => act(`/api/missions/${mission.id}/cancel`)}>${t("cancel_mission")}</button>` : null}
          ${mission.status === "done" && mission.commit_sha ? html`
            <button class="btn" onClick=${() => open(mission.id)}>${t("review_changes")}</button>
            <button class="btn primary" onClick=${() => act(`/api/tasks/${mission.id}/merge`)}>${t("merge")}</button>
            <button class="btn" onClick=${() => act(`/api/tasks/${mission.id}/publish`)}>${t("publish")}</button>
            <button class="btn danger" onClick=${() => act(`/api/tasks/${mission.id}/discard`)}>${t("discard")}</button>` : null}
        </div>
        <div class="grid section">
          <${Meter} label=${t("budget_calls")} used=${mission.budget.used.calls} limit=${mission.budget.limits.calls} unit="" />
          <${Meter} label=${t("budget_minutes")} used=${mission.budget.used.minutes} limit=${mission.budget.limits.minutes} unit="min" />
        </div>
        <div class="label section">${t("steps")}</div>
        <div class="graph">${stepLevels(mission.details.mission.steps).map((column) => html`<div class="graph-col">
          ${column.map((s) => html`<div class="card step">
            <div class="row" style="justify-content:space-between"><strong>${s.title}</strong><${Pill} status=${s.status} /></div>
            <div class="muted">${s.agent}${s.depends_on.length ? ` · ${t("after")} ${s.depends_on.join(", ")}` : ""}</div>
            ${s.error ? html`<div style="color:var(--danger);font-size:12px">${s.error}</div>` : null}
            ${s.task_id ? html`<button class="btn ghost" onClick=${() => open(s.task_id)}>${t("open_task")}</button>` : null}
          </div>`)}</div>`)}</div>
        <div class="label section">${t("mission_log")}</div>
        <div class="card">${[...mission.details.mission.log].reverse().map((e) => html`<div class="activity-row log-row"><span class="faint">${clock(e.at)}</span><span>${e.text}</span></div>`)}</div>
      </div>` : html`<div class="detail"><div class="label">${t("activity")}</div><${Activity} /></div>`}
    </div>`;
}

// --------------------------------------------------------------- memory ---

function PreferencesCard({ toast }) {
  const [prefs, setPrefs] = useState(null);
  const [text, setText] = useState("");
  const load = () => api("/api/preferences").then(setPrefs).catch(() => setPrefs(null));
  useEffect(() => { load(); }, []);
  const call = async (path, body) => {
    try { await api(path, { method: "POST", body }); load(); } catch (e) { toast(e.message, "error"); }
  };
  const add = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    await call("/api/preferences", { text });
    setText("");
  };
  if (!prefs) return null;
  return html`<div class="label">${t("preferences")}</div>
    <p class="faint">${t("preferences_help")}</p>
    ${prefs.configured.map((p) => html`<div class="card row" style="margin-bottom:8px"><span style="flex:1">${p}</span><span class="faint">${t("from_config")}</span></div>`)}
    ${prefs.accepted.map((p, i) => html`<div class="card row" style="margin-bottom:8px"><span style="flex:1">${p.text}</span>
      <button class="btn ghost" onClick=${() => call(`/api/preferences/${i}/remove`)}>${t("remove")}</button></div>`)}
    ${prefs.proposed.length ? html`<div class="label">${t("pref_proposed")}</div>` : null}
    ${prefs.proposed.map((p, i) => html`<div class="card fact"><div>${p.text}</div>
      <div class="row"><button class="btn primary" onClick=${() => call(`/api/preferences/${i}/accept`)}>${t("keep")}</button>
        <button class="btn ghost" onClick=${() => call(`/api/preferences/${i}/reject`)}>${t("forget")}</button></div></div>`)}
    <form class="row" onSubmit=${add}><input class="input" style="flex:1" placeholder=${t("pref_add")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <button class="btn">+</button></form>`;
}

function DecisionsCard({ toast }) {
  const [rows, setRows] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  useEffect(() => { api("/api/decisions?limit=8").then(setRows).catch(() => setRows([])); }, []);
  const ask = async (e) => {
    e.preventDefault();
    if (!question.trim()) return setAnswer(null);
    try { setAnswer((await api(`/api/why?q=${encodeURIComponent(question)}`)).text); } catch (err) { toast(err.message, "error"); }
  };
  return html`<div class="label">${t("decisions")}</div>
    <form class="row" onSubmit=${ask}><input class="input" style="flex:1" placeholder=${t("why_placeholder")} value=${question} onInput=${(e) => setQuestion(e.target.value)} />
      <button class="btn">${t("why_ask")}</button></form>
    ${answer ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${answer}</pre>` : null}
    ${rows.map((d) => html`<div class="card" style="margin-top:8px"><div class="row"><span class="mono faint">${d.at.slice(0, 10)}</span>
      <${Pill} status=${["merged", "approved"].includes(d.outcome) ? "done" : ["discarded", "rejected", "rolled back", "changes_requested"].includes(d.outcome) ? "failed" : "planned"} label=${d.outcome} />
      <span style="flex:1">${d.title}</span></div>
      ${d.reason && d.kind !== "review" ? html`<div class="faint">${d.reason}</div>` : null}</div>`)}`;
}

function ProfileCard({ toast }) {
  const [data, setData] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api("/api/profile").then((d) => { setData(d); setText(d.text); }).catch(() => setData(null));
  useEffect(() => { load(); }, []);
  const call = async (path, options) => {
    setBusy(true);
    try { await api(path, options); load(); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  if (!data) return null;
  return html`<div class="label">${t("profile")}</div>
    <p class="faint">${t("profile_help")}</p>
    <textarea class="textarea mono" style="min-height:120px" placeholder=${t("profile_empty")} value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
    <div class="row" style="margin-top:8px">
      <button class="btn primary" disabled=${busy || text === data.text} onClick=${() => call("/api/profile", { method: "PUT", body: { text } })}>${t("save")}</button>
      <button class="btn" disabled=${busy} onClick=${() => call("/api/profile/update", { method: "POST" })}>${t("profile_update")}</button></div>
    ${data.proposal ? html`<div class="label" style="margin-top:12px">${t("profile_proposed")}</div>
      <pre class="prose" style="white-space:pre-wrap">${data.proposal}</pre>
      <button class="btn primary" disabled=${busy} onClick=${() => call("/api/profile/accept", { method: "POST" })}>${t("profile_accept")}</button>` : null}`;
}

function MemoryView({ toast }) {
  const [info, setInfo] = useState(null);
  const [note, setNote] = useState(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const load = () => api("/api/memory").then(setInfo).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const openNote = async (path) => {
    try { const n = await api(`/api/memory/note?path=${encodeURIComponent(path)}`); setNote(n); setText(n.text); }
    catch (e) { toast(e.message, "error"); }
  };
  const save = async () => {
    try { await api("/api/memory/note", { method: "PUT", body: { path: note.path, text } }); toast(t("saved")); load(); setNote({ ...note, text }); }
    catch (e) { toast(e.message, "error"); }
  };
  const search = async (e) => {
    e.preventDefault();
    if (!query.trim()) return setHits(null);
    try { setHits(await api(`/api/memory/search?q=${encodeURIComponent(query)}`)); } catch (err) { toast(err.message, "error"); }
  };
  const decide = async (taskId, accept, reject) => {
    try { await api(`/api/tasks/${taskId}/learn`, { method: "POST", body: { accept, reject } }); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!info) return html`<div class="empty">…</div>`;
  if (!info.enabled) return html`<div class="page"><${PreferencesCard} toast=${toast} />
    <div class="section"><${ProfileCard} toast=${toast} /></div><div class="section"><${DecisionsCard} toast=${toast} /></div>
    <p class="muted">${t("memory_off_help")}</p></div>`;
  const groups = ["profile", "project", "howto", "journal", "other"].map((k) => [k, info.notes.filter((n) => n.kind === k)]).filter(([, n]) => n.length);
  const prefix = info.folder ? `${info.folder}/` : "";
  return html`
    <div class="split ${note ? "has-selected" : ""}">
      <div class="list">
        <form class="list-head" onSubmit=${search}>
          <input class="input" style="flex:1" placeholder=${t("memory_search")} value=${query} onInput=${(e) => setQuery(e.target.value)} />
          <button class="btn">${t("search")}</button>
        </form>
        ${hits ? html`<div class="memory-group"><div class="label">${t("results")}</div>
          ${hits.map((h) => html`<button class="task-row" disabled=${!h.path.startsWith(prefix)} onClick=${() => openNote(h.path.slice(prefix.length))}>
            <span class="task-title">${h.link}</span><span class="faint">${h.score}</span>
            <span class="task-meta">${h.snippet.slice(0, 140)}</span></button>`)}
          ${hits.length ? null : html`<p class="muted">${t("no_results")}</p>`}</div>` : null}
        <div class="memory-group"><${PreferencesCard} toast=${toast} /></div>
        <div class="memory-group"><${DecisionsCard} toast=${toast} /></div>
        <div class="memory-group"><${ProfileCard} toast=${toast} /></div>
        ${info.pending.length ? html`<div class="memory-group"><div class="label">${t("learn")}</div>
          ${info.pending.map((p) => p.facts.map((f, i) => f.status === "proposed" ? html`<div class="card fact">
            <div>${f.fact}</div><div class="faint">${p.project} · ${p.prompt}</div>
            <div class="row"><button class="btn primary" onClick=${() => decide(p.task_id, [i], [])}>${t("remember")}</button>
              <button class="btn ghost" onClick=${() => decide(p.task_id, [], [i])}>${t("forget")}</button></div></div>` : null))}</div>` : null}
        ${groups.map(([kind, notes]) => html`<div class="memory-group"><div class="label">${t(`notes_${kind}`)}</div>
          ${notes.slice(0, kind === "journal" ? 14 : 200).map((n) => html`<button class="task-row ${note?.path === n.path ? "active" : ""}" onClick=${() => openNote(n.path)}>
            <span class="task-title">${n.title}</span><span class="faint">${ago(n.modified)}</span></button>`)}</div>`)}
      </div>
      ${note ? html`<div class="detail note-editor">
        <button class="btn ghost back" onClick=${() => setNote(null)}>← ${t("memory")}</button>
        <div class="row"><strong>${note.path}</strong><span class="spacer"></span>
          <button class="btn primary" disabled=${text === note.text} onClick=${save}>${t("save")}</button></div>
        <textarea class="textarea mono" value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
        <p class="faint">${t("memory_edit_help")}</p>
      </div>` : html`<div class="empty">${t("pick_note")}<br /><span class="faint">${info.describe}</span></div>`}
    </div>`;
}

// ---------------------------------------------------------------- usage ---

function Bars({ rows, value, label, title }) {
  const max = Math.max(1, ...rows.map(value));
  return html`<div class="hbars">${rows.map((r) => html`
    <div class="hbar" title=${title(r)}>
      <span class="hbar-label">${label(r)}</span>
      <span class="hbar-track"><span class="hbar-fill" style=${`width:${(100 * value(r)) / max}%`}></span></span>
      <span class="hbar-value">${value(r)}</span>
    </div>`)}</div>`;
}

function Columns({ rows, days }) {
  // One column per day of the period, empty days included, so gaps are visible.
  const byDay = Object.fromEntries(rows.map((r) => [r.day, r]));
  const list = [];
  for (let i = days - 1; i >= 0; i--) {
    const day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    list.push(byDay[day] || { day, calls: 0, minutes: 0 });
  }
  const max = Math.max(1, ...list.map((r) => r.calls));
  return html`<div class="cols">${list.map((r) => html`
    <div class="col" title=${`${r.day}: ${r.calls} · ${r.minutes} min`}>
      <span class="col-fill" style=${`height:${(100 * r.calls) / max}%`}></span></div>`)}</div>
    <div class="cols-axis faint"><span>${list[0].day.slice(5)}</span><span>${list[list.length - 1].day.slice(5)}</span></div>`;
}

const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function UsageView({ toast }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const load = () => api(`/api/usage?days=${days}`).then(setData).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, [days]);
  const apply = async (s) => {
    try { toast((await api("/api/settings/apply-suggestion", { method: "POST", body: s })).message); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!data) return html`<div class="empty">…</div>`;
  const calls = data.agents.reduce((n, a) => n + a.calls, 0);
  const ok = data.agents.reduce((n, a) => n + a.ok, 0);
  const minutes = data.agents.reduce((n, a) => n + a.minutes, 0);
  const limited = data.agents.reduce((n, a) => n + a.limited, 0);
  const tiles = [[t("calls"), calls], [t("agent_time"), `${Math.round(minutes)} min`],
    [t("success"), calls ? `${Math.round((100 * ok) / calls)}%` : "–"], [t("limits_hit"), limited]];
  return html`
    <div class="page">
      <div class="row" style="margin-bottom:16px">
        ${[7, 30, 90].map((d) => html`<button class="btn ${days === d ? "primary" : ""}" onClick=${() => setDays(d)}>${t("last_days", { days: d })}</button>`)}
      </div>
      <div class="tiles">${tiles.map(([k, v]) => html`<div class="card tile"><div class="label">${k}</div><div class="tile-value">${v}</div></div>`)}</div>
      ${calls ? html`
        <div class="label section">${t("calls_per_agent")}</div>
        <div class="card" style="margin-top:8px"><${Bars} rows=${data.agents} value=${(a) => a.calls} label=${(a) => a.agent}
          title=${(a) => `${a.agent}: ${a.calls} · ${Math.round((100 * a.ok) / a.calls)}% ok · ${a.minutes} min · ${t("limits_hit")}: ${a.limited}`} /></div>
        <div class="label section">${t("calls_per_day")}</div>
        <div class="card" style="margin-top:8px"><${Columns} rows=${data.daily} days=${days} /></div>
        <div class="label section">${t("projects")}</div>
        <div class="card" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("tasks")}</th><th>${t("col_done")}</th><th>${t("col_failed")}</th></tr>
          ${data.projects.map((p) => html`<tr><td>${p.project}</td><td>${p.tasks}</td><td>${p.done}</td><td>${p.failed}</td></tr>`)}
        </table></div>` : html`<p class="muted">${t("no_usage")}</p>`}
      ${data.suggestions?.length ? html`<div class="label section">${t("proposals")}</div>
        ${data.suggestions.map((s) => html`<div class="card row" style="margin-top:8px">
          <span style="flex:1">${t("proposal_text", { project: s.project, agent: s.agent, current: s.current })}<br /><span class="faint">${s.reason}</span></span>
          <button class="btn primary" onClick=${() => apply(s)}>${t("apply")}</button></div>`)}` : null}
      ${data.agents_by_project?.length ? html`<div class="label section">${t("agent_skill")}</div>
        <div class="card" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("agent")}</th><th>${t("tasks")}</th><th>${t("success")}</th><th>${t("tests")}</th><th>${t("review_ok")}</th><th>${t("quality")}</th><th>min</th></tr>
          ${data.agents_by_project.map((r) => html`<tr><td>${r.project}</td><td>${r.agent}</td><td>${r.tasks}</td>
            <td>${Math.round(r.success * 100)}%</td><td>${r.tests == null ? "–" : `${Math.round(r.tests * 100)}%`}</td>
            <td>${r.approved == null ? "–" : `${Math.round(r.approved * 100)}%`}</td>
            <td title=${[r.reverted && `${t("sc_rolled_back")}: ${r.reverted}`, r.regressions && `${t("sc_regressions")}: ${r.regressions}`, r.review_rounds && `${t("sc_rounds")}: ${r.review_rounds}`].filter(Boolean).join(" · ")}>${Math.round(r.quality * 100)}%</td>
            <td>${r.minutes}</td></tr>`)}
        </table></div>` : null}
      ${data.scorecard?.some((w) => w.tasks) ? html`<div class="label section">${t("scorecard")}</div>
        <div class="card" style="margin-top:8px;overflow-x:auto"><table class="table">
          <tr><th>${t("sc_week")}</th><th>${t("tasks")}</th><th>${t("success")}</th><th>${t("col_discarded")}</th><th>${t("sc_rolled_back")}</th>
            <th>${t("sc_rescue")}</th><th>${t("sc_rounds")}</th><th>${t("sc_minutes")}</th><th>${t("incidents")}</th><th>${t("sc_regressions")}</th></tr>
          ${data.scorecard.map((w) => html`<tr><td class="mono" style="white-space:nowrap">${w.week}</td><td>${w.tasks}</td><td>${pct(w.success)}</td><td>${w.discarded}</td>
            <td>${w.rolled_back}</td><td>${pct(w.retry_rescue)}</td><td>${w.review_rounds ?? "–"}</td><td>${w.minutes_per_task ?? "–"}</td>
            <td style=${w.incidents ? "color:var(--danger)" : ""}>${w.incidents}</td><td style=${w.regressions ? "color:var(--warn)" : ""}>${w.regressions}</td></tr>`)}
        </table></div>` : null}
    </div>`;
}

// ------------------------------------------------------------------ app ---

// ------------------------------------------------- desktop title bar ---

// In Dia's own window (Qt, without the system frame) the page is the title bar:
// the sidebar's top and the top bar drag the window, a double click maximizes it,
// the edges resize it, and the three buttons sit at the top right. The window
// hears it through console messages (see dia/appwindow.py).
const FRAMELESS = navigator.userAgent.includes("DiaDesktop/frameless");
const windowCall = (action) => console.log(`dia-window:${action}`);
const NOT_DRAG = "button, a, input, select, textarea, label, [data-no-drag]";
if (FRAMELESS) {
  document.documentElement.classList.add("frameless");
  let last = { at: 0, x: 0, y: 0 };
  document.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const edge = e.target.closest("[data-edge]");
    if (edge) { e.preventDefault(); windowCall(`resize:${edge.dataset.edge}`); return; }
    if (!e.target.closest("[data-drag]") || e.target.closest(NOT_DRAG)) return;
    e.preventDefault();
    const double = e.timeStamp - last.at < 400 && Math.abs(e.screenX - last.x) < 4 && Math.abs(e.screenY - last.y) < 4;
    last = double ? { at: 0, x: 0, y: 0 } : { at: e.timeStamp, x: e.screenX, y: e.screenY };
    windowCall(double ? "maximize" : "move");
  });
}

function WindowControls() {
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    window.diaWindowState = (state) => {
      setMaximized(state === "maximized");
      document.documentElement.classList.toggle("maximized", state === "maximized");
    };
  }, []);
  if (!FRAMELESS) return null;
  return html`<div class="win-controls" data-no-drag>
    <button class="win-btn" title=${t("win_minimize")} onClick=${() => windowCall("minimize")}>
      <svg viewBox="0 0 12 12"><path d="M2 6.5h8" /></svg></button>
    <button class="win-btn" title=${t(maximized ? "win_restore" : "win_maximize")} onClick=${() => windowCall("maximize")}>
      ${maximized
        ? html`<svg viewBox="0 0 12 12"><path d="M3.5 4.5h4v4h-4z M5 4.5V3h4v4H7.5" /></svg>`
        : html`<svg viewBox="0 0 12 12"><path d="M2.5 2.5h7v7h-7z" /></svg>`}</button>
    <button class="win-btn close" title=${t("win_close")} onClick=${() => windowCall("close")}>
      <svg viewBox="0 0 12 12"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7" /></svg></button>
  </div>`;
}

const WindowEdges = () => (FRAMELESS ? html`<div class="edges">
  ${["top", "bottom", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right"].map((edge) => html`<div class="edge edge-${edge}" data-edge=${edge}></div>`)}
</div>` : null);

function Login({ onToken }) {
  const [value, setValue] = useState("");
  return html`
    ${FRAMELESS ? html`<div class="login-bar" data-drag><span class="spacer"></span><${WindowControls} /></div><${WindowEdges} />` : null}
    <div class="login"><div class="card">
      <div class="brand"><img class="brand-logo" src="/static/icons/dia.svg" alt="" />Dia</div>
      <strong>${t("login_title")}</strong>
      <span class="muted">${t("login_help")}</span>
      <input class="input" placeholder=${t("token")} value=${value} onInput=${(e) => setValue(e.target.value)} />
      <button class="btn primary" onClick=${() => onToken(value.trim())}>${t("connect")}</button>
    </div></div>`;
}

function App() {
  const [authed, setAuthed] = useState(Boolean(token));
  const [view, setView] = useState(START_VIEW || "tasks");
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(START_TASK);
  const [connected, setConnected] = useState(false);
  const [voice, setVoice] = useState("idle");
  const [looking, setLooking] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [, rerender] = useState(0);

  const toast = useCallback((text, kind = "info") => {
    const id = Math.random();
    setToasts((all) => [...all, { id, text, kind }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4000);
  }, []);

  const loadTasks = useCallback(() => api("/api/tasks").then(setTasks).catch((e) => {
    if (/token/.test(e.message)) { store(TOKEN_KEY, null); token = ""; setAuthed(false); }
  }), []);
  const loadStatus = useCallback(() => api("/api/status").then((s) => {
    if (s.language !== lang) { lang = s.language; rerender((n) => n + 1); }
    setStatus(s);
  }).catch(() => {}), []);

  useEffect(() => { applyTheme(store(THEME_KEY) || "dark"); }, []);
  // The desktop window's tray menu (and links like #view=chat) switch the tab.
  useEffect(() => {
    window.diaNavigate = (name, task) => {
      if (task) { setSelected(task); setView("tasks"); } else if (VIEWS.includes(name)) setView(name);
    };
    const onHash = () => {
      const name = hashParam("view");
      if (VIEWS.includes(name)) setView(name);
      const task = hashParam("task");
      if (task) { setSelected(task); setView("tasks"); }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { if (authed) { loadTasks(); loadStatus(); } }, [authed]);

  // Live updates: task changes, CI/review news and the voice state.
  useEffect(() => {
    if (!authed) return;
    let ws, retry, closed = false;
    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${scheme}://${location.host}/ws?token=${encodeURIComponent(token)}`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(connect, 2000); };
      ws.onmessage = (message) => {
        const data = JSON.parse(message.data);
        if (data.type === "task") {
          setTasks((all) => [data.task, ...all.filter((x) => x.id !== data.task.id)]
            .sort((a, b) => b.created_at.localeCompare(a.created_at)));
          window.dispatchEvent(new CustomEvent("dia-task", { detail: data.task }));
        } else if (data.type === "event" && data.kind === "voice") {
          setVoice(data.message.split(":")[0]);
        } else if (data.type === "event" && data.kind === "camera") {
          if (data.message === "looking") toast(`📷 ${t("camera_on")}`);
          else loadStatus();
        } else if (data.type === "event" && data.kind === "quiet") {
          loadStatus();
        } else if (data.type === "event" && data.kind === "screen") {
          setLooking(data.message === "looking");
          if (data.message === "looking") toast(`👁 ${t("screen_looking")}`);
          else loadStatus();
        } else if (data.type === "event" && (data.kind === "stop" || data.kind === "resume")) {
          loadStatus();
          toast(data.kind === "stop" ? `🛑 ${t("stopped_all")}` : t("resumed"), data.kind === "stop" ? "error" : "info");
        } else if (data.type === "audit") {
          window.dispatchEvent(new CustomEvent("dia-audit", { detail: data.entry }));
        } else if (data.type === "event" && data.kind === "mission" && !/^(ready|failed|paused|done|integration)/.test(data.message)) {
          // step-by-step progress shows in Mission Control; only outcomes pop up
        } else if (data.type === "event") {
          toast(`${data.kind.toUpperCase()} · ${data.message}`);
        } else if (data.type === "error") {
          toast(data.message, "error");
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); ws && ws.close(); };
  }, [authed]);

  if (!authed) {
    return html`<${Login} onToken=${(value) => { token = store(TOKEN_KEY, value); setAuthed(Boolean(value)); }} />`;
  }

  const toggleScreen = async () => {
    try { await api("/api/screen", { method: "POST", body: { on: !status.screen } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const toggleCamera = async () => {
    try { await api("/api/camera", { method: "POST", body: { on: !status.camera } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const toggleQuiet = async () => {
    try { await api("/api/quiet", { method: "POST", body: { on: !status.quiet } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const stopAll = async () => {
    if (!confirm(t("stop_confirm"))) return;
    try { await api("/api/stop", { method: "POST" }); loadStatus(); } catch (e) { toast(e.message, "error"); }
  };
  const resumeAll = async () => {
    try { await api("/api/resume", { method: "POST" }); loadStatus(); } catch (e) { toast(e.message, "error"); }
  };
  const toggleVoice = async () => {
    try { await api("/api/voice/toggle", { method: "POST" }); } catch (e) { toast(e.message, "error"); }
  };
  const active = tasks.filter((x) => ["running", "queued", "waiting"].includes(x.status)).length;
  const nav = [["tasks", active || ""], ["missions", ""], ["chat", ""], ["cli", ""], ["memory", ""], ["status", ""], ["usage", ""], ["settings", ""]];
  const open = (id) => { setSelected(id); setView("tasks"); };

  return html`
    <div class="shell">
      <aside class="sidebar">
        <div class="brand" data-drag><img class="brand-logo" src="/static/icons/dia.svg" alt="" />Dia${status?.version ? html`<span class="brand-version">${status.version}</span>` : null}</div>
        ${nav.map(([key, count]) => html`
          <button class="nav-item ${view === key ? "active" : ""}" onClick=${() => setView(key)}>
            ${t(key)}<span class="nav-count">${count}</span></button>`)}
        <div class="sidebar-foot">
          ${status && !status.device ? html`<button class="mic ${voice}" onClick=${toggleVoice} title="dia voice toggle">
            <span class="mic-orb"></span><span class="mic-label">${t(`voice_${voice}`) || t("voice_idle")}</span></button>` : null}
          ${status ? html`<button class="quiet ${status.screen ? "on" : ""} ${looking ? "looking" : ""}" title=${t("screen_help")} onClick=${toggleScreen}>
            ${status.screen ? "👁" : "◌"}<span class="mic-label">${status.screen ? t("screen_on") : t("screen_off")}</span></button>` : null}
          ${status ? html`<button class="quiet ${status.camera ? "on" : ""}" title=${t("camera_help")} onClick=${toggleCamera}>
            ${status.camera ? "📷" : "◌"}<span class="mic-label">${status.camera ? t("camera_on") : t("camera_off")}</span></button>` : null}
          ${status ? html`<button class="quiet ${status.quiet ? "on" : ""}" title=${t("quiet_help")} onClick=${toggleQuiet}>
            ${status.quiet ? "🔇" : status.quiet_hours ? "🌙" : "🔈"}<span class="mic-label">${status.quiet ? t("quiet_on") : status.quiet_hours ? t("quiet_hours_on") : t("quiet_off")}</span></button>` : null}
          <div class="conn"><span class="conn-dot ${connected ? "on" : ""}"></span>${connected ? t("connected") : t("offline")}
            ${IN_APP ? html` · <a href="#" onClick=${(e) => { e.preventDefault(); location.href = APP_HOME; }}>${t("change_server")}</a>` : null}</div>
        </div>
      </aside>
      <main class="main">
        <div class="topbar" data-drag><h1>${t(view)}</h1><span class="spacer"></span>
          ${status ? html`<span class="faint hide-phone">${status.agents.filter((a) => a.ok).length}/${status.agents.length} ${t("agents").toLowerCase()}</span>` : null}
          ${status && !status.halted ? html`<button class="btn danger stop-btn" title=${t("stop_help")} onClick=${stopAll}>■ ${t("stop")}</button>` : null}
        <${WindowControls} />
        </div>
        ${status?.halted ? html`<div class="halted-bar">🛑 ${t("halted")}
          <button class="btn primary" onClick=${resumeAll}>${t("resume_btn")}</button></div>` : null}
        <div class="content">
          ${view === "tasks" ? html`<${TasksView} tasks=${tasks} status=${status} selected=${selected} select=${setSelected} toast=${toast} reload=${loadTasks} />` : null}
          ${view === "chat" ? html`<${ChatView} open=${open} toast=${toast} />` : null}
          ${view === "cli" ? html`<${CliView} toast=${toast} />` : null}
          ${view === "status" ? html`<${StatusView} status=${status} reload=${loadStatus} toast=${toast} />` : null}
          ${view === "usage" ? html`<${UsageView} toast=${toast} />` : null}
          ${view === "memory" ? html`<${MemoryView} toast=${toast} />` : null}
          ${view === "missions" ? html`<${MissionsView} status=${status} toast=${toast} open=${open} />` : null}
          ${view === "settings" ? html`<${SettingsView} toast=${toast} device=${status?.device} full=${status?.device_full} />` : null}
        </div>
      </main>
      <div class="toasts">${toasts.map((x) => html`<div key=${x.id} class="toast ${x.kind}">${x.text}</div>`)}</div>
      <${WindowEdges} />
    </div>`;
}

render(html`<${App} />`, document.getElementById("app"));

// Installable app (PWA); service workers need https or localhost.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
