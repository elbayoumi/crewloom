# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مهندس الهوية (Brand Identity Engineer Architecture)

```
[طلب brand جديد] → [12 سؤال إلزامي] → [Market scan + Competitor analysis]
  → [7 مخرجات: Strategy + Palette + Typography + Logo Brief + Tokens + Voice + Applications]
  → [brand-identity-guide.md + design-tokens.json]
  → [تسليم لـ graphic-design-producer + frontend-ux-auditor]
```

## مصادر الحقيقة

| المدخل | المصدر |
|---|---|
| Color Psychology | علم نفس الألوان (Küller, Mehta & Zhu) + `03_Design/Brain/CHALLITECT.md` |
| Typography | خطوط Google Fonts المتاحة مجاناً + Cairo/IBM Plex للنصوص العربية |
| Logo Direction | Best practices (Walsh, Airey) — مش إعادة اختراع |
| Tokens | `03_Design/Branding/design-tokens.json` schema |
| Voice | `04_Clients/Active/Client_X/00_Context_Snapshot.md` لو موجود |

## القواعد الصارمة (Token-Only Law)

1. **ممنوع** أي قيمة Hex غير موثقة في `design-tokens.json`.
2. **ممنوع** كتابة brand من تخيُّل — لازم 8/12 سؤال مجاب.
4. **لازم** كل token يتوافق مع [W3C Design Tokens spec](https://design-tokens.github.io/community-group/format/).

## حدود الاختصاص

| المهارة | نطاقها | الفرق |
|---|---|---|
| `brand-identity-engineer` (أنا) | بناء منظومة Brand كاملة من الصفر | Strategy + Tokens + Brief |
| `graphic-design-producer` | تنفيذ أصول ثابتة | بنرات، كاروسيل، cards |
| `frontend-ux-auditor` | فحص tokens في كود الواجهات | RTL + Tokens compliance |
| `viral-hook-architect` | كتابة copy إعلاني | يستخدم Voice من عندي |
| `tech-stack-architect` | اختيار stack | يتأثر بطبيعة الـ brand site |
## بوابة الاسم — 2026-09-13
المشروع بلا اسم يمر عبر [عقد الاسم والدومين](naming-and-domain.md): سؤال، اقتراح، تحقق مسجّل، اختيار، ثم هوية؛ لا يعاد طلب اسم لم يختَر بعد ولا يفترض توفره من DNS.
