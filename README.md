# Guided Workflow Assistant — a Claude skill

A [Claude skill](https://docs.claude.com/en/docs/claude-code/skills) for building an **in-app guided workflow assistant**: a real task engine that walks users through actual work on the real screens of your app. It is not a product tour.

The assistant:

- takes the user to the right page and opens the right tab
- highlights the **group** of fields that matters, never just one input, and never covers them
- ticks fields off live as they are filled, and lets Enter move to the next one
- will not move on until the **server proves** the step is done
- skips work that is already done, and branches on questions
- survives refreshes, logouts and walking away, with "Continue your work" to pick a task back up
- records where people get stuck, where they give up, and what they skip

It was built and shipped in a production Laravel + Inertia/React admin, then carried over to a server-rendered (Blade/Livewire) customer portal. Real users then broke it in about thirty instructive ways. This skill contains the architecture, reference implementations, and every one of those failures, written as symptom → cause → fix.

## What is inside

```
guided-workflow-assistant/
├── SKILL.md                         # the mental model, build order, contracts, non-negotiables
├── references/
│   ├── architecture.md              # moving parts, data flow, why it is shaped this way
│   ├── backend.md                   # server engine (Laravel reference; notes for Rails/Django/Node)
│   ├── frontend.md                  # React provider, watcher, spotlight, docked panel, launcher
│   ├── writing-workflows.md         # authoring definitions, page hooks, words that work
│   ├── server-rendered-island.md    # Blade/Livewire/Rails/Django pages; a second audience
│   ├── testing-and-audit.md         # tests, the selector audit, driving it in a browser
│   ├── pitfalls.md                  # 34 real failures: symptom → cause → fix
│   └── guide-character.md           # optional mascot with poses and crops
└── scripts/
    ├── audit-hooks.js               # browser console: check selectors resolve, opening tabs
    ├── dump-selectors.php           # list every selector every step uses, by page
    └── build-crops.py               # cut character art into avatar/chest/half/full WebP crops
```

## Install

**One command, Claude Code:**

```bash
curl -fsSL https://raw.githubusercontent.com/ngumcbrightazongwa-ops/guided-workflow-assistant/main/install.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ngumcbrightazongwa-ops/guided-workflow-assistant/main/install.ps1 | iex
```

Both install it for every project, in `~/.claude/skills/`. To install it for one project only, clone the repo and run `./install.sh /path/to/project` or `.\install.ps1 -Project C:\path\to\project`.

**Claude.ai / Claude desktop:** download `guided-workflow-assistant.skill` from the [latest release](https://github.com/ngumcbrightazongwa-ops/guided-workflow-assistant/releases/latest) and upload it under Settings → Capabilities → Skills.

**By hand, Claude Code (personal, all projects):**

```bash
git clone https://github.com/ngumcbrightazongwa-ops/guided-workflow-assistant.git
cp -r guided-workflow-assistant/guided-workflow-assistant ~/.claude/skills/
```

On Windows (PowerShell):

```powershell
git clone https://github.com/ngumcbrightazongwa-ops/guided-workflow-assistant.git
Copy-Item -Recurse guided-workflow-assistant\guided-workflow-assistant "$HOME\.claude\skills\"
```

**One project only:** copy the inner `guided-workflow-assistant/` folder into the project's `.claude/skills/` instead.

## Use

Ask Claude about it naturally. The skill triggers on requests such as:

- "Add a workflow assistant to our admin that walks staff through adding a product"
- "Our users keep getting the refund process wrong. Can we guide them through it step by step?"
- "Build a Ctrl+K task launcher that actually does the task with them"
- "Bring the admin's guided workflows to our customer portal too. It's Blade, not React"
- "The walkthrough covers the fields it's highlighting and doesn't notice when I fill them in"

Or invoke it directly with `/guided-workflow-assistant`.

## Stack

The reference implementation is **Laravel (PHP 8.2+) + React/TypeScript**, with Inertia for the admin and a React island on Blade/Livewire pages. The design is framework-neutral: `backend.md`, `frontend.md` and `server-rendered-island.md` each include a section mapping it to Rails, Django, Node, Vue and Svelte.

## Contributing

Issues and pull requests are welcome, especially new entries for `pitfalls.md` from your own builds. Please use the same **symptom → cause → fix** format.

## Credits

Created by **Aneta Prime** · by [@ngumcbrightazongwa-ops](https://github.com/ngumcbrightazongwa-ops)

If you use this skill or build on it, a link back is appreciated.

## Licence

[MIT](LICENSE) © Aneta Prime
