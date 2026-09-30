# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية الفحص البصري (Visual QA Architecture)

```
[سكرين/رابط] → [capture_views.py: 3 لقطات + report.json] → [استخراج التوكنز من الكود]
  → [المحاور السبعة visual_checklist.md] → [تقرير شدة + file:line] → [بوابة: لا إنجاز بلا لقطة حالية]
```

## مصادر الحقيقة

| المدخل | المصدر |
|---|---|
| المحاور والشدة | `references/visual_checklist.md` (مكيف من jezweb/design-review) |
| هيكل المراحل والتقرير | `references/github-recruitment-research.md` (عن Bbasche/design-review) |
| عقد بوابة الإنجاز | نمط DEV screenshot-feedback-loop (report.json إلزامي) |
| قياس التراكب | `frontend-ux-auditor/scripts/` — مرجع لا نسخة |
| الألوان المسموحة | `design-tokens.json` الخاص بكل مشروع |

## حدود الاختصاص

| المهارة | نطاقها | الفرق |
|---|---|---|
| `visual-qa-reviewer` (أنا) | مدخل صورة/رابط → عيوب بصرية بـ file:line | حكم بصري + قياس |
| `frontend-ux-auditor` | صحة الكود الهندسي (بناء/RTL/DOM) | تنفيذ/تصحيح هندسي |
| `creative-frontend-designer` | تحسين بصري تنفيذي لواجهة شغالة | تنفيذ التحسين |
| `graphic-design-producer` | إنتاج أصول ثابتة جديدة | إنتاج لا فحص |
