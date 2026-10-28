# Dia UI concept

Visual proposal, 2026-10-28. This is a standalone prototype, not the production UI.
The task history, test results, code diff, agent activity and service states are
fictional examples. No API calls are made and no host configuration is changed.

Open `index.html` directly in a browser. It uses the existing Dia logo from the
repository, system fonts and inline SVG icons; no build or network is required.

## Screens

- [Tasks](01-tasks.png): prioritize decisions, keep the task list beside changes,
  surface checks before approval, and give each task state a readable label.
- [Chat](02-chat.png): calmer conversation layout with an inline task handoff,
  separate conversation history and a visible composer.
- [Settings](03-settings.png): category navigation, theme previews and grouped
  desktop lifecycle preferences with explanatory text.

The direction retains Dia's graphite and violet identity, adds more spacing,
groups the navigation by purpose and makes secondary actions quieter.

## Interactive scope

The three implemented destinations are Tasks, Conversations and Settings.
Task filters, search, selection, detail tabs, Ctrl+K, the light/dark preview,
settings switches, new conversation and local message entry work in the mockup.
Other destinations and workflow actions show explanatory preview messages.
Midnight is a palette swatch only. UI state is ephemeral; switches and messages
reset when their view is rebuilt. The sidebar's settings entry is hidden on the
narrow layout; `index.html#settings` opens the settings preview directly.

## Validation

Checked in headless Chromium at 1440 × 1000 and 390 × 844:

- Task filters/search/selection and detail tabs.
- Navigation, local chat input, switches and light theme.
- Ctrl+K moves focus to task search.
- No JavaScript errors or horizontal page overflow in any of the three narrow views.
- Desktop PNGs were rendered from this HTML and visually inspected.

This validates the concept's interactions, not production integration or the
fictional test results shown inside the design. Application behavior is unchanged.
