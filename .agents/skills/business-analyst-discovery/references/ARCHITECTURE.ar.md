# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية تتبع فجوات الاكتشاف (Discovery Gap Architecture)

```
[مسح PRD + Context Snapshot لكل عميل نشط] → [استخراج كل [TBD] حرفياً]
  → [فلترة: سؤال للعميل / قرار داخلي] → [صياغة سؤال مباشر قابل للإرسال]
  → [قائمة واحدة لكل عميل] → [تتبع أسبوعي لأي سؤال بلا إجابة]
```

## الفرق عن `Discovery_Brief_Template.md`

| | `Discovery_Brief_Template.md` | `business-analyst-discovery` (هنا) |
|---|---|---|
| التوقيت | قبل التوقيع (بوابة إلزامية) | بعد التوقيع، طول عمر المشروع |
| الاستخدام | مرة واحدة لكل عميل جديد | متكرر كل ما تراكمت [TBD] جديدة |
| المخرج | تأهيل BANT + تحديد service_type | قائمة أسئلة جاهزة للإرسال + تتبع |

## مصادر الفحص لكل عميل

- `04_Clients/Active/Client_<slug>/00_Product_Requirements_Document.md` — قسم
- `04_Clients/Active/Client_<slug>/00_Context_Snapshot.md` — كل الحقول `[TBD]`
  في الأقسام 1-4.


- بوابة الدفع الإلكتروني (Stripe/Tap/Paymob/Moyasar؟) — سؤال للعميل، موثق في
  PRD القسم 8 كمخاطرة توقف Sprint 4.
- مصدر بيانات GPS الحية — سؤال للعميل، موثق في PRD القسم 8.
- استضافة سحابية (Supabase/Neon؟) — قرار داخلي للوكالة بعد معرفة حجم الاستخدام
  المتوقع من العميل، مش سؤال يتبعت له مباشرة.
