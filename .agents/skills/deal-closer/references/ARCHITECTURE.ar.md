# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مقفّل الصفقات (Deal Closer Architecture)

```
[b2b-sales-hunter: Hot/SQL + BANT] → [deal-closer: qualified→proposal→negotiation→won/lost]
  → [توقيع مسجّل] → [حزمة تسليم] → [delivery-director: ما بعد التوقيع]
```

المهارة تملك **الوسط فقط**: خط الأنابيب، المتابعات، الاعتراضات، بوابة الإغلاق، حزمة التسليم.
الإغلاق يبدأ من المؤهلين حصراً (بوابات BANT في `02_Marketing/B2B-Outreach/Lead_Qualification_Framework.md`)،
والتسعير استشهاد بنطاقات `05_Admin/Finance/Agency_Pricing_Rate_Card.md` فقط — بلا حسابات.
المخزن: `scripts/deals.jsonl` (JSONL سطر-لكل-صفقة، تواريخ حقيقية من ساعة النظام).
التعثر: proposal>7 أيام، negotiation>14 يوماً، أو أي صفقة بلا `next_action` — يكشفها `audit`.

## جدول الحدود (مسح الأقران — صفر تداخل زنادات)

| المهارة | دورها | حد deal-closer |
|---|---|---|
| b2b-sales-hunter (يا صيّاد صفقات) | صيد بارد + تأهيل BANT + تسليم Hot/SQL | تستلم منه فقط؛ لا تصطاد ولا تؤهل من الصفر |
| rfp-proposal-engineer (يا عروض) | كتابة محتوى العرض الفني/التجاري و SOW | تطلب العرض وتتابع مرحلته؛ لا تكتبه |
| delivery-director (يا مسلّم) | تسليم ما بعد التوقيع (سبرنتات/ديمو/دفعات) | تسلّمه حزمة التوقيع؛ لا تعمل بعده |
| executive-accountant (يا محاسب) | حسابات الربحية والفواتير وتقسيم الإيراد | تستشهد بنطاق Rate Card فقط؛ لا تحسب |
| admin-hr-legal-officer (يا إداري) | صياغة بنود العقد من قوالب MSA/Retainer | تشير للقالب فقط؛ لا تصيغ بنداً |
