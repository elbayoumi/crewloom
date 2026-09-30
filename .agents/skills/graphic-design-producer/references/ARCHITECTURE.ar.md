# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مهارة إنتاج الجرافيك (Graphic Design Producer Architecture)

```
[طلب أصل بصري] → تحديد المصدر (هوية رموز / هوية عميل)
      │
      ├── أصل جديد (بنر/كاروسيل/موك أب) ──→ design-tokens.json أو أصول العميل الموثقة
      │        → بناء SVG → تحقق بصري في المتصفح → تسليم
      │
      └── استخراج لوجو من صورة ──→ crop تجريبي متدرج (imagemagick)
               → قياس لون الخلفية الفعلي → fuzz-transparent
               → تحذير تلقائي لو الدقة < 300px
               → مقارنة بصرية مع الأصل → تسليم مع الإفصاح عن أي قيد
```

## مصادر الحقيقة الوحيدة (Single Sources of Truth)
- ألوان/خطوط هوية رموز: `03_Design/Branding/design-tokens.json` (project-supplied: `design-tokens.json`).
- مقاسات المنصات وأنماط القوالب: `03_Design/Graphics/Design_System_Templates.md` (project-supplied: `Design_System_Templates.md`).
- ألوان/خطوط هوية عميل: فقط الأصول الفعلية الموجودة في مجلد العميل داخل `04_Clients/Active/` (project-supplied: `Active`) — لا افتراض، لا استنتاج من الذاكرة.

## أداة الاستخراج المعتمدة
`scripts/extract_logo_from_image.sh` (project-supplied: `extract_logo_from_image.sh`) — غلاف على ImageMagick (`convert -crop` + `-fuzz -transparent`). هذا هو المسار الوحيد المعتمد لاستخراج شعار من صورة؛ أي محاولة "رسم" بديلة مرفوضة بحكم [`CHALLENGES.md`](../brain/CHALLENGES.md) — التحدي 1.

## ملكية المعمارية
القسم المالك: `03_Design/Brain/` (project-supplied: `Brain`). هذه المهارة هي الذراع التنفيذي لفريق الجرافيك الموصوف في `03_Design/Graphics/01_UI-UX_Designer_Role.md` (project-supplied: `01_UI-UX_Designer_Role.md`).
