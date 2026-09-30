# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية المحاسب التنفيذي

```
[دفعة واردة] → calculate_profit_split.py --amount → [5 أركان: 40/15/15/10/20]
[عرض سعر جديد] → calculate_profit_split.py --price-check → [قبول ≥2.2x وهامش≥50% / رفض]
[استحقاق فاتورة] → Invoice_Template.md → [تحصيل] → مطابقة delivery-director
```

مصدر الحقيقة الوحيد للنسب والمعادلات:
`05_Admin/Finance/Financial_Model_Profit_Allocation.md` (project-supplied: `Financial_Model_Profit_Allocation.md`).
أي تعديل على النسب أو المضاعف يتم هناك أولاً، ثم ينعكس في
`scripts/calculate_profit_split.py` — لا يُعدَّل الرقم في السكريبت وحده.
