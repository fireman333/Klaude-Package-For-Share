---
name: auto-git
description: |
  Automatically manage git throughout project development — init repos, commit after each logical step, create safety checkpoints before risky changes, and push to remote only after asking the user. Use this skill whenever: starting a new project, writing or editing code, debugging, refactoring, or any multi-step development task. This skill should be active in ALL coding sessions, not just when the user mentions git. Think of it as a background discipline that runs alongside everything else.
---

# Auto-Git: Automatic Version Control

This skill ensures every coding session has proper version control, so the user can always roll back to a working state. The user experienced significant pain from not being able to revert during debug cycles — this skill prevents that from ever happening again.

## When a Session Starts

Before writing any code, check the project's git status:

1. **No git repo?** Initialize one:
   ```
   git init
   ```
   - Detect project type from existing files and create appropriate `.gitignore`
   - Use the user's existing git config (`git config user.name` / `user.email`). If either is unset, ask the user for their name and email (a GitHub noreply address is fine) before the first commit; never invent one
   - Create initial commit with all existing files

2. **Repo exists?** Run `git status` silently to understand the current state. If there are uncommitted changes from a previous session, commit them as `chore: 保存前次未提交的變更` before starting new work.

3. **No remote?** If the user mentions a GitHub repo or asks to push, set up the remote. Otherwise, just commit locally until they ask.

## .gitignore Templates

Detect project type and include relevant patterns:

**Always include:**
```
.DS_Store
.env
*.log
```

**Chrome Extension:** `_metadata/`

**Python:** `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `*.egg-info/`

**Node.js:** `node_modules/`, `dist/`, `.next/`

Merge patterns if the project spans multiple types.

## When to Commit

Commit after each **logical step** — not every single file edit, but every meaningful unit of work. Examples:

- A bug fix is complete (even if it touched 5 files)
- A new feature or function is added
- A config file is updated
- Refactoring is done
- Tests are written or updated
- Documentation is updated

Do NOT wait for the user to ask. Just commit naturally as part of the workflow.

## Commit Message Format

Use **Conventional Commits with Chinese descriptions**:

```
<type>: <Chinese description>
```

Types:
- `feat`: 新功能
- `fix`: 修復 bug
- `refactor`: 重構（不改功能）
- `docs`: 文件/README
- `chore`: 雜項（設定、.gitignore、依賴）
- `style`: 格式調整
- `test`: 測試

Examples:
```
feat: 加入 postMessage 跨 iframe 通訊
fix: 修復第二題無法送出的問題
refactor: 簡化 simulateInput 策略為兩層
docs: 更新 README 安裝說明
chore: 新增 .gitignore 排除 _metadata
```

Keep messages concise (one line). The message should tell the user what this commit does, so they can find it later when they need to roll back.

Always append:
```
Co-Authored-By: Claude {current model — copy the attribution line the system provides this session; never hardcode a version} <noreply@anthropic.com>
```

## Safety Checkpoints

Before any of these situations, create a **checkpoint commit** with whatever is currently working:

- **Before starting debug** — when the user reports a bug or something isn't working
- **Before rewriting a file** — especially if replacing large sections of code
- **Before exploratory changes** — when the user says "試試看", "try this", or you're unsure if a change will work
- **Before removing features** — when simplifying or removing code

Checkpoint commit format:
```
checkpoint: <what's working right now>
```

Example:
```
checkpoint: 第一題正常運作，準備 debug 第二題問題
```

This way, if the change breaks things, the user can `git diff` to see exactly what changed, or `git checkout` to go back.

## Push (ask first)

Never push automatically. After a batch of commits, if a remote is configured, ask the user once: "要推到遠端嗎？" and only then run:
```
git push origin <current-branch>
```

Pushing may publish code or trigger a deploy, so always wait for an explicit yes. If push fails (no remote, auth issue), mention it briefly and move on.

## Workflow Example

Here's how a typical session should flow:

```
User: 幫我加一個匯出 CSV 的功能

[You check git status — clean]
[You write the feature across 2-3 files]
[You commit]:  feat: 加入 CSV 匯出功能
[You ask: 要推到遠端嗎？ → push only if yes]

User: 匯出的格式不對，幫我修

[You commit checkpoint]:  checkpoint: CSV 匯出功能完成，準備修復格式
[You fix the format]
[You commit]:  fix: 修正 CSV 匯出的欄位格式
[You ask: 要推到遠端嗎？ → push only if yes]

User: 試試看把匯出改成用 streaming 的方式

[You commit checkpoint]:  checkpoint: CSV 格式修正完成，準備嘗試 streaming
[You try streaming — it breaks things]

User: 算了，改回來

[You can easily revert because there's a checkpoint]
```

## What NOT to Do

- Don't ask "要我 commit 嗎?" — just do it
- Don't commit half-finished work (wait until the logical step is done)
- Don't skip commits because "it's a small change" — small changes are the hardest to reconstruct later
- Don't use `git add -A` blindly — check for `.env`, credentials, or large binary files first
- Don't amend previous commits — always create new ones
- Don't force push unless the user explicitly asks
