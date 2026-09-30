# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية تطوير المهارات في مكانها (In-Place Skill Improvement Architecture)

```
[تقرير IMPROVE من skill-performance-auditor أو طلب مالك مباشر]
  → [RCA: علّة واحدة محددة] → [حجز محاولة مسجلة ناجح] → [تعديل SKILL.md/scripts/brain في نفس المسار]
  → [validate_skill.py PASS] → [اكتشاف المهارة في المضيف + مثال تشغيل محدود]
  → [تسجيل نتيجة المحاولة + تحقق قبل الإغلاق] → [COMPLETED.md للمهارة المطوَّرة نفسها]
```

## قاعدة "التطور في المكان نفسه" (لا نسخ موازية)

هذه المهارة تطبيق فعلي مباشر لبند `reusable_code_registry_protocol.md` (project-supplied: `reusable_code_registry_protocol.md`)
بند 3 ("التطور في المكان نفسه") — لكن مخصص حصرياً لملفات `.agents/skills/*` (SKILL.md +
brain + scripts الخاصة بالمهارة)، وليس لأكواد الأقسام التشغيلية العامة.

## حد التصعيد (متى IMPROVE مش كافي)

لو نفس العلّة رجعت بعد محاولتين تطوير على نفس المهارة، الإجراء الإلزامي التالي هو
تصعيد لـ `skill-performance-auditor` لإعادة النظر في القرار (قرار جديد بناءً على الأدلة وحكم المالك)
— وليس محاولة تطوير ثالثة. موثق في `SKILL.md` قسم "مرفوضات التطوير".

## مدخل التصعيد الديناميكي — 2026-09-07
قائمة development_queue في .agents/SKILL_HEALTH.json مدخل تطوير موثق ومعتمد بطلب المالك.
الإصلاح في مكانه، ثم اختبار السبب الأصلي وتسجيل --resolve بدليل. مجرد انخفاض تنبيهات
التوثيق أو رفع رقم السكور لا يثبت إصلاحاً. الاستبدال يظل قرار المراقب مع حكم المالك.

## حفظ محاولات الإصلاح — 2026-09-09
استخدم إجراء الحجز والتنفيذ في [مهارة التقييم](../../skill-performance-auditor/SKILL.md). الرفض يمنع البدء؛ قوائم active/review/verification تحدد المتابعة دون إعادة تنفيذ تلقائية. الحجز اليدوي لا يمنع أدوات المضيف خارج الإجراء.
