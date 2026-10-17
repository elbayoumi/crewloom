# Crewloom

![Crewloom](assets/crewloom-banner.svg)

[English](README.md) · [المهارات](documentation/SKILLS.md) · [الأدوات](documentation/TOOLS.md) · [أمثلة التشغيل](examples/README.md)

أدوات وإجراءات لتنظيم شغل وكلاء الذكاء الاصطناعي داخل الريبو: تختار الدور، توفر بيانات المشروع، تحفظ الذاكرة، وتفحص المخرجات.

- **43 دليل دور بالإنجليزية** و**153 مراجع تفصيلية** تتضمن إجراءات المصدر بالعربية.
- **19 أداة Python** للفحوص والسياق وقياس الموارد والتوقيت والإنفاق.
- خمس ملفات ذاكرة لكل دور، وفحوص قبل الـcommit وفي GitHub Actions.

## ابدأ عمليًا

تحتاج Git وPython 3.9 أو أحدث.

```bash
git clone https://github.com/elbayoumi/crewloom.git
cd crewloom
python3 scripts/crewloom.py tools
python3 scripts/crewloom.py run workflow-contract -- examples/workflows/valid.json
python3 scripts/crewloom.py run seo-packet -- --packet examples/seo/article-packet.json
```

المثالان يطبعان `PASS`. باقي الأمثلة وأوامرها في [دليل الأمثلة](examples/README.md).

افتح المشروع في أداة الوكيل واطلب منه:

> اقرأ AGENTS.md ومهارة frontend-ux-auditor ومراجعها والبرين. استخدم العربية. راجع واجهة مشروعي، وشغّل الفحوص المناسبة، واعرض المشاكل بمواقع الملفات وأدلة التحقق. حدّث الذاكرة بعد الانتهاء.

```bash
python3 scripts/crewloom.py context frontend-ux-auditor --language ar --out /tmp/crewloom-ar.md
```

[مسارات العمل](documentation/WORKFLOWS.md) توضح ترتيب الأدوار والمدخلات والمخرجات. الوكيل والنموذج وأدوات الفيديو والمنصات الخارجية توفرها بيئة مشروعك. فحوص الكود الثابتة لا تثبت جودة العرض الفعلي، وفحص ملفات الأدلة لا يثبت صحة محتواها.

الأساس والتوثيق الرئيسي بالإنجليزية. لا توجد حزمة منشورة على npm أو PyPI أو خدمة استضافة للوكلاء. الترخيص [Apache-2.0](LICENSE)، مع حفظ [نسبة المصدر](NOTICE) لوكالة رموز.

## استخدمه داخل مشروعك

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
crewloom install --host claude --target /path/to/project --skill frontend-ux-auditor
crewloom dashboard
```

أوامر تفعيل البيئة أعلاه لـmacOS وLinux. `--host claude` ينسخ الأدوار إلى `.claude/skills`، و`--host agents` إلى `.agents/skills`. لا يكتب فوق دور موجود بدون `--force`. الداشبورد يحتاج Node 24+؛ يفتح `crewloom dashboard` محليًا على `127.0.0.1` دون كلمة مرور أو توليد رمز. تظل فحوص العنوان المحلي ومصدر الطلب مفعّلة. الاستضافة على واجهة غير محلية تتطلب ضبط `CREWLOOM_DASHBOARD_TOKEN` صراحةً. انظر [الداشبورد](dashboard/README.md).

الجسر الاختياري [Project Task MCP](documentation/MCP_BRIDGE.md) يربط الأدوات بمشروع ومهمة محددين؛ يحتاج Python 3.11+ وتثبيت `python -m pip install '.[mcp]'`. القراءة هي الوضع الافتراضي، واستيراد الملفات والتحقق يحتاجان تفعيلًا صريحًا. [إضافة المتصفح](documentation/CHROME_EXTENSION_SIDE_PANEL.md) أدوات يدوية، و[قبول سطح المكتب](documentation/NATIVE_DESKTOP.md) محدود بتطبيق الاختبار المصرّح به.

إصدار المصدر الحالي `0.6.1`؛ راجع وسوم الإصدارات في المستودع لمعرفة ما نُشر فعلاً. [قائمة التحقق للإصدار](documentation/RELEASE.md) تفصل اختبارات الكود عن أدلة جودة الأدوار وعن النشر الفعلي.

## مسار برمجي قابل للتشغيل

أضفنا تنفيذًا معزولًا عبر Docker، وحالة استئناف، وحزمة تسليم بين الأدوار، وفحص جاهزية البيئة. المثال البرمجي ينفذ ست مراحل ويفحص التعامل مع العربية والإنجليزية. راجع [دليل التنفيذ](documentation/EXECUTION.md) و[إعداد المضيف](documentation/HOSTS.md). مثال التنفيذ يستخدم كودًا مرجعيًا جاهزًا؛ لا يثبت جودة توليد الوكيل.

## توليد ملفات عبر نموذج فعلي

[مثال التشغيل الآلي](examples/model-workflow/README.md) يولّد كودًا عبر Codex أو Claude، ثم يشغّل اختبارات داخل Docker. الأدوات تحتاج تسجيل الدخول المحلي للمضيف. [التقييم المتكرر](examples/evaluation/unicode-slug/HOST_TRIALS.md) يفصل توليد الملفات عن تصحيحها، ويسجّل المحاولات الفاشلة بوضوح. نجاح التوليد وحده ليس قبولًا لجودة الكود.

## التعديل الذاتي

[وضع التعديل الذاتي](documentation/SELF_EDITING.md) هو مسار تحسين الأدوار والأدوات والتوثيق الموجودة: تشخيص المشكلة، تعديل التنفيذ، التحقق، ثم تسجيل النتيجة. الاسم الإنجليزي: **Self-Editing Mode**. شغّله بطلب واضح لوكيلك مع تحديد المشروع والمشكلة؛ لا يضيف صلاحيات إلى المضيف.

## سياق المشروع

[سياق المشروع](documentation/PROJECT_CONTEXT.md) اختياري لكل مشروع، ويضيف هوية مشروع صالحة، وربطًا محليًا لنسخة العمل، وسياقًا مجمدًا لكل مهمة مع مراجع أسطر مُتحقَّق من بصمتها، ودروسًا لا ترفعها إلا أدلة تنفيذ مسجّلة.

```bash
crewloom project enter  --project /path/to/project --project-id sample-project --task-id login-fix --role context-guardian --seed src/auth.py
crewloom project status --project /path/to/project --project-id sample-project
crewloom project finish --project /path/to/project --project-id sample-project --task-id login-fix --evidence '[{"workflow": "login-flow", "step": "acceptance", "scope": "unit tests"}]'
```

الدخول ينشئ الناقص ويحدّث الموجود دون إعادة كتابة دستور مشروعك أو ذاكرة أدوارك. `status` يوضّح هل دورة الحياة يديرها مشغّل Crewloom أم أنها مُساعَدة بتعليمات أم يدوية؛ فتح المجلد لا يستدعي شيئًا وحده. `finish` لا يعلن الاكتمال إلا من أدلة تنفيذ مسجّلة، أما `--verification` فيسجّل إقرارًا يدويًا ويُبقي المهمة بانتظار التحقق. راجع [القياس التجريبي](documentation/PROJECT_CONTEXT.md#measurements) للسلوك المقيس فعليًا.

## تنفيذ المهام المستقلة على نحو متزامن

المهام المستقلة في مشروع واحد تُنفَّذ كدفعة واحدة: لكل مهمة شجرة عمل Git خاصة داخل `.crewloom`، وتعمل داخلها نفس منفّذ Docker المعزول، وتقرأ المهمة التابعة مخرجات أسلافها الملتزَمة فعلًا.

```bash
crewloom coordinator validate --project /path/to/project --project-id sample-project --manifest coordinator.json
crewloom coordinator run      --project /path/to/project --project-id sample-project --manifest coordinator.json
crewloom coordinator prepare  --project /path/to/project --project-id sample-project --manifest coordinator.json
```

لا تتغيّر الشجرة المفحوصة إلا بعد قرار مراجعة صريح ينقلها بخطوة «تقدّم سريع» واحدة مسجّلة. راجع [دليل المنسّق](documentation/COORDINATOR.ar.md) و[مرجعه الإنجليزي](documentation/COORDINATOR.md).

إعداد دورة التشغيل في الأدوات المدعومة: [دليل التشغيل التلقائي](documentation/HOST_LIFECYCLE.md). فحص ملفات تجهيز العملاء دون تعديلها: [دليل الجاهزية](documentation/READINESS.md).

[مثال تطوير تطبيق كامل](documentation/DEVELOPMENT_EXAMPLE.md): مهام فواتير وتخطيط متوازية، تقرير عربي أو إنجليزي، دمج واختبارات Docker، ثم نشر بمراجعة موثقة. اختبارات المكتبة تستبدل توليد المزوّد فقط بكود مرجعي؛ لا تمثل قياسًا لجودة النموذج. [دراسة السياق](documentation/CONTEXT_STUDY.md) تقيس التوكنز والكاش والوقت والصحة بصورة منفصلة، وتترك القياسات غير المتاحة مجهولة.

راجع [دعم العربي والإنجليزي ومعايير قبولهما](documentation/LANGUAGES.md) لمعرفة سلوك الواجهة وحدود ترجمة المخرجات والأدوات.
