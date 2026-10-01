# Generate and verify a real feature

Unlike the deterministic software-workflow fixture, this example requests a fresh implementation from an authenticated Codex CLI. The following Docker step executes five separately supplied acceptance tests, including English, Arabic and invalid types.

```bash
docker pull python:3.14-slim
cp -R examples/model-workflow/project /tmp/crewloom-model-demo
crewloom install --host agents --target /tmp/crewloom-model-demo --skill fullstack-mvp-engineer
crewloom workflow run --project /tmp/crewloom-model-demo
crewloom workflow handoff --project /tmp/crewloom-model-demo
```

Use a fresh destination. You need a supported, locally authenticated CLI. Change `host` to `claude` in the copied plan to use Claude; do not edit an already executed plan and reuse its workflow ID. The role is project-local even when generated through a different host. The plan's language field accepts `en` or `ar`; identifiers and source module paths remain stable.

The model receives task text and role guidance. It does not receive tests unless they are declared inputs. The tests are public here and provide contract acceptance, not a hidden generalization benchmark. The runner writes source and verification artifacts in the selected project, preserves evidence and skips completed steps on resume. See [host boundaries](../../documentation/HOSTS.md).

[Recorded execution](evidence.json) captures real Codex generation followed by five passing Docker acceptance tests. [Generated source](generated-slug.txt) preserves the artifact matching its hash; it is evidence, not an implementation copied by the workflow. An initial nonfatal-diagnostic parsing bug was fixed before the recorded successful run.
