# Crewloom Codex plugin

The native Codex plugin packages one entry skill that uses the installed Crewloom CLI. It exposes project roles, context, memory and verification guidance without duplicating the 42 public role trees. Python/Git and the runtime are separate dependencies; Docker is needed for isolated checks. The plugin does not grant desktop tools, configure model credentials or implement a model/browser action bridge.

From a current source checkout:

```bash
codex plugin marketplace add /absolute/path/to/crewloom
codex plugin add crewloom@crewloom-local
```

Supported local Codex clients expose installed plugins in their plugin controls; start a fresh chat or reload the app to refresh discovery. Enabling/disabling this plugin changes skill availability, not the permissions of another plugin or the manual browser extension. Use the existing [host guide](HOSTS.md) for execution boundaries.

The manifest uses the supported compatibility layout, with a project marketplace at `.agents/plugins/marketplace.json`. Paths are relative to the checkout root. See [official plugin packaging](https://developers.openai.com/plugins/build/plugins). Public directory publication has not been requested or performed.
