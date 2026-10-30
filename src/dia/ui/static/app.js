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
    desktop_tab: "Desktop & services", security_tab: "Security", about_tab: "About Dia",
    about_tagline: "A personal assistant that orchestrates coding agents across your repositories.",
    about_author: "Author", about_website: "Website", about_github: "GitHub", about_email: "Email",
    about_license: "License", about_components: "Components", about_instance: "This copy",
    about_config: "Config", about_data: "Data",
    settings_help: "Who Dia is, how she works, and how she connects to your world.",
    settings_you: "You and Dia", settings_work: "Work", settings_connect: "Connect", settings_computer: "This computer",
    s_identity: "Identity", s_skills_brief: "Skills and briefing", s_conversation: "Conversation",
    s_defaults: "Defaults", s_review_retry: "Review and retries", s_task_limits: "Task limits",
    s_plans_missions: "Plans and missions", s_specialists: "Specialists", s_quality: "Quality gates",
    s_watchers: "Watchers", s_system_tidy: "Computer and tidy", s_suggestions: "Suggestions and goals",
    s_mail_home: "Mail and home", s_senses: "Screen and camera", s_publish: "Publishing",
    s_vault: "Vault", s_memory_search: "Search and learning", s_notify_policy: "Quiet hours and budget",
    s_security_hosts: "Your machines", s_sandbox: "Agent sandbox",
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
    local_brain_help: "Understands your requests on this computer, free and private; Claude stays as the fallback. Install: sudo pacman -S ollama; ollama pull qwen3.5:4b  (best measured 25.10.2026: 8/9)",
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
    inbox: "Inbox", workspace: "Personal space", nav_work: "Workspace", nav_system: "Knowledge and system",
    menu_collapse: "Collapse menu", menu_expand: "Expand menu", talk_to_dia: "Talk to Dia", voice_ready: "Voice ready to talk",
    senses: "Dia's senses", agents_ready: "{ok}/{all} agents", local_dia: "Dia on this computer",
    inbox_waiting: "Waiting for your decision: {n}", inbox_clear: "Nothing waits for you. Dia handles the rest.",
    waiting_for_you: "Waiting for you", working_now: "Working now", nothing_running: "No agent is working right now.",
    ready_to_merge: "Ready to merge", plan_to_approve: "Plan to approve", ci_failed: "CI failed",
    comments_waiting: "Review comments", running_count: "{n} running",
    plan_steps_count: "{n} steps", needs_override: "Has blockers: decide in the task",
    summary_tab: "Summary", changes_tab: "Changes",
    filter_tasks: "Filter tasks", earlier: "Earlier", open_view: "Open",
    theme_app: "App theme", theme_app_help: "Dia's window and the browser.", theme_phone: "Phone theme",
    theme_phone_help: "The phone app and Dia in the phone's browser.", theme_widget: "KDE widget theme",
    theme_widget_help: "The widget in the panel and its popup.", theme_same: "Same as the app ({name})",
    theme_own: "Its own", custom_theme: "yours",
    budget_calls_short: "Calls", budget_minutes_short: "Minutes", priority: "Priority",
    cli_new: "New session", cli_new_help: "Starts the agent you pick, with its model, in the project's folder. It works there as in a terminal; you answer here, and Release gives you the command to go on in a terminal.",
    cli_new_first: "The first message, e.g. “look at the failing test in the save system”", cli_new_start: "Start", cli_new_starting: "Starting…",
    cli_new_started: "The session is on: answer below.", cli_new_working: "The agent is working on the first answer…",
    cli_new_failed: "The session did not start", cancel: "Cancel", cli_new_here: "started in Dia", cli_new_none: "No Claude Code, Codex or Cursor Agent is configured (Settings → Agents).",
    search: "Search", palette_hint: "Go to, find a task, or do something…", nothing_found: "Nothing found.", kind_view: "view", kind_action: "action", kind_task: "task", quiet_on_action: "Quiet mode on", quiet_off_action: "Quiet mode off",
    files_changed: "files changed: {n}", diff_file_list: "Changed files", diff_added_file: "added",
    diff_deleted_file: "deleted", diff_renamed_file: "renamed", diff_modified_file: "modified",
    diff_binary: "Binary file — no text preview", diff_empty: "No changes in this commit.",
    diff_collapse: "Collapse", diff_expand: "Expand",
    split_resize: "Drag to resize · double-click resets",
    mission: "Mission", agent_unavailable: "unavailable", calls_today: "24 h: {n} calls · {min} min", idle_today: "no calls in 24 h",
    more: "More", talk_phone: "Conversation", talk_hint: "Tap the microphone and speak", talk_listening: "Listening…",
    talk_thinking: "Thinking…", talk_speaking: "Speaking… tap to interrupt", talk_unheard: "No speech recognised. Try again.",
    talk_unsupported: "This browser can't take dictation here. Write instead: the keyboard's microphone works too.",
    talk_type: "Write instead", talk_end: "End the conversation", talk_mic: "Microphone",
    talk_denied: "No access to the microphone: allow it in the browser's or the app's settings.", talk_local: "heard and spoken on your computer",
    today: "Today", yesterday: "Yesterday",
    cli_commands: "Commands", cli_commands_help: "The same slash commands as in this agent's own CLI. Type / to pick one, or send it like in a terminal.",
    cli_web: "Web access", cli_cmd_hint: "Type / for this agent's commands",
    cli_unknown: "Unknown command. Try /help.",
    cli_model_set: "Next replies use {name}.",
    cli_mode_set: "This session is now {mode}.",
    cli_status_text: "{kind} in {cwd}\nmodel: {model}\nmode: {mode}\nweb: {web}\nresume: {resume}",
    f_check_updates: "Look for Dia updates (tray)",
    f_max_diff: "Most characters of a diff sent to the reviewer",
    f_chat_default: "Default chat engine (dia, or a provider id)",
    f_chat_ollama: "Ollama address for chat models",
    f_chat_timeout: "Chat timeout (seconds)",
    f_howtos_dir: "How-tos folder",
    f_create_notes: "Create missing project notes",
    f_journal_on: "Write a journal of what agents did",
    f_snippet_chars: "Snippet length when searching notes",
    f_howto_results: "How-tos found per search",
    f_index_per_search: "Notes in the semantic index per search",
    f_routing_rules: "Routing rules (match => agent, or project:match => agent)",
    f_routing_min: "Auto-routing after this many tasks",
    f_ui_enabled: "Local web UI",
    f_ga_nodes: "Godot: most nodes in a scene",
    f_ga_depth: "Godot: deepest node tree",
    f_ga_lights: "Godot: most lights in a scene",
    f_ga_texture: "Godot: largest texture (px)",
    s_chat_models: "Direct chat", s_godot: "Godot analysis", s_computer_alerts: "Alerts",
    s_lab: "Lab", s_tidy: "Tidy",
    status_now: "Now", status_computer: "Computer", status_work: "Work", status_about: "About",
    jump_to: "Jump to",
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
    desktop_tab: "Pulpit i usługi", security_tab: "Bezpieczeństwo", about_tab: "O programie",
    about_tagline: "Osobista asystentka, która prowadzi agentów kodujących w Twoich repozytoriach.",
    about_author: "Autor", about_website: "Strona", about_github: "GitHub", about_email: "E-mail",
    about_license: "Licencja", about_components: "Komponenty", about_instance: "Ta kopia",
    about_config: "Konfiguracja", about_data: "Dane",
    settings_help: "Kim jest Dia, jak pracuje i jak łączy się z Twoim światem.",
    settings_you: "Ty i Dia", settings_work: "Praca", settings_connect: "Połączenia", settings_computer: "Ten komputer",
    s_identity: "Tożsamość", s_skills_brief: "Umiejętności i briefing", s_conversation: "Rozmowa",
    s_defaults: "Domyślne", s_review_retry: "Recenzja i ponowienia", s_task_limits: "Limity zadań",
    s_plans_missions: "Plany i misje", s_specialists: "Specjaliści", s_quality: "Bramki jakości",
    s_watchers: "Obserwatorzy", s_system_tidy: "Komputer i porządki", s_suggestions: "Sugestie i cele",
    s_mail_home: "Poczta i dom", s_senses: "Ekran i kamera", s_publish: "Publikacja",
    s_vault: "Skarbiec", s_memory_search: "Szukanie i uczenie", s_notify_policy: "Ciche godziny i budżet",
    s_security_hosts: "Twoje maszyny", s_sandbox: "Piaskownica agentów",
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
    local_brain_help: "Rozumie Twoje polecenia na tym komputerze, za darmo i prywatnie; Claude zostaje jako zapas. Instalacja: sudo pacman -S ollama; ollama pull qwen3.5:4b  (najlepszy wynik 25.10.2026: 8/9)",
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
    inbox: "Skrzynka", workspace: "Osobista przestrzeń", nav_work: "Przestrzeń pracy", nav_system: "Wiedza i system",
    menu_collapse: "Zwiń menu", menu_expand: "Rozwiń menu", talk_to_dia: "Porozmawiaj z Dią", voice_ready: "Głos gotowy do rozmowy",
    senses: "Zmysły Dii", agents_ready: "agenci: {ok}/{all}", local_dia: "Dia na tym komputerze",
    inbox_waiting: "Czeka na Twoją decyzję: {n}", inbox_clear: "Nic nie czeka na Twoją decyzję. Resztą Dia zajmuje się sama.",
    waiting_for_you: "Czeka na Ciebie", working_now: "Teraz pracuje", nothing_running: "Żaden agent teraz nie pracuje.",
    ready_to_merge: "Gotowe do scalenia", plan_to_approve: "Plan do akceptacji", ci_failed: "CI nie przeszło",
    comments_waiting: "Uwagi z recenzji", running_count: "w toku: {n}",
    plan_steps_count: "kroki: {n}", needs_override: "Są blokady: zdecyduj w zadaniu",
    summary_tab: "Podsumowanie", changes_tab: "Zmiany",
    filter_tasks: "Filtruj zadania", earlier: "Wcześniej", open_view: "Otwórz",
    theme_app: "Motyw aplikacji", theme_app_help: "Okno Dii i przeglądarka.", theme_phone: "Motyw na telefonie",
    theme_phone_help: "Aplikacja na telefonie i Dia w przeglądarce telefonu.", theme_widget: "Motyw widżetu KDE",
    theme_widget_help: "Widżet w panelu i jego okienko.", theme_same: "Jak aplikacja ({name})",
    theme_own: "Własny", custom_theme: "Twój",
    budget_calls_short: "Wywołania", budget_minutes_short: "Minuty", priority: "Priorytet",
    cli_new: "Nowa sesja", cli_new_help: "Uruchamia wybranego agenta z jego modelem w folderze projektu. Pracuje tam jak w terminalu; odpowiadasz tutaj, a Zwolnij poda polecenie, by ciągnąć dalej w terminalu.",
    cli_new_first: "Pierwsza wiadomość, np. „zajrzyj do testu systemu zapisu, który nie przechodzi”", cli_new_start: "Rozpocznij", cli_new_starting: "Uruchamiam…",
    cli_new_started: "Sesja działa: odpowiadaj poniżej.", cli_new_working: "Agent pracuje nad pierwszą odpowiedzią…",
    cli_new_failed: "Sesja nie wystartowała", cancel: "Anuluj", cli_new_here: "rozpoczęta w Dii", cli_new_none: "Nie skonfigurowano Claude Code, Codex ani Cursor Agent (Ustawienia → Agenci).",
    search: "Szukaj", palette_hint: "Przejdź do, znajdź zadanie albo zrób coś…", nothing_found: "Nic nie znaleziono.", kind_view: "widok", kind_action: "akcja", kind_task: "zadanie", quiet_on_action: "Włącz tryb cichy", quiet_off_action: "Wyłącz tryb cichy",
    files_changed: "zmienione pliki: {n}", diff_file_list: "Zmienione pliki", diff_added_file: "nowy",
    diff_deleted_file: "usunięty", diff_renamed_file: "przeniesiony", diff_modified_file: "zmieniony",
    diff_binary: "Plik binarny — bez podglądu tekstu", diff_empty: "Brak zmian w tym commitcie.",
    diff_collapse: "Zwiń", diff_expand: "Rozwiń",
    split_resize: "Przeciągnij, by zmienić szerokość · podwójne kliknięcie przywraca domyślną",
    mission: "Misja", agent_unavailable: "niedostępny", calls_today: "24 h: wywołania {n} · {min} min", idle_today: "brak wywołań w 24 h",
    more: "Więcej", talk_phone: "Rozmowa", talk_hint: "Dotknij mikrofonu i mów", talk_listening: "Słucham…",
    talk_thinking: "Myślę…", talk_speaking: "Mówię… dotknij, żeby przerwać", talk_unheard: "Nie rozpoznano mowy. Spróbuj jeszcze raz.",
    talk_unsupported: "Ta przeglądarka nie przyjmuje tu dyktowania. Napisz: mikrofon klawiatury też działa.",
    talk_type: "Pisz zamiast mówić", talk_end: "Zakończ rozmowę", talk_mic: "Mikrofon",
    talk_denied: "Brak dostępu do mikrofonu: zezwól na niego w ustawieniach przeglądarki lub aplikacji.", talk_local: "słucha i mówi Twój komputer",
    today: "Dzisiaj", yesterday: "Wczoraj",
    cli_commands: "Komendy", cli_commands_help: "Te same komendy z ukośnikiem co w CLI tego agenta. Wpisz /, żeby wybrać, albo wyślij jak w terminalu.",
    cli_web: "Dostęp do sieci", cli_cmd_hint: "Wpisz / po komendy tego agenta",
    cli_unknown: "Nieznana komenda. Spróbuj /help.",
    cli_model_set: "Kolejne odpowiedzi użyją {name}.",
    cli_mode_set: "Ta sesja jest teraz: {mode}.",
    cli_status_text: "{kind} w {cwd}\nmodel: {model}\ntryb: {mode}\nsieć: {web}\nwznowienie: {resume}",
    f_check_updates: "Szukaj aktualizacji Dia (zasobnik)",
    f_max_diff: "Najwięcej znaków diffa dla recenzenta",
    f_chat_default: "Domyślny silnik czatu (dia albo id dostawcy)",
    f_chat_ollama: "Adres Ollamy dla modeli czatu",
    f_chat_timeout: "Limit czasu czatu (sekundy)",
    f_howtos_dir: "Folder sposobów (how-to)",
    f_create_notes: "Twórz brakujące notatki projektów",
    f_journal_on: "Pisz dziennik tego, co zrobili agenci",
    f_snippet_chars: "Długość fragmentu przy szukaniu notatek",
    f_howto_results: "Sposobów na wyszukiwanie",
    f_index_per_search: "Notatek z indeksu semantycznego na szukanie",
    f_routing_rules: "Reguły routingu (wzorzec => agent albo projekt:wzorzec => agent)",
    f_routing_min: "Auto-routing po tylu zadaniach",
    f_ui_enabled: "Lokalny interfejs WWW",
    f_ga_nodes: "Godot: najwięcej węzłów w scenie",
    f_ga_depth: "Godot: najgłębsze drzewo węzłów",
    f_ga_lights: "Godot: najwięcej świateł w scenie",
    f_ga_texture: "Godot: największa tekstura (px)",
    s_chat_models: "Czat wprost", s_godot: "Analiza Godota", s_computer_alerts: "Alerty",
    s_lab: "Laboratorium", s_tidy: "Porządki",
    status_now: "Teraz", status_computer: "Komputer", status_work: "Praca", status_about: "O Dia",
    jump_to: "Przejdź do",
  },
};
let lang = "en";
const t = (key, vars) => {
  const text = (STRINGS[lang] || STRINGS.en)[key] || STRINGS.en[key] || key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? vars[name] : m)) : text;
};
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const localeOf = () => (lang === "pl" ? "pl-PL" : "en-GB");

function parseWhen(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    const d = new Date(value < 1e12 ? value * 1000 : value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const raw = String(value).trim();
  if (!raw) return null;
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const n = Number(raw);
    const d = new Date(n < 1e12 ? n * 1000 : n);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime())) return d;
  const d2 = new Date(raw.replace(/\s*\([^)]*\)\s*$/, ""));
  return Number.isNaN(d2.getTime()) ? null : d2;
}

function stamp(value) {
  const d = parseWhen(value);
  if (!d) return "";
  return d.toLocaleString(localeOf(), {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function dayKey(value) {
  const d = parseWhen(value);
  if (!d) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayLabel(value) {
  const d = parseWhen(value);
  if (!d) return "";
  const today = new Date();
  const yday = new Date(today);
  yday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return t("today");
  if (d.toDateString() === yday.toDateString()) return t("yesterday");
  return d.toLocaleDateString(localeOf(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function MessageList({ messages, open, pendingPlan, send }) {
  let lastDay = "";
  return messages.map((m, i) => {
    const day = dayKey(m.at);
    const sep = Boolean(day) && day !== lastDay;
    if (day) lastDay = day;
    const mine = m.from === "me" || m.role === "user";
    const system = m.from === "system" || m.role === "system";
    return html`<div key=${`${day}-${i}`} class=${`msg-block ${system ? "is-system" : mine ? "is-me" : "is-dia"}`}>
      ${sep ? html`<div class="day-sep">${dayLabel(m.at)}</div>` : null}
      <div class=${`msg ${system ? "system" : mine ? "me" : "dia"}`}>
        <${RichText} text=${m.text} class="" />
        ${m.task && open ? html`<div class="chip"><button class="btn" onClick=${() => open(m.task)}>${t("open_task")}</button></div>` : null}
        ${m.plan && pendingPlan === m.plan && send ? html`<div class="chip row">
          <button class="btn primary" onClick=${() => send(t("yes"))}>${t("run_plan")}</button>
          <button class="btn" onClick=${() => send(t("no"))}>${t("discard")}</button></div>` : null}
        ${m.at ? html`<time class="msg-meta" datetime=${parseWhen(m.at)?.toISOString() || ""}>${stamp(m.at)}</time>` : null}
      </div>
    </div>`;
  });
}

// ------------------------------------------------------------------- api ---

const TOKEN_KEY = "dia-token";
// Inside the Android/iOS app (mobile/): its pairing screen, to switch to another Dia.
const IN_APP = navigator.userAgent.includes("DiaApp");
const APP_HOME = /iPhone|iPad|iPod/.test(navigator.userAgent)
  ? "capacitor://localhost/index.html?reset=1" : "https://localhost/index.html?reset=1";
const THEME_KEY = "dia-theme";
let onPhone = false;  // a paired device: its own theme may differ from the app's
const SIDEBAR_KEY = "dia-sidebar";
const SPLIT_SIDEBAR = "dia-split-sidebar";
const SPLIT_TASKS = "dia-split-tasks";
const SPLIT_MISSIONS = "dia-split-missions";
const SPLIT_MEMORY = "dia-split-memory";
const SPLIT_CHAT = "dia-split-chat";
const SPLIT_CLI = "dia-split-cli";
const SPLIT_INBOX = "dia-split-inbox";
const SPLIT_SETTINGS = "dia-split-settings";

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* storage may be unavailable; the UI still works */ }
  return value;
}

function loadSplitWidth(key, fallback, min, max) {
  const n = Number(store(key));
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}

/** Remembered pane width + a vertical drag handle (like an IDE splitter). */
function useSplitWidth(key, fallback, min, max) {
  const [width, setWidth] = useState(() => loadSplitWidth(key, fallback, min, max));
  const commit = useCallback((next) => {
    const clamped = Math.min(max, Math.max(min, Math.round(next)));
    setWidth(clamped);
    store(key, String(clamped));
    return clamped;
  }, [key, min, max]);
  return [width, setWidth, commit];
}

/** Vertical drag handle. `reverse` when the sized pane sits to the right of the bar. */
function VSplitter({ width, setWidth, commit, min, max, def, reverse = false }) {
  const live = useRef(width);
  live.current = width;
  const drag = useRef(null);
  const [active, setActive] = useState(false);
  const ceiling = () => Math.min(max, Math.floor(window.innerWidth * 0.55));
  const apply = (delta) => {
    const next = Math.min(ceiling(), Math.max(min, live.current + (reverse ? -delta : delta)));
    live.current = next;
    setWidth(next);
    return next;
  };

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, w: live.current };
    live.current = drag.current.w;
    setActive(true);
    document.body.classList.add("is-resizing");
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    live.current = drag.current.w;
    apply(e.clientX - drag.current.x);
  };
  const end = () => {
    if (!drag.current) return;
    drag.current = null;
    setActive(false);
    document.body.classList.remove("is-resizing");
    commit(live.current);
  };
  const reset = () => {
    live.current = def;
    commit(def);
  };
  return html`<div class=${`vsplit${active ? " active" : ""}`} role="separator" aria-orientation="vertical"
    aria-valuenow=${Math.round(width)} aria-valuemin=${min} aria-valuemax=${max}
    aria-label=${t("split_resize")} title=${t("split_resize")} tabindex="0"
    onPointerDown=${onPointerDown} onPointerMove=${onPointerMove}
    onPointerUp=${end} onPointerCancel=${end} onDblClick=${reset}
    onKeyDown=${(e) => {
      const step = e.shiftKey ? 40 : 16;
      if (e.key === "ArrowLeft") { e.preventDefault(); commit(width + (reverse ? step : -step)); }
      if (e.key === "ArrowRight") { e.preventDefault(); commit(width + (reverse ? -step : step)); }
      if (e.key === "Home") { e.preventDefault(); reset(); }
    }} />`;
}

// What the address asks for (#token=...&view=chat&task=ID), read before the
// token is wiped from it: the desktop window and its tray open a given tab.
const VIEWS = ["inbox", "tasks", "missions", "chat", "cli", "memory", "status", "usage", "settings"];
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

async function api(path, { method = "GET", body, raw } = {}) {
  const response = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}),
      ...(raw ? { "Content-Type": raw.type } : {}) },
    body: raw || (body ? JSON.stringify(body) : undefined),
  });
  const type = response.headers.get("Content-Type") || "";
  const data = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error((data && data.error) || data || response.statusText);
  return data;
}

function applyTheme(name) {
  const link = document.getElementById("theme");
  const href = `/themes/${encodeURIComponent(name)}.css`;
  store(THEME_KEY, name);
  if (link.getAttribute("href") === href) { paintIcon(); return; }  // loaded with the page
  link.onload = paintIcon;  // the new theme's accent colours Dia's icon
  link.href = href;
}

// ------------------------------------------------------------ Dia's icon ---
// The rings of icons/dia.svg, their gradient made from the theme's accent:
// lighter, the accent itself, darker, darkest.
const LOGO_MIX = [[0, 0.45, 255], [0.46, 1, 0], [0.72, 0.7, 0], [1, 0.35, 0]];  // offset, accent share, mixed with

function logoSvg(stops, id = "dia") {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">${
    stops.map(([offset, color]) => `<stop offset="${offset}" stop-color="${color}"/>`).join("")
  }</linearGradient></defs><circle cx="256" cy="256" r="208" fill="none" stroke="url(#${id})" stroke-width="54"/><circle cx="256" cy="256" r="112" fill="url(#${id})"/></svg>`;
}

function DiaLogo({ class: cls = "brand-logo" }) {
  // live CSS colours: the icon follows a theme switch at once
  const stops = LOGO_MIX.map(([offset, share, other]) => [offset, share === 1 ? "var(--accent)"
    : `color-mix(in srgb, var(--accent) ${share * 100}%, ${other ? "white" : "black"})`]);
  return html`<svg class=${cls} viewBox="0 0 512 512" aria-hidden="true" dangerouslySetInnerHTML=${{
    __html: logoSvg(stops, "dia-logo").replace(/^<svg[^>]*>|<\/svg>$/g, "").replace(/stop-color="([^"]+)"/g, 'style="stop-color:$1"') }}></svg>`;
}

// The favicon, and in Dia's own window its window and tray icon, in the accent too.
function paintIcon() {
  const probe = document.createElement("i");
  probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  document.body.appendChild(probe);
  const rgb = (getComputedStyle(probe).color.match(/\d+/g) || []).slice(0, 3).map(Number);
  probe.remove();
  if (rgb.length !== 3) return;
  const hex = (c) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
  const stops = LOGO_MIX.map(([offset, share, other]) => [offset, hex(rgb.map((v) => v * share + other * (1 - share)))]);
  const svg = logoSvg(stops);
  document.querySelectorAll('link[rel="icon"]').forEach((link) => link.remove());
  const link = Object.assign(document.createElement("link"), { rel: "icon", type: "image/svg+xml",
    href: `data:image/svg+xml,${encodeURIComponent(svg)}` });
  document.head.appendChild(link);
  if (navigator.userAgent.includes("DiaDesktop")) console.log(`dia-window:accent:${hex(rgb).slice(1)}`);
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

// Line icons (24×24, drawn with the text colour).
const ICONS = {
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z",
  tasks: "M4.5 3h4a1.5 1.5 0 0 1 1.5 1.5v4A1.5 1.5 0 0 1 8.5 10h-4A1.5 1.5 0 0 1 3 8.5v-4A1.5 1.5 0 0 1 4.5 3zM15.5 3h4A1.5 1.5 0 0 1 21 4.5v4a1.5 1.5 0 0 1-1.5 1.5h-4A1.5 1.5 0 0 1 14 8.5v-4A1.5 1.5 0 0 1 15.5 3zM4.5 14h4a1.5 1.5 0 0 1 1.5 1.5v4A1.5 1.5 0 0 1 8.5 21h-4A1.5 1.5 0 0 1 3 19.5v-4A1.5 1.5 0 0 1 4.5 14zM15.5 14h4a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5v-4a1.5 1.5 0 0 1 1.5-1.5z",
  missions: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z",
  chat: "M21 11.5a8.4 8.4 0 0 1-12.2 7.5L3 21l2-5.5A8.4 8.4 0 1 1 21 11.5z",
  cli: "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM7 10l3 2.5L7 15M12 15h4",
  memory: "M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2zM22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z",
  status: "M2 12h4l3-7 5 14 3-7h5",
  usage: "M3 3v18h18M8 17v-5M12 17V8M16 17v-6",
  settings: "M4 7h3M11 7h9M4 17h9M17 17h3M9 4.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4zM15 14.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4z",
  mic: "M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3zM19 10v1a7 7 0 0 1-14 0v-1M12 18v4",
  screen: "M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM8 21h8M12 17v4",
  camera: "M23 7l-7 5 7 5V7zM3 5h11a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
  speaker: "M11 5 6 9H2v6h4l5 4V5zM15.5 8.5a5 5 0 0 1 0 7",
  muted: "M11 5 6 9H2v6h4l5 4V5zM22 9l-6 6M16 9l6 6",
  moon: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z",
  panel: "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 4v16",
  check: "M20 6 9 17l-5-5",
  arrow: "M5 12h14M12 5l7 7-7 7",
  chevronDown: "M6 9l6 6 6-6",
  chevronUp: "M18 15l-6-6-6 6",
  stop: "M6 6h12v12H6z",
  close: "M6 6l12 12M18 6 6 18",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5",
  more: "M5 10.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zM12 10.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zM19 10.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8z",
};
const Icon = ({ name, size = 18 }) => html`<svg class="icon" width=${size} height=${size} viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${ICONS[name]} /></svg>`;

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
// Markdown as agents write it, drawn as elements (never as HTML from the text):
// paragraphs, headings, lists, tables, **bold**, *italic*, `code`, [links](https://…)
// and ```fenced code```.
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*|__[^_\n]+?__)|(\[[^\]\n]+\]\((https?:\/\/[^)\s]+)\))|(\*[^*\s][^*\n]*?\*)/g;

function inline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(html`<code class="inline">${m[1].slice(1, -1)}</code>`);
    else if (m[2]) out.push(html`<strong>${inline(m[2].slice(2, -2))}</strong>`);
    else if (m[3]) out.push(html`<a href=${m[4]} target="_blank" rel="noopener noreferrer">${m[3].slice(1, m[3].indexOf("]("))}</a>`);
    else out.push(html`<em>${m[5].slice(1, -1)}</em>`);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

function blocks(text) {
  const lines = text.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")) {
      const head = cells(line);
      const rows = [];
      for (i += 2; i < lines.length && /^\s*\|/.test(lines[i]); i++) rows.push(cells(lines[i]));
      out.push(html`<div class="md-table"><table><thead><tr>${head.map((c) => html`<th>${inline(c)}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr>${r.map((c) => html`<td>${inline(c)}</td>`)}</tr>`)}</tbody></table></div>`);
      continue;
    }
    const heading = line.match(/^\s*#{1,4}\s+(.*)$/);
    if (heading) { out.push(html`<div class="md-h">${inline(heading[1])}</div>`); i++; continue; }
    const bullet = /^\s*[-*•]\s+/, number = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || number.test(line)) {
      const ordered = number.test(line);
      const items = [];
      for (; i < lines.length && (ordered ? number : bullet).test(lines[i]); i++) items.push(lines[i].replace(ordered ? number : bullet, ""));
      const list = items.map((item) => html`<li>${inline(item)}</li>`);
      out.push(ordered ? html`<ol>${list}</ol>` : html`<ul>${list}</ul>`);
      continue;
    }
    const para = [];
    for (; i < lines.length && lines[i].trim() && !bullet.test(lines[i]) && !number.test(lines[i])
      && !/^\s*#{1,4}\s/.test(lines[i]) && !(/^\s*\|/.test(lines[i]) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")); i++) para.push(lines[i]);
    out.push(html`<p>${para.flatMap((l, k) => (k ? [html`<br />`, ...inline(l)] : inline(l)))}</p>`);
  }
  return out;
}

function RichText({ text, class: cls = "card prose", style }) {
  const parts = (text || "").split(/```([\w+#.-]*)[^\n]*\n([\s\S]*?)```/g);
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    out.push(...blocks(parts[i]));
    if (i + 2 < parts.length) {
      out.push(html`<pre class="code mono"><${Code} code=${parts[i + 2].replace(/\n$/, "")} lang=${languageOf(parts[i + 1])} /></pre>`);
    }
  }
  return html`<div class=${`${cls} md`} style=${style}>${out}</div>`;
}

/** Split a unified diff into per-file patches (path, status, hunks, +/- counts). */
function parseUnifiedDiff(text) {
  const files = [];
  let current = null;
  let oldLine = 0, newLine = 0;
  for (const raw of (text || "").split("\n")) {
    if (raw.startsWith("diff --git ")) {
      const parts = raw.slice("diff --git ".length).split(" ");
      const a = (parts[0] || "").replace(/^a\//, "");
      const b = (parts[1] || "").replace(/^b\//, "");
      current = {
        path: b || a || "?", oldPath: a || b || "?", status: "modified",
        lang: null, added: 0, removed: 0, binary: false, hunks: [],
      };
      files.push(current);
      continue;
    }
    if (!current) continue;
    if (raw.startsWith("new file mode")) { current.status = "added"; continue; }
    if (raw.startsWith("deleted file mode")) { current.status = "deleted"; continue; }
    if (raw.startsWith("rename from ")) { current.status = "renamed"; current.oldPath = raw.slice(12); continue; }
    if (raw.startsWith("rename to ")) { current.path = raw.slice(10); continue; }
    if (raw.startsWith("Binary files ") || raw.startsWith("GIT binary patch")) {
      current.binary = true;
      continue;
    }
    if (raw.startsWith("--- ")) {
      const p = raw.slice(4);
      if (p === "/dev/null") current.status = current.status === "renamed" ? current.status : "added";
      else current.oldPath = p.replace(/^a\//, "");
      continue;
    }
    if (raw.startsWith("+++ ")) {
      const p = raw.slice(4);
      if (p === "/dev/null") current.status = "deleted";
      else {
        current.path = p.replace(/^b\//, "");
        current.lang = languageOf(current.path);
      }
      continue;
    }
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      oldLine = Number(m?.[1] || 0);
      newLine = Number(m?.[2] || 0);
      current.hunks.push({ header: raw, lines: [] });
      continue;
    }
    if (!current.hunks.length) continue;
    const hunk = current.hunks[current.hunks.length - 1];
    const sign = raw[0];
    if (sign === "+") {
      hunk.lines.push({ type: "add", oldLine: null, newLine: newLine++, text: raw.slice(1) });
      current.added += 1;
    } else if (sign === "-") {
      hunk.lines.push({ type: "del", oldLine: oldLine++, newLine: null, text: raw.slice(1) });
      current.removed += 1;
    } else if (sign === "\\") {
      hunk.lines.push({ type: "meta", oldLine: null, newLine: null, text: raw });
    } else {
      const textLine = sign === " " ? raw.slice(1) : raw;
      hunk.lines.push({ type: "ctx", oldLine: oldLine++, newLine: newLine++, text: textLine });
    }
  }
  for (const file of files) {
    if (!file.lang) file.lang = languageOf(file.path);
  }
  return files;
}

function DiffFile({ file, notes, open, onToggle }) {
  const statusKey = {
    added: "diff_added_file", deleted: "diff_deleted_file",
    renamed: "diff_renamed_file", modified: "diff_modified_file",
  }[file.status] || "diff_modified_file";
  const rows = [];
  let rowKey = 0;
  for (const hunk of file.hunks) {
    rows.push(html`<div key=${`h-${rowKey++}`} class="diff-hunk" title=${hunk.header}>
      <span class="diff-ln"></span><span class="diff-ln"></span>
      <span class="sign"> </span><span class="diff-code">${hunk.header}</span></div>`);
    for (const line of hunk.lines) {
      const cls = line.type === "add" ? "add" : line.type === "del" ? "del" : line.type === "meta" ? "hunk" : "";
      const sign = line.type === "add" ? "+" : line.type === "del" ? "−" : " ";
      rows.push(html`<div key=${`l-${rowKey++}`} class=${`diff-row ${cls}`}>
        <span class="diff-ln">${line.oldLine ?? ""}</span>
        <span class="diff-ln">${line.newLine ?? ""}</span>
        <span class="sign">${sign}</span>
        <span class="diff-code"><${Code} code=${line.text || " "} lang=${file.lang} /></span>
      </div>`);
      if (line.type !== "del" && line.newLine != null) {
        notes.filter((n) => n.path === file.path && n.line === line.newLine).forEach((n, j) => {
          rows.push(html`<div key=${`n-${rowKey++}-${j}`} class="diff-note">
            <strong>${n.author}</strong><${RichText} text=${n.body} class="prose muted" /></div>`);
        });
      }
    }
  }
  const title = file.status === "renamed" && file.oldPath !== file.path
    ? `${file.oldPath} → ${file.path}` : file.path;
  return html`<section class="diff-file" data-diff-file=${file.path}>
    <button type="button" class="diff-file-head" aria-expanded=${open}
      title=${open ? t("diff_collapse") : t("diff_expand")} onClick=${onToggle}>
      <span class="diff-chevron" aria-hidden="true">${open ? "▾" : "▸"}</span>
      <span class="diff-path mono" title=${title}>${title}</span>
      <span class="diff-badge">${t(statusKey)}</span>
      <span class="spacer"></span>
      ${file.added || file.removed ? html`<span class="mono diff-stat">
        <span class="tone-ok">+${file.added}</span>
        <span class="tone-danger">−${file.removed}</span></span>` : null}
    </button>
    ${open ? html`<div class="diff-file-body mono">
      ${file.binary ? html`<div class="diff-binary faint">${t("diff_binary")}</div>`
        : rows.length ? rows : html`<div class="diff-binary faint">${t("diff_empty")}</div>`}
    </div>` : null}
  </section>`;
}

function Diff({ text, notes = [], focusPath = null, onFocused }) {
  const files = parseUnifiedDiff(text);
  const [open, setOpen] = useState(() => Object.fromEntries(files.map((f) => [f.path, true])));
  const [active, setActive] = useState(files[0]?.path || "");
  const root = useRef(null);

  useEffect(() => {
    if (!focusPath || !root.current) return;
    setActive(focusPath);
    setOpen((prev) => ({ ...prev, [focusPath]: true }));
    const node = root.current.querySelector(`[data-diff-file="${CSS.escape(focusPath)}"]`);
    node?.scrollIntoView({ behavior: "smooth", block: "start" });
    onFocused?.();
  }, [focusPath]);

  if (text === "") return html`<div class="faint">${t("diff_empty")}</div>`;
  if (!files.length) {
    // Unusual payload without git headers: keep a readable fallback.
    return html`<pre class="diff mono">${text}</pre>`;
  }

  return html`<div class="diff-view" ref=${root}>
    <div class="diff-stack">
      ${files.map((f) => html`<${DiffFile} key=${f.path} file=${f} notes=${notes}
        open=${open[f.path] !== false}
        onToggle=${() => {
          setActive(f.path);
          setOpen((prev) => ({ ...prev, [f.path]: prev[f.path] === false }));
        }} />`)}
    </div>
  </div>`;
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
    if (!text.trim()) return;
    if (kind !== "research" && !chosen) return;
    setBusy(true);
    try {
      if (kind === "research") {
        const task = await api("/api/research", {
          method: "POST",
          body: { topic: text, project: chosen || null, agent: spec || undefined },
        });
        setText(""); onCreated(task); toast(t("research_started")); setBusy(false);
        return;
      }
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
      <textarea class="textarea" placeholder=${t("what")} value=${text} aria-label=${t("what")}
        onInput=${(e) => setText(e.target.value)}
        onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit("run"); }}></textarea>
      <div class="composer-bar">
        <select class="chip-select" value=${chosen} title=${t("project")} onChange=${(e) => setProject(e.target.value)}>
          ${projects.length ? null : html`<option value="">—</option>`}
          ${projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}
        </select>
        <select class="chip-select" value=${agent} title=${t("agent")} onChange=${(e) => { setAgent(e.target.value); setModel(""); }}>
          <option value="">${t("default_agent")}</option>
          ${(status?.agents || []).map((a) => html`<option value=${a.name}>${a.name}</option>`)}
        </select>
        ${agentInfo ? html`<input class="chip-select" style="width:130px" list="task-models" placeholder=${`${t("model")}: ${agentInfo.model || t("auto")}`}
            value=${model} onInput=${(e) => setModel(e.target.value)} />
          <datalist id="task-models">${agentInfo.models.map((m) => html`<option value=${m}></option>`)}</datalist>` : null}
        <select class="chip-select" value=${mode} title=${t("mode")} onChange=${(e) => setMode(e.target.value)}>
          <option value="edit">${t("edit")}</option>
          <option value="read-only">${t("read_only")}</option>
        </select>
        ${status?.pipelines?.length ? html`
          <select class="chip-select" value=${pipeline} onChange=${(e) => setPipeline(e.target.value)}>
            <option value="">${t("planner")}</option>
            ${status.pipelines.map((p) => html`<option value=${p}>${t("pipeline")}: ${p}</option>`)}
          </select>` : null}
        <label class="chip-check"><input type="checkbox" checked=${review}
          onChange=${(e) => setReview(e.target.checked)} /> ${t("review")}</label>
        <span class="spacer"></span>
        <button class="btn ghost" title=${t("research_help")} disabled=${busy || !text.trim()} onClick=${() => submit("research")}>${t("research")}</button>
        <button class="btn ghost" title=${t("scenario_help")} disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("scenario")}>${t("scenario")}</button>
        <button class="btn ghost" title=${t("council_help")} disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("council")}>${t("council")}</button>
        <button class="btn" disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("plan")}>${t("plan")}</button>
        <button class="btn primary" title="Ctrl+↵" disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("run")}>${t("run")}</button>
      </div>
    </div>`;
}

function TaskDetail({ id, toast, onChanged, onBack }) {
  const [task, setTask] = useState(null);
  const [diff, setDiff] = useState(null);
  const [log, setLog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [focusPath, setFocusPath] = useState(null);
  const asked = useRef({});

  const load = useCallback(() => api(`/api/tasks/${id}`).then(setTask).catch((e) => toast(e.message, "error")), [id]);
  useEffect(() => {
    setDiff(null); setLog(null); setTab(null); setFilesOpen(false); setFocusPath(null); asked.current = {}; load();
  }, [id]);
  useEffect(() => {
    const onUpdate = (e) => {
      if (e.detail.id !== id) return;
      asked.current = {};  // a new commit or test run: fetch them again when shown
      load();
    };
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
  const reviewable = task.commit_sha && ["done", "failed"].includes(task.status);
  const ci = d.ci || {};
  const pending = d.comments_pending || [];
  const tests = task.tests_ok === null ? t("not_run") : task.tests_ok ? t("passed") : "FAILED";

  const changes = task.commit_sha && !["merged", "discarded"].includes(task.status);
  const reviewed = d.reviews?.length || pending.length;
  const tabs = [["summary", t("summary_tab")], changes && ["changes", t("changes_tab")],
    task.has_test_log && ["tests", t("tests")], reviewed && ["review", t("reviews")]].filter(Boolean);
  const shown = tab && tabs.some(([key]) => key === tab) ? tab
    : changes && task.status === "done" ? "changes" : "summary";
  const loadDiff = () => {
    if (asked.current.diff) return;
    asked.current.diff = true;
    api(`/api/tasks/${id}/diff`).then(setDiff).catch((e) => { setDiff(""); toast(e.message, "error"); });
  };
  // Prefetch the diff whenever there are changes, so the file menu in the
  // decision bar can open without waiting for the Changes tab.
  if (changes && diff === null) loadDiff();
  if (shown === "tests" && !asked.current.log) {
    asked.current.log = true;
    api(`/api/tasks/${id}/tests`).then(setLog).catch((e) => { setLog(""); toast(e.message, "error"); });
  }
  const lastReview = d.reviews?.length ? d.reviews[d.reviews.length - 1] : null;
  const diffFiles = typeof diff === "string" && diff ? parseUnifiedDiff(diff) : [];
  const pickFile = (path) => {
    setTab("changes");
    setFocusPath(path);
  };
  const toggleFiles = () => {
    setTab("changes");
    loadDiff();
    setFilesOpen((was) => !was);
  };

  return html`
    <div class="detail">
      <button class="btn ghost back" onClick=${onBack}>← ${t("tasks")}</button>
      <div class="detail-head">
        <div class="inbox-meta"><span class="dot ${task.status === "failed" ? "danger" : RUNNING.includes(task.status) ? "warn" : "ok"}"></span>
          <span>${task.project}</span><span class="sep">/</span><span class="mono">${task.id}</span><span class="sep">·</span><span>${ago(task.created_at)}</span></div>
        <div class="title-row"><h2>${d.scenario ? d.scenario : firstLine(task.prompt)}</h2><${Pill} status=${task.status} /></div>
        ${task.status === "waiting" && d.waiting_until ? html`<span class="muted">${t("waiting_until", { time: clock(d.waiting_until) })}</span>` : null}
        ${d.scenario_result ? html`<div class="row"><${Pill} status=${d.scenario_result === "works" ? "done" : d.scenario_result === "broken" ? "failed" : "planned"} label=${t(`scenario_${d.scenario_result}`)} /></div>` : null}
        <div class="chips">
          <span class="chip">${task.agent} · ${task.mode}</span>
          ${task.branch ? html`<span class="chip mono">${task.branch}${task.commit_sha ? ` @ ${task.commit_sha.slice(0, 10)}` : ""}</span>` : null}
          ${d.published ? html`<span class="chip">${t("ci")}: ${ci.state || "-"}${d.published.url ? html` · <a href=${d.published.url} target="_blank">${t("open_pr")}</a>` : null}</span>` : null}
          ${d.routed ? html`<span class="chip">${t("routed")}: ${d.routed}</span>` : null}
          ${d.reverts ? html`<span class="chip">${t("reverts")}: <span class="mono">${d.reverts}</span></span>` : null}
          ${d.reverted_by ? html`<span class="chip">${t("reverted_by")}: <span class="mono">${d.reverted_by}</span></span>` : null}
        </div>
      </div>
      <div class=${`decision-bar${filesOpen ? " files-open" : ""}`}>
        <div class="decision-bar-top">
          <div class="decision-checks">
            ${task.tests_ok !== null ? html`<span class=${task.tests_ok ? "tone-ok" : "tone-danger"}>${task.tests_ok ? html`<${Icon} name="check" size=${13} />` : "✕"} ${t("tests")}: ${tests}</span>` : null}
            ${lastReview ? html`<span class="muted">${lastReview.reviewer}: ${lastReview.verdict.replace("_", " ")}</span>` : null}
            ${task.diffstat ? html`<span class="mono decision-diffstat">
              <span class="tone-ok">+${task.diffstat.added}</span>
              <span class="tone-danger">−${task.diffstat.removed}</span>
              <button type="button" class=${`diff-files-trigger${filesOpen ? " open" : ""}`} aria-expanded=${filesOpen}
                title=${t("diff_file_list")} onClick=${toggleFiles}>
                <span>· ${t("files_changed", { n: task.diffstat.files })}</span>
                <span class="diff-files-caret" aria-hidden="true">
                  <${Icon} name=${filesOpen ? "chevronUp" : "chevronDown"} size=${16} /></span>
              </button>
            </span>` : null}
          </div>
          <div class="decision-actions">
            ${task.status === "planned" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("run-plan")}>${t("run_plan")}</button>` : null}
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
          </div>
        </div>
        ${filesOpen ? html`<div class="decision-files-panel">
          <div class="decision-files" role="listbox" aria-label=${t("diff_file_list")}>
            ${diff === null ? html`<div class="diff-files-empty faint">…</div>`
              : diffFiles.length ? diffFiles.map((f) => html`<button type="button" key=${f.path} role="option"
                class=${`diff-files-item ${f.path === focusPath ? "active" : ""}`}
                onClick=${() => pickFile(f.path)}>
                <span class="diff-path mono" title=${f.path}>${f.path}</span>
                <span class="mono diff-stat">
                  ${f.added ? html`<span class="tone-ok">+${f.added}</span>` : null}
                  ${f.removed ? html`<span class="tone-danger">−${f.removed}</span>` : null}
                </span>
              </button>`)
              : html`<div class="diff-files-empty faint">${t("diff_empty")}</div>`}
          </div>
          <button type="button" class="decision-files-fold" title=${t("diff_collapse")}
            aria-label=${t("diff_collapse")} onClick=${() => setFilesOpen(false)}>
            <span class="diff-files-caret" aria-hidden="true"><${Icon} name="chevronUp" size=${14} /></span>
          </button>
        </div>` : null}
      </div>
      <div class="tabs" role="tablist">
        ${tabs.map(([key, label]) => html`<button role="tab" aria-selected=${shown === key} class="tab ${shown === key ? "active" : ""}" onClick=${() => setTab(key)}>${label}</button>`)}
      </div>
      ${shown === "changes" ? html`<div>
        ${lastReview ? html`<div class="review-note"><strong>${lastReview.reviewer}</strong> <span class="faint">· ${lastReview.verdict.replace("_", " ")}</span>
          <${RichText} text=${lastReview.findings} class="prose muted" /></div>` : null}
        ${diff === null ? html`<div class="faint">…</div>`
          : html`<${Diff} text=${diff} notes=${pending} focusPath=${focusPath} onFocused=${() => setFocusPath(null)} />`}</div>` : null}
      ${shown === "tests" ? html`<pre class="log mono">${log ?? "…"}</pre>` : null}
      ${shown === "review" ? html`<div>
      ${d.reviews?.length ? html`<div class="section"><div class="label">${t("reviews")}</div>
        ${d.reviews.map((r) => html`<div class="card" style="margin-bottom:8px">
          <div class="row"><strong>${r.reviewer}</strong><span class="pill">${r.verdict.replace("_", " ")}</span><span class="faint">#${r.round}</span></div>
          <${RichText} text=${r.findings} class="prose muted" style="margin-top:6px" /></div>`)}</div>` : null}
      ${pending.length ? html`<div class="section"><div class="label">${t("comments")}</div>
        ${pending.map((c) => html`<div class="card" style="margin-bottom:8px"><strong>${c.author}</strong>
          ${c.path ? html` <span class="faint mono">${c.path}${c.line ? `:${c.line}` : ""}</span>` : null}
          <${RichText} text=${c.body} class="prose muted" /></div>`)}</div>` : null}
      </div>` : null}
      ${shown === "summary" ? html`<div>
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
      ${blockers.length && !["merged", "discarded"].includes(task.status) ? html`<div class="section"><div class="label" style="color:${d.override ? "var(--text-muted)" : "var(--warn)"}">${d.override ? `${t("overridden")}: ${d.override}` : `⚠ ${t("blocked")}`}</div></div>` : null}
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
      ${d.learn?.some((f) => f.status === "proposed") ? html`<div class="section"><div class="label">${t("learn")}</div>
        ${d.learn.map((f, i) => f.status === "proposed" ? html`<div class="card row" style="margin-bottom:8px">
          <span style="flex:1">${f.fact}</span>
          <button class="btn primary" disabled=${busy} onClick=${() => act("learn", { accept: [i] })}>${t("remember")}</button>
          <button class="btn ghost" disabled=${busy} onClick=${() => act("learn", { reject: [i] })}>${t("forget")}</button></div>` : null)}</div>` : null}
      </div>` : null}
    </div>`;
}

function TasksView({ tasks, status, selected, select, toast, reload }) {
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const [query, setQuery] = useState("");
  const [composing, setComposing] = useState(false);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_TASKS, 360, 260, 560);
  const words = query.trim().toLowerCase();
  const shown = tasks.filter((x) => (!project || x.project === project) && (!state || x.status === state)
    && (!words || `${x.prompt} ${x.id} ${x.branch || ""} ${x.agent}`.toLowerCase().includes(words)));
  const groups = [
    ["waiting_for_you", shown.filter(decisionOf)],
    ["working_now", shown.filter((x) => RUNNING.includes(x.status))],
    ["earlier", shown.filter((x) => !decisionOf(x) && !RUNNING.includes(x.status))],
  ].filter(([, list]) => list.length);
  const row = (x) => html`
    <button key=${x.id} class="task-row ${x.id === selected ? "active" : ""}" onClick=${() => select(x.id)}>
      <span class="task-title">${firstLine(x.prompt)}</span><${Pill} status=${x.status} />
      <span class="task-meta">${x.project} · ${x.agent} · ${ago(x.created_at)}${x.diffstat ? html` · <span class="tone-ok">+${x.diffstat.added}</span> <span class="tone-danger">−${x.diffstat.removed}</span>` : null}</span>
    </button>`;
  return html`
    <div class="split ${selected ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
      <div class="list">
        <div class="list-tools">
          <button class="btn new-task" aria-expanded=${composing} onClick=${() => setComposing(!composing)}>${composing ? t("hide") : `+ ${t("new_task")}`}</button>
          <input class="input" type="search" placeholder=${t("filter_tasks")} aria-label=${t("filter_tasks")} value=${query} onInput=${(e) => setQuery(e.target.value)} />
          <div class="row">
            <select class="chip-select" value=${project} onChange=${(e) => setProject(e.target.value)}>
              <option value="">${t("all_projects")}</option>
              ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}
            </select>
            <select class="chip-select" value=${state} onChange=${(e) => setState(e.target.value)}>
              <option value="">${t("all_statuses")}</option>
              ${STATUS_ORDER.map((st) => html`<option value=${st}>${st}</option>`)}
            </select>
          </div>
        </div>
        ${composing ? html`<${Composer} status=${status} toast=${toast} onCreated=${(task) => { reload(); select(task.id); setComposing(false); }} />` : null}
        ${groups.length ? groups.map(([key, list]) => html`<div class="list-group">${t(key)}</div>${list.map(row)}`)
          : html`<div class="empty">${t("no_tasks")}</div>`}
      </div>
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
      ${selected ? html`<${TaskDetail} id=${selected} toast=${toast} onChanged=${reload} onBack=${() => select(null)} />`
        : html`<div class="empty">${t("pick_task")}</div>`}
    </div>`;
}

// ------------------------------------------------------ Ctrl+K palette ---

function Palette({ tasks, items, onClose, open }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef(null);
  useEffect(() => input.current?.focus(), []);
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (text) => words.every((w) => text.toLowerCase().includes(w));
  const found = [
    ...items.filter((x) => matches(x.label)).map((x) => ({ ...x, kind: x.kind })),
    ...(words.length ? tasks.filter((x) => matches(`${x.prompt} ${x.id} ${x.branch || ""} ${x.project} ${x.agent}`)).slice(0, 8)
      .map((x) => ({ kind: "task", label: firstLine(x.prompt), hint: `${x.project} · ${x.status} · ${x.id}`, run: () => open(x.id) })) : []),
  ];
  const at = Math.min(index, Math.max(0, found.length - 1));
  const choose = (x) => { if (x) { onClose(); x.run(); } };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((at + 1) % Math.max(1, found.length)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((at - 1 + found.length) % Math.max(1, found.length)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(found[at]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };
  return html`<div class="palette-backdrop" onClick=${onClose}>
    <div class="palette" role="dialog" aria-modal="true" aria-label=${t("search")} onClick=${(e) => e.stopPropagation()}>
      <div class="palette-input"><${Icon} name="search" size=${17} />
        <input ref=${input} value=${query} placeholder=${t("palette_hint")} aria-label=${t("search")}
          role="combobox" aria-expanded="true" aria-controls="palette-list"
          onInput=${(e) => { setQuery(e.target.value); setIndex(0); }} onKeyDown=${onKey} />
        <kbd>Esc</kbd></div>
      <div class="palette-list" id="palette-list" role="listbox">
        ${found.length ? found.map((x, i) => html`<button role="option" aria-selected=${i === at} class="palette-item ${i === at ? "active" : ""}"
          onMouseEnter=${() => setIndex(i)} onClick=${() => choose(x)}>
          <${Icon} name=${x.icon || (x.kind === "task" ? "tasks" : "arrow")} size=${16} />
          <span class="palette-label">${x.label}</span><span class="faint">${x.hint || t(`kind_${x.kind}`)}</span></button>`)
          : html`<div class="palette-empty faint">${t("nothing_found")}</div>`}
      </div>
    </div></div>`;
}

// ---------------------------------------------------------------- inbox ---

// What waits for the owner's decision: the same rule as the KDE widget's badge
// (changes to merge, plans), plus published work whose CI failed or got comments.
function decisionOf(task) {
  const d = task.details || {};
  if (task.status === "done" && task.commit_sha) return "merge";
  if (task.status === "planned") return "plan";
  if (task.status === "published" && d.ci?.state === "failed") return "ci";
  if (task.status === "published" && (d.comments_pending || []).length) return "comments";
  return null;
}
const RUNNING = ["running", "queued", "waiting"];

function InboxCard({ task, kind, open, toast, reload }) {
  const [busy, setBusy] = useState(false);
  const d = task.details || {};
  const blocked = (d.violations || []).length || (d.verification?.checks || []).some((c) => c.held === false);
  const act = async (action, body) => {
    setBusy(true);
    try {
      const result = await api(`/api/tasks/${task.id}/${action}`, { method: "POST", body });
      toast(result.message || result.status || action);
      if (result.url) window.open(result.url, "_blank");
      reload();
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const decide = (action) => {
    const reason = prompt(t("reason_prompt"), "");
    if (reason !== null) act(action, { reason });
  };
  const label = { merge: t("ready_to_merge"), plan: t("plan_to_approve"), ci: t("ci_failed"), comments: t("comments_waiting") }[kind];
  const tone = { merge: "ok", plan: "info", ci: "danger", comments: "warn" }[kind];
  return html`
    <article class="inbox-card ${kind === "ci" ? "alert" : ""}">
      <div class="inbox-meta"><span class="dot ${tone}"></span><span>${task.project}</span><span class="sep">/</span>
        <span class="mono">${task.id}</span><span class="sep">·</span><span>${task.agent} · ${ago(task.created_at)}</span>
        <span class="spacer"></span>
        ${task.diffstat ? html`<span class="mono stat" title=${t("files_changed", { n: task.diffstat.files })}><span class="tone-ok">+${task.diffstat.added}</span> <span class="tone-danger">−${task.diffstat.removed}</span></span>` : null}
        <span class="tone-${tone}">${label}</span></div>
      <button class="inbox-title" onClick=${() => open(task.id)}>${d.scenario || firstLine(task.prompt)}</button>
      ${kind === "merge" ? html`<div class="inbox-checks">
        ${task.tests_ok ? html`<span class="tone-ok"><${Icon} name="check" size=${13} />${t("tests")}: ${t("passed")}</span>` : null}
        ${task.tests_ok === false ? html`<span class="tone-danger">${t("tests")}: FAILED</span>` : null}
        ${d.reviews?.length ? html`<span class="muted">${t("reviews")}: ${d.reviews[d.reviews.length - 1].verdict.replace("_", " ")}</span>` : null}
        ${task.branch ? html`<span class="mono faint">${task.branch}</span>` : null}</div>` : null}
      ${kind === "plan" && d.plan ? html`<ol class="inbox-steps">${d.plan.slice(0, 3).map((s) => html`<li>${s.title || s.agent}</li>`)}
        ${d.plan.length > 3 ? html`<li class="faint">+${d.plan.length - 3}</li>` : null}</ol>` : null}
      ${kind === "ci" && d.ci?.failed?.length ? html`<div class="inbox-checks">${d.ci.failed.map((f) => html`<a class="tone-danger mono" href=${f.url} target="_blank">✕ ${f.name}</a>`)}</div>` : null}
      <div class="row">
        ${kind === "merge" && !blocked ? html`<button class="btn primary" disabled=${busy} onClick=${() => decide("merge")}>${t("merge")}</button>` : null}
        ${kind === "merge" && blocked ? html`<span class="tone-warn">⚠ ${t("needs_override")}</span>` : null}
        ${kind === "plan" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("run-plan")}>${t("run_plan")}</button>` : null}
        ${kind === "ci" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-ci")}>${t("fix_ci")}</button>` : null}
        ${kind === "comments" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("address-comments")}>${t("address")} (${d.comments_pending.length})</button>` : null}
        <button class="btn" onClick=${() => open(task.id)}>${kind === "merge" ? t("review_changes") : t("open_task")} <${Icon} name="arrow" size=${14} /></button>
        ${kind === "merge" && !blocked ? html`<button class="btn" disabled=${busy} onClick=${() => act("publish")}>${t("publish")}</button>` : null}
        <span class="spacer"></span>
        ${kind === "merge" || kind === "plan" ? html`<button class="btn ghost danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
      </div>
    </article>`;
}

function MissionCard({ open }) {
  const [missions, setMissions] = useState(null);
  useEffect(() => {
    const load = () => api("/api/missions").then(setMissions).catch(() => setMissions([]));
    load();
    const every = setInterval(load, 30000);
    return () => clearInterval(every);
  }, []);
  const live = (missions || []).filter((m) => !["merged", "discarded"].includes(m.status));
  const mission = live.find((m) => m.status === "running") || live[0];
  if (!mission) return null;
  const steps = mission.details.mission.steps;
  const done = steps.filter((x) => x.status === "done").length;
  const current = steps.find((x) => x.status === "running") || steps.find((x) => x.status === "pending");
  return html`<div class="card side-card">
    <div class="row"><span class="label">${t("mission")}</span><span class="spacer"></span>
      <button class="btn ghost" onClick=${() => open("missions")}>${t("open_view")}</button></div>
    <div>${firstLine(mission.prompt)}</div>
    <div class="steps-bar" role="img" aria-label=${`${done}/${steps.length}`}>
      ${steps.map((x) => html`<span class="step-seg ${x.status}"></span>`)}</div>
    <div class="faint">${done}/${steps.length}${current ? ` · ${current.title}` : ""} · <${Pill} status=${mission.status} /></div>
  </div>`;
}

function AgentsCard({ status }) {
  const [usage, setUsage] = useState(null);
  useEffect(() => {
    const load = () => api("/api/usage?days=1&weeks=1").then(setUsage).catch(() => setUsage(null));
    load();
    const every = setInterval(load, 60000);
    return () => clearInterval(every);
  }, []);
  if (!status) return null;
  const today = Object.fromEntries((usage?.per_agent || usage?.agents || []).map((a) => [a.agent, a]));
  return html`<div class="card side-card">
    <span class="label">${t("agents")}</span>
    ${status.agents.map((a) => {
      const used = today[a.name];
      const state = a.limited_until ? "warn" : a.ok ? "ok" : "danger";
      return html`<div class="agent-line" title=${a.problem || ""}>
        <span class="dot ${state}"></span><span class="agent-name">${a.name}</span>
        <span class="faint">${a.limited_until ? t("limited_until", { time: clock(a.limited_until) })
          : !a.ok ? t("agent_unavailable")
          : used ? t("calls_today", { n: used.calls, min: used.minutes }) : t("idle_today")}</span></div>`;
    })}
  </div>`;
}

function InboxView({ tasks, status, open, toast, reload, go }) {
  const [sideW, setSideW, commitSideW] = useSplitWidth(SPLIT_INBOX, 320, 240, 480);
  const waiting = tasks.map((x) => [x, decisionOf(x)]).filter(([, kind]) => kind)
    .sort(([a], [b]) => a.created_at.localeCompare(b.created_at));
  const running = tasks.filter((x) => RUNNING.includes(x.status));
  const today = new Date().toLocaleDateString(lang === "pl" ? "pl-PL" : "en-GB", { weekday: "long", day: "numeric", month: "long" });
  return html`
    <div class="page wide inbox">
      <div class="page-head">
        <div class="eyebrow">${today}</div>
        <h1>${t("inbox")}</h1>
        <p class="muted">${waiting.length ? t("inbox_waiting", { n: waiting.length }) : t("inbox_clear")}</p>
      </div>
      <${Composer} status=${status} toast=${toast} onCreated=${(task) => { reload(); open(task.id); }} />
      <div class="inbox-cols" style=${{ "--inbox-side-w": `${sideW}px` }}>
        <section class="inbox-main">
          <h2>${t("waiting_for_you")}</h2>
          ${waiting.length ? waiting.map(([x, kind]) => html`<${InboxCard} key=${x.id} task=${x} kind=${kind} open=${open} toast=${toast} reload=${reload} />`)
            : html`<div class="card faint">${t("inbox_clear")}</div>`}
        </section>
        <${VSplitter} width=${sideW} setWidth=${setSideW} commit=${commitSideW} min=${240} max=${480} def=${320} reverse />
        <aside class="inbox-side">
          <h2>${t("working_now")}</h2>
          <div class="card flush">
            ${running.length ? running.map((x) => html`<button key=${x.id} class="run-row" onClick=${() => open(x.id)}>
              <span class="dot warn pulse"></span>
              <span class="run-text"><span>${firstLine(x.prompt)}</span>
                <span class="faint">${x.project} · ${x.agent} · ${x.status === "running" ? ago(x.created_at) : x.status}</span></span></button>`)
              : html`<div class="run-row faint">${t("nothing_running")}</div>`}
          </div>
          <${MissionCard} open=${go} />
          <${AgentsCard} status=${status} />
        </aside>
      </div>
    </div>`;
}

// ----------------------------------------------------------------- chat ---

const SESSION_KEY = "dia-chat-session";

// ---------------------------------------------------------- phone voice ---

// A paired phone may not use the computer's microphone (docs/MOBILE.md), so it
// talks through its own: it records itself and sends the recording to Dia
// (/api/talk), whose own Whisper hears it and whose own voice answers. Without
// speech recognition on the computer, the browser's own recognition stands in.
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const TALK_RATE = 16000;

function wavOf(samples, rate) {
  const ratio = rate / TALK_RATE;
  const length = Math.floor(samples.length / ratio);
  const view = new DataView(new ArrayBuffer(44 + length * 2));
  const text = (at, word) => [...word].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); text(8, "WAVE"); text(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, TALK_RATE, true); view.setUint32(28, TALK_RATE * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, length * 2, true);
  for (let i = 0; i < length; i++) {
    // the average of the samples this one stands for: a simple low-pass before resampling
    let sum = 0, n = 0;
    for (let j = Math.floor(i * ratio); j < Math.floor((i + 1) * ratio) && j < samples.length; j++) { sum += samples[j]; n++; }
    const value = Math.max(-1, Math.min(1, n ? sum / n : 0));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

// Records until the speaker stops (a pause after speech), at most 28 s; resolves
// with a 16 kHz mono WAV, or null when nobody spoke.
async function recordSpeech(control) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const node = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let spoke = false, quiet = 0, total = 0, done = false;
  return new Promise((resolve) => {
    const finish = () => {
      if (done) return;
      done = true;
      control.stop = null;
      node.onaudioprocess = null;
      node.disconnect(); source.disconnect(); stream.getTracks().forEach((track) => track.stop()); ctx.close();
      if (!spoke) return resolve(null);
      const samples = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
      chunks.reduce((at, c) => { samples.set(c, at); return at + c.length; }, 0);
      resolve(wavOf(samples, ctx.sampleRate));
    };
    control.stop = finish;
    node.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      chunks.push(new Float32Array(data));
      const seconds = data.length / ctx.sampleRate;
      const level = Math.sqrt(data.reduce((sum, x) => sum + x * x, 0) / data.length);
      total += seconds;
      if (level > 0.02) { spoke = true; quiet = 0; } else quiet += seconds;
      if ((spoke && quiet > 1.2) || total > 28 || (!spoke && total > 8)) finish();
    };
    source.connect(node); node.connect(ctx.destination);
  });
}

function TalkSheet({ local, quiet, onClose, onType, open }) {
  const [mode, setMode] = useState(local ? "dia" : Recognition ? "browser" : "none");
  const [state, setState] = useState(mode === "none" ? "unsupported" : "idle");
  const [lines, setLines] = useState([]);
  const control = useRef({});
  const player = useRef(null);
  const end = useRef(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [lines, state]);
  useEffect(() => () => { control.current.stop?.(); control.current.abort?.(); player.current?.pause(); window.speechSynthesis?.cancel(); }, []);
  const locale = lang === "pl" ? "pl-PL" : "en-US";

  const browserSpeak = (text) => {
    if (quiet || !text || !window.speechSynthesis) { setState("idle"); return; }
    const say = new SpeechSynthesisUtterance(text);
    say.lang = locale;
    say.onend = say.onerror = () => setState("idle");
    setState("speaking");
    window.speechSynthesis.speak(say);
  };
  const play = (answer) => {
    if (!answer.audio) { browserSpeak(quiet ? "" : answer.reply); return; }
    const audio = player.current;
    audio.src = `data:${answer.audio_type};base64,${answer.audio}`;
    audio.onended = audio.onerror = () => setState("idle");
    setState("speaking");
    audio.play().catch(() => setState("idle"));
  };
  const said = (heard, answer) => {
    const at = Date.now() / 1000;
    setLines((all) => [...all, { from: "me", text: heard, at },
      { from: "dia", text: answer.reply || "", task: answer.task?.id || answer.plan?.id, at }]);
  };
  const failed = (e) => { setLines((all) => [...all, { from: "dia", text: `${t("failed")}: ${e.message}`, at: Date.now() / 1000 }]); setState("idle"); };
  const session = () => store(SESSION_KEY) || "owner";

  const listenWithDia = async () => {
    // a sound started by the tap itself lets the answer play later (autoplay rules)
    player.current = player.current || new Audio();
    player.current.src = URL.createObjectURL(wavOf(new Float32Array(1600), TALK_RATE));
    player.current.play().catch(() => {});
    let wav;
    try {
      setState("listening");
      wav = await recordSpeech(control.current);
    } catch (e) { setState("denied"); return; }
    if (!wav) { setState("unheard"); return; }
    setState("thinking");
    try {
      const answer = await api(`/api/talk?session=${encodeURIComponent(session())}`, { method: "POST", raw: wav });
      if (!answer.heard) { setState("unheard"); return; }
      said(answer.heard, answer);
      play(answer);
    } catch (e) {
      // no speech recognition on the computer (any more): the browser's own, where there is one
      if (Recognition && /whisper|stt|speech|install/i.test(e.message)) { setMode("browser"); setState("idle"); return; }
      failed(e);
    }
  };
  const listenWithBrowser = () => {
    const r = new Recognition();
    r.lang = locale;
    r.interimResults = false;
    let heard = "";
    r.onresult = (e) => { heard = Array.from(e.results).map((x) => x[0].transcript).join(" ").trim(); };
    r.onerror = () => {};
    r.onend = async () => {
      control.current.stop = null;
      if (!heard) { setState("unheard"); return; }
      setState("thinking");
      try {
        const answer = await api("/api/chat", { method: "POST", body: { text: heard, session: session() } });
        said(heard, answer);
        browserSpeak(answer.reply);
      } catch (e) { failed(e); }
    };
    control.current.stop = () => r.stop();
    control.current.abort = () => r.abort();
    setState("listening");
    r.start();
  };
  const tap = () => {
    if (state === "speaking") { player.current?.pause(); window.speechSynthesis?.cancel(); setState("idle"); return; }
    if (state === "listening") { control.current.stop?.(); return; }
    if (!["idle", "unheard", "denied"].includes(state)) return;
    (mode === "dia" ? listenWithDia : listenWithBrowser)();
  };
  const hint = { idle: t("talk_hint"), listening: t("talk_listening"), thinking: t("talk_thinking"),
    speaking: t("talk_speaking"), unheard: t("talk_unheard"), unsupported: t("talk_unsupported"), denied: t("talk_denied") }[state];

  return html`
    <div class="talk" role="dialog" aria-modal="true" aria-label=${t("talk_phone")}>
      <div class="talk-head"><span class="talk-title">${t("talk_phone")}${mode === "dia" ? html` · <span class="faint">${t("talk_local")}</span>` : null}</span>
        <button class="icon-btn" aria-label=${t("talk_end")} onClick=${onClose}><${Icon} name="close" /></button></div>
      <div class="talk-lines">
        ${lines.map((x) => html`<div class="talk-line ${x.from}">${x.text}
          ${x.at ? html`<time class="msg-meta">${stamp(x.at)}</time>` : null}
          ${x.task ? html`<button class="btn ghost" onClick=${() => open(x.task)}>${t("open_task")} <${Icon} name="arrow" size=${14} /></button>` : null}</div>`)}
        <span ref=${end}></span>
      </div>
      <div class="talk-orb-wrap">
        <button class="talk-orb ${state}" onClick=${tap} disabled=${state === "unsupported" || state === "thinking"}
          aria-label=${t("talk_mic")}><${Icon} name="mic" size=${30} /></button>
        <div class="talk-hint" aria-live="polite">${hint}</div>
      </div>
      <div class="talk-actions">
        <button class="btn" onClick=${onType}><${Icon} name="chat" size=${16} /> ${t("talk_type")}</button>
        <button class="btn ghost danger" onClick=${onClose}>${t("talk_end")}</button>
      </div>
    </div>`;
}


function ChatView({ open, toast }) {
  const [sessions, setSessions] = useState([]);
  const [current, setCurrent] = useState(() => store(SESSION_KEY) || "owner");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [showList, setShowList] = useState(false);
  const [providers, setProviders] = useState([]);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_CHAT, 260, 180, 420);
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
    setMessages((m) => [...m, { from: "me", text: content, at: Date.now() / 1000 }]);
    setBusy(true);
    try {
      const answer = await api("/api/chat", { method: "POST", body: { text: content, session: current } });
      setMessages((m) => [...m, { from: "dia", text: answer.reply || "", task: answer.task?.id, plan: answer.plan?.id, at: Date.now() / 1000 }]);
      loadSessions();
      loadMessages(current);
    } catch (e) {
      setMessages((m) => [...m, { from: "dia", text: `${t("failed")}: ${e.message}`, at: Date.now() / 1000 }]);
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
    <div class="chat-split ${showList ? "show-list" : ""}" style=${{ "--chat-list-w": `${listW}px` }}>
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
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${180} max=${420} def=${260} />
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
          <${MessageList} messages=${messages} open=${open} pendingPlan=${session?.pending_plan} send=${send} />
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

const RESUMABLE = ["claude-code", "codex", "cursor"];  // agents whose conversation can go on

// A new agent session started here: the agent, its model and the project's folder.
// Submit hands the request to the parent immediately so the form is not stuck on
// "Starting…" for the whole first answer (which can take minutes).
function NewCliSession({ status, onSubmit, onCancel }) {
  const agents = (status?.agents || []).filter((a) => RESUMABLE.includes(a.type));
  const [agent, setAgent] = useState(agents[0]?.name || "");
  const [model, setModel] = useState("");
  const [project, setProject] = useState(status?.projects?.[0]?.name || "");
  const [mode, setMode] = useState("edit");
  const [web, setWeb] = useState(false);
  const [text, setText] = useState("");
  const info = agents.find((a) => a.name === agent);
  const start = (e) => {
    e.preventDefault();
    if (!text.trim() || !project) return;
    onSubmit({ agent, model, project, mode, web, text: text.trim() });
  };
  if (!agents.length) return html`<div class="empty">${t("cli_new_none")}</div>`;
  return html`<form class="page cli-new" onSubmit=${start}>
    <h2>${t("cli_new")}</h2>
    <p class="muted">${t("cli_new_help")}</p>
    <label class="field"><span>${t("agent")}</span>
      <select class="select" value=${agent} onChange=${(e) => { setAgent(e.target.value); setModel(""); }}>
        ${agents.map((a) => html`<option value=${a.name} disabled=${!a.ok}>${a.name} · ${a.type}${a.ok ? "" : ` (${t("agent_unavailable")})`}</option>`)}
      </select></label>
    <label class="field"><span>${t("model")}</span>
      <input class="input" list="cli-models" value=${model} placeholder=${`${info?.model || t("auto")}`} onInput=${(e) => setModel(e.target.value)} />
      <datalist id="cli-models">${(info?.models || []).map((m) => html`<option value=${m}></option>`)}</datalist></label>
    <label class="field"><span>${t("project")}</span>
      <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
        ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name} · ${p.path}</option>`)}
      </select></label>
    <label class="field"><span>${t("mode")}</span>
      <select class="select" value=${mode} onChange=${(e) => setMode(e.target.value)}>
        <option value="edit">${t("edit")}</option>
        <option value="read-only">${t("read_only")}</option>
      </select></label>
    <label class="field"><span>${t("cli_web")}</span>
      <input type="checkbox" checked=${web} onChange=${(e) => setWeb(e.target.checked)} /></label>
    <textarea class="textarea" placeholder=${t("cli_new_first")} value=${text} onInput=${(e) => setText(e.target.value)}
      onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) start(e); }}></textarea>
    <div class="row">
      <button class="btn primary" disabled=${!text.trim() || !project}>${t("cli_new_start")}</button>
      <button type="button" class="btn ghost" onClick=${onCancel}>${t("cancel")}</button>
    </div>
  </form>`;
}

function CliView({ toast, status }) {
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState(null);  // {agent, project, text} while the first answer runs
  const [live, setLive] = useState([]);
  const [held, setHeld] = useState([]);
  const [key, setKey] = useState(null);
  const [talk, setTalk] = useState({ messages: [], available: true });
  const [notes, setNotes] = useState([]);  // local /help /status replies
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [cmds, setCmds] = useState({});
  const [slash, setSlash] = useState(-1);  // highlighted index in the / menu, -1 = closed
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_CLI, 280, 200, 480);
  const end = useRef(null);
  const loadHeld = () => api("/api/cli-captured").then(setHeld).catch(() => setHeld([]));
  useEffect(() => {
    api("/api/cli-commands").then(setCmds).catch(() => setCmds({}));
    const load = () => api("/api/cli-sessions").then(setLive).catch(() => setLive([]));
    load(); loadHeld();
    const timer = setInterval(() => { load(); loadHeld(); }, 5000);
    return () => clearInterval(timer);
  }, []);
  const startSession = async (payload) => {
    setCreating(false);
    setPending(payload);
    setNotes([]);
    setTalk({ messages: [{ role: "user", text: payload.text, at: Date.now() / 1000 }], available: true });
    try {
      const item = await api("/api/cli-captured", { method: "POST", body: payload });
      setPending(null);
      await loadHeld();
      setKey(`c:${item.id}`);
      toast(t("cli_new_started"));
    } catch (err) {
      setPending(null);
      toast(`${t("cli_new_failed")}: ${err.message}`, "error");
    }
  };
  const rows = [
    ...(pending ? [{ key: "pending", kind: pending.agent, cwd: pending.project, pending: true, captured: true }] : []),
    ...held.map((c) => ({ ...c, key: `c:${c.id}`, captured: true })),
    ...live.map((s) => ({ ...s, key: `p:${s.pid}` })),
  ];
  const chosen = pending && (!key || key === "pending") ? rows[0]
    : rows.find((r) => r.key === key) || rows.find((r) => !r.pending) || rows[0];
  const path = chosen && !chosen.pending
    ? (chosen.captured ? `/api/cli-captured/${chosen.id}/transcript` : `/api/cli-sessions/${chosen.pid}/transcript`)
    : null;
  const refresh = () => (path ? api(path).then(setTalk).catch(() => setTalk({ messages: [], available: false })) : null);
  useEffect(() => {
    setNotes([]); setSlash(-1);
    if (!path) return undefined;
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [path]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [talk.messages.length, notes.length, chosen?.key, pending]);
  const age = (s) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  const folder = (s) => (s.cwd || "").split("/").filter(Boolean).slice(-2).join("/") || s.cwd || "";
  const catalog = cmds[chosen?.kind] || [];
  const typed = text.startsWith("/") ? text.slice(1).toLowerCase() : "";
  const matches = text.startsWith("/")
    ? catalog.filter((c) => c.cmd.slice(1).startsWith(typed) || c.cmd.includes(typed.split(/\s/)[0]))
    : [];
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
  const note = (body) => setNotes((all) => [...all, { role: "system", text: body, at: Date.now() / 1000 }]);
  const patchSession = async (fields) => {
    const item = await api(`/api/cli-captured/${chosen.id}`, { method: "PATCH", body: fields });
    await loadHeld();
    return item;
  };
  const sendPrompt = async (message) => {
    setBusy(true);
    try {
      const r = await api(`/api/cli-captured/${chosen.id}/send`, { method: "POST", body: { text: message } });
      setText(""); setSlash(-1);
      if (r.id !== chosen.id) { await loadHeld(); setKey(`c:${r.id}`); } else await refresh();
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  const modeOf = (cmd, arg) => {
    const a = (arg || "").trim().toLowerCase();
    if (cmd === "plan") return a && a !== "on" ? null : "read-only";
    if (cmd === "mode") {
      if (["ask", "plan", "read-only", "readonly"].includes(a)) return "read-only";
      if (["edit", "agent"].includes(a)) return "edit";
      return null;
    }
    if (cmd === "permissions") {
      if (a === "plan") return "read-only";
      if (["default", "acceptedits", "bypasspermissions"].includes(a.replace(/\s/g, ""))) return "edit";
      return null;
    }
    if (cmd === "approvals") {
      if (["untrusted", "on-request", "on_request"].includes(a)) return "read-only";
      if (["never", "on-failure", "on_failure"].includes(a)) return "edit";
      return null;
    }
    return null;
  };
  const runLocal = async (cmd, arg) => {
    if (cmd === "help" || cmd === "commands") {
      const lines = catalog.map((c) => `${c.cmd}${c.args ? ` ${c.args}` : ""}  —  ${c.help}`).join("\n");
      note(`${t("cli_commands_help")}\n\n${lines}`);
      return true;
    }
    if (cmd === "status" || cmd === "about") {
      note(t("cli_status_text", {
        kind: chosen.kind, cwd: chosen.cwd || "—", model: chosen.model || t("auto"),
        mode: chosen.mode || "edit", web: chosen.web ? "on" : "off", resume: chosen.resume || "—",
      }));
      return true;
    }
    if (cmd === "release") { await release(); return true; }
    if (cmd === "model") {
      if (!arg) { note(`${t("model")}: ${chosen.model || t("auto")}`); return true; }
      await patchSession({ model: arg });
      toast(t("cli_model_set", { name: arg }));
      return true;
    }
    if (["plan", "mode", "permissions", "approvals"].includes(cmd)) {
      if (!arg && cmd !== "plan") {
        note(`${t("mode")}: ${chosen.mode || "edit"}`);
        return true;
      }
      const next = modeOf(cmd, arg);
      if (!next) return false;
      await patchSession({ mode: next });
      toast(t("cli_mode_set", { mode: next }));
      return true;
    }
    return false;
  };
  const send = async (e) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy || chosen?.pending) return;
    if (message.startsWith("/")) {
      const [raw, ...rest] = message.slice(1).split(/\s+/);
      const cmd = (raw || "").toLowerCase();
      const arg = rest.join(" ");
      const known = catalog.some((c) => c.cmd.slice(1) === cmd);
      if (!known) { note(t("cli_unknown")); setText(""); setSlash(-1); return; }
      setText(""); setSlash(-1);
      if (await runLocal(cmd, arg)) return;
    }
    await sendPrompt(message);
  };
  const pickCmd = (c) => {
    setText(c.args ? `${c.cmd} ` : c.cmd);
    setSlash(-1);
  };
  const onInputKey = (e) => {
    if (slash >= 0 && matches.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSlash((slash + 1) % matches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSlash((slash - 1 + matches.length) % matches.length); return; }
      if (e.key === "Tab") {
        e.preventDefault(); pickCmd(matches[Math.max(0, slash)]); return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        const head = text.trim().split(/\s+/)[0];
        if (catalog.some((c) => c.cmd === head)) return;
        e.preventDefault(); pickCmd(matches[Math.max(0, slash)]); return;
      }
      if (e.key === "Escape") { e.preventDefault(); setSlash(-1); return; }
    }
  };
  const shown = [...talk.messages, ...notes];
  return html`<div class="chat-split" style=${{ "--chat-list-w": `${listW}px` }}>
    <div class="chat-sessions">
      <button class="btn new-task" disabled=${Boolean(pending)} onClick=${() => setCreating(true)}>+ ${t("cli_new")}</button>
      <p class="muted" style="padding:8px">${t("cli_sessions_help")}</p>
      ${rows.length ? rows.map((r) => html`<div key=${r.key} class="session-row ${!creating && chosen?.key === r.key ? "active" : ""}" style="flex-direction:column;align-items:flex-start" onClick=${() => { if (!r.pending) { setKey(r.key); setCreating(false); } }}>
        <span class="session-title" style="max-width:100%"><strong>${r.kind}</strong> · ${folder(r)}</span>
        <span class="faint">${r.pending ? t("cli_new_starting")
          : r.captured ? `${r.started_in_app ? t("cli_new_here") : t("cli_in_app")}${r.model ? ` · ${r.model}` : ""}`
          : `${r.from_dia ? t("cli_from_dia") : t("cli_external")} · ${r.model || t("auto")} · ${age(r.age_s)}`}</span></div>`)
        : html`<p class="faint" style="padding:8px">${t("cli_none")}</p>`}
    </div>
    <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${200} max=${480} def=${280} />
    ${creating ? html`<${NewCliSession} status=${status} onCancel=${() => setCreating(false)} onSubmit=${startSession} />` : html`
    <div class="chat">
      <div class="chat-head"><strong style="flex:1">${chosen ? `${chosen.kind} · ${chosen.cwd || ""}` : ""}</strong>
        ${chosen?.captured && !chosen.pending ? html`<select class="chip-select" title=${t("mode")} value=${chosen.mode || "edit"}
          onChange=${(e) => patchSession({ mode: e.target.value })}>
          <option value="edit">${t("edit")}</option>
          <option value="read-only">${t("read_only")}</option></select>
          <label class="chip-check" title=${t("cli_web")}><input type="checkbox" checked=${Boolean(chosen.web)}
            onChange=${(e) => patchSession({ web: e.target.checked })} /> ${t("cli_web")}</label>` : null}
        ${chosen && !chosen.captured && !chosen.pending ? html`<button class="btn" title=${t("cli_capture_help")} onClick=${capture}>${t("cli_capture")}</button>` : null}
        ${chosen?.captured && !chosen.pending ? html`<button class="btn ghost" title=${chosen.resume} onClick=${release}>${t("cli_release")}</button>` : null}</div>
      <div class="messages">
        ${chosen?.pending ? html`<div class="empty">${t("cli_new_working")}</div>` : null}
        ${chosen && !chosen.pending && !talk.available ? html`<div class="empty">${t("cli_no_transcript")}</div>` : null}
        ${chosen && !chosen.pending && talk.available && !shown.length ? html`<div class="empty">${t("cli_empty")}</div>` : null}
        <${MessageList} messages=${shown} />
        ${busy || chosen?.pending ? html`<div class="msg dia">…</div>` : null}
        <div ref=${end}></div>
      </div>
      ${chosen?.captured && !chosen.pending ? html`<div class="cli-cmds" title=${t("cli_commands_help")}>
        ${catalog.map((c) => html`<button type="button" class="cli-cmd" title=${c.help} onClick=${() => pickCmd(c)}>${c.cmd}</button>`)}
      </div>
      <form class="chat-input" onSubmit=${send}>
        ${matches.length ? html`<div class="slash-menu" role="listbox">
          ${matches.map((c, i) => html`<button type="button" role="option" class=${`slash-item ${i === Math.max(0, slash) ? "active" : ""}`}
            onMouseEnter=${() => setSlash(i)} onClick=${() => pickCmd(c)}>
            <span class="mono">${c.cmd}${c.args ? ` ${c.args}` : ""}</span><span class="faint">${c.help}</span></button>`)}
        </div>` : null}
        <input class="input" placeholder=${t("cli_cmd_hint")} value=${text} disabled=${busy}
          onInput=${(e) => { setText(e.target.value); setSlash(e.target.value.startsWith("/") ? 0 : -1); }}
          onKeyDown=${onInputKey} />
        <button class="btn primary" disabled=${busy || !text.trim()}>${t("send")}</button></form>`
        : chosen && !chosen.pending ? html`<div class="chat-input"><span class="faint">${t("cli_capture_help")}</span></div>` : null}
    </div>`}</div>`;
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

function AboutCard() {
  const [about, setAbout] = useState(null);
  useEffect(() => { api("/api/about").then(setAbout).catch(() => setAbout({})); }, []);
  if (!about || !about.version) return html`<div class="card">…</div>`;
  const link = (href, label) => html`<a href=${href} target="_blank" rel="noreferrer">${label}</a>`;
  return html`<div class="about-card">
    <div class="about-head">
      <${DiaLogo} class="about-logo" />
      <div>
        <h2>Dia ${about.version}</h2>
        <p class="muted">${t("about_tagline")}</p>
      </div>
    </div>
    <div class="kv card">
      <span>${t("about_author")}</span><span>${about.author}</span>
      <span>${t("about_website")}</span><span>${link(about.website, about.website.replace(/^https:\/\//, ""))}</span>
      <span>${t("about_github")}</span><span>${link(about.github, about.github.replace(/^https:\/\//, ""))}</span>
      <span>${t("about_email")}</span><span>${link(`mailto:${about.email}`, about.email)}</span>
      <span>${t("about_license")}</span><span>${link(about.license_url, about.license)}</span>
      ${about.config ? html`<span>${t("about_config")}</span><span class="mono faint">${about.config}</span>` : null}
      ${about.data_dir ? html`<span>${t("about_data")}</span><span class="mono faint">${about.data_dir}</span>` : null}
    </div>
    <div class="label">${t("about_components")}</div>
    <div class="table-wrap">
      <table class="about-table">
        ${(about.components || []).map((row) => html`<tr>
          <td>${row.name}</td>
          <td>${row.version}</td>
          <td class="faint">${row.detail || ""}</td></tr>`)}
      </table>
    </div>
  </div>`;
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
  const jump = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const jumps = [
    ["status-now", "status_now"], ["status-computer", "status_computer"],
    ["status-agents", "agents"], ["status-projects", "projects"],
    ["status-work", "status_work"], ["status-about", "status_about"],
  ];
  return html`
    <div class="page wide status">
      <div class="page-head">
        <h1>${t("status")}</h1>
        <p class="muted">${t("version")}: Dia ${status.version || "?"}</p>
      </div>
      <div class="page-jump" role="navigation" aria-label=${t("jump_to")}>
        ${jumps.map(([id, key]) => html`<button type="button" class="jump-chip" onClick=${() => jump(id)}>${t(key)}</button>`)}
        <span class="spacer"></span>
        <button class="btn" onClick=${reload}>${t("refresh")}</button>
      </div>
      <div class="status-board">
        <section id="status-now" class="status-section">
          <${SuggestionsCard} toast=${toast} />
          <${HealthCard} />
          <${WorkCard} toast=${toast} />
          <${HeldCard} />
        </section>
        <section id="status-computer" class="status-section">
          <${SystemCard} />
          <${SecurityCard} toast=${toast} />
          <${TidyCard} toast=${toast} />
        </section>
        <section id="status-agents" class="status-section">
          <div class="label">${t("agents")}</div>
          <div class="grid" style="margin-top:8px">
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
        </section>
        <section id="status-projects" class="status-section">
          <div class="label">${t("projects")}</div>
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
              ${analysis[p.name] ? html`<pre class="prose status-out">${analysis[p.name]}</pre>` : null}</div>`)}
          </div>
        </section>
        <section id="status-work" class="status-section">
          ${status.projects.length ? html`<${ExperimentCard} status=${status} toast=${toast} />` : null}
          ${status.projects.length ? html`<${DebugCard} status=${status} toast=${toast} />` : null}
          <${SkillsCard} toast=${toast} />
          ${status.device && !status.device_full ? null : html`<${ToolsCard} toast=${toast} />`}
        </section>
        <section id="status-about" class="status-section">
          <${AboutCard} />
          <div class="label" style="margin-top:16px">${t("about_instance")}</div>
          <div class="kv card" style="margin-top:8px">
            <span>${t("brains")}</span><span>${status.brains.join(" → ")}</span>
            <span>${t("memory")}</span><span>${status.memory || t("off")}</span>
            <span>${t("sandbox")}</span><span style=${status.sandbox === "on" ? "" : "color:var(--danger)"}>${t(`sandbox_${status.sandbox || "unavailable"}`)}</span>
            <span>${t("channels")}</span><span>${status.channels.join(", ") || "-"}</span>
            <span>${t("language")}</span><span>${status.language}</span>
          </div>
        </section>
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
const ruleLine = (r) => `${r.project ? `${r.project}:` : ""}${r.match} => ${r.agent}`;
const parseRule = (line) => {
  const m = line.trim().match(/^(?:([\w-]+):)?(.+?)\s*=>\s*([\w.:-]+)$/);
  return m ? { ...(m[1] ? { project: m[1] } : {}), match: m[2].trim(), agent: m[3] } : null;
};
const toForm = (value, type) => {
  if (type === "bool") return Boolean(value);
  if (type === "list") return (value || []).join(", ");
  if (type === "lines") return (value || []).join("\n");
  if (type === "rules") return (value || []).map(ruleLine).join("\n");
  return value == null ? "" : String(value);
};
const fromForm = (value, type) => {
  if (type === "bool") return value;
  if (value === "") return null; // removed from the settings: the config file's value applies
  if (type === "number") return Number(value);
  if (type === "list") return value.split(/[,\s]+/).filter(Boolean);
  if (type === "lines") return value.split("\n").map((x) => x.trim()).filter(Boolean);
  if (type === "rules") return value.split("\n").map(parseRule).filter(Boolean);
  return value;
};

function settingsForms(meta) {
  const v = meta.values;
  const forms = {
    assistant: [
      { section: "s_identity" },
      ["assistant.name", "f_name", "text"],
      ["assistant.user_name", "f_user_name", "text"],
      ["assistant.personality", "f_personality", "personality"],
      ["dia.language", "language", "select", ["pl", "en"]],
      { section: "s_skills_brief" },
      ["skills.weather.place", "f_weather_place", "text"],
      ["skills.news.feeds", "f_news_feeds", "lines"],
      ["skills.stocks.symbols", "f_stocks", "list"],
      ["skills.stocks.source", "f_stocks_source", "select", ["", "yahoo", "stooq"]],
      ["skills.crypto.coins", "f_crypto", "list"],
      ["skills.crypto.currency", "f_crypto_currency", "select", ["", "usd", "pln", "eur"]],
      ["skills.briefing.sections", "f_briefing", "list"],
      ["assistant.skills", "f_skills", "list"],
      { section: "s_conversation" },
      ["assistant.learn_preferences", "f_learn_prefs", "bool"],
      ["assistant.history_turns", "f_history_turns", "number"],
      ["assistant.history_minutes", "f_history_minutes", "number"],
      ["assistant.one_conversation", "f_one_conversation", "bool", null, false, true],
      ["assistant.owner_ids", "f_owner_ids", "list"],
      ["assistant.log_intents", "f_log_intents", "bool", null, false, true],
      { section: "s_chat_models" },
      ["chat.default", "f_chat_default", "text"],
      ["chat.ollama_url", "f_chat_ollama", "text"],
      ["chat.timeout", "f_chat_timeout", "number"],
    ],
    agents: [
      { section: "s_defaults" },
      ["dia.default_agent", "default_agent", "select", ["", ...meta.agents]],
      ["dia.max_parallel_tasks", "f_parallel", "number"],
      ["routing.auto", "f_routing_auto", "bool"],
      ["routing.min_tasks", "f_routing_min", "number"],
      ["routing.rules", "f_routing_rules", "rules"],
      ["limits.fallback", "f_fallback", "list"],
      ["limits.wait", "f_limit_wait", "bool"],
      ["limits.max_wait_hours", "f_max_wait", "number"],
      ["limits.cooldown_minutes", "f_cooldown", "number"],
      { section: "s_review_retry" },
      ["review.auto", "f_auto_review", "bool"],
      ["review.reviewer", "f_reviewer", "select", ["", ...meta.agents]],
      ["review.fix_rounds", "f_fix_rounds", "number"],
      ["review.max_diff_chars", "f_max_diff", "number"],
      ["retry.agent_errors", "f_retry_errors", "number"],
      ["retry.switch_agent", "f_retry_switch", "bool"],
      ["retry.test_fixes", "f_retry_tests", "number"],
      { section: "s_task_limits" },
      ["task_limits.minutes", "f_task_minutes", "number"],
      ["task_limits.calls", "f_task_calls", "number"],
      ["task_limits.agent_timeout", "f_agent_timeout", "number"],
      ["task_limits.nice", "f_nice", "number"],
      { section: "s_plans_missions" },
      ["plans.planner", "f_planner", "select", ["", ...meta.agents]],
      ["plans.max_steps", "f_plan_steps", "number"],
      ["missions.planner", "f_mission_planner", "select", ["", ...meta.agents]],
      ["missions.max_steps", "f_mission_steps", "number"],
      ["missions.budget_calls", "f_mission_calls", "number"],
      ["missions.budget_minutes", "f_mission_minutes", "number"],
      ["missions.step_tests", "f_mission_tests", "bool", null, false, true],
      { section: "s_specialists" },
      ["council.members", "f_council_members", "list"],
      ["council.moderator", "f_council_moderator", "select", ["", ...meta.agents]],
      ["experiments.agents", "f_experiment_agents", "list"],
      ["experiments.max_variants", "f_experiment_variants", "number"],
      ["debug.agents", "f_debug_agents", "list"],
      ["debug.max_checks", "f_debug_checks", "number"],
      ["profile.agent", "f_profile_agent", "select", ["", ...meta.agents]],
      ["contradictions.agent", "f_contradictions_agent", "select", ["", ...meta.agents]],
      ["research.agent", "f_research_agent", "select", ["", ...meta.agents]],
      { section: "s_quality" },
      ["verification.min_lines", "f_verify_lines", "number"],
      ["verification.always", "f_verify_always", "bool"],
      ["debt.function_lines", "f_debt_function", "number"],
      ["debt.nesting", "f_debt_nesting", "number"],
      ["debt.file_lines", "f_debt_file", "number"],
    ],
    automation: [
      { section: "s_watchers" },
      ["watch.enabled", "f_watch", "bool", null, true],
      ["watch.interval", "f_watch_interval", "number", null, true],
      ["watch.projects", "f_watch_projects", "list", null, true],
      ["watch.branch", "f_watch_branch", "text", null, true],
      ["issues.enabled", "f_issues", "bool", null, true],
      ["issues.label", "f_issues_label", "text", null, true],
      ["issues.interval", "f_issues_interval", "number", null, true],
      ["issues.planner", "f_issues_planner", "bool"],
      ["ci.autofix", "f_ci_autofix", "bool"],
      ["ci.watch", "f_ci_watch", "bool", null, false, true],
      ["ci.interval", "f_ci_interval", "number"],
      ["ci.fix_rounds", "f_ci_fix_rounds", "number"],
      ["ci.watch_comments", "f_ci_comments", "bool"],
      ["ci.autofix_comments", "f_ci_autofix_comments", "bool"],
      { section: "s_suggestions" },
      ["suggestions.per_day", "f_suggest_per_day", "number"],
      ["suggestions.repeat_days", "f_suggest_repeat", "number"],
      ["goals.review_days", "f_goal_days", "number"],
    ],
    integrations: [
      { section: "s_mail_home" },
      ["skills.mail.host", "f_mail_host", "text"],
      ["skills.mail.user", "f_mail_user", "text"],
      ["skills.home.url", "f_home_url", "text"],
      ["skills.notion.parent", "f_notion_parent", "text"],
      { section: "s_senses" },
      ["camera.device", "f_camera_device", "text"],
      ["screen.agent", "f_screen_agent", "select", ["", ...meta.agents]],
      { section: "s_publish" },
      ["builds.itch", "f_itch", "text"],
      ["builds.steam.app_id", "f_steam_app", "number"],
      ["builds.steam.username", "f_steam_user", "text"],
      ["builds.steam.branch", "f_steam_branch", "text"],
      ["builds.presets", "f_presets", "list"],
    ],
    security: [
      { section: "s_security_hosts" },
      ["security.hosts", "f_security_hosts", "list"],
      ["security.networks", "f_networks", "list"],
      { section: "s_sandbox" },
      ["sandbox.enabled", "f_sandbox", "select", ["", "auto", "true", "false"]],
      ["sandbox.decoys", "f_sandbox_decoys", "bool"],
      ["sandbox.allow_read", "f_sandbox_read", "list"],
    ],
    computer: [
      { section: "s_computer_alerts" },
      ["system.cpu_temp", "f_cpu_temp", "number"],
      ["system.disk_used", "f_disk_used", "number"],
      ["system.battery_low", "f_battery_low", "number"],
      ["system.check_urls", "f_check_urls", "lines"],
      { section: "s_tidy" },
      ["tidy.folders", "f_tidy_folders", "list"],
      { section: "s_lab" },
      ["lab.engine", "f_lab_engine", "select", ["", "podman", "docker"]],
      { section: "s_godot" },
      ["godot_analysis.max_nodes", "f_ga_nodes", "number"],
      ["godot_analysis.max_depth", "f_ga_depth", "number"],
      ["godot_analysis.max_lights", "f_ga_lights", "number"],
      ["godot_analysis.max_texture", "f_ga_texture", "number"],
    ],
    notify: [
      { section: "s_notify_policy" },
      ["push.events", "f_push_events", "list"],
      ["push.subject", "f_push_subject", "text"],
      ["notifications.quiet_hours", "f_quiet_hours", "text"],
      ["notifications.budget", "f_budget", "number"],
    ],
  };
  forms.memory = [
    { section: "s_vault" },
    ["memory.type", "f_memory_type", "select", ["", "obsidian", "markdown"]],
    ["memory.vault", "f_vault", "text"],
    ["memory.folder", "f_memory_folder", "text"],
    ["memory.projects_dir", "f_projects_dir", "text"],
    ["memory.journal_dir", "f_journal_dir", "text"],
    ["memory.profile_note", "f_profile_note", "text"],
    ["memory.exclude", "f_memory_exclude", "list"],
    ["memory.howtos_dir", "f_howtos_dir", "text"],
    ["memory.create_project_notes", "f_create_notes", "bool", null, false, true],
    ["memory.journal", "f_journal_on", "bool", null, false, true],
    { section: "s_memory_search" },
    ["memory.snippet_chars", "f_snippet_chars", "number"],
    ["memory.howto_results", "f_howto_results", "number"],
    ["memory.index_per_search", "f_index_per_search", "number"],
    ["memory.max_context_chars", "f_context_chars", "number"],
    ["memory.search_results", "f_search_results", "number"],
    ["memory.learn_agent", "f_learn_agent", "select", ["", ...meta.agents]],
  ];
  forms.remote = [
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
    ["app.check_updates", "f_check_updates", "bool", null, false, true],
    ["ui.enabled", "f_ui_enabled", "bool", null, true, true],
    ["ui.port", "f_ui_port", "number", null, true],
  ];
  if (v.memory) {
    forms.memory.push(
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
  // { section: "key" } entries are headings, not fields.
  const entries = fields.filter((f) => Array.isArray(f));
  const initial = Object.fromEntries(entries.map(([path, , type, , , fallback]) => [path, toForm(getPath(meta.values, path) ?? fallback, type)]));
  const [form, setForm] = useState(initial);
  const [custom, setCustom] = useState(false);
  useEffect(() => setForm(initial), [meta]);
  const set = (path, value) => setForm({ ...form, [path]: value });
  const save = async () => {
    const changes = {};
    for (const [path, , type] of entries) {
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
    if (type === "lines" || type === "rules") return html`<textarea class="textarea" rows="3" value=${value} onInput=${(e) => set(path, e.target.value)}></textarea>`;
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
  const fieldClass = (type) => type === "bool" ? "field field-bool" : type === "number" ? "field field-num" : "field";
  return html`<div class="card form">
    ${fields.map((field) => field.section
      ? html`<div class="form-section">${t(field.section)}</div>`
      : html`<label class=${fieldClass(field[2])}><span>${t(field[1])}${field[4] ? html` <span class="faint">↻</span>` : null}</span>${input(field)}</label>`)}
    <div class="row form-actions"><button class="btn primary" onClick=${save}>${t("save")}</button>
      ${entries.some((f) => f[4]) ? html`<span class="faint">↻ ${t("needs_restart")}</span>` : null}</div>
  </div>`;
}

function LocalBrain({ meta, onSaved, toast }) {
  const local = meta.values.brains?.local;
  const [on, setOn] = useState(Boolean(local));
  const [model, setModel] = useState(local?.model || "qwen3.5:4b");
  const save = async () => {
    const order = meta.values.dia?.default_agent ? ["rules", "local", "default-agent"] : ["rules", "local"];
    const changes = on
      ? { brains: { local: { type: "ollama", model } }, dia: { brain: order } }
      : { brains: { local: null }, dia: { brain: null } };
    try { await api("/api/settings", { method: "PUT", body: { changes } }); toast(t("saved")); onSaved(); }
    catch (e) { toast(e.message, "error"); }
  };
  return html`<div class="card form">
    <label class="field field-bool"><span>${t("f_local_brain")}</span><input type="checkbox" checked=${on} onChange=${(e) => setOn(e.target.checked)} /></label>
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

const SETTINGS_TABS = [
  "assistant", "voice_brain", "look", "notifications",
  "agents_tab", "projects_tab", "memory_tab", "automation", "schedule",
  "integrations_tab", "devices_tab", "secrets",
  "desktop_tab", "security_tab", "config_file", "about_tab",
];
const SETTINGS_NAV = [
  { group: "settings_you", items: ["assistant", "voice_brain", "look", "notifications"] },
  { group: "settings_work", items: ["agents_tab", "projects_tab", "memory_tab", "automation", "schedule"] },
  { group: "settings_connect", items: ["integrations_tab", "devices_tab", "secrets"] },
  { group: "settings_computer", items: ["desktop_tab", "security_tab", "config_file", "about_tab"] },
];

// One theme choice: the app's, or the phone's / the widget's, which can follow the app's.
function ThemeChoice({ label, help, value, follows, themes, onPick }) {
  const own = follows === undefined || Boolean(value);
  const names = [...themes.built_in, ...themes.custom];
  return html`<section class="theme-choice">
    <div class="label">${label}</div>
    <p class="muted">${help}</p>
    ${follows !== undefined ? html`<div class="segmented" role="radiogroup" aria-label=${label}>
      <button role="radio" aria-checked=${!own} class=${!own ? "on" : ""} onClick=${() => onPick(null)}>${t("theme_same", { name: follows })}</button>
      <button role="radio" aria-checked=${own} class=${own ? "on" : ""} onClick=${() => !own && onPick(follows)}>${t("theme_own")}</button>
    </div>` : null}
    ${own ? html`<div class="theme-list">
      ${names.map((name) => html`<button class="theme-pick ${value === name ? "on" : ""}" aria-pressed=${value === name}
        onClick=${() => onPick(name)}><span class="theme-dot" data-theme=${name}></span>${name}
        ${themes.custom.includes(name) ? html`<span class="faint">${t("custom_theme")}</span>` : null}</button>`)}
    </div>` : null}
  </section>`;
}

function SettingsView({ toast, device: remote, full }) {
  // A paired phone sees its look and schedule; one with full access nearly everything.
  const device = remote && !full ? remote : null;
  const [tab, setTab] = useState(device ? "look" : "assistant");
  const [meta, setMeta] = useState(null);
  const [themes, setThemes] = useState(null);
  const [chosen, setChosen] = useState(null);  // {name, phone, widget}
  const [config, setConfig] = useState(null);
  const [navW, setNavW, commitNavW] = useSplitWidth(SPLIT_SETTINGS, 200, 160, 320);
  const loadMeta = () => api("/api/settings").then(setMeta).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    api("/api/themes").then(setThemes).catch((e) => toast(e.message, "error"));
    api("/api/theme").then(setChosen).catch((e) => toast(e.message, "error"));
    if (!device) { loadMeta(); api("/api/config").then(setConfig).catch((e) => toast(e.message, "error")); }
  }, [device]);
  // which: "name" (the app), "phone" or "widget"; value: a theme, or null for the app's
  const pick = async (which, value) => {
    try {
      const answer = await api("/api/theme", { method: "PUT", body: { [which]: value } });
      setChosen(answer);
      applyTheme(answer.effective);
    } catch (e) { toast(e.message, "error"); }
  };
  useEffect(() => {  // switched elsewhere (another window, the phone)
    const onTheme = (e) => setChosen((was) => ({ ...was, ...e.detail }));
    window.addEventListener("dia-theme", onTheme);
    return () => window.removeEventListener("dia-theme", onTheme);
  }, []);
  const saveFile = async () => {
    try { await api("/api/config", { method: "PUT", body: { text: config.text } }); toast(t("saved_restart")); }
    catch (e) { toast(e.message, "error"); }
  };
  // Phone: look, notifications, schedule. Paired remote without full access: no secrets/devices/desktop.
  const hidden = device ? SETTINGS_TABS.filter((k) => !["look", "schedule", "notifications", "about_tab"].includes(k))
    : remote ? ["secrets", "devices_tab", "desktop_tab"] : [];
  const tabs = SETTINGS_TABS.filter((k) => !hidden.includes(k));
  const allowed = new Set(tabs);
  const nav = SETTINGS_NAV.map((g) => ({ ...g, items: g.items.filter((k) => allowed.has(k)) })).filter((g) => g.items.length);
  const forms = meta ? settingsForms(meta) : null;
  const form = (key) => (forms ? html`<${Form} fields=${forms[key]} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : "…");
  const body = (() => {
    if (tab === "assistant") return html`${form("assistant")}
      <${PreferencesCard} toast=${toast} />`;
    if (tab === "voice_brain") return html`
      ${forms?.voice ? form("voice") : html`<p class="muted">${t("voice_off")}</p>`}
      <div class="label section">${t("brains")}</div>
      ${meta ? html`<${LocalBrain} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}
      <${BrainTest} toast=${toast} />`;
    if (tab === "agents_tab") return html`${form("agents")}
      <div class="label section">${t("your_agents")}</div>
      ${meta ? html`<${EntityEditor} kind="agents" fields=${AGENT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}`;
    if (tab === "projects_tab") return html`<p class="muted">${t("projects_help")}</p>
      ${meta ? html`<${EntityEditor} kind="projects" fields=${PROJECT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}`;
    if (tab === "memory_tab") return html`${form("memory")}<p class="muted">${t("memory_help")}</p>`;
    if (tab === "automation") return form("automation");
    if (tab === "integrations_tab") return html`${form("integrations")}
      ${forms?.discord ? html`<div class="label section">Discord</div>${form("discord")}` : null}
      <p class="muted">${t("integrations_help")}</p>`;
    if (tab === "schedule") return html`<${ScheduleList} toast=${toast} />`;
    if (tab === "secrets") return html`<${Secrets} toast=${toast} />`;
    if (tab === "notifications") return html`
      <${Notifications} toast=${toast} />
      ${form("notify")}`;
    if (tab === "devices_tab") return html`
      <${Devices} toast=${toast} />
      <div class="label section">${t("remote_access")}</div>${form("remote")}`;
    if (tab === "look") return html`
      ${chosen && themes ? html`
        ${device ? null : html`<${ThemeChoice} label=${t("theme_app")} help=${t("theme_app_help")} value=${chosen.name}
          themes=${themes} onPick=${(name) => pick("name", name)} />`}
        <${ThemeChoice} label=${t("theme_phone")} help=${t("theme_phone_help")} value=${chosen.phone} follows=${chosen.name}
          themes=${themes} onPick=${(name) => pick("phone", name)} />
        ${device ? null : html`<${ThemeChoice} label=${t("theme_widget")} help=${t("theme_widget_help")} value=${chosen.widget}
          follows=${chosen.name} themes=${themes} onPick=${(name) => pick("widget", name)} />`}` : "…"}
      <p class="muted">${t("themes_help")} <code>${themes?.dir || "~/.config/dia/themes"}</code></p>
      ${device ? html`<p class="muted section">${t("device_note", { name: device })}</p>` : null}`;
    if (tab === "desktop_tab") return html`
      <${DesktopCard} toast=${toast} />
      ${forms ? html`<div class="label section">${t("app_window")}</div>${form("app")}<p class="muted">${t("app_window_help")}</p>
        ${form("computer")}` : null}`;
    if (tab === "security_tab") return form("security");
    if (tab === "about_tab") return html`<${AboutCard} />`;
    if (tab === "config_file") return config ? html`
      <p class="faint mono">${config.path}</p>
      ${meta?.settings_path ? html`<p class="muted">${t("overlay_note")} <code>${meta.settings_path}</code></p>` : null}
      <textarea class="textarea config-editor" value=${config.text}
        onInput=${(e) => setConfig({ ...config, text: e.target.value })}></textarea>
      <div class="row" style="margin-top:8px"><button class="btn primary" onClick=${saveFile}>${t("save")}</button></div>` : "…";
    return null;
  })();
  return html`
    <div class="page wide settings">
      <div class="page-head">
        <h1>${t("settings")}</h1>
        <p class="muted">${t("settings_help")}</p>
      </div>
      <div class="settings-layout" style=${{ "--settings-nav-w": `${navW}px` }}>
        <nav class="settings-nav" aria-label=${t("settings")}>
          ${nav.map((g) => html`<div class="settings-group">
            <div class="nav-group">${t(g.group)}</div>
            ${g.items.map((k) => html`<button type="button" class="settings-nav-item ${tab === k ? "active" : ""}"
              onClick=${() => setTab(k)}>${t(k)}</button>`)}
          </div>`)}
        </nav>
        <${VSplitter} width=${navW} setWidth=${setNavW} commit=${commitNavW} min=${160} max=${320} def=${200} />
        <div class="settings-main">
          <div class="settings-panel-head">
            <h2>${t(tab)}</h2>
          </div>
          ${body}
        </div>
      </div>
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
  const create = () => { call("/api/goals", { project, goal: text, weeks }); setText(""); };
  return html`<div class="goals"><div class="label">${t("goals")}</div>
    <div class="composer goal-form">
      <input class="goal-input" placeholder=${t("goal_new")} aria-label=${t("goal_new")} value=${text} onInput=${(e) => setText(e.target.value)}
        onKeyDown=${(e) => { if (e.key === "Enter" && text.trim() && project) create(); }} />
      <div class="composer-bar">
        <label class="chip-number" title=${t("goal_weeks")}><span>${t("goal_weeks")}</span>
          <input type="number" min="1" placeholder="4" value=${weeks} onInput=${(e) => setWeeks(e.target.value)} /></label>
        <span class="spacer"></span>
        <button class="btn" disabled=${busy || !text.trim() || !project} onClick=${create}>${t("goal_create")}</button>
      </div></div>
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
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_MISSIONS, 360, 260, 560);
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
    <div class="split ${selected ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
      <div class="list">
        <div class="composer">
          <textarea class="textarea" rows="3" placeholder=${t("mission_goal")} value=${form.goal} aria-label=${t("mission_goal")}
            onInput=${(e) => setForm({ ...form, goal: e.target.value })}
            onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && form.goal.trim()) create(); }}></textarea>
          <div class="composer-bar">
            <select class="chip-select" title=${t("project")} value=${form.project || status?.projects[0]?.name} onChange=${(e) => setForm({ ...form, project: e.target.value })}>
              ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
            <select class="chip-select" title=${t("priority")} value=${form.priority} onChange=${(e) => setForm({ ...form, priority: e.target.value })}>
              ${["low", "normal", "high"].map((p) => html`<option value=${p}>${t(`prio_${p}`)}</option>`)}</select>
            <label class="chip-number" title=${t("budget_calls")}><span>${t("budget_calls_short")}</span>
              <input type="number" min="0" placeholder="∞" value=${form.calls} onInput=${(e) => setForm({ ...form, calls: e.target.value })} /></label>
            <label class="chip-number" title=${t("budget_minutes")}><span>${t("budget_minutes_short")}</span>
              <input type="number" min="0" placeholder="∞" value=${form.minutes} onInput=${(e) => setForm({ ...form, minutes: e.target.value })} /></label>
            <span class="spacer"></span>
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
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
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
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_MEMORY, 360, 260, 560);
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
    <div class="split ${note ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
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
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
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
    <div class="page wide usage">
      <div class="page-head">
        <h1>${t("usage")}</h1>
        <div class="row">
          ${[7, 30, 90].map((d) => html`<button class="btn ${days === d ? "primary" : ""}" onClick=${() => setDays(d)}>${t("last_days", { days: d })}</button>`)}
        </div>
      </div>
      <div class="tiles">${tiles.map(([k, v]) => html`<div class="card tile"><div class="label">${k}</div><div class="tile-value">${v}</div></div>`)}</div>
      ${calls ? html`
        <div class="usage-charts">
          <div>
            <div class="label section">${t("calls_per_agent")}</div>
            <div class="card" style="margin-top:8px"><${Bars} rows=${data.agents} value=${(a) => a.calls} label=${(a) => a.agent}
              title=${(a) => `${a.agent}: ${a.calls} · ${Math.round((100 * a.ok) / a.calls)}% ok · ${a.minutes} min · ${t("limits_hit")}: ${a.limited}`} /></div>
          </div>
          <div>
            <div class="label section">${t("calls_per_day")}</div>
            <div class="card" style="margin-top:8px"><${Columns} rows=${data.daily} days=${days} /></div>
          </div>
        </div>
        <div class="label section">${t("projects")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("tasks")}</th><th>${t("col_done")}</th><th>${t("col_failed")}</th></tr>
          ${data.projects.map((p) => html`<tr><td>${p.project}</td><td>${p.tasks}</td><td>${p.done}</td><td>${p.failed}</td></tr>`)}
        </table></div>` : html`<p class="muted">${t("no_usage")}</p>`}
      ${data.suggestions?.length ? html`<div class="label section">${t("proposals")}</div>
        ${data.suggestions.map((s) => html`<div class="card row" style="margin-top:8px">
          <span style="flex:1">${t("proposal_text", { project: s.project, agent: s.agent, current: s.current })}<br /><span class="faint">${s.reason}</span></span>
          <button class="btn primary" onClick=${() => apply(s)}>${t("apply")}</button></div>`)}` : null}
      ${data.agents_by_project?.length ? html`<div class="label section">${t("agent_skill")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("agent")}</th><th>${t("tasks")}</th><th>${t("success")}</th><th>${t("tests")}</th><th>${t("review_ok")}</th><th>${t("quality")}</th><th>min</th></tr>
          ${data.agents_by_project.map((r) => html`<tr><td>${r.project}</td><td>${r.agent}</td><td>${r.tasks}</td>
            <td>${Math.round(r.success * 100)}%</td><td>${r.tests == null ? "–" : `${Math.round(r.tests * 100)}%`}</td>
            <td>${r.approved == null ? "–" : `${Math.round(r.approved * 100)}%`}</td>
            <td title=${[r.reverted && `${t("sc_rolled_back")}: ${r.reverted}`, r.regressions && `${t("sc_regressions")}: ${r.regressions}`, r.review_rounds && `${t("sc_rounds")}: ${r.review_rounds}`].filter(Boolean).join(" · ")}>${Math.round(r.quality * 100)}%</td>
            <td>${r.minutes}</td></tr>`)}
        </table></div>` : null}
      ${data.scorecard?.some((w) => w.tasks) ? html`<div class="label section">${t("scorecard")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
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
      <div class="brand"><${DiaLogo} />Dia</div>
      <strong>${t("login_title")}</strong>
      <span class="muted">${t("login_help")}</span>
      <input class="input" placeholder=${t("token")} value=${value} onInput=${(e) => setValue(e.target.value)} />
      <button class="btn primary" onClick=${() => onToken(value.trim())}>${t("connect")}</button>
    </div></div>`;
}

function App() {
  const [authed, setAuthed] = useState(Boolean(token));
  const [view, setView] = useState(START_VIEW || (START_TASK ? "tasks" : "inbox"));
  const [collapsed, setCollapsed] = useState(store(SIDEBAR_KEY) === "collapsed");
  const [sidebarW, setSidebarW, commitSidebarW] = useSplitWidth(SPLIT_SIDEBAR, 240, 180, 400);
  const [talking, setTalking] = useState(false);
  const [more, setMore] = useState(false);
  const [palette, setPalette] = useState(false);
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
    // Dia keeps the theme: the app's, or on a paired phone the phone's (Settings → Look)
    onPhone = Boolean(s.device);
    if (s.theme && s.theme !== store(THEME_KEY)) applyTheme(s.theme);
    setStatus(s);
  }).catch(() => {}), []);

  useEffect(() => { applyTheme(store(THEME_KEY) || "dark"); }, []);
  // The desktop window's tray menu (and links like #view=chat) switch the tab.
  useEffect(() => {
    window.diaNavigate = (name, task) => {
      setMore(false);
      if (task) { setSelected(task); setView("tasks"); } else if (VIEWS.includes(name)) setView(name);
    };
    const onHash = () => {
      setMore(false);
      const name = hashParam("view");
      if (VIEWS.includes(name)) setView(name);
      const task = hashParam("task");
      if (task) { setSelected(task); setView("tasks"); }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { if (authed) { loadTasks(); loadStatus(); } }, [authed]);
  // Ctrl+B folds the sidebar down to its icons (and back); remembered on this device.
  const toggleSidebar = useCallback(() => setCollapsed((was) => {
    store(SIDEBAR_KEY, was ? "open" : "collapsed");
    return !was;
  }), []);
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
      if (e.key.toLowerCase() === "b") { e.preventDefault(); toggleSidebar(); }
      if (e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((was) => !was); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
          setTasks((all) => {
            const before = all.find((x) => x.id === data.task.id);
            const kept = before && before.commit_sha === data.task.commit_sha ? before.diffstat : undefined;
            return [{ diffstat: kept, ...data.task }, ...all.filter((x) => x.id !== data.task.id)]
              .sort((a, b) => b.created_at.localeCompare(a.created_at));
          });
          // a new commit waits for a decision: fetch its +/- once
          if (data.task.commit_sha && ["done", "failed", "published"].includes(data.task.status)) loadTasks();
          window.dispatchEvent(new CustomEvent("dia-task", { detail: data.task }));
        } else if (data.type === "theme") {
          applyTheme((onPhone && data.phone) || data.name);
          window.dispatchEvent(new CustomEvent("dia-theme", { detail: data }));
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
  const active = tasks.filter((x) => RUNNING.includes(x.status)).length;
  const decisions = tasks.filter(decisionOf).length;
  const work = [["inbox", decisions || ""], ["tasks", active || ""], ["missions", ""], ["chat", ""], ["cli", ""]];
  const system = [["memory", ""], ["status", ""], ["usage", ""]];
  const open = (id) => { setSelected(id); setView("tasks"); setTalking(false); };
  const go = (key) => { setView(key); setMore(false); };
  // On the computer the microphone is Dia's own; a paired phone talks through its own.
  const talk = () => (status?.device ? setTalking(true) : toggleVoice());
  const navItem = ([key, count]) => html`
    <button class="nav-item ${view === key ? "active" : ""} ${key === "inbox" && count ? "has-badge" : ""}" title=${t(key)}
      aria-current=${view === key ? "page" : undefined} onClick=${() => go(key)}>
      <${Icon} name=${key} /><span class="nav-label">${t(key)}</span><span class="nav-count">${count}</span></button>`;
  const okAgents = status ? status.agents.filter((a) => a.ok).length : 0;

  return html`
    <div class="shell ${collapsed ? "collapsed" : ""}" style=${collapsed ? null : { "--sidebar-w": `${sidebarW}px` }}>
      <aside class="sidebar">
        <div class="brand" data-drag><${DiaLogo} /><span class="brand-name">dia</span>
          ${status?.version ? html`<button type="button" class="brand-version" title=${t("about_tab")}
            onClick=${(e) => { e.stopPropagation(); go("status"); setTimeout(() => document.getElementById("status-about")?.scrollIntoView({ behavior: "smooth" }), 50); }}>${status.version}</button>` : null}</div>
        <nav class="nav" aria-label="Dia">
          <div class="nav-group">${t("nav_work")}</div>
          ${work.map(navItem)}
          <div class="nav-group">${t("nav_system")}</div>
          <span class="nav-rule" aria-hidden="true"></span>
          ${system.map(navItem)}
          <span class="nav-fill"></span>
          ${navItem(["settings", ""])}
        </nav>
        <div class="sidebar-foot">
          ${status ? html`<button class="mic ${status.device ? "" : voice}" onClick=${talk} title=${status.device ? t("talk_to_dia") : `${t("talk_to_dia")} · dia voice toggle`} aria-label=${t("talk_to_dia")}>
            <span class="mic-orb"><${Icon} name="mic" size=${16} /></span>
            <span class="mic-text"><span class="mic-title">${t("talk_to_dia")}</span>
              <span class="mic-label">${status.device || voice === "idle" ? t("voice_ready") : t(`voice_${voice}`)}</span></span></button>` : null}
          ${status ? html`<div class="senses" role="group" aria-label=${t("senses")}>
            <button class="sense ${status.screen ? "on" : ""} ${looking ? "looking" : ""}" aria-pressed=${Boolean(status.screen)}
              title="${status.screen ? t("screen_on") : t("screen_off")} · ${t("screen_help")}" onClick=${toggleScreen}><${Icon} name="screen" size=${16} /></button>
            <button class="sense ${status.camera ? "on" : ""}" aria-pressed=${Boolean(status.camera)}
              title="${status.camera ? t("camera_on") : t("camera_off")} · ${t("camera_help")}" onClick=${toggleCamera}><${Icon} name="camera" size=${16} /></button>
            <button class="sense ${status.quiet || status.quiet_hours ? "on" : ""}" aria-pressed=${Boolean(status.quiet)}
              title="${status.quiet ? t("quiet_on") : status.quiet_hours ? t("quiet_hours_on") : t("quiet_off")} · ${t("quiet_help")}" onClick=${toggleQuiet}>
              <${Icon} name=${status.quiet ? "muted" : status.quiet_hours ? "moon" : "speaker"} size=${16} /></button>
          </div>` : null}
          <div class="conn" title=${connected ? t("connected") : t("offline")}><span class="conn-dot ${connected ? "on" : ""}"></span>
            <span class="conn-text">${connected ? t("local_dia") : t("offline")}</span>
            ${status ? html`<span class="conn-agents">${t("agents_ready", { ok: okAgents, all: status.agents.length })}</span>` : null}
            ${IN_APP ? html` · <a href="#" onClick=${(e) => { e.preventDefault(); location.href = APP_HOME; }}>${t("change_server")}</a>` : null}</div>
        </div>
      </aside>
      ${collapsed ? null : html`<${VSplitter} width=${sidebarW} setWidth=${setSidebarW} commit=${commitSidebarW} min=${180} max=${400} def=${240} />`}
      <main class="main">
        <div class="topbar" data-drag>
          <button class="icon-btn sidebar-toggle" onClick=${toggleSidebar} aria-expanded=${!collapsed}
            title="${collapsed ? t("menu_expand") : t("menu_collapse")} (Ctrl+B)" aria-label=${collapsed ? t("menu_expand") : t("menu_collapse")}><${Icon} name="panel" /></button>
          <nav class="crumbs" aria-label="breadcrumb"><span class="hide-phone">${t("workspace")}</span><span class="sep hide-phone">/</span><h1>${t(view)}</h1></nav>
          <span class="spacer"></span>
          <button class="search-btn" onClick=${() => setPalette(true)} title=${t("search")} aria-label=${t("search")}>
            <${Icon} name="search" size=${16} /><span class="hide-phone">${t("search")}</span><kbd class="hide-phone">Ctrl K</kbd></button>
          ${active ? html`<span class="tag ok hide-phone">${t("running_count", { n: active })}</span>` : null}
          ${status && !status.halted ? html`<button class="btn danger-outline stop-btn" title=${t("stop_help")} onClick=${stopAll}><${Icon} name="stop" size=${11} /> ${t("stop")}</button>` : null}
          <${WindowControls} />
        </div>
        ${status?.halted ? html`<div class="halted-bar">🛑 ${t("halted")}
          <button class="btn primary" onClick=${resumeAll}>${t("resume_btn")}</button></div>` : null}
        <div class="content">
          ${view === "inbox" ? html`<${InboxView} tasks=${tasks} status=${status} open=${open} go=${go} toast=${toast} reload=${loadTasks} />` : null}
          ${view === "tasks" ? html`<${TasksView} tasks=${tasks} status=${status} selected=${selected} select=${setSelected} toast=${toast} reload=${loadTasks} />` : null}
          ${view === "chat" ? html`<${ChatView} open=${open} toast=${toast} />` : null}
          ${view === "cli" ? html`<${CliView} toast=${toast} status=${status} />` : null}
          ${view === "status" ? html`<${StatusView} status=${status} reload=${loadStatus} toast=${toast} />` : null}
          ${view === "usage" ? html`<${UsageView} toast=${toast} />` : null}
          ${view === "memory" ? html`<${MemoryView} toast=${toast} />` : null}
          ${view === "missions" ? html`<${MissionsView} status=${status} toast=${toast} open=${open} />` : null}
          ${view === "settings" ? html`<${SettingsView} toast=${toast} device=${status?.device} full=${status?.device_full} />` : null}
        </div>
      </main>
      <nav class="phone-bar" aria-label="Dia">
        ${[["inbox", decisions], ["tasks", active]].map(([key, count]) => html`<button class="phone-tab ${view === key && !more ? "active" : ""}"
          aria-current=${view === key && !more ? "page" : undefined} onClick=${() => go(key)}>
          <span class="phone-icon"><${Icon} name=${key} size=${22} />${count ? html`<span class="phone-badge">${count}</span>` : null}</span>${t(key)}</button>`)}
        <button class="phone-mic ${status?.device ? "" : voice}" onClick=${talk} aria-label=${t("talk_to_dia")}><${Icon} name="mic" size=${26} /></button>
        <button class="phone-tab ${view === "chat" && !more ? "active" : ""}" onClick=${() => go("chat")}>
          <span class="phone-icon"><${Icon} name="chat" size=${22} /></span>${t("chat")}</button>
        <button class="phone-tab ${more ? "active" : ""}" aria-expanded=${more} onClick=${() => setMore(!more)}>
          <span class="phone-icon"><${Icon} name="more" size=${22} /></span>${t("more")}</button>
      </nav>
      ${more ? html`<div class="sheet-backdrop" onClick=${() => setMore(false)}></div>
        <div class="sheet" role="dialog" aria-label=${t("more")}>
          ${[...work.slice(2).filter(([key]) => key !== "chat" && !(key === "cli" && status?.device)), ...system, ["settings", ""]].map(([key]) => html`
            <button class="sheet-item ${view === key ? "active" : ""}" onClick=${() => go(key)}><${Icon} name=${key} />${t(key)}</button>`)}
          ${status ? html`<div class="sheet-row">
            <button class="sense ${status.screen ? "on" : ""}" aria-pressed=${Boolean(status.screen)} title=${t("screen_help")} onClick=${toggleScreen}><${Icon} name="screen" size=${16} /> ${status.screen ? t("screen_on") : t("screen_off")}</button>
            <button class="sense ${status.camera ? "on" : ""}" aria-pressed=${Boolean(status.camera)} title=${t("camera_help")} onClick=${toggleCamera}><${Icon} name="camera" size=${16} /> ${status.camera ? t("camera_on") : t("camera_off")}</button>
            <button class="sense ${status.quiet ? "on" : ""}" aria-pressed=${Boolean(status.quiet)} title=${t("quiet_help")} onClick=${toggleQuiet}><${Icon} name=${status.quiet ? "muted" : "speaker"} size=${16} /> ${status.quiet ? t("quiet_on") : t("quiet_off")}</button>
          </div>` : null}
          <div class="conn"><span class="conn-dot ${connected ? "on" : ""}"></span><span class="conn-text">${connected ? t("connected") : t("offline")}</span>
            ${IN_APP ? html`<a href="#" onClick=${(e) => { e.preventDefault(); location.href = APP_HOME; }}>${t("change_server")}</a>` : null}</div>
        </div>` : null}
      ${palette ? html`<${Palette} tasks=${tasks} open=${open} onClose=${() => setPalette(false)} items=${[
        ...VIEWS.map((key) => ({ kind: "view", icon: key, label: t(key), run: () => go(key) })),
        { kind: "action", icon: "tasks", label: t("new_task"), run: () => go("inbox") },
        { kind: "action", icon: "mic", label: t("talk_to_dia"), run: talk },
        { kind: "action", icon: "panel", label: collapsed ? t("menu_expand") : t("menu_collapse"), hint: "Ctrl+B", run: toggleSidebar },
        ...(status ? [{ kind: "action", icon: status.quiet ? "speaker" : "muted", label: status.quiet ? t("quiet_off_action") : t("quiet_on_action"), run: toggleQuiet }] : []),
      ]} />` : null}
      ${talking ? html`<${TalkSheet} local=${status?.talk} quiet=${status?.quiet} open=${open} onClose=${() => setTalking(false)}
        onType=${() => { setTalking(false); go("chat"); }} />` : null}
      <div class="toasts">${toasts.map((x) => html`<div key=${x.id} class="toast ${x.kind}">${x.text}</div>`)}</div>
      <${WindowEdges} />
    </div>`;
}

render(html`<${App} />`, document.getElementById("app"));

// Installable app (PWA); service workers need https or localhost.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
