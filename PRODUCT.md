# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Developers testing Python AI agents locally, often from VS Code, and reviewing evidence before accepting a change.

## Product Purpose
Thadam tests developer-supplied expectations, records observable execution evidence, and compares agent reliability. The local dashboard lets developers edit saved suites, run evaluations, investigate failures, compare results, and explicitly review and approve baselines.

## Operating Context
One selected project folder per dashboard session. Existing Python SDK and CLI remain the source of evaluation rules and useful for CI. The browser opens from a terminal command; end users need no frontend development tools, account, or hosted service.

## Capabilities and Constraints
Support single/repeated evaluations, shared callables/factories, every built-in assertion, available tool/model traces and token usage, both comparison types, suite revisions, review artifacts and approved baselines. Python agent and custom verifier source stays in the user's editor. Only explicit actions run code or save files. One active evaluation, visible progress, interruption without a fabricated completed report. Local trusted application execution is not a sandbox or enforced timeout.

## Brand Commitments
Thadam (தடம்), with its existing teal/blue identity and amber failures/red errors. The user supplied refined dark reference screenshots and requested neatness and elegance: warm charcoal, a slim icon rail, quiet controls, compact type and persistent list/detail panes. These replace the earlier broad-sidebar composition. Dark remains default with a light toggle. Navigation: Overview, Suites, Evaluations, Comparisons, Baselines.

## Evidence on Hand
Controlled refund and LangGraph examples; saved baseline artifacts; SDK-generated single/repeated runs, comparisons, reviews and approvals. No invented analytics, usage totals, dates, trends, or hidden reasoning.

## Product Principles
- Preserve complete evidence and unavailable-versus-zero distinctions.
- Make the overall result obvious, then disclose detailed evidence on demand.
- Share evaluation and approval rules across the CLI, SDK, and dashboard.
- Validate before execution/saving and protect reviewed baselines.
