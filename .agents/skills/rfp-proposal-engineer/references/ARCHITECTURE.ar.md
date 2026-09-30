# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ المعمارية الهندسية لصياغة العروض الفنية والمناقصات (Proposal Architecture)
## المعايير الهندسية والتجارية لوثائق العروض الفنية — Crewloom

---

## 1. فلسفة العرض الفني الفائز
- **التمايز عن الشركات التقليدية (The Unfair Advantage):** لا نبيع ساعات عمل مبرمجين (Body Shopping) كما يفعل المنافسون التقليديون، بل نبيع أصلاً رقمياً هندسياً منضبطاً (Digital Asset) بمواصفات أداء وأمان قابلة للقياس.
- **التسعير المرتبط بالقيمة والالتزام:** كل عرض يربط المدفوعات ببوابات تسليم فعلية (Milestones) يراها العميل ويعتمدها أسبوعياً.

---

## 2. المكونات المعمارية القياسية في كل عرض
1. **صفحة الغلاف والهوية:** تصميم رسمي يلتزم بـ `design-tokens.json` وخطوط Cairo و Readex Pro.
2. **تحليل النطاق (Scope Breakdown):** جدول DoR و DoD ومخطط تدفق العمليات.
3. **مصفوفة الأمان والجودة (QA & Security Matrix):** تغطية اختبارات Vitest + Playwright + فحص OWASP.
4. **المسار الزمني (Timeline Gantt):** 6 أسابيع مقسمة لـ 3 سبرنتات إنتاجية + سبرنت استقرار ونشر.
5. **شروط الدفع الرسمية (40 / 30 / 30):** 40% مقدم، 30% بعد سبرنت المعاينة الحية، 30% عند النشر النهائي.
