# CLAUDE.md

## Repository Overview

This is a **GitHub Skills** learning course: *"Code with GitHub Copilot"*. It is a template-based, self-paced exercise that teaches learners how to use GitHub Copilot inside a GitHub Codespace with VS Code. There is no application source code — the repository drives a guided tutorial via GitHub Actions workflows that automatically advance learners through sequential steps.

**Repository:** `mehena05/compta`
**Primary branch:** `main`
**License:** MIT

---

## Repository Structure

```
.
├── README.md                        # Live course instructions (auto-updated by workflows)
├── LICENSE
├── .gitignore
├── .github/
│   ├── dependabot.yml               # Monitors github-actions and devcontainers (monthly)
│   ├── steps/
│   │   ├── -step.txt                # Current step tracker (single integer, e.g. "1")
│   │   ├── 0-welcome.md             # Step 0 content (placeholder)
│   │   ├── 1-copilot-extension.md   # Step 1 instructions
│   │   ├── 2-skills-javascript.md   # Step 2 instructions
│   │   ├── 3-copilot-hub.md         # Step 3 instructions
│   │   ├── 4-copilot-comment.md     # Step 4 instructions
│   │   └── X-finish.md              # Completion message
│   └── workflows/
│       ├── 0-welcome.yml            # Step 0 → 1 on any push to main
│       ├── 1-copilot-extension.yml  # Step 1 → 2 on .devcontainer/devcontainer.json push
│       ├── 2-skills-javascript.yml  # Step 2 → 3 on skills.js push
│       ├── 3-copilot-hub.yml        # Step 3 → 4 on member.js push
│       └── 4-copilot-comment.yml    # Step 4 → X on comments.js push
```

---

## Course Flow

The course has 4 learner steps plus an intro and finish. Progression is tracked in `.github/steps/-step.txt`, which contains a single number (`0`–`4`, or `X` for complete). Each GitHub Actions workflow checks this value before running to prevent out-of-order execution.

| Step | Trigger file | Validates | Transitions to |
|------|-------------|-----------|---------------|
| 0    | Any push to `main` | — | Step 1 |
| 1    | `.devcontainer/devcontainer.json` | Contains `GitHub.copilot` extension | Step 2 |
| 2    | `skills.js` | Contains `function calculateNumbers` | Step 3 |
| 3    | `member.js` | Contains `function skillsMember` | Step 4 |
| 4    | `comments.js` | Contains `// Create web server` | Step X (finish) |

**Current state:** Step 1 (learner must create `.devcontainer/devcontainer.json`).

---

## GitHub Actions Conventions

All workflows follow the same pattern:

1. **`get_current_step` job** — reads `.github/steps/-step.txt` and exposes it as an output variable.
2. **Main job** — runs only when `needs.get_current_step.outputs.current_step == <expected>` AND `!github.event.repository.is_template`.
3. **File validation** — uses `skills/action-check-file@v1` to verify the learner's file contains the expected content.
4. **Step advancement** — uses `skills/action-update-step@v2` to update both `README.md` and `-step.txt` atomically.

All workflows require `contents: write` permission to update the step tracker and README.

### Reusable Actions

| Action | Purpose |
|--------|---------|
| `skills/action-update-step@v2` | Swaps step content in `README.md` and increments `-step.txt` |
| `skills/action-check-file@v1` | Asserts a file exists and contains a regex/string match |
| `actions/checkout@v4` | Standard checkout; uses `fetch-depth: 0` when branch history is needed |

---

## Development Workflow

### Branching
- All learner work goes to `main`.
- Feature/automation changes (like this file) go to dedicated branches (e.g., `claude/claude-md-docs-eK3pV`) and are merged via PR.

### Adding or Modifying a Step

1. Add a step instructions file under `.github/steps/<N>-<name>.md`.
2. Create a corresponding workflow `.github/workflows/<N>-<name>.yml` following the pattern above.
3. Update the `from_step`/`to_step` values in adjacent workflows to keep the chain intact.
4. Update `README.md` to include the new step's content block.

### Updating Workflow Dependencies

Dependabot monitors `github-actions` and `devcontainers` ecosystems monthly. When it opens a PR, review the pinned version bump and merge if CI passes.

---

## Key Files for AI Assistants

| File | Role |
|------|------|
| `.github/steps/-step.txt` | Single source of truth for current course step — do not modify manually without updating README |
| `README.md` | Rendered course instructions — auto-managed by `action-update-step`; manual edits may be overwritten |
| `.github/workflows/*.yml` | All automation — changes here affect course progression for all learners |

---

## What This Repository Does NOT Contain

- No application source code, test suites, or build scripts.
- No `package.json`, Makefile, or language-specific tooling.
- No secrets or environment variables beyond `GITHUB_TOKEN` (automatic).

When a learner completes the course, their repo will have gained: `.devcontainer/devcontainer.json`, `skills.js`, `member.js`, and `comments.js`.
