# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مونتاج وتجميع الفيديو (Video Assembly Architecture)

## Timeline Stacking, Safe Zones Geometry & Export Presets

تحدد هذه المعمارية المعايير الهندسية لعمليات مونتاج وتصدير الفيديو العمودي (9:16) في Crewloom:

### 1. طبقات التايم لاين المعتمدة (Timeline Layers)
- **Track 1 (الفيديو الأساسي):** لقطات الـ B-Roll والشاشات وحركات الجرافيك (تغيير كل 1.5 - 2.5 ثانية).
- **Track 2 (العناصر والتراكبات):** أشكال الهوية، الأسهم، الأيقونات الحركية، وموك أب الشاشات.
- **Track 3 (الكابشن الحركي):** خط Cairo Black بحجم 48-60pt مع تظليل ناعم وتأثير الكلمة النشطة.
- **Track 4 (التعليق الصوتي):** مسار صوت المعلق، معالج بـ -14 LUFS ومقدم في الصدارة.
- **Track 5 (المؤثرات الصوتية SFX):** أصوات الـ Whoosh، Pop، Click متزامنة بدقة الإطار (Frame-accurate).
- **Track 6 (الموسيقى التصويرية):** موسيقى خلفية إيقاعية هادئة بمستوى -26 LUFS مع Ducking آلي.

### 2. هندسة مناطق الأمان الصارمة (Safe Zones Matrix - 1080x1920)
- **مساحة العرض الآمنة المركزية:** من Y=220px إلى Y=1540px، ومن X=60px إلى X=960px.
- **المنطقة المحظورة العليا (0 - 220px):** مخصصة لتبويبات التطبيق وشريط البحث.
- **المنطقة المحظورة السفلى (1540 - 1920px):** مخصصة لنص المنشور، زر الصوت، وشريط التقدم.
- **المنطقة المحظورة الجانبية (960 - 1080px):** مخصصة لأزرار التفاعل (Like, Comment, Share).
