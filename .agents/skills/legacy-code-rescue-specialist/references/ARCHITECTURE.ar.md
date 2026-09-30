# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية فحص وإنقاذ المشاريع المتعثرة (Rescue Architecture)
## المعايير الهندسية لتقييم وترحيل الأنظمة القديمة — Crewloom

---

## 1. مبادئ التشخيص والإنقاذ (Triage & Stabilization)
- **عدم التسرع في الحذف (Respect Working Features):** نقوم أولاً بتثبيت ما يعمل وحمايته باختبارات Smoke Tests قبل أي تعديل.
- **عزل طبقة البيانات (Data First Migration):** تأمين قاعدة بيانات العميل، والتأكد من سلامة الجداول والعلاقات قبل لمس الواجهات أو الـ API.

---

## 2. المسار المعياري لإنقاذ المشروع (The 3-Phase Rescue Pipeline)
1. **المرحلة 1: التشخيص وإيقاف النزيف (Discovery & Triage — 48 ساعة):**
   - فحص أمني عاجل لكشف أي تسريب للمفاتيح أو ثغرات خطرة.
   - قياس زمن الاستجابة ورصد الأخطاء في السجلات (Logs).
2. **المرحلة 2: الترقيع الحرج والاستقرار (Stabilization — 5 أيام):**
   - إصلاح مشاكل الذاكرة والـ Crashes المتكررة.
   - ضبط إعدادات السيرفرات والشبكة وحماية الـ Database.
3. **المرحلة 3: الترحيل المعماري الكامل (Modern Refactoring — 7-14 يوماً):**
   - نقل الواجهات إلى Next.js 15 وربطها بنقاط النهاية المعيارية.
   - تسليم العميل مشروعاً مطابقاً لمعايير رموز الهندسية مع تقرير إنجاز تفصيلي.
