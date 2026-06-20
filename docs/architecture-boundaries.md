# ROM-AI Architecture Boundaries

This note records the current authority boundaries after the five-section cleanup.

## Product Sections

- Project Center: current project facts, analysis, meetings, tasks, data link, results.
- Knowledge Base: local folder intake, managed packages, Markdown summaries, index, cross-project retrieval.
- AI Agents: existing skill-card experience, strengthened by project data, meetings, tasks, and knowledge retrieval.
- Network Platform: placeholder only for now.
- Boss Dashboard: cross-project overview.

## Backend Authority

- `routes/projects.py`: authoritative project workspace routes and the main `POST /api/projects/{project_id}/agent-chat` runtime.
- `routes/knowledge.py`: authoritative knowledge and local material intake routes.
- `routes/agents.py`: AI catalog and legacy agent-run entry only.
- `routes/agent_chat.py`: lightweight context and writeback compatibility only.
- `routes/skill_cards.py`: skill-card read/manual/legacy execution compatibility only.
- `routes/inbox.py`: legacy compatibility; product concept is now Knowledge Base local material intake.

## Service Boundaries

- `managed_package.py`: non-destructive managed material packages.
- `cross_project.py`: source-backed cross-project experience retrieval.
- `image_prompting.py`: image prompt templates, keyword extraction, and four-view prompt variants.
- `analysis.py`: startup and incremental analysis.
- `execution.py`: existing skill-card execution runtime; do not expand it with intake or retrieval package concerns.

## Cleanup Rule

Compatibility modules may remain, but new product behavior should be added to the authority module listed above.
