# Crewloom project review — 2026-10-06, repeated audit

This document preserves findings and version-scoped evidence. The [unified implementation plan](INTELLIGENCE_ROADMAP.md) owns the active W01–W12 execution register covering R01–R39 and all owner requirements. Delivery-order passages below are review history, not separate active plans.

The repeated audit identifies two additional publication/privacy defects: nested project-local data can enter a source distribution, and local ignore coverage can report publication readiness without checking the staged ignore policy. The current published branch has completed the first context-study v2 run; the earlier statement that useful token effects were entirely unmeasured is superseded below.

This task reviews and records findings. Runtime repairs, release publication and consumer-project enrollment are separate acceptance work.

## Next-stage follow-up — newer local source, 2026-10-06

The [next-stage assessment in the unified plan](INTELLIGENCE_ROADMAP.md#next-stage-audit-and-benefit-assessment--2026-10-06) updates W01–W05 acceptance and compares existing source with Paperclip, Aider, Repomix, LangGraph continuation and MCP capability negotiation. External comparisons concern documented mechanisms, not measured product superiority. The earlier tables retain their original source-scoped observations.

The local candidate now has an sdist filter in `setup.py`, revised `MANIFEST.in`, a static-SVG/motion resource distinction and `project_binding.staged_ignore_gaps`. These changes were already present when inspected; this review did not author or publish runtime repairs. Published main remains `40d4168a`; all 45 frozen acceptance files remain unchanged.

Fresh actual builds with setuptools 80.10.2 used 13 synthetic canaries injected after making a disposable source copy. The sdist hook excludes nested `.crewloom` content and `.env.local`; the private `.crewloom` path still appears in its `SOURCES.txt`. Nested `node_modules`, `build` and `dist` bytes reach the direct wheel, sdist and rebuilt wheel; `.next`, `.venv` and `.pytest_cache` bytes also reach the sdist. A public-looking symlink copies synthetic content from outside the build root into all three artifacts. A portable project JSON remains; the synthetic `.env.example` is excluded too, so public-template preservation needs an explicit reviewed contract. This extends R33; it does not establish that real credentials were previously published.

An independent staged-policy fixture shows R34's original unstaged-ignore case now refused. Complete staged consumer rules are accepted; `.git/info/exclude` alone is refused. However, a later nested negation leaves `nested/.crewloom/private.json` unignored while readiness remains `ready`. An unmerged `.gitignore` also reports `ready` because its stage entries are reconstructed without refusing the conflict. Git's own merge-commit refusal remains a separate boundary. First fixture attempts used a noncanonical macOS temporary-root alias, then omitted the consumer-role privacy option; those setup problems were corrected and retained before attributing results to the product.

Fresh existing suites: packaging 18 cases (17 passed, one skipped), privacy34 passed and model-host29 passed. These supersede the earlier packaging failures for this local source but do not close the independently reproduced boundaries. The host probe still proves CLI flag/version support while leaving authentication unverified; it does not establish actual model capabilities or quota. Existing handoff/state writes remain useful foundations without proving the planned durable cross-host transfer protocol.

Raw source hashes, build logs, extracted-byte/member observations and corrected fixture attempts are retained in the selected project's ignored state. No paid model calls, other-project changes, public pushes or release publication occurred in this review. W01–W12 remain open; the unified plan alone owns their current status and acceptance.

### Assessment of the supplied implementation report

The supplied agent report honestly declares partial W01 work, no commit/push, archive-test skips in the ordinary gate and a build backend outside the declared range. Its broader completion labels are not supported by the independent boundary evidence above. The relevant runtime/build source hashes are unchanged since that review. A fresh follow-up independently passes all20 packaging cases on the existing setuptools80.10.2 builder within `>=77,<81`, plus all5 root-separation cases. No download or permission was needed for that validation. These cases do not include all known adversarial archive/readiness conditions.

The implementation checkpoint marks R34 completed and pending simultaneously, with empty `known_failures`/`unverified` lists despite the unresolved boundaries and original unsupported build verification. Its short fingerprints also omit the changed staged-policy implementation. Preserve the original checkpoint/report as attempt evidence; reconcile current source fingerprints, verified receipts and remaining failures before the next dispatch. The authoritative register and memory now describe R33/R34 as partial. This assessment changes evidence/status documentation only; no runtime repair or published branch was changed, and the complete gate claimed by the agent was not independently rerun here.

## Exact versions and scope

- Published main reviewed in an isolated clean snapshot: [40d4168a](https://github.com/elbayoumi/crewloom/commit/40d4168a64df53e0381aaaf0b67f4c3d18f86dd9). All eight jobs of [Core checks run 37476504993](https://github.com/elbayoumi/crewloom/actions/runs/37476504993) passed. PRs 5, 6 and 7 are merged; no PR was open when inspected.
- Development and the globally exposed editable CLI remain based on `23a6ebb`, with substantial local modifications. Privacy/install/coordinator fixes and reviewed branding are local; published main does not contain the new privacy CLI or index guard. `model_host`, the study runner and map sources also differ. These source variants must be reconciled before a release.
- Latest GitHub release remains `v0.5.0`; both inspected package declarations are `0.6.0.dev0`.
- Audit fixtures use synthetic contents only. No customer project, actual credential, public branch or frozen acceptance contract was changed. The 45 frozen acceptance files are unchanged.
- Fresh archive/index/dashboard reproductions and command logs are retained in project-private state. A pristine published source snapshot was restored after synthetic canaries were copied to a separate packaging fixture.

## Priority findings from this audit

| ID | Priority and affected scope | Demonstrated behavior | Required acceptance |
| --- | --- | --- | --- |
| R33 | **P1 — source distribution privacy**, identical local/main `MANIFEST.in` | A real sdist built with setuptools 80.10.2 includes synthetic `examples/review-private-canary/.env.local` and `.crewloom/backup.json`. The root-specific prunes do not protect every nested namespace included by `recursive-include examples *`. A synthetic project JSON is included too; portable declarative policy is ordinarily allowed source and is not itself a secret. Existing distribution tests sanitize `.crewloom` folders out of the build source first, and the filename exclusion assertions do not cover `.env.local`; passing that suite is not this adversarial archive check. | Explicitly exclude reserved private namespaces and environment files at every depth, preserve approved public fixtures/templates, and test actual sdist and wheel members using private canaries. Reject before release, without deleting local data. |
| R34 | **P1 — publication-readiness semantics**, local privacy implementation | With an empty `.gitignore` staged and generated privacy rules only in the working tree, `project privacy` returns `ready`; the staged file is zero bytes. Coverage probes read current working-tree ignore rules, not the policy that would be committed. | Distinguish local readiness from staged/published readiness. Require effective staged ignore coverage or refuse the inconsistent index before publication; retain ordinary setup behavior and test absent/staged/nested ignore files and later negations. |
| R01/R08 | **P1 — source reconciliation**, local versus published | The global command resolves to the old editable source. Published main lacks the local forced/ignored-index privacy checks and task-memory seeding. Green hosted checks do not mean unpublished guards are deployed. | Integrate exact reviewed source with hooks enabled, run selected-index and installed-distribution acceptance, and expose source root/version/revision in diagnostics. Preserve independent projects and unrelated changes. |
| R13/R14 | **P1 before the selected local release — asset packaging** | Two of 17 packaging cases fail: three animation files are undeclared in package-data, and the frozen asset-inventory assertion still expects one banner. A freshly built local wheel carries three SVGs and none of the new GIF/MP4s. Eleven clean build/install cases nevertheless pass, so those cases do not cover this new resource contract. | Agree a coherent public brand-resource layout, retain immutable acceptance, ensure documented assets resolve after wheel/sdist install, and prove both positive and private-exclusion cases. |
| R09/R10/R18/R19 | **P2 — dashboard evidence and input correctness**, identical local/main files | Fresh reproduction: 36 of 42 roles are `healthy` with zero tool runs; a status-less challenge is invisible; folded description becomes `>-`; a quoted path containing a space becomes three argv entries. | Separate documentation/configuration/execution/acceptance, expose unknown challenge status, parse a bounded validated frontmatter format, and use exact validated argv/typed forms with bilingual path cases. |
| R02/R12 | **P2 — current integrity/evidence metadata**, published main | Full verification of all 608 recorded manifest paths finds 47 hash mismatches and one missing generated `dashboard/tsconfig.tsbuildinfo`. The manifest identifies `0.5.1`, while package metadata is `0.6.0.dev0`. These are full-manifest results; the earlier 15-file figure used a limited cached subset. | Preserve historical evidence under a clearly historical label; create and independently verify an exact candidate manifest excluding generated state. Keep current claims consistent across CLI, docs and release. |
| R35 | **P2 — local Docker-enabled gate budget**, published snapshot | The mandatory gate times out after its unchanged 60-second module limit on `test_context_study.py`, after 119 completed passing cases. This is a local execution failure; the published CI is green. | Standalone diagnostic passes all 50 cases in 213.292 seconds with real Docker and no skips. Measure grader/container overhead, preserve the existing acceptance and timeout contract, and prove the actual Docker-enabled mandatory invocation completes on the target host. Do not increase the limit or omit cases merely to hide the failure. |

The archive case demonstrates an exclusion defect using synthetic data; it does not establish that any real secret was previously published. The staged-ignore case demonstrates a misleading readiness verdict, while existing reserved-path detection still rejects forced private additions covered by its classifier.

## Corrections to earlier study findings

### R03 — first study v2 outcome is now recorded

[The published v2 record](https://github.com/elbayoumi/crewloom/blob/40d4168a64df53e0381aaaf0b67f4c3d18f86dd9/examples/evaluation/context-study-v2-20261006.json) contains all 18 planned Codex rows, all scored, at source revision `6e092eca`. Independently recomputing the public rows gives:

- Full source: 9 rows, 99/99 held-out checks, mean input tokens 14,940.78.
- Closure map: 9 rows, 99/99 held-out checks, mean input tokens 12,193.67.
- Input tokens are **18.3867% lower**, with differences of 2,731–2,767 tokens in all nine matched pairs.
- Mean generation duration is 30.967 seconds versus 31.675 seconds; a speed improvement is not established. All cost fields are null. Cache effects do not support a reliable billed-cost saving.
- This is one host, three synthetic Python tasks and three repeats. Quality is at the ceiling; general project quality, other hosts and other languages remain unverified. This audit recomputed the existing record; it made no new provider calls. Input fingerprints were reported verified by the original runner, not independently recovered from its private raw trial archive here.

### R04 — OpenCode response shape diagnosed, real outcome pending

Merged PR 7 states the artifact schema and declared paths in OpenCode's task-local agent profile while preserving the frozen user prompt. Sixteen fresh boundary cases pass. Recorded diagnosis is 13 flat path maps and one `files` response, rather than the required `artifacts` list. This corrects a missing instruction without accepting unsupported response shapes. Actual-model success after this change remains unobserved; the four earlier timeouts and failed actual application pilot remain open.

## Fresh verification ledger

- Local privacy boundary suite: 28/28 pass. Selected-index privacy reports local `ready` with no detected tracked private paths; the staged-policy counterexample above limits that claim.
- Local dashboard: 32/32 tests pass and production build passes. The four dashboard counterexamples above are outside those passing assertions.
- Local real wheel/sdist build, clean install and use suite: 11/11 pass. Packaging declaration/resource contract: 15/17 pass, two failures retained.
- Published OpenCode schema boundary suite: 16/16 pass.
- Published study module without its Docker opt-in: 50 cases, 33 pass and 17 explicit skips.
- Published full gate with Docker enabled: fails by a 60-second study-module timeout; 119 preceding cases complete successfully. This cannot be described as full local runtime acceptance.
- Published full offline gate: 1044 cases, 951 pass and 93 explicit optional skips; exit 0. This does not replace the failed Docker-enabled mandatory run.
- Published standalone study module with real Docker: 50/50 pass, no skips, 213.292 seconds. Acceptance succeeds outside the gate, but this does not repair its 60-second mandatory invocation. Providers are stand-ins in the collector tests; this is not a new live model study.

## Remaining product boundaries and delivery order

Native callback coverage remains host/version/launch-mode dependent, with Claude unobserved. Managed broker/container controls do not sandbox arbitrary same-user tools. Review tokens prove possession, not independent human review. The failed actual application pilot still needs an accepted end-to-end generation run. Multi-project scheduling/UI, aggregate request budgets, process cancellation/orphan reconciliation, bounded history/shared watchers and representative role evaluations remain the earlier scoped backlog; they were not load-tested or implemented in this audit.

1. Close R33 and R34, then integrate the selected privacy/source variants with release gates intact.
2. Resolve brand-resource packaging and candidate manifests; verify archives rather than declaration strings alone.
3. Repair reproduced dashboard evidence/input defects.
4. Verify actual OpenCode response behavior, application acceptance and claimed host callbacks; extend the v2 workload before general savings claims.
5. Add measured admission, aggregate budgets, cancellation/recovery and project/task UX.

## Intelligence follow-up — same published revision

[The detailed intelligence roadmap](INTELLIGENCE_ROADMAP.md) translates the review into repair contracts, proposed features, their owning modules, failure handling and acceptance. These are proposals, not shipped automation.

Four additional source-level counterexamples are independently reproduced:

- **R36:** dependency conditions accepted by lesson validation are ignored during matching, including in published main.
- **R37:** accepted malformed lesson patterns raise an error during selection, including in published main.
- **R38:** missing seed warnings let both map renderers return 1,800 bytes under a 1,024-byte budget.
- **R39:** the published closure builder silently drops an oversized reached constant-only module from both representation and omission metadata. The final fixture uses its supported absolute-import convention.

Fresh focused lesson/map suites pass 23 and 30 cases respectively; those assertions do not cover the new counterexamples. Prior full-gate, archive and provider-study results above are reused with their recorded scope; no new provider study, runtime repair or client rollout occurred in this follow-up. Main remained `40d4168a` at inspection.

The proposed sequence is publication/privacy correctness, context and lesson correctness, explainable retrieval/impact tests, evidence-driven learning/repair, then multi-project workspace, budgets/cancellation and optional provider caching/model policy.

## Historical initial assessment

The following earlier snapshot and backlog are preserved for traceability. Its PR status, unmeasured-v2 statement and limited manifest count are superseded by the repeated audit above. Remaining unverified items are not implicitly closed by passing CI.


Crewloom has a verified execution and project-isolation foundation, but useful context savings and reliable provider-generated application delivery are not established. The next iteration should close those measured failures, make status indicators reflect execution evidence, and reconcile development, release and documentation state.

This is an assessment and implementation backlog, not a claim that the proposed fixes were made.

## Reviewed versions and evidence

- Published `main`: [`e4c06c83`](https://github.com/elbayoumi/crewloom/commit/e4c06c83ace6b7da34dc7be67779db8f4f502689). Its eight [Core checks jobs](https://github.com/elbayoumi/crewloom/actions/runs/37378986175) completed successfully.
- Open [PR #5](https://github.com/elbayoumi/crewloom/pull/5): study-v2 runner at `4470f72f`; its hosted checks passed at inspection. The PR states that no v2 provider call was made.
- Local development checkout: base `23a6ebb`, with 152 changed/untracked status entries before this report. The globally installed editable CLI imports that checkout, rather than the newer published main. This is development divergence, not evidence that changes were lost.
- New offline checks: 23 tests pass across repository-scope, filesystem-alias, native-delivery and readiness acceptance boundaries. The public structure/syntax/link check passes with regression execution skipped.
- New dashboard reproductions: 36/42 roles are classified `healthy` with zero recorded tool runs; a challenge without an explicit status line is counted as zero open challenges; a folded YAML description becomes the literal string `>-`. Published `dashboard/lib/repo.ts` matches the inspected local file.
- Historical recorded study: 36 rows; all nine scored full-source Codex trials passed 11/11, while all eight scored selected-map trials passed 0/11. OpenCode had 14 structured-response failures and four timeouts.
- Recorded actual application pilot: billing acceptance failed `missing_description_is_refused`, planning timed out, and publication was correctly refused. The reference application passes 37/37 with a deterministic provider stand-in, which is a separate result.

The review did not rerun a paid/provider study, live Claude callbacks, all runtime regressions, load tests, or a complete browser interaction audit. Fresh checks and recorded results are identified separately. Project-owned raw snapshots and reproduction receipts are retained in private runtime state.

## P1 — Close before claiming a stable production edition

| ID | Finding and status | Required change and acceptance |
| --- | --- | --- |
| R01 | **Verified environment divergence:** the global editable CLI runs the older local development checkout, while main contains the v2 map. | Distinguish development and stable installations; expose resolved source root, version and commit through a diagnostic command. Verify the chosen command outside the checkout and after switching/reinstalling versions. Preserve unrelated work during integration. |
| R02 | **Verified stale integrity metadata:** main's source manifest identifies version 0.5.1, while package metadata is 0.6.0.dev0. Fifteen cached files with manifest entries have different SHA256 values. | Identify historical manifests as historical; generate a fresh manifest from the exact release candidate and independently validate every included file after extraction. Do not replace preserved historical evidence with a new claim. |
| R03 | **Measured v1 quality failure; v2 outcome unverified:** import convention, rather than missing helper bodies, caused the eight map failures. The map implementation is now merged and the v2 runner is in PR #5. | Finish independent review of the runner, freeze the 18-call protocol, pass the pre-call sufficiency gate and run it once without substituting failures. Report quality alongside reported token/cache/cost/latency measurements. Smaller prompt bytes alone are insufficient. |
| R04 | **Measured OpenCode interoperability failures:** 14/18 study responses failed the structured-artifact contract; four timed out. | Diagnose the captured wire format and host/model settings. Add contract fixtures for supported real responses without accepting malformed artifacts. Verify a small controlled actual-host pilot before another expensive study. |
| R05 | **Measured generated-application failure:** the actual provider application never passed combined acceptance. | Fix the demonstrated missing-description behavior and diagnose the planning timeout. Preserve the failed attempt; verify actual generated outputs, dependency integration, acceptance and credential-reviewed publication in one recorded application run. |
| R06 | **Unverified host coverage:** Claude callbacks remain unobserved; documentation also marks Codex project-file hook loading unproven. Some local pilots demonstrate launcher-delivered context. | Publish a versioned host/launch-mode matrix distinguishing installation, actual callback delivery, allowed edit, denied edit, refresh and acceptance. Test each claimed path; label unsupported paths explicitly. |
| R07 | **Documented isolation limit:** instructions and native callbacks cannot constrain arbitrary same-user host tools or tools the host never reports. | Make managed execution versus native coverage visible at entry and in every result. Keep protected work in the existing broker/container boundary. If broader isolation is needed, prove a separate OS/account/container boundary before claiming universal enforcement. |
| R08 | **Verified scope incident is corrected in the current tree, with history retained:** `sms-forwarder` is absent from main, but earlier commits still retain it. | Keep the current scope gate and protected-branch controls. Verify project ID, canonical root, Git parent and declared outputs at publication. Treat any historical-content removal as a separately authorized history operation; current-tree removal is not history deletion. |
| R09 | **Reproduced misleading health:** documentation entries make 36 roles appear healthy without any recorded tool run. | Separate documented, configured, exercised and acceptance-verified status. No execution history must display unverified/idle. A failing current run must remain visible; a documentation edit must not create a success verdict. |
| R10 | **Reproduced hidden challenges:** the counter recognizes only entries with an explicit `status`/`الحالة` line. | Define and validate an explicit memory record status schema. Migrate conservatively; show unknown status rather than silently treating a challenge as closed. Cover English and Arabic records. |
| R11 | **Documented reviewer limit:** default names are declarations; verified tokens prove possession, not independent human review, and same-user processes remain outside that authority boundary. | Show review mode in the result and make verified review the selected default where required. For independent review, use a separate principal boundary and verify the actual review workflow; never describe a credential alone as human independence. |

## P2 — Improve daily usefulness and efficiency

| ID | Finding and status | Required change and acceptance |
| --- | --- | --- |
| R12 | **Verified stale public evidence:** main's validation top-level date is 2026-10-01 and release field is 0.5.0; roadmap/design text includes older pending or design-only statements beside newer completion records. | Add one current readiness summary bound to a source SHA. Preserve historical records, but label them as history. Resolve contradictory current claims about map implementation, model steps, host pilots and release state. |
| R13 | **Verified local-only brand work:** current main has the old banner and dashboard media, while reviewed logo/mobile banner/READMEs and motion assets remain local. | Integrate the selected reviewed assets through the normal release process. Recheck final English/Arabic README rendering and links on the exact integrated source. |
| R14 | **Verified release lag:** latest inspected release tag is v0.5.0; package source is 0.6.0.dev0. A wheel exists as a supported build path, but its dashboard is intentionally unavailable. | Prepare a versioned release after its acceptance gates pass. Make CLI-only installation and checkout/sdist dashboard installation explicit; verify clean installs rather than relying on the developer's editable environment. |
| R15 | **Read-history scaling gap in source:** readRuns reads the complete JSONL file before slicing its last records. Each overview also reads role memory repeatedly. | Bound history reads, add rotation/archive policy and cache summaries using validated fingerprints. Benchmark growing histories and many installed roles; report memory and latency rather than assuming gains. |
| R16 | **Admission/scaling gap in source:** a run POST immediately launches a tool; the route does not provide a job queue or aggregate concurrent-run policy. | Add bounded request size/argument counts, an explicit admission limit and task/job IDs. Show queued/running/failed/cancelled states; verify overlapping requests without weakening project locks. |
| R17 | **Watcher scaling gap in source:** each SSE connection creates its own set of recursive watchers. | Share watchers per bound project and impose stream limits/backpressure. Verify connection churn and session revocation; existing authentication is not a concurrency budget. |
| R18 | **Source-confirmed argument limitation:** the UI splits arguments on whitespace, so a quoted path containing spaces becomes several arguments. | Prefer typed per-tool forms or a validated argument array editor. Show the exact argv before launch. Verify Arabic paths, spaces and special characters while retaining traversal refusals. |
| R19 | **Reproduced frontmatter parsing limitation:** folded/multiline YAML descriptions become `>-`/`|` rather than their text. | Use a bounded YAML parser or formally restrict and validate the supported frontmatter subset. Add actual folded/multiline role examples. |
| R20 | **Process-lifecycle verification gap:** dashboard timeout code kills its immediate child; descendant termination is not established by that operation. | Test a deliberately spawning registered-tool fixture. Where needed, own a process group and verify cancellation leaves no child/container behind, while preserving evidence and unrelated processes. |
| R21 | **Documented aggregate budget gap:** a per-checkout request ceiling is not a batch-wide or provider-account cost cap. | Add batch admission/reservation accounting with persisted reconciliation across crashes/resume. Track reported tokens/cost per project/task/host; retain unknown values as unknown. |
| R22 | **Context correctness needs expansion:** the v2 import correction is tested on three synthetic Python tasks. Closure growth can exceed budgets; JS/TS conventions need their own evidence. | Add representative Python and JS/TS retrieval contracts, explicit omissions and safe fallback when the selected context is insufficient. Verify quality before broad default rollout. |
| R23 | **Documented indexing boundaries:** source indexing supports Python/JS/TS with bounded files/bytes and a labelled approximate fallback; it is not a comprehensive multilingual graph. | Publish supported languages/resolution coverage. Add parser adapters only for selected real workloads, with pinned dependencies and import-resolution fixtures. Scope large projects explicitly. |
| R24 | **Learning quality and reuse remain narrow:** verified local lesson promotion exists; broad improvements across projects are not measured. | Keep project facts isolated, promote reusable lessons only with recorded acceptance, and test relevance/staleness on held-out tasks. Add outcome/source provenance to any reuse decision. |
| R25 | **Scheduling is a product gap:** explicit concurrent worktree coordination exists, including model generation through workflows; it is not a priority/fairness scheduler. | Add scheduling only after aggregate budgets and cancellation are sound. Verify priorities, dependencies, per-project admission, queued cancellation and restart recovery. |
| R26 | **Recorded recovery limitation:** reclaiming a controller/root lock does not itself stop a container that outlived the controller; grouped publication is recoverable rather than instant multi-file atomic visibility. | Provide a recovery diagnostic and explicit orphan reconciliation. Verify a killed-controller scenario and readers that obey the lock; do not claim arbitrary readers observe atomic groups. |
| R27 | **UX capability gap:** the dashboard is bound to one selected project; a unified multi-project workspace/switcher with coordinator task views is not established. | Add registered-project selection with visible canonical root/project/task IDs, pending-output/review screens and per-project histories. Freeze identity throughout a run and reject accidental cross-project switching. |
| R28 | **Role usefulness evidence is limited:** 42 documented roles are not 42 independently evaluated autonomous workers; ordinary repository checks do not execute every external-domain workflow. | Evaluate representative development, marketing and design tasks with concrete artifacts and independent criteria. Mark manual procedures versus runnable integrations. Improve existing roles through the established audit process. |
| R29 | **Rollout remains unresolved in recorded readiness:** four previously audited private project records need reconciliation. Their present state was not re-audited here. | Select an explicitly registered project and verify current evidence before any rollout. Pilot English and Arabic work separately; do not enroll or modify unrelated clients from a library review. |

## P3 — Maintainability and adoption

| ID | Finding and status | Required change and acceptance |
| --- | --- | --- |
| R30 | **Maintenance risk, not a reproduced defect:** several controller modules contain more than a thousand lines and combine policy, process, state and transport concerns. | Extract stable internal boundaries gradually with existing frozen acceptance unchanged. Avoid parallel replacement runtimes or a large rewrite before closing measured failures. |
| R31 | **Adoption gap:** the inspected repository has no standalone open issue describing the remaining backlog. | Convert selected report items into scoped issues with acceptance and owners when authorized. Add working examples for the supported installation, host and language combinations. |
| R32 | **Evidence and observability improvement:** failure reasons, duration, attempts and task state exist across multiple records, but a consolidated diagnostic/measurement view is needed. | Provide a project-scoped doctor/summary showing resolved roots, host versions, adapter coverage, image readiness, last verified acceptance, queue/budget and actual usage fields. Redact secrets and keep no-run/unknown values explicit. |

## Delivery order

1. Reconcile the exact source used by development, the global CLI and the release candidate. Correct current metadata without rewriting historical outcomes.
2. Repair dashboard evidence semantics and argument handling; these are small, reproduced defects with observable acceptance.
3. Close the v2 study runner review, run the frozen study, and resolve OpenCode/app-pilot failures with recorded attempts.
4. Prove claimed native-host entry/edit/refresh paths and make enforcement/review modes explicit.
5. Add bounded run admission, aggregate accounting, history/watch scaling and recovery diagnostics.
6. Build project/task UX and representative role/language pilots; then prepare a coherent versioned release.

Every fix should carry one canonical project identity, a bounded change, a reproduced failing case where appropriate, passing acceptance, and fresh evidence tied to its source revision. More roles or smaller prompts alone are not a success metric.
