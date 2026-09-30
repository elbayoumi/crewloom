# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية الحصاد (Harvest Architecture)

```
[طلب المالك: "هات داتا X"]
  → [web_search: اكتشاف 5-10 مصادر] → [تقييم سريع: أيها مباشر/محمي/JS]
  → [المباشر: web_extract أو harvest.py] → [dataset JSONL + provenance]
  → [JS/React/SPA: harvest_dynamic.py (Playwright/Chromium)] → [dataset JSONL + provenance]
  → [المحمي: سلم blocked-page-recovery] → [dataset + تاريخ السناب شوت]
  → [تقرير: ملف + جدول ملخص + عمر البيانات]
```

- ملكية المهارة: قسم التسويق (تغذي `competitor-spy` والخطافات بالداتا الحية).
- التخزين: `02_Marketing/` لبيانات السوق، `04_Clients/_Sandbox-Demo-Data/` لبيانات العملاء.
- الجودة: عينة تحقق يدوية على 3 سجلات قبل تسليم أي dataset (العنوان/الرقم يطابق الصفحة).

## فرع ثانٍ: بحث مشاريع Open Source للـ Base Projects (يخدم `tech-stack-architect`)
```
[tech-stack-architect يحتاج مرشح OSS جديد] → [find_oss_base_candidates.py: GitHub Search API حي]
  → [JSONL: نجوم + رخصة + آخر push + archived] → [رفض تلقائي: رخصة غير Permissive / مهجور / Archived]
  → [tech-stack-architect يختار ويستنسخ فعلياً] → [تسجيل في BASE_PROJECTS_REGISTRY.md مع رابط JSONL كدليل]
```
- لا اختيار "أقوى مشروع" من ذاكرة النموذج — GitHub API الحي دايماً هو المصدر، مش تدريب النموذج.

## تحقق التشغيل — 2026-09-13
استخدام .venv، عدم تجاهل فشل HTTP/selector/click، وخروج غير صفري للفشل؛ 4 حالات Chromium فعلية محلية محفوظة. الاختبارات الآلية مسجلة في المشغل المشترك للـpre-commit وCI.
