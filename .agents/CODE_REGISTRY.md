# Reusable code registry

Core Python tools use the standard library. Commands run from the checkout root. Host tools for specialist tasks are not bundled.

| Path | Purpose | Command |
| --- | --- | --- |
| [scripts/crewloom.py](../scripts/crewloom.py) | Role discovery, validation, and context CLI | `python3 scripts/crewloom.py list` |
| [scripts/check_repository.py](../scripts/check_repository.py) | Public checkout structure, syntax, links, and regressions | `python3 scripts/check_repository.py` |
| [.agents/skills/skill-forge-recruiter/scripts/validate_skill.py](../.agents/skills/skill-forge-recruiter/scripts/validate_skill.py) | Bilingual procedure structure | `python3 .agents/skills/skill-forge-recruiter/scripts/validate_skill.py --skill context-guardian` |
| [.agents/skills/skill-forge-recruiter/scripts/test_validate_skill.py](../.agents/skills/skill-forge-recruiter/scripts/test_validate_skill.py) | Bilingual validator regressions | `python3 -m unittest discover -s .agents/skills/skill-forge-recruiter/scripts -p test_validate_skill.py` |
| [.agents/skills/context-guardian/scripts/context_pack.py](../.agents/skills/context-guardian/scripts/context_pack.py) | Bounded English / Arabic context packs | `python3 scripts/crewloom.py context context-guardian --out /tmp/crewloom.md --language en` |
| [.agents/skills/context-guardian/scripts/test_context_pack.py](../.agents/skills/context-guardian/scripts/test_context_pack.py) | Context completeness and language regressions | `python3 -m unittest discover -s .agents/skills/context-guardian/scripts -p test_context_pack.py` |
| [.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py](../.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py) | Heuristic resource-pattern scan | `python3 .agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py --project-dir /path/to/project` |
| [scripts/test_public_core.py](../scripts/test_public_core.py) | CLI and public checker regressions | `python3 -m unittest discover -s scripts -p test_public_core.py` |
