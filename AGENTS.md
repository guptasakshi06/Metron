# Data Optimizer repository instructions

The user executes this project one sprint per new chat.

## Required reading

Read `SPRINT_HANDOFF.md` at the repository root before implementation. It is the canonical scope, sprint status and continuity record. Read `docs/ARCHITECTURE.md` for the original architecture and follow newer recorded decisions in the handoff.

## Execution

- When asked to continue or given the handoff path for implementation without a sprint ID, resume an in-progress sprint or execute the first eligible unfinished sprint. Inspect actual code and Git state before trusting status claims.
- Complete one sprint's real implementation and appropriate verification per chat unless the user explicitly requests a different scope. Do not stop at another plan.
- Before substantial work, set the active sprint to in_progress and record a resume point.
- Update task checkboxes and continuity notes at checkpoints and after partial attempts.
- Before ending, update the sprint ledger, execution record, current/next pointers, last-updated date, decisions, blockers and session history in SPRINT_HANDOFF.md.
- Mark completion only when required acceptance gates pass with recorded evidence. Do not claim unrun tests, simulated measurements, live integrations or customer validation.
- Keep the next pointer on incomplete work. Preserve unrelated changes and all prior history.
- Use the recorded stack and local defaults; document justified changes. Do not require access to previous chats or the original Page to proceed.
- Do not start post-MVP work automatically. Do not publicly deploy, provision paid services, mutate production data, send messages or commit/push without the relevant authorization.
- If the user requests only review or planning, respect that scope and do not start an implementation sprint.

The full protocol, technical boundaries, tasks and definition of done are in SPRINT_HANDOFF.md.

