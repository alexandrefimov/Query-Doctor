# Query Doctor UI/UX Audit Notes

Last updated: 2026-05-21

This note records the accepted product takeaways from the May 2026 UI/UX audit.
The goal is to make Query Doctor usable by an analyst who needs to understand
what is wrong with a slow query, where to inspect it, and what to try next,
without weakening the safety contract or exposing raw artifacts.

## Accepted For Current Quick-Win Slice

- Make the results table easier to scan: replace `Score`, `STATS`, and `META`
  shorthand with visible priority, table-stat, and metadata wording.
- Add a permanent results legend so color and small badges are not the only
  explanation of severity and status.
- Rename result groups from engine-centric labels to task-centric labels.
- Open Details in the current tab. The Details pages already have breadcrumbs
  back to results, and same-tab navigation avoids tab sprawl.
- Remove the production design-style toggle from the header; keep the light/dark
  theme toggle.
- Make the fixed scan timezone visible in the Scan Hour label until timezone
  selection becomes configurable.
- Add a short first-run hint above the scan form that tells analysts the basic
  workflow.
- Split Recent scan setup into a default Basic scan layer with scan target,
  date/hour, and Run, plus collapsed Source and Advanced settings for source
  selection, filters, and collection limits. Owner-gated username selection
  stays visible in Basic scan when required by source visibility.
- Make the Recent results table read from the analyst signal first: `Finding`
  is the first content column after rank, while Query ID, user, priority, and
  collection statuses stay available as context.
- Replace the dense Results metric grid with a compact summary strip:
  `Scanned`, `Needs attention`, `Worth reviewing`, `Rewrite`, and `Stats`.
  Move secondary counters such as result rows, metadata contexts, and rewrite
  funnel counts into collapsed Scan details.
- Combine Results notices such as rewrite guidance, action-outcome count,
  empty-state notes, and scan warnings into one compact notes block so they do
  not compete as separate first-screen cards.

## Accepted For Diagnose Form Follow-Up Slice

- Keep `Recent queries` as the primary mode and `One Query ID` as the secondary
  mode, but make the first-run hint mode-specific so Query ID mode does not
  instruct users to choose a finished-query hour.
- Move the `Finished queries` / `Running now` scan target into Basic scan.
  This is a workflow choice, not an advanced filter. Advanced settings should
  keep only filters, scope notes, and collection limits.
- Keep `Source` shared by Recent and Known Query ID modes, and keep the selected
  source cluster always visible near the top. Source cluster is one of the first
  choices an analyst must verify before running diagnosis, so it should not be
  hidden inside Advanced settings.
- Put the primary Run action close to the Basic scan inputs on desktop, while
  preserving the full-width mobile action.
- Replace native select arrows with a consistent right-side affordance that
  gives the chevron breathing room and separates it from the selected value.
- Add visible keyboard focus treatment to segmented controls.
- When the user switches the scan target to `Running now` before submitting,
  label already visible finished-query results as previous results so stale
  output is not confused with the pending running scan.
- When the user switches to `One Query ID`, collapse already visible Recent
  results behind a previous-results disclosure so the one-query form remains the
  primary task.
- Compact the mobile header and Recent results pre-table area: keep navigation
  on one short row, make the metrics strip horizontal, and move the table legend
  after the table.

## Kept As Follow-Up

- Mobile card layout for result rows. This is a larger responsive redesign.
- Unified Report/Optimizer naming and copy/print export. This touches action
  semantics and validation affordances, so it should be handled separately.
- Further Details safe fact expansion. The current Details view model now carries
  query-context timestamp, admission wait, and resource footprint when the
  analyzer provides them. Compile/admission/execution time splits and worst
  estimate-to-actual operator pairs still need explicit browser-safe analyzer
  facts before they can be displayed.

## Accepted For Source And Advanced Polish Slice

- Make the selected source cluster a persistent top-level control. It should be
  easy to verify and change before choosing Recent queries versus One Query ID,
  while credentials and endpoints remain local-config only.
- Move `Minimum duration (sec)` back into Basic scan. It is an everyday scan
  narrowing control, not an advanced collection detail.
- Treat collection concurrency as configuration-owned by default. `Parallelism`
  and `Metadata parallelism` already have bounded server defaults and local
  config keys; the default browser flow should not ask analysts to tune worker
  counts before a normal scan.
- Keep any collection override behind a clearly secondary disclosure only if it
  remains needed for local troubleshooting. Do not remove the server-side caps
  or local config support.
- Reconsider `Resource pool` as a default visible filter now that Username can
  be inferred and preselected for owner-gated local web runs. Pool remains
  useful on multi-tenant clusters and for admission/pool investigations, but it
  should not compete with source, scan target, time window, duration, username,
  and Run in the primary form.
- Keep Diagnose `Advanced settings` hidden by default. Show it only when local
  config explicitly enables editable advanced filters such as `user` or `pool`;
  otherwise those filters remain config-owned defaults and do not add another
  disclosure to the everyday scan path.

## Accepted For Desktop Web Audit Follow-Up Slice

- Move instructional Diagnose copy off the main form surface and into the
  nearest `i` help controls. Source-locality, Recent scan start guidance,
  Running caveats, and One Query ID scope are useful context, but they should
  not consume first-screen space when the user already knows the workflow.
- Keep the Diagnose page title compact. The mode explanation belongs in the
  `What to analyze` help popover, not as a permanent subtitle above the form.
- Keep the Running now layout tight after the user switches scan target: the
  Run button should stay next to the visible Basic scan fields, not parked at
  the far edge of a Finished-query grid with hidden date/hour controls.
- Keep the Results table key terse. It should explain column shorthand, not
  repeat the Details call to action or read like a second help paragraph.
- Keep the separate `/running` page consistent with the main Diagnose running
  mode. It should not reintroduce Resource pool, worker-count controls, or
  dense scope cards by default after those controls moved to config-owned
  behavior.
- Simplify the `One Query ID` mode by replacing the heavy scope card with a
  short helper sentence near the Query ID input. The task is a single explicit
  id, so the form should stay lighter than the Recent scan setup.
- Record broader desktop audit follow-ups before starting a larger visual
  redesign: Details can read as nested cards inside a large panel.
  This is not a safety blocker, but it remains a desktop polish target.
- Collapse standalone Query Optimizer scope strips into one secondary
  disclosure and move input rules into the SQL field help. The trust boundary
  must stay explicit, but it should not compete with the pasted-SQL task before
  the user asks for more context.
- Rework Help from one long document into a compact task surface: shortcut
  cards, a short quick-start list, and collapsed topic sections keep safety and
  workflow explanations available without making the page feel like a manual.

## Accepted For Secondary Desktop Pages Slice

- Keep the standalone Running Queries page aligned with Diagnose: source,
  minimum duration, and Run are the visible task controls, while live-snapshot
  caveats move into nearby field help instead of occupying form space or page
  header space.
- Keep Query Optimizer focused on paste-and-analyze. The primary Analyze action
  should sit directly after the SQL input, and Scope and safety should remain a
  secondary disclosure below the action rather than a wide peer control.
- Make Action outcomes useful when empty. A compact empty state should explain
  the next action and avoid rendering two blank tables before any feedback has
  been recorded.

## Accepted For Results And Details Control Slice

- Keep the Results table key visible, but style it as a quiet reference strip
  rather than separate chip-like controls.
- Keep available Details actions as explicit buttons. When report or optimizer
  work is not available for a case, render the reason as compact status text
  instead of a disabled action card.
- Do not remove the safety reason for optimizer unavailability; keep the same
  safe source-scope message visible without exposing raw SQL or local paths.
- In Details, a row with a clean analyzer score but a Medium/High action
  candidate should read as a follow-up candidate, not as a clean verdict.
  Candidate strength remains in the recommendation card so case priority and
  candidate strength do not collapse into one label.
- Reduce Details first-screen weight by splitting long verdict summaries into
  a short headline plus supporting signal, and replacing the large verdict KPI
  cards with a compact meta strip for Query ID, priority, duration, and
  confidence.

## Accepted For Details Quick-Win Slice

- Merge the old Case overview and Analysis summary into one verdict block. The
  verdict title owns the main signal, while KPI cards add supporting context
  such as priority, duration/baseline, and confidence.
- Make the verdict title read as a supported analyst review signal rather than
  an engine label: query-shape rewrite review, stats gaps, runtime queueing,
  skew, data movement, storage follow-up, or competing signals.
- Keep "what to do next" only in Recommended changes so the page does not repeat
  action guidance in multiple formats.
- Promote existing baseline/regression, cluster-runtime, spill, table-stat, and
  review-anchor facts as secondary chips rather than equal-weight overview
  cards.
- When primary bottleneck classification is unavailable but a High/Medium
  action candidate exists, make the verdict say that a query-shape or stats
  review candidate was found instead of showing `Not classified`.
- Keep the low-level Diagnostics and evidence block collapsed by default.
- Use one page `h1`; make Recommended changes and Details action controls
  section headings instead of nested page titles.
- Collapse action-outcome buttons behind one "Mark result" disclosure so the
  recommendation text remains the primary reading path.
- Rename Query Doctor pipeline timings so they are not confused with query
  runtime timings.
- Keep generated report and optimizer outputs available on Details, but collapse
  the bulky trusted result bodies by default so action controls do not dominate
  the page after a report or optimizer run.
- Make Details read as one continuous case page instead of nested cards inside
  a large card. The verdict, Recommended changes, Diagnostics, and action
  controls should be sibling sections; repeated recommendation/evidence items
  can remain card-like for scanning.

## Accepted For Visual Quick-Win Slice

- Keep monospace typography for code, SQL, query ids, and compact technical
  values, but use the main sans-serif face for UI chrome such as inputs,
  badges, segmented controls, navigation, and outcome controls.
- Raise the default reading size to 14px and make page/section headings more
  visible without changing the existing page architecture.
- Normalize visible UI font weights to the 400/600/700 range.
- Darken muted color tokens so secondary text remains legible at the sizes used
  by the UI.
- Increase desktop control heights and provide 44px touch targets on mobile for
  common buttons, inputs, segmented controls, and the theme toggle.
- Use `not-allowed` for disabled controls instead of the wait cursor.

## Accepted For Diagnostics Flattening Slice

- Keep `Diagnostics and evidence` collapsed by default, but make the expanded
  content flat: `Pipeline`, `Runtime`, `Metrics`, `Metadata`, and `Score` are
  sibling sections instead of `Supporting findings` and `Evidence details`
  wrappers.
- Keep existing runtime, metrics, metadata, and score renderers on the same
  safe typed view-model inputs; this slice changes information architecture, not
  diagnostic claims.
- Remove the nested `All collected runtime metrics` disclosure. Correlated and
  all-metric tables remain in the Runtime metrics block without a fourth
  click-through layer.

## Accepted For Details Safe-Facts Slice

- Surface existing analyzer-owned `CM Query Context` / `Query Profile Context`
  fields in Details without reading raw provider payloads or raw artifacts.
- Promote bounded query context into the verdict chips when available: query
  window, query type, pool, admission wait, and a compact resource footprint.
- Add one `Query context` disclosure under Runtime diagnostics for the same
  allowlisted facts.
- Keep `CM Time-Series Context` metric-window timestamps hidden from browser
  output; only query-level start/end timestamps from the safe query-context
  section are eligible for display.
- Keep the synthetic demo pack aligned with the Details story by including safe
  query-context facts for the demo cases: query window, admission wait, and
  compact resource footprint.

## Accepted For Details Visible-Dedupe Slice

- Details has a durable product contract: the visible page is an analyst
  decision flow before it is an engineering evidence dump. It should answer
  why this query deserves attention, where to inspect the query or plan, what
  supported change direction to try, and how to verify the result.
- Treat the visible Details path as a three-step analyst story: why this query
  deserves attention, where to inspect the query or plan, and what supported
  change direction to try next.
- Keep collector-source organization out of the first screen. Pipeline status,
  profile sections, metric-provider details, and broad fact tables stay in the
  collapsed Diagnostics layer unless they directly support the verdict,
  recommendation, verification step, or an explicit limitation.
- Do not repeat the verdict sentence as a KPI card. The verdict title already
  owns the "what is wrong" answer; KPI cards should add context such as
  priority, duration, confidence, baseline, or resource footprint.
- Keep verdict chips for context that helps triage the case, not for action
  facts already shown in Recommended changes. Review anchors and candidate
  ranks belong in the recommendation card.
- Keep Recommended changes action cards focused on the action: where to look,
  what to change, how to verify, and only non-duplicated supporting facts.
  Candidate score/rank and guardrails should stay secondary.
- Render each Recommended changes card in analyst decision order: lead with the
  visible change direction and verification step, keep safe review anchors
  visible, and collapse the longer "why" text behind a compact disclosure.
  Supporting facts, technical guardrails, and candidate score/rank details stay
  below that flow.
- Make the `Why` and `What to change` copy explain the decision, not the
  internal scoring model. Use language like "deterministic analysis found...",
  "start with this SQL/plan location...", and "try to reduce rows earlier..."
  while preserving guardrails that the recommendation is not a proven root
  cause or guaranteed speedup.
- Keep Diagnostics as the engineer layer. Its question groups should answer
  questions that are not already answered by the visible verdict and action
  card, such as when/how much work ran, baseline normality, and queue or cluster
  context.
- Keep unavailable Details report/optimizer actions compact. When no action can
  run for the selected case, show a single collapsed status row instead of
  giving unavailable notes the same weight as Recommended changes.
- Distinguish case priority from candidate strength in labels. A High stats or
  query-shape candidate can still live on a Medium-priority case; the UI should
  not make that look contradictory.

## Rejected Or Not Applicable Now

- Hiding safety language everywhere. Safety copy should not dominate the first
  screen, but safety affordances and Help explanations remain important because
  Query Doctor handles trusted diagnostic output.
- Changing backend scan timezone behavior in this UI slice. The current engine
  still uses the configured Recent scan timezone; this slice only makes that
  visible to the user.
- Reworking the result table into a mobile card layout. That needs a dedicated
  responsive table pass because it changes row scanning and keyboard behavior.
- Compile/admission/execution time breakdowns and worst estimate-to-actual
  operator pairs are still follow-up work until the analyzer exposes them as
  explicit browser-safe facts.
