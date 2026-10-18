# Repository review — 2026-10-15

The review starts from public main `5d9102f`, retains the existing defect-closure work
through `35d1055`, and adds release-verification improvements. Existing checkouts and
the installed runtime are preserved. The package version is `0.6.1`.

## Findings and changes

| Finding | Resolution | Verification |
| --- | --- | --- |
| Explicit browser/distribution acceptance could skip unavailable prerequisites and finish green | Fail missing SDK, browser/display and build backend; clean partial browser setup | Bad/clean regressions and actual browser/distribution acceptance |
| Hosted CI omitted real MCP and unpacked-extension protocols | Add official SDK round trips and headed Chromium with Xvfb | Local SDK/Docker calls, real DOM clicks and capture; hosted evidence belongs to the PR's exact commit |
| First dashboard launch could resolve beyond the reviewed lockfile | Use npm ci and stop startup on installation failure | Successful/failed first-install regression |
| Dashboard tests reparsed ambiguous JavaScript modules | Declare ES modules and Node 24+; synchronize the lockfile | Dashboard tests, TypeScript and production build |
| Arabic/release login instructions and status rules lagged behind implementation | Align setup with verified loopback access and actual role-run evidence | Existing authorization/metrics regressions and documentation link checks |
| Optional-extra commands assumed an unpublished PyPI package | Install MCP/syntax extras from the source checkout in an activated environment | Fresh local source/extra installation and wheel/sdist acceptance |
| Mutable CI action tags and no scheduled dependency review | Pin reviewed v6 action commits, schedule Dependabot proposals and bound CI duration | Official action refs and parsed YAML; no automatic merge |
| Python 3.9 required an event loop while constructing the native controller lock | Allocate the operation lock on first asynchronous use and refuse reuse on another loop | Python 3.9/3.14 regressions cover synchronous construction, contended serialization and foreign-loop refusal |

Inherited fixes cover delayed cross-tab responses, changed/inert/covered targets, viewport
reachability, open Shadow DOM/readable frames, directory pagination, memory counters,
typed run records, quoted tool arguments, compatible examples, message documentation and
daemon refresh. See [browser/dashboard acceptance](BROWSER_DASHBOARD_ACCEPTANCE.md).

The optional task MCP, candidate import, prompt capture and native fixture adapter retain
their existing scope and permission boundaries. This review exercises actual task MCP and
Docker acceptance; it does not repeat the human-approved macOS fixture session.

## Local verification

| Check | Result |
| --- | --- |
| Baseline repository / mandatory commit gate (`720dff2`) | 1,104 pass; 112 optional skips across 99 suite invocations |
| Native compatibility follow-up | Nine pass, one live-fixture skip on Python 3.9 and 3.14 |
| Dashboard | 56/56; TypeScript and production build pass |
| Browser extension and rendered fixtures | 41 pass; one optional screenshot-refresh skip |
| Task MCP | Nine pass including SDK/Docker; one separate browser-provider skip |
| Prompt capture/clarification | Eight pass including SDK question/answer calls |
| Distribution | 14/14; wheel/sdist installed outside the checkout |
| Docker workflows / publication policy | 34/34 and 43/43 |
| npm audit | Zero known advisories at review time |

Reproduce with the [release checklist](RELEASE.md). Raw logs remain in the selected checkout's
ignored `.crewloom/reviews/2026-10-15/` directory. Read full gate and hosted outcomes for the
exact reviewed commit; optional skips are not executed acceptance.

## Remaining work

- Review and merge the source proposal before treating it as public-main behavior.
- A stable version/tag and runtime rollout remain separate release operations.
- Broad role quality, authenticated model identity and representative cross-model cost/quality
  require the [agency acceptance contract](AGENCY_ACCEPTANCE.md).
- The manual Chrome panel, task MCP, separate browser provider and bounded native fixture
  are distinct integrations; fixture success does not establish unrestricted desktop control.

Linux headed setup follows the [official Playwright CI guide](https://playwright.dev/python/docs/ci).
Dependency proposals follow [GitHub's Dependabot configuration](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).
