# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية فحص الواجهات (Frontend/UX Audit Architecture)

```
[Sprint فيه واجهة جديدة/معدّلة] → [قائمة الفحص الـ 19] → [تشغيل فعلي: typecheck + build + متصفح + فحص النشر الحي]
  → [سجل نتائج وأدلة للنسخة] → [إصلاح مباشر لأي FAIL] → [مراجع منفصل يسجل technical في delivery-packet] → [توثيق أي قاعدة جديدة في CHALLENGES]
```

## قائمة الفحص الـ 19 (مصدرها الرسمي)

كل بند من الـ 19 في `SKILL.md` مصدره واحد من ثلاثة:
1. حادثة حقيقية اتكشفت في مشروع عميل فعلي (موثقة في `brain/CHALLENGES.md` هنا وفي
   `01_Development/Brain/CHALLENGES.md` (project-supplied: `CHALLENGES.md`)).
2. قاعدة دائمة معتمدة في `Engineering_Standards_Playbook.md` (project-supplied: `Engineering_Standards_Playbook.md`)
   القسم 2، أو `anti_ai_randomness_guardrails.md` (project-supplied: `anti_ai_randomness_guardrails.md`)
   (قانون Token-Only، التنوع التركيبي، مطابقة النشر الحي، وقاطع اللوب).
3. طلب مالك مباشر مُسجَّل بتاريخه (بند 18 — الكومنتات إنجليزي دايماً وi18n حقيقي —
   طلب 2026-09-12).

## حدود الاختصاص (لتفادي تداخل triggers)

| المهارة | نطاقها | الفرق |
|---|---|---|
| `frontend-ux-auditor` (هنا) | كود واجهة منتج فعلي (Next.js apps, dashboards) | هندسي — build/typecheck/RTL/DB-safety/Live Parity |
| `funnel-cro-auditor` | صفحات هبوط تسويقية وقمع مبيعات | تحويل/نفسي — Core Web Vitals ومعدل الشراء |
| `graphic-design-producer` | جرافيك ثابت (بانرات، كاروسيل، موك أب) | بصري ثابت — لا كود تفاعلي |

## أدوات الفحص المعتمدة

- `npm run typecheck` — يفحص الأنواع بس، **لا يكشف** تحذيرات Edge Runtime أو static/dynamic rendering.
- `npm run build` — المصدر الوحيد لتحذيرات Edge Runtime وجدول `○ Static`/`ƒ Dynamic` وحزم الـ JS المنتجة.
- `curl -sI <URL>` — فحص استجابة السيرفر وتاريخ الكاش ورأس `last-modified` لضمان تحديث الإنتاج.
- متصفح حي (Claude_Browser أو ما يعادله) — التحقق النهائي، لا بديل عنه.
- `scripts/check_palette_drift.py` (مضمّن في Crewloom؛ الأمر: `crewloom.py run palette-drift`) — بوابة آلية لبند 2؛
  يتطلب `--tokens` لملف هوية المشروع المعتمد، ويقارن به إعداد Tailwind والألوان النصية المدعومة.
  غياب الإعداد أو تعذر تحليله = غير متحقق (2)، والتوكن غير المستخدم تنبيه فقط.
  يرفض الألوان الافتراضية المتسربة والهيكس خارج الهوية؛ لا يغني عن مراجعة المتصفح والتباين. راجع حادثة AqarSafe (`brain/CHALLENGES.md` مرجع 10).
- `scripts/check_comment_language.py` (project-supplied: `check_comment_language.py`) — بوابة آلية
  لبند 18؛ يرصد أي كومنت كود غير إنجليزي (متسامح-مقتبسات، لا يلمس نصوص الواجهة)، ويرصد
  `lang`/`dir` ثابتين في الـ Layout الجذري رغم دعم المشروع لأكتر من لغة. راجع حادثة
  AqarSafe (`brain/CHALLENGES.md` مرجع 11).
- `scripts/check_ui_quality.py` (project-supplied: `check_ui_quality.py`) — مساعد إشارات نصية غير مؤهل للقبول؛ يرجع 2 دائماً. تحقق من الملاحظات على العناصر في المتصفح، ولا تعتبر غيابها إثباتاً للتجاوب أو الوصول أو جودة التصميم.
- `scripts/check_seo_baseline_presence.py` (project-supplied: `check_seo_baseline_presence.py`) — بوابة آلية
  لبند 19؛ يشغَّل **قبل** `check_seo_aeo_gates.py` دايماً — يتحقق من *وجود* meta description،
  الحد الأدنى من Open Graph، JSON-LD، و`robots.txt`/`sitemap.xml` حقيقيين (لا SPA fallback)،
  بعكس بنود 11-15 اللي بتفحص التناسق فقط بافتراض إن العناصر موجودة. راجع حادثة
