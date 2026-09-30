# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية اللمسة الإبداعية للواجهات (Creative Frontend Architecture)

```
[سجل مراجعة تقني مستقل من frontend-ux-auditor] → [تشخيص رائحة القالب]
  → [إيقاع مسافات + حركة موثّقة في design-tokens.json + كسر تناظر مدروس]
  → [إثبات قبل/بعد] → [تسليم لـ frontend-ux-auditor لفحص نهائي]
```

مساعد المراجعة: `frontend-ux-auditor/scripts/check_ui_quality.py` يرجع 2 (غير متحقق) ولا يمنح static PASS. يتبعه فحص العناصر والتفاعل في متصفح فعلي بثلاثة مقاسات؛ الإشارات النصية لا تمنع مواصلة التصميم ولا تثبت اعتماده.

## 1. توكنز الحركة المعتمدة (Motion Tokens Standard)

أي مشروع تُضاف له `motion` جديدة في `design-tokens.json` يلتزم بهذا السلّم
(نفس منطق سلّم `spacing` — قيم موحّدة، لا اختراع لكل مشروع):

| المفتاح | القيمة | الاستخدام |
|---|---|---|
| `motion.duration.fast` | `150ms` | hover/focus على عناصر تفاعلية صغيرة (زرار، رابط) |
| `motion.duration.base` | `300ms` | انتقالات عامة (فتح قائمة، تبديل تبويب) |
| `motion.duration.slow` | `500ms` | ظهور محتوى عند التمرير (scroll-reveal) |
| `motion.easing.standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | كل الانتقالات الافتراضية |
| `motion.easing.emphasized` | `cubic-bezier(0.2, 0, 0, 1)` | حركة تحتاج تأكيد بصري أقوى (CTA رئيسي) |

**قاعدة صارمة:** لو المشروع Crewloom نفسها، هذا السلّم يُكتب فعلياً داخل قسم `motion`
في `03_Design/Branding/design-tokens.json` (project-supplied: `design-tokens.json`)
(القسم الحالي فيه `motion.caption-animation` بس لفيديوهات الكابشن — لازم يتوسّع
بمفاتيح `duration`/`easing` أعلاه أول مرة تُستخدم فيها هذه المهارة على واجهة Crewloom).
لو المشروع لعميل، نفس السلّم يُكتب في ملف توكنز العميل، لا يُخترع من الصفر لكل صفحة.

## 2. حدود التقاطع مع `frontend-ux-auditor`

- `frontend-ux-auditor` = بوابة الصحة التقنية (RTL, Edge Runtime, force-dynamic, a11y,
  TypeScript) — **قبل وبعد** أي لمسة إبداعية.
- `creative-frontend-designer` = طبقة الإحساس البصري (إيقاع، تفاعل، كسر تناظر) فوق
  واجهة لها سجل مراجعة تقني مستقل.
- الترتيب الإلزامي: سجل مراجعة تقني أولاً → لمسة إبداعية → فحص نهائي يتأكد إن اللمسة ما
  كسرتش أي بند من العشرة (خصوصاً `prefers-reduced-motion` وتباين الألوان).

## 3. مرجع الفلسفة البصرية العامة للوكالة

راجع `03_Design/Brain/ARCHITECTURE.md` (project-supplied: `ARCHITECTURE.md`)
لهوية الوكالة الحالية فقط؛ هوية العميل واتجاهه المعتمد يحكمان واجهته. لا Dark Cyber Tech أو نيون أو كسر تناظر إلزامي لكل مشروع. مراجعة المراجع والمحتوى والهرمية تسبق الزخرفة؛ التناظر جائز إذا خدم الاستخدام.
