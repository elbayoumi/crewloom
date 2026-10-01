# Objective Unicode feature acceptance

This benchmark scores `src/slug.py` against nine held-out expected results: English, Arabic, compatibility normalization, case folding, repeated separators, empty strings, punctuation, Arabic digits, and invalid types. Expected answers remain outside the candidate Docker container; the probe receives only requests and returns actual values. The scorer receives no model or treatment label.

```bash
python3 scripts/crewloom.py evaluate --project /path/to/submission --repeats 3
```

A submission is copied into an isolated temporary project; its source is not modified. The report records source/image fingerprints, each case result, repeat count and execution duration. No tokens or model calls are measured.

`seeded-baseline/` is a deliberately incomplete ASCII implementation, not a generic agent's output. Comparing it with the supplied full implementation validates that the grader discriminates contract failures; it does not establish that Crewloom improves model quality. For a real with/without experiment, an independent coordinator should collect anonymized submissions from the same tasks/models, freeze the task/ground truth before runs, then apply this scorer without treatment labels. Broader features need their own held-out acceptance harness.

The acceptance cases are public in this repository. They validate a known contract, not unseen model generalization. Real treatment trials should add independently frozen private cases unavailable to the producing agents.
