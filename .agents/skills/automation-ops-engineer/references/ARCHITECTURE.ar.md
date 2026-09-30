# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مهندس عمليات الأتمتة

```
[يا أتمتة] → [Pre-Flight: برين المهارة + حقائق n8n الحية] → [صحة/فرز/ربط/إصدار]
  → [check_workflow_contract.py = PASS] → [Post-Flight: COMPLETED + TODO]
```

- الملكية: `02_Marketing` (التسويق والنمو)، تنفيذ IT-مساند. الأصول: `02_Marketing/Automation-n8n/workflows/` + `docker-compose.yml` (حاوية `rumuze_n8n`).
- الحارس: `scripts/check_workflow_contract.py` — بوابة كل إصدار/استيراد قبل أي commit.

## جدول الفصل عن الأقران (يمنع تداخل الزنادات)

| الطلب | المسؤول | لماذا ليست هذه المهارة |
|---|---|---|
| استراتيجية حملة/تنسيق فرق | `growth-director-orchestrator` (يا مدير) | تنسيق فقط، لا يشغّل n8n |
| تحكم بجهاز المالك/GUI | `machine-control-operator` (يا مشغّل) | جهاز محلي، لا ورك فلوز |
| إدارة حساب إعلاني يومية | `paid-media-buyer` | حسابات Meta/LinkedIn، لا n8n |
| ربط دومين/SSL/شبكات | `network-infra-engineer` | طبقة شبكة، لا ورك فلوز |
| صحة ورك فلو/فشل تنفيذ/ربط credential/إصدار | **هذه المهارة (يا أتمتة)** | عمليات n8n حصراً |
