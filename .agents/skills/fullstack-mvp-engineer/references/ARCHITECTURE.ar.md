# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ المعمارية الهندسية لبناء الـ MVP (Engineering Architecture)

## Clean Architecture & Next.js 15 Standards for Full-Stack Products

تلتزم مهارة `fullstack-mvp-engineer` بالمخطط المعماري المعتمد والمثبت في Crewloom لعام 2026:

### 1. طبقات النظام (System Layers)
- **Presentation Layer:** Next.js 15 (App Router) + React 19 + Tailwind CSS + Design Tokens.
- **Validation & Gateway Layer:** Zod Schemas للتحقق الصارم من كل طلب قبل لمس المنطق الداخلي.
- **Business Logic Layer:** Server Actions & Route Handlers مدمجة داخل Next.js بدون خوادم Backend وسيطة غير مبررة.
- **Persistence Layer:** PostgreSQL السحابية، باستخدام `pg` خام أو Drizzle حسب درجة تعقيد المشروع (تجنب الحشو غير المبرر).

### 2. قواعد الكود النظيف (Clean Code Invariants)
1. **حظر `any` التام:** أي استخدام لـ `any` يرفضه الـ ESLint والـ pre-commit gate فوراً.
2. **عزل مكونات السيرفر والعميل:** إبقاء المكونات Server Components افتراضياً، وعدم إضافة `"use client"` إلا عند الحاجة الفعلية للتفاعل وحالات الـ state.
3. **معالجة الأخطاء الصريحة:** إرجاع ردود JSON واضحة بكود الحالة المناسب (200, 400, 404, 500) ورسائل واضحة، مع حظر ابتلاع الأخطاء صامتاً.
