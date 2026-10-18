# Browser and dashboard defect acceptance

This contract records observable acceptance for the browser companion and dashboard fixes.
It does not certify model quality, native desktop control or autonomous browser dispatch.

| Behavior | Acceptance |
| --- | --- |
| Tab navigation | A delayed index response cannot populate another tab's directory or dispatch its click |
| Document identity | Clicks require the original document token, frame ID and indexing generation |
| Changed targets | A changed label/action attribute, removed node or obsolete generation refuses the click |
| Interactivity | Inert/invisible ancestors and a covering modal prevent event dispatch |
| Dense pages | Scrolling then re-indexing exposes targets beyond the original 400-item prefix |
| DOM boundaries | Open Shadow DOM and readable frames are indexed; a real same-origin frame receives its own click |
| Directory access | Previous/Next pages expose every returned item, with distinct found/indexed/displayed counts |
| Role status | Installation/template history alone cannot mark an untested role healthy |
| Memory statistics | Both dated headings and compact dated records count; explicit open status is required for challenges |
| Tool arguments | Quoted paths, JSON argument arrays and empty strings survive parsing without shell evaluation |
| Catalog defaults | Runnable defaults remain project-relative; tools needing external identities/roots are CLI-only |
| Message documentation | The guide states required window/document/generation fields and actual settings behavior |
| Run history | One malformed JSON value cannot hide valid neighboring run records |
| Daemon status | A refreshed handshake changes the badge without reopening the panel or repeating unchanged logs |
| Distribution | A stale or unreviewed browser ZIP is rejected; a deterministic rebuild matches declared public source files |

## Verification commands

```bash
python3 scripts/package_browser.py --check
python3 -m unittest discover -s scripts -p test_packaging.py
python3 -m unittest discover -s scripts -p test_sidepanel.py
CREWLOOM_REAL_BROWSER=1 python3 -m unittest discover -s scripts -p test_sidepanel.py
CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_workflow.py
CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_execution_policy.py
python3 scripts/check_repository.py
```

From `dashboard`, run `npm test`, `npx tsc --noEmit` and `npm run build`. Rendered default
browser checks use controlled Chrome transport; the optional headed suite loads the actual
extension against disposable HTTP fixtures. Capture screenshots are optional and skipped
unless requested. No private project page or paid model generation is needed.

Reload the unpacked extension after updating its source, or rebuild the ZIP with
`python3 scripts/package_browser.py` before installing it. The browser companion remains
an explicit manual opt-in. Closed Shadow DOM and parent-frame visibility that cannot be
verified stay explicit limits. The dashboard shows its runtime source separately from the
project it monitors so a legacy checkout is not mistaken for the running implementation.
