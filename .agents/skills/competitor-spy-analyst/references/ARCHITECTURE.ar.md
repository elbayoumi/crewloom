# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية استخبارات وتجسس المنافسين (Competitor Intelligence Architecture)
## Ad Reverse-Engineering Topology, Market Gap Extraction & Counter-Offer Engine

---

## 🕵️ 1. معمارية فحص وتفكيك إعلانات المنافسين

```
[مسح المكتبات الإعلانية: Meta Ad Library + TikTok Creative Center + Google Transparency]
                                 │
                                 ↓
[فلتر الأولوية: الإعلانات النشطة لأكثر من 30 يوماً = قرينة أداء قوية (مش إثبات ربحية)]
                                 │
                                 ↓
[تفكيك العناصر الأربعة: الخطاف + الوعد/العرض + الشريحة المستهدفة + الثغرة]
                                 │
                                 ↓
[تعدين شكاوى العملاء: تقييمات Google Maps و Trustpilot لعملاء المنافسين]
                                 │
                                 ↓
[صياغة العرض المضاد لCrewloom: The Rumuze Counter-Offer Blueprint]
```

---

## ⚠️ حدود الدليل — مؤشر "مدة بقاء الإعلان" ليس إثبات ربحية
مكتبات الإعلانات العامة (Meta Ad Library, TikTok Creative Center) **لا تكشف** ميزانية
الصرف الفعلية، ولا التحويلات المنسوبة (Attributed Conversions)، ولا هامش ربح المنافس —
دي بيانات داخلية للمعلن مش متاحة لأي طرف خارجي. استمرار الإعلان 25-30+ يوماً **قرينة
أولوية قوية** (يستحق وقت التفكيك) لأن أغلب المعلنين بيوقفوا الإعلان الخاسر بسرعة نسبياً —
لكنه **مش دليل قاطع على الربحية**، وممنوع وصفه كـ"مؤكد" أو"بالتأكيد" في أي تقرير
للعميل أو قرار تسعير. أي ادعاء ربحية فعلي لازم يتأسس على دليل صرف/تحويل/هامش حقيقي،
مش على مدة العرض وحدها (راجع `anti_ai_randomness_guardrails.md` (project-supplied: `anti_ai_randomness_guardrails.md`)).

## 🛡️ 2. مبادئ التفوق التنافسي لرموز:
1. لا ندخل في حرب أسعار خاسرة على الإطلاق (Never compete on bottom-barrel pricing).
2. نتفوق دائماً في: **السرعة المحددة (6 أسابيع)**، **جودة الكود (Clean Architecture)**، و **الأتمتة المدمجة**.
