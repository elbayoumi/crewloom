# Challenges

No local incidents have been recorded. Record the cause, attempted solution, result, and remaining blocker.

### 2026-10-14 — Current SDK and browser schemas
- Cause: official MCP SDK2 uses MCPServer and Python3.11+; typing.Dict return annotations wrap structured results, and Playwright MCP0.0.83 click uses target.
- Solution: pin the optional dependency, use dict[str, Any] tool return schemas, inspect live list-tools schemas and test legacy stdio interoperability. Default write tools absent; candidate import validates immutable launch scope and fresh packet revisions.
