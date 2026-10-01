# Run real examples

These synthetic inputs contain no client data. They exercise local tools and do not connect to accounts or publish anything.

| Example | Command | Expected result |
| --- | --- | --- |
| n8n export contract | `python3 scripts/crewloom.py run workflow-contract -- examples/workflows/valid.json` | PASS, exit 0 |
| SEO article packet | `python3 scripts/crewloom.py run seo-packet -- --packet examples/seo/article-packet.json` | PASS, exit 0 |
| MCP configuration structure | `python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/config.json` | PASS, exit 0; no server is launched |
| Campaign spend pacing | `python3 scripts/crewloom.py run budget-pacing -- --daily-budget 100 --days-elapsed 3 --actual-spend 300` | Expected and actual spend agree |
| Short video script timing | `python3 scripts/crewloom.py run script-pacing -- --file examples/video/script.txt --duration 30` | Word count and words per second |
| Responsive grid source | `python3 scripts/crewloom.py run grid-safety -- --project-dir examples/ui --json` | No unbounded fixed-pixel grid floor |

SEO packet word count is declared metadata, not a generated article. MCP `your_server.py` is an external project input, not a bundled server. Static grid checks do not prove rendered layout. Video pacing is a measurement tool, not a speech engine.

- [Model-generated software feature](model-workflow/README.md): authenticated CLI generation, scoped artifacts and isolated acceptance.
- [Repeated host trials](evaluation/unicode-slug/HOST_TRIALS.md): frozen protocol, anonymized submissions and deterministic scoring.
