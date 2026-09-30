# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية التسليم (Delivery Architecture)

```
[سجل التحكم صالح] → [العقد الموقع + SOW] → [سبرنت 1: تصميم 1-2] → [سبرنت 2: تطوير 3-4]
  → [سبرنت 3: دفع + QA أسبوع 5] → [إطلاق أسبوع 6 + ضمان 30 يوماً]
        ↓ كل أسبوع                          ↓ اليوم 14
  [ديمو 20 دقيقة + اعتماد]            [NPS + شهادة + عرض Retainer]
```

- قائمة المشاريع ومالك كل تسليم من `.agents/project-control/registry.json` بعد
  `validate_project_control.py`. لا توجد قائمة عملاء ثابتة داخل المهارة أو المعمارية.
- `needs_reconciliation` بوابة قبل السبرنت: تجمع حالة موثقة وتسليم تالٍ واحداً، ولا تعني أن المشروع متوقف أو مكتمل.
- الأدوات: `Client_Workspace_Template.md` + `scripts/sprint_reminder.py` +
  `Client_Onboarding_Kit.md` + `Client_Retention_SLA.md` (استجابة P1 أقل من 30 دقيقة).
- المالية: أسعار `Agency_Pricing_Rate_Card.md` + توزيع `Financial_Model_Profit_Allocation.md`.
