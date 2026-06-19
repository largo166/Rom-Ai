# Rmo-AI Desktop Mainline Rules

1. The only active product mainline is `ROM-AI-local-demo`.
2. The current product target is a local Windows desktop app. Server, multi-user, object storage, JWT, CORS serverization, and SaaS work are extension seams only.
3. The knowledge base is the context backbone. Judgment, strategy, translation, risk, reuse, and review outputs should prefer project context plus knowledge retrieval and cite sources where possible. Simple formatting and copy tasks do not require retrieval.
4. Real user file operations must be previewable, reversible, and non-destructive by default. AI proposes structured plans; the system executes only after confirmation.
5. `get_current_principal()` is a future seam for identity, not a login/auth system for this desktop round.
6. Do not delete packaging, build, migration, or demo chains. Deprecated branches should be archived or marked, not silently removed.
7. Project Center is for reading project state. AI Agent is for executing project-bound tasks. Do not turn AI Agent into a duplicate dashboard.
8. Built-in skills must run inside Rmo-AI at runtime. Codex/Claude can help development but must not be required for installed users.
9. Skill logic, prompt templates, execution chain, output schema, and writeback behavior are built into the app.
10. API credentials are runtime configuration. The desktop app may prefill local runtime config for an installed single-user build, but synchronized files and docs must not depend on external assistants.
