# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية الحراسة (Guardian Architecture)

```
[بداية مهمة/تبديل دور] → [context_pack.py: حزمة <8k] → [تنفيذ بدفعات + دليل]
  → [فشل تحقق؟ محاولتا إصلاح بدليل جديد] → [نجح: تسليم | بقي الفشل: عائق محدد + عمل مستقل]
```

ملكية الحارس: ضبط السياق والتسليم بين الأدوار؛ تعليمات المالك والمضيف لها الأولوية.
الحزمة ≤8k حرف: ملفات كاملة أو إحالات صريحة للقراءة، دون قص شروط القبول والتوقف.
عداد محاولات السبب يستمر عبر تبديل الأدوار؛ نجاح شروط القبول ينهي الدورة.
