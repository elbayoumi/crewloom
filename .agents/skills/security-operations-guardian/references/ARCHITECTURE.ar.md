# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

```
[Security Operations Guardian]
         │
         ├─► [Secret Scanning Layer]
         │      ├─ Pre-commit: gitleaks (fast, offline, regex + entropy)
         │      ├─ CI Diff: gitleaks (per-PR, blocks merge)
         │      ├─ CI Weekly: TruffleHog --only-confirmed (full history, live verification)
         │      └─ Server-side: GitHub Push Protection (non-bypassable gate)
         │
         ├─► [Vulnerability Management]
         │      ├─ OWASP Live: owasp-smoke.mjs ضد staging/production (Grade ≥ 3)
         │      ├─ Dependency: npm audit / pip-audit (كل CI run)
         │      ├─ Container: Trivy على الصور (release pipeline)
         │      └─ k6 Load: نقطة الانهيار الفعلية تحت حمل
         │
         ├─► [Credential Lifecycle]
         │      ├─ Registry: Security-Credentials/credentials-registry.json
         │      ├─ Rotation: 90-day automated + manual runbook
         │      ├─ Access: Access_Request_Form.md (Least Privilege + Revocation Plan)
         │      └─ Offboarding: إلغاء خلال ساعة (IT_Security_Compliance_SOP.md §4)
         │
         └─► [Incident Response]
                ├─ Detection: **مُؤكد** finding → alert فوري
                ├─ Containment: revoke + rotate ≤ 15 min
                ├─ Investigation: access logs ≤ 1 hour
                ├─ Remediation: history rewrite إن لزم ≤ 4 hours
                └─ Postmortem: توثيق في CHALLENGES.md ≤ 24 hours
```

## المبادئ الهندسية الإلزامية

1. **Defense in Depth:** لا طبقة وحدة تكفي — pre-commit + CI + server-side + scheduled history.
2. **Verification First:** finding غير مؤكد = noise، finding **مُؤكد** = incident فوري.
3. **Live Proof Only:** تقرير أمني بلا تشغيل فعلي (curl، gitleaks، OWASP، k6) مرفوض.
4. **Least Privilege + Rotation:** لا credential دائم بلا owner و expiry و revocation plan.
5. **Audit Trail Immutable:** كل تدوير، حادث، استثناء مسجل بتوقيت و owner في البرين.
