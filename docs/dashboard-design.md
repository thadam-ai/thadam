# Dashboard surface brief

Mode: Operate. Target: local browser dashboard (`dashboard/src`).

## Confirmed direction

The user's supplied reference screenshots are the visual authority: an inset, warm
charcoal workspace, slim icon rail, compact controls, regular-weight typography,
quiet dividers, subdued status colors, and persistent list/detail panes. This
replaces the earlier broad-sidebar/full-page dashboard composition. Keep the
Thadam name, Tamil identity, teal/blue accents, amber failures and red errors.
Do not copy reference-product names, chat capabilities, production analytics,
charts or statistics that Thadam does not have.

Use a 52px navigation rail, a 46px project header, a bounded independently scrolling
file list and an independently scrolling inspector. The frame has one subtle border
and modest corner rounding. Headers are 20px, section titles 14px, body 12–13px;
metadata is 10–11px with sufficient contrast. Self-hosted Inter carries the entire
interface. Monospace is reserved for evidence, paths and identifiers.

## Workflow and hierarchy

Overview → Suites → Evaluations → Comparisons → Baselines remain the five scopes.
Icons have accessible names, current-page state and hover/focus labels. The project
header carries the current scope and the explicit Run action. Search, outcome
filters and compact invocation totals belong to the file library. Selecting a
file in Overview keeps the mixed library visible; opening a referenced source in
another scope switches to its correct library. The file-list toggle gives the
inspector the full width when needed. File modification dates remain in the
inspector footer, explicitly labeled as file dates.

Select real saved evidence on desktop by default. On narrow screens start with the
file list, then replace it with the chosen detail; Back to files restores the list
without opening another file automatically. Keep the navigation rail available.
Use container queries within the inspector so forms, expected/actual comparisons,
and the focused case editor adapt to pane width as well as screen width.

Results lead with a readable outcome and small counts. Errors/failures sort first;
the first problem and unsuccessful checks open into expected/actual evidence.
Run metadata and raw invocation input/output expand separately. Traces and every
repeated attempt remain inspectable. Comparison outcomes use SDK classifications;
the exact saved gate result stays visible. No invented reasoning or measurements.

A case list selects a focused suite editor. Inactive form panes stay mounted to
preserve invalid JSON drafts. Invalid drafts block saving and switching to full
JSON. Suite identity, revision and file location expand under Suite settings.
Saving refreshes both the inspector and the stale-write fingerprint. File, scope,
back and run actions honor unsaved-edit guards before changing the view.

Run, Compare and Review actions open their existing forms in the inspector; they
do not execute or write merely by opening. Shared/factory execution, progress,
logs, stopping, both comparison types, and exact-evidence baseline acknowledgement
continue to use the existing SDK and session controls.

Dark mode uses warm grays and restrained but distinct teal/blue accents: teal for
active navigation, primary actions and passes; blue for selected evidence, links
and focus. Amber failures and red errors remain distinct. Status dots carry words.
Light mode uses warm paper surfaces and darker semantic colors. Primary buttons
use a muted teal fill rather than bright turquoise. Keep badges unboxed, headings
regular in weight, and borders limited to actual pane/data boundaries. No marketing
headlines, decorative card grids or ornamental imagery.

## Required states and proof

Empty project, invalid artifact, loading, missing/partial trace, reported zero usage,
failed expectations, execution errors, incompatible comparisons, blocked reviews,
unsaved and stale edits, one active job with progress/logs, interruption, saved
comparison, explicit approval, stale digest/destination and unavailable source run.
Use controlled fixtures for browser and API verification. Existing SDK rules own
all evaluation decisions. End users launch through `thadam dashboard` without Node.
