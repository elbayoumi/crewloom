# Arabic and English support

Arabic and English are product acceptance requirements. An English-only happy path does not establish bilingual readiness. Use the explicitly selected language for agent-facing output; retain stable paths, flags, role IDs and machine-readable keys. Public foundation documentation defaults to English, with Arabic entry points and references where provided.

| Surface | Language behavior | Verification boundary |
| --- | --- | --- |
| Role context and workflow prompts | Explicit `en` or `ar`; the same project identity, source selection and correction rules | Paired context and understanding regressions; model/domain quality is evaluated separately |
| Dashboard | English/Arabic labels and RTL/LTR switching | Render both languages at supported viewports; external role names, command output and identifiers retain their source text |
| Browser companion | Saved English/Arabic choice; panel and owned in-page HUD adopt the language and direction; known companion errors are translated | Test switching both ways, reload persistence, indexing, frame warnings and failure messages in a real browser |
| Native application observations | Exact application/window/button labels from the application | Do not translate target labels before matching; app-specific evidence does not prove app localization |
| CLI and third-party tools | Context/output language options where documented; command names and many diagnostics remain English | Do not claim every CLI/help/error is localized; preserve unknown provider/browser diagnostics verbatim |

For browser acceptance, verify the Arabic HUD on an English page and the English HUD on an Arabic page. Changing the companion language must not change the site's language, text or direction. Existing historical log entries remain in the language used when emitted; new entries follow the current choice. Unknown external diagnostics remain intact so error details are not lost.

For every relevant change, exercise the same success, empty, refusal and error conditions in both languages. Inspect Arabic text and mixed technical values in the renderer; a translation-key count alone cannot prove usability. Keep generated content, human source statements and model conclusions distinct.
