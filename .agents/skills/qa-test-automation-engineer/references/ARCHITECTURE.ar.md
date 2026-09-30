# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية الاختبار

```
[Grade من tech-stack-architect] → [جدول متطلبات Testing في tech-decision-tree.md]
  Grade 1: Unit اختياري + Integration/E2E يدوي (لا Load ولا Security)
  Grade 2+: Unit إلزامي (Vitest/pytest) + E2E (Playwright/Detox)
  Grade 3+: + Load (k6) + Security (OWASP)
  Grade 4-5: + Contract/Mutation/Chaos testing
```

مصدر الحقيقة الوحيد للمتطلبات: [`tech-decision-tree.md`](../../tech-stack-architect/references/tech-decision-tree.md)
قسم "متطلبات الـ Testing" — لا جدول موازٍ يُنشأ هنا.

## بوابة القبول الآلية للحفظ الفعلي (Persistence Acceptance Gate)

رد HTTP 2xx على مسار بيحمل اسم يوحي بحفظ بيانات (lead/submit/contact/...) مش
دليل حفظ — راجع حادثة AqarSafe (`brain/CHALLENGES.md`). البوابة الآلية:
`scripts/check_persistence_acceptance.py` (project-supplied: `check_persistence_acceptance.py`)
الفحص النصي تشخيص استدلالي فقط: لا يصدر قبولاً للحفظ (خروج 1 أو 2).
وضع probe ينفذ كتابة وقراءة مستقلة على loopback ويثبت roundtrip فقط؛ لا يثبت
الاستمرار بعد إعادة التشغيل أو سلوك انقطاع التخزين. يلزم اختبارهما قبل قبول الإنتاج.
عقد التسليم: [قبول المشروع](project_acceptance.md).
## ملف أدلة التسليم
القسمان 6 و7 من references/project_acceptance.md يحددان صفحة أولى ومراجعة مستقلة وملفاً يحسبه scripts/check_delivery_packet.py. النتيجة جاهزية للمراجعة فقط، لا اعتماد المنتج. سجل الحوادث القائم يملك تاريخ محاولات الإصلاح.
## سلامة الأدلة — 2026-09-15
عقد الحزمة schema_version=2: evidence يحتوي path وsha256، والفاحص يتطلب --expected-revision مستقلاً عن الحزمة. لا ترقيات تلقائية ولا اعتماد المنتج من تطابق البصمات وحده.
