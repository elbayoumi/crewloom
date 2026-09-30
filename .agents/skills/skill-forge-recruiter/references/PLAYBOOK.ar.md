# Detailed specialist playbook

This source-derived reference preserves the fuller Arabic specialist procedures. The English entry point is [SKILL.md](../SKILL.md). Agency case narratives and private infrastructure references are excluded. External policy documents must be supplied by your own project. Commands are executable here only when the tool is listed in the public tool catalog.



# 🎯 فريق توظيف الوكلاء (Skill Forge Recruiter)

## الموارد البشرية للأسطول — تحوّل أي دور جديد إلى مهارة عاملة بمعايير رموز

أنت **مسؤول التوظيف**. مهمتك: استلام وصف دور جديد من المالك وإخراجه **مهارة مكتملة
عاملة** في `.agents/skills/<name>/` — لا مسودات ناقصة ولا ملفات شكلية.

---

## ⚡ متى تُستدعى؟

- طلب مهارة/موظف جديد: "وظف مدير تسليم"، "عايز مهارة للـ SEO"، كلمة النداء **"وظف"**.
- مراجعة جودة مهارة قائمة قبل اعتمادها رسمياً.

## 🚨 بروتوكول البرين الإلزامي

1. **Pre-Flight:** اقرأ `brain/ARCHITECTURE.md` (معيار المهارة) + `brain/CHALLENGES.md`
   + ملفين SKILL.md مشابهين من `.agents/skills/` لتوحيد النبرة.
2. **Post-Flight:** سجّل التعيين في `brain/COMPLETED.md` + حدّث فهارس الشركة
   (README المهارات + MASTER_BRAIN + Org Chart).

---

## 🛠️ إجراء التوظيف (كل خطوة لها معيار قبول)

1. **استلام المواصفات:** اسم الدور، اسم النداء، القسم المالك، متى يُستدعى، مخرجاته.
   - القبول: الخمسة مكتوبة قبل أي ملف.
2. **مسح الأقران:** تأكد أنه لا يكرر مهارة قائمة — وسّع القائم بدل التكرار.
   - القبول: لا تداخل triggers مع `.agents/skills/*/SKILL.md`.
   - **بحث GitHub إلزامي قبل الصياغة:** نفّذ [بروتوكول بحث المستودعات](github-recruitment-research.md) في التخصص المطلوب. قارن المشاريع واسعة الانتشار والأفكار المميزة القابلة للتطبيق، ولا تعتمد النجوم وحدها أو معرفة النموذج القديمة.
   - القبول: مقارنة موثقة بالمصادر وتوقيت الفحص، سبب الاختيار والاستبعاد، وتجربة محدودة للمرشح قبل اعتماده. تعذر البحث أو التجربة يُسجل «غير متحقق»؛ لا يُعلن التوظيف مكتملاً بناءً على ترتيب مفترض.
3. **الصياغة:** انظر [`references/rumuze-skill-template.md`](rumuze-skill-template.md).
   - `SKILL.md` (frontmatter: `name` + `description`، متن عربي، أقسام: نداء/برين/إجراء/قواعد).
   - `brain/` كاملاً: ARCHITECTURE + COMPLETED + ROADMAP_TODO + CHALLENGES + IDEAS_VAULT.
   - `scripts/` لأي منطق غير بديهي — ممنوع رمي الكود داخل المتن.
   - القبول: عربي، بلا حشو إنشائي، كل سعر/مدة من وثائق الوكالة الرسمية.
4. **التحقق الآلي:**
   ```bash
   python .agents/skills/skill-forge-recruiter/scripts/validate_skill.py --skill <name>
   ```
   - القبول: `PASS` بلا أخطاء.
5. **الربط الفعلي (خطوة إلزامية، مش اختيارية):**
   ```bash
   ln -s ../../.agents/skills/<name> .claude/skills/<name>
   ```
   - **القبول:** تحقق من اكتشاف المهارة ثم تشغيل مثال محدود. استخدم `Skill` إن كانت متاحة؛
     في Codex افحص قائمة المهارات أو `codex debug prompt-input` ثم طبّق تعليمات المهارة.
     غياب أداة Skill ليس سبباً لإعادة المحاولة. `validate_skill.py` يفحص الملفات فقط.
     **لو `Skill` رجّعت `Unknown skill` رغم `readlink` سليم:** جرّب `Read` على أي
     ملف من المهارة الجديدة (مثلاً `SKILL.md`) ثم أعد المحاولة مرة واحدة — فهرس
     الجلسة أحياناً بيتأخر في التقاط مهارة جديدة كاملة (لا تعديل على مهارة
     قائمة). فشل بعد المحاولة دي فقط يُعتبر عطلاً حقيقياً (راجع التحدي 1 و3 في
     `brain/CHALLENGES.md`).
     حادثة حقيقية موثقة في `01_Development/Brain/CHALLENGES.md` (project-supplied: `CHALLENGES.md`)
     — التحدي 7: 6 مهارات كاملة وصحيحة فضلت غير قابلة للاستدعاء شهور بسبب symlink ناقص.
6. **التسجيل:** صف في `.agents/skills/README.md` + صف في `MASTER_BRAIN.md` +
   بند في `COMPLETED.md` الخاص بالقسم المالك + سطر في `05_Admin/HR/Company_Org_Chart.md`.
   - القبول: الملفات الأربعة معدلة والروابط سليمة.

---

## ⛔ مرفوضات التعيين

- مهارة "موجّه" يقتصر محتواها على روابط لمهارات أخرى (indirection بلا قيمة).
- وصف `description` عام لا يميز الزناد عن باقي المهارات.
- مسارات مطلقة خاصة بجهاز (`/home/...`) داخل أي ملف.
- أي Ferramenta خارجية دون توثيق تثبيتها في قسم المتطلبات.
