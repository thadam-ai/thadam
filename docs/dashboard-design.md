# Dashboard surface brief

Mode: Operate. Target: local browser dashboard (`dashboard/src`).

## Confirmed direction

The user approved a complete local testing workspace and the supplied dark sidebar
reference, simplified for clarity in Thadam's existing teal/blue identity. This
extends the established world; it does not replace the brand. Build directly in
code. No alternative visual-world or mockup approval round remains open.

Use a restrained sidebar, project breadcrumb and explicit Run action. Overview
starts with real saved-evaluation and invocation counts, followed by recent
artifacts. Avoid invented charts, decorative gauges, fake timelines, account menus,
or hosted-service controls. Inter is self-hosted. Semantic tokens inherit DESIGN.md.

## Workflow and hierarchy

Overview → Suites → Evaluations → Comparisons → Baselines. Each library is searchable
and filterable. Detail pages lead with a result, metadata and counts; disclose
cases, checks, expected/actual evidence, traces, and individual attempts on demand.
Forms and JSON support suite editing. Running and saving are explicit actions.
Approval places its acknowledgement after contract changes and execution evidence.

Dark default plus light toggle; neutral body text, teal actions/passes, blue context,
amber failed expectations and red errors. Pair every status with words. Borders
separate data; spacing separates tasks. No ornamental imagery is needed.

On narrow screens use five compact navigation tabs, two-column overview counts,
stacked artifact rows, and single-column forms/evidence. Preserve every detail
through expansion rather than shrinking text indefinitely. Tables that genuinely
need multiple numeric columns may scroll inside their container.

## Required states and proof

Empty project, invalid artifact, loading, missing/partial trace, reported zero usage,
failed expectations, execution errors, incompatible comparisons, blocked reviews,
unsaved and stale edits, one active job with progress/logs, interruption, saved
comparison, explicit approval, stale digest/destination and unavailable source run.
Use controlled fixtures for browser and API verification. Existing SDK rules own
all evaluation decisions. End users launch through `thadam dashboard` without Node.
