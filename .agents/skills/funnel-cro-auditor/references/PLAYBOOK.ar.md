# Detailed specialist playbook

This source-derived reference preserves the fuller Arabic specialist procedures. The English entry point is [SKILL.md](../SKILL.md). Agency case narratives and private infrastructure references are excluded. External policy documents must be supplied by your own project. Commands are executable here only when the tool is listed in the public tool catalog.



# 📈 مهارة تدقيق قمع المبيعات ومعدلات التحويل (Funnel & CRO Auditor)
## الذراع الهندسي لتحويل الزوار إلى عملاء ومبيعات فعلية لCrewloom

حتى لو قمت بأقوى حملة إعلانية، فإذا كانت صفحة الهبوط أو قمع البيع (Funnel) يحتوي على احتكاك تقني (Friction) أو بطء أو غموض في العرض، ستضيع كل ميزانيتك. مهمة هذا الفريق هي التدقيق الشامل لمسار العميل واقتراح التعديلات البرمجية والتصميمية لرفع نسبة التحويل (Conversion Rate Optimization).

---

## ⚡ متى يتم تنشيط واستخدام هذه المهارة؟
- عند طلب المستخدم: فحص صفحة هبوط، تحليل موقع، معرفة سبب عدم شراء الزوار، أو تدقيق قمع المبيعات.
- عند إعداد صفحات الهبوط لحملات الوكالة أو عملائها (Meta Ads, Google Ads).
- عند كتابة تقرير تدقيق مجاني للعملاء المحتملين كـ Lead Magnet.

---

## 🚨 بروتوكول البرين الإلزامي (Mandatory Brain Protocol)
1. **الخطوة صفر (Pre-Flight):** قبل فحص وتدقيق أي صفحة أو قمع، **يجب إلزامياً** فتح وقراءة:
   - [`brain/ARCHITECTURE.md`](../brain/ARCHITECTURE.md) لفهم معمارية الصفحة المثالية ومؤشرات Core Web Vitals.
   - [`brain/COMPLETED.md`](../brain/COMPLETED.md) ومراجعة [قائمة الـ 35 معياراً للـ CRO](cro_audit_checklist.md).
   - [`brain/ROADMAP_TODO.md`](../brain/ROADMAP_TODO.md) لمعرفة أولويات الفحص الجارية.
   - [`brain/CHALLENGES.md`](../brain/CHALLENGES.md) لتفادي اختناقات الهواتف ومشاكل النماذج الطويلة.
2. **الخطوة الختامية (Post-Flight):** بعد تقديم تقرير التدقيق، **يجب إلزامياً** توثيق الثغرات المكتشفة والحلول في `brain/CHALLENGES.md` وتحديث `brain/COMPLETED.md`.

---

## 🛠️ خطوات تنفيذ المهارة (Step-by-Step Procedure)

### 1. الفحص الفني للأداء والسرعة (Technical & Performance Audit)
- اختبار زمن الاستجابة والتحميل وسرعة الهواتف (Core Web Vitals):
  - مقياس LCP (Largest Contentful Paint) يجب أن يكون أقل من `2.5` ثانية.
  - فحص أوزان الصور واستخدام صيغ الجيل الجديد (WebP / AVIF).
  - فحص التجاوب الكامل مع جميع قياسات الهواتف والشاشات (Responsive Design).

### 2. التدقيق النفسي والمعماري للصفحة (Psychological & Architecture Audit)
استعن بقائمة الفحص الرسمية:
[قائمة فحص الـ 35 معياراً لصفحات الهبوط الرابحة (CRO Audit Checklist)](cro_audit_checklist.md)

تحقق من الأركان الـ 5:
1. **Above the Fold (الجزء العلوي):** هل يعرف الزائر في 5 ثوانٍ: من أنت؟ ماذا تقدم؟ وماذا يستفيد؟
2. **عرض القيمة الصريح (Clear Value Proposition):** حل محدد لمشكلة واضحة بدون تعقيد لغوي.
3. **تقليل الاحتكاك (Friction Reduction):** تقليص حقول النماذج إلى أقل حد ممكن (الاسم + الهاتف/الإيميل فقط).
4. **الإثبات المجتمعي (Social Proof & Trust):** شعارات شركاء، تقييمات عملاء حقيقية، شهادات موثقة.
5. **وضوح الدعوة للإجراء (Single Focused CTA):** زر واحد بلون واضح ومتكرر بدون تشتيت.

تحقق أيضاً من **الركن السادس: الفهرسة وإتاحة النطاق التقنية (SEO/AEO)** في نفس
القائمة — Canonical/OpenGraph مطابق للنطاق الحي، لا `meta-keywords` قديم، توحيد
الأرقام والرموز، تطابق روابط الهيدر/الفوتر، وإيميلات كروابط `mailto:` حية. أي
مخالفة هنا تُصحَّح على مستوى الكود بواسطة `frontend-ux-auditor` (بنوده 11-15) —
البنود بين اختصاص هذه المهارة و`frontend-ux-auditor` معاً.

### 3. إصدار تقرير التدقيق وخطة التحسين (The Actionable Audit Report)
أخرج التقرير للعميل في 3 أقسام:
- **المشاكل الحرجة التي تفقدك مبيعات فوراً (Red Flags).**
- **التحسينات السريعة في 48 ساعة (Quick Wins).**
- **الحل الجذري المقترح من Crewloom (The Rumuze Blueprint).**
