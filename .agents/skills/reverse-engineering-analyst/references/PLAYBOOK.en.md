# Reverse Engineering Analyst

This English procedure defines the role’s project work. The analysis tool is supplied by the host; [REA](https://github.com/morluto/rea) is the recommended one and is a separate MIT-licensed project that Crewloom does not bundle.

## Inputs and scope

The exact target (file path with SHA-256, or URL), a written authorization statement naming the owner or the legal basis (own software, a security engagement, interoperability, a CTF), the question to answer and the output language. Read this project’s constitution and the role’s architecture, completed work, challenges and ideas before acting. Bind one canonical project root.

## Procedure

1. Hash the target and copy it into the bound project. Record the authorization statement before any analysis.
2. Choose the least powerful operation that answers the question: format and metadata inspection first, then disassembly or decompilation, then cross-references. Launching a process, attaching a debugger, injecting instrumentation or editing memory are separate operations that the task must authorize.
3. Run the analysis tool in a bounded environment. Opening an untrusted binary delegates parsing to local software with your permissions, so use a disposable VM or container for hostile samples.
4. Classify every claim as `observation` (read directly from the target), `derivation` (computed from observations), `inference` (a judgement that could be wrong) or `unknown`. Link each to the evidence identifiers that the tool returned. State limitations for inferences and unknowns.
5. Write the findings packet and run `crewloom run re-findings -- --findings findings.json`.

## Deliverable and acceptance

A findings packet that passes the checker, plus a short report in the requested language. Do not reproduce protected code or assets, do not bypass licensing, DRM or access controls, and do not claim a conclusion the evidence does not support.

## Dependencies and failure handling

Use the [public tool catalog](../../../../documentation/TOOLS.md) to establish which checks are bundled. Confirm that the analysis tool, runtime and any native engine (Ghidra, Hopper, IDA) are installed before starting. Record missing facts and blocked steps explicitly. Preserve earlier attempts; after two unchanged failures, report the cause and continue only independent authorized work.

## Handoff and memory closure

Carry project root, target hash, authorization statement, evidence identifiers, checks actually performed and unresolved questions. The next owner re-verifies the target hash. Update project-local completed work and backlog, record root causes and useful ideas, and keep binaries, extracted secrets and client history out of public library memory.
