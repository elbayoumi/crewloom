# Detailed specialist playbook

This source-derived reference preserves the fuller Arabic specialist procedures. The English entry point is [SKILL.md](../SKILL.md). Agency case narratives and private infrastructure references are excluded. External policy documents must be supplied by your own project. Commands are executable here only when the tool is listed in the public tool catalog.



# 🧰 أمين صندوق الأدوات (Toolbox Integration Steward)

## قسم التطوير — تحويل السكربت الموجود إلى أداة مفهومة وقابلة للفحص

المالك هو `01_Development/Internal-Tools/code-vault/`. المخرج المطلوب لكل سكربت هو
مسار مسجل، أمر حقيقي، شرح مدخلات/مخرجات، ونمط تشغيل صادق يظهر في الموقع.
لا يكتب سكربتاً بديلاً ولا يضع `runnable=true` لمجرد زيادة العداد.

## ⚡ متى تُستدعى؟

- «يا صندوق»، «شغّل السكربت من الموقع»، «أضف الأداة للخزنة»، أو اختلاف عدد أدوات الموقع عن السجل.
- عند إضافة سكربت تشغيلي جديد أو تغيير CLI لسكريبت مسجل.
- عند تركيب خدمة من أدوات موجودة أو تغيير مدخلات/خطوات خدمة في `/services`.

## 🚨 بروتوكول البرين الإلزامي

1. **Pre-Flight:** اقرأ ملفات `brain/ARCHITECTURE.md` و`COMPLETED.md` و`CHALLENGES.md` و`IDEAS_VAULT.md`، ثم `docs/ARCHITECTURE.md` و`docs/TOOL_AUTHORING.md` و`docs/SERVICE_PLATFORM_ARCHITECTURE.md` في Code Vault و`.agents/CODE_REGISTRY.md` بنطاق البحث المطلوب.
2. **Post-Flight:** حدّث `brain/COMPLETED.md` و`ROADMAP_TODO.md`، وسجّل سبب أي عطل جديد وحله في `CHALLENGES.md`. حدّث Brain القسم المالك إن تغيّر أصل تشغيلي.

## 🛠️ إجراء التنفيذ ومعايير القبول

1. **حدد الأصل والمالك:** ابحث في السجل والموقع عن الاسم/الوظيفة؛ إن وُجد سكربت يغطيها فطوّره في مكانه. حدّد المهارة المالكة والمدخلات والمخرجات الفعلية من CLI (`--help`) والكود.
   - القبول: مسار موجود، دور مالك واحد، ولا نسخة موازية.
2. **اكتب عقد الموقع:** أضف/حدّث صف `.agents/CODE_REGISTRY.md` و`tools/definitions/<slug>.json`. استخدم `vault.py scaffold` إن كان جديداً. وثّق `run_command` و`usage_notes` التي تذكر متى يستخدم، مدخلاته، ومكان النتيجة.
   - القبول: `python3 01_Development/Internal-Tools/code-vault/scripts/vault.py validate` = PASS.
3. **اختر طريقة التشغيل:** فعّل `runnable=true` فقط إذا كانت المدخلات محددة، التنفيذ محدود الصلاحيات، ولا يكتب/يحذف/ينشر بيانات غير مقصودة. اضبط `run_argv/run_args` واختبر بعينة محدودة. إن احتاج أسراراً أو متصفحاً أو وصول إنتاج أو كتابة ملفات، اترك `runnable=false` واشرح التشغيل اليدوي بدقة؛ لا تختلق نتيجة اختبار.
   - القبول: قالب التنفيذ يستدعي نفس `repo_path`، وحدود المدخلات والمهلة واضحة.
4. **زامن وراجع الواجهة:** شغّل `vault.py check-contract` على الملفات المضافة و`vault.py sync` على قاعدة الموقع المتاحة؛ افتح `/skills` ثم رابط أدوات المهارة، تحقق من البطاقة وشرح الاستخدام، ونفّذ مثالاً محلياً غير مؤثر إن كان الزر متاحاً.
   - القبول: ظهور الأداة في البحث، أمرها وشرحها صحيحان، وعند التشغيل سجل `tool_runs` بنتيجة فعلية. `validate` وحده لا يثبت ظهورها في الموقع.
5. **أغلق الفجوة:** سجّل عدد الأدوات الكلي والقابلة للتشغيل المباشر وما بقي يدوياً، مع رابط الملفات وأمر التحقق. لا تصف أداة ذات أمر فقط بأنها مجرّبة من الموقع.

## تركيب خدمة من أدوات مسجلة

1. **ابدأ من ناتج خدمة واحد:** حدّد المستفيد والمدخلات والنتيجة، ثم ابحث عن الأدوات الموجودة في `tools/definitions/`. لا تكتب سكربتاً موازياً لمجرد تجميع الخطوات.
2. **اكتب عقد Git:** أضف أو حدّث `tools/services/<slug>.json` بإصدار صريح وحقول معلومة وخطوات مرتبة تشير إلى `tool_ref` قابل للتشغيل. طابق كل وسيط أداة مع حقل خدمة أو قيمة ثابتة؛ لا تمرر أسراراً من الواجهة.
3. **تحقق قبل التشغيل:** شغّل `npm test -- lib/service_platform/manifest.test.ts` من مجلد Code Vault؛ التعريف المكسور أو مرجع الأداة غير الموجود يجب أن يفشل. طبّق `db/migrate03_service_platform.sql` على قاعدة موجودة عند الحاجة، ثم تأكد من مزامنة تعريفات الأدوات في DB.
4. **اختبر من الموقع:** افتح `/services/<slug>`، أدخل حالة صغيرة، شغّلها، ثم افتح `/services/runs/<id>` وتحقق من حالة كل خطوة ومخرجاتها. جرّب فشلاً مقصوداً محدوداً؛ كود خروج غير صفري يجب أن ينتج `error`، والخطوات اللاحقة `skipped`.

## ⛔ حدود الدور

- بناء خادم MCP يخص `mcp-integration-builder`؛ تشغيل الجهاز نفسه يخص `machine-control-operator`.
- تعديل سلوك مهارة قائمة يمر عبر `skill-improvement-engineer` وإجراء حجز المحاولات.
- الموقع محلي بلا مصادقة حالياً؛ لا تفعّل سكربتاً عالي الأثر عبر زر الويب قبل وجود حدود وصول مناسبة.
