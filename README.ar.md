<div dir="rtl">

# Crewloom

<p align="center">
  <picture>
    <source media="(max-width: 600px)" srcset="assets/crewloom-banner-mobile.svg" />
    <img src="assets/crewloom-banner.svg" alt="Crewloom — أدوار وذاكرة للمشروع وأدلة تحقق." width="100%" />
  </picture>
</p>

[English](README.md) · [المهارات](documentation/SKILLS.md) · [الأدوات](documentation/TOOLS.md) · [أمثلة التشغيل](examples/README.md)

أدوات وإجراءات لتنظيم شغل وكلاء الذكاء الاصطناعي داخل الريبو: تختار الدور، توفر بيانات المشروع، تحفظ الذاكرة، وتفحص المخرجات.

- **42 دليل دور بالإنجليزية** و**150 مراجع تفصيلية** تتضمن إجراءات المصدر بالعربية.
- **18 أداة Python** للفحوص والسياق وقياس الموارد والتوقيت والإنفاق.
- خمس ملفات ذاكرة لكل دور، وفحوص قبل الـcommit وفي GitHub Actions.

## ابدأ عمليًا

تحتاج <span dir="ltr">Git</span> و<span dir="ltr">Python 3.9</span> أو أحدث. بعد تثبيت نسخة حديثة من [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html)، الذي يحتاج بنفسه <span dir="ltr">Python 3.10+</span>:

<div dir="ltr">

```bash
git clone https://github.com/elbayoumi/crewloom.git
cd crewloom
pipx install --backend pip --editable .
pipx ensurepath
```

</div>

افتح تيرمنال جديدًا لو أُضيف مسار إلى `PATH`. تحقق من إتاحة الأمر من أي فولدر:

<div dir="ltr">

```bash
crewloom --help
crewloom list
crewloom tools
```

</div>

ارجع إلى نسخة Crewloom لتشغيل الأمثلة المرفقة:

<div dir="ltr">

```bash
crewloom run workflow-contract -- examples/workflows/valid.json
crewloom run seo-packet -- --packet examples/seo/article-packet.json
```

</div>

المثالان يطبعان `PASS`. باقي الأمثلة وأوامرها في [دليل الأمثلة](examples/README.md).

بعد تثبيت الدور، افتح فولدر التطبيق المختار في أداة الوكيل. اذكر مساره الكامل وهوية المشروع في كل تسليم، واحفظ ملفات المشروع وذاكرته داخله. اطلب من الوكيل قراءة `AGENTS.md` للتطبيق والدور المثبّت داخل `.claude/skills` أو `.agents/skills`:

> اقرأ AGENTS.md ومهارة frontend-ux-auditor ومراجعها والبرين. استخدم العربية. راجع واجهة مشروعي، وشغّل الفحوص المناسبة، واعرض المشاكل بمواقع الملفات وأدلة التحقق. حدّث الذاكرة بعد الانتهاء.

<div dir="ltr">

```bash
python3 scripts/crewloom.py context frontend-ux-auditor --language ar --out /tmp/crewloom-ar.md
```

</div>

[مسارات العمل](documentation/WORKFLOWS.md) توضح ترتيب الأدوار والمدخلات والمخرجات. الوكيل والنموذج وأدوات الفيديو والمنصات الخارجية توفرها بيئة مشروعك. فحوص الكود الثابتة لا تثبت جودة العرض الفعلي، وفحص ملفات الأدلة لا يثبت صحة محتواها.

الأساس والتوثيق الرئيسي بالإنجليزية، وحزم السياق تدعم العربية والإنجليزية؛ هذا لا يعني ترجمة كل رسائل <span dir="ltr">CLI</span> أو قوالب المجالات. التثبيت الموضح هنا يتم من نسخة الريبو. الترخيص [Apache-2.0](LICENSE)، مع حفظ [نسبة المصدر](NOTICE) لوكالة رموز.

## استخدمه داخل مشروعك

وضع editable يتابع تعديلات نسخة الريبو؛ احتفظ بها في نفس المسار أو أعد التثبيت بعد نقلها. اختيار backend `pip` يعمل أيضًا عندما تكون نسخة `uv` الموجودة أقدم مما يتطلبه pipx.

خرائط <span dir="ltr">JavaScript</span> و<span dir="ltr">TypeScript</span> تستخدم استخراجًا تقريبيًا ما لم تُثبّت إضافة `syntax` الاختيارية ذات الإصدارات المثبّتة؛ راجع [إعداد الخريطة وحدودها](documentation/REPOSITORY_MAP.md).

لو تستخدم بيئة <span dir="ltr">Python</span> افتراضية مفعّلة بالفعل، شغّل `python3 -m pip install -e .`؛ يكون الأمر متاحًا أثناء تفعيل البيئة. ويمكن تشغيل الأدوات دون تثبيت عبر `python3 scripts/crewloom.py tools` من نسخة الريبو. ثبّت Crewloom من ريبو المكتبة، ثم اختر مشروع التطبيق بصورة مستقلة باستخدام `--target` أو `--project`.

### تثبيت الأدوار داخل مشروعك

استخدم فولدر التطبيق الموجود بالفعل مع `--target`؛ يرفض المثبّت وجهة غير موجودة.

<div dir="ltr">

```bash
crewloom install --host claude --target /path/to/project --skill frontend-ux-auditor
crewloom dashboard
```

`--host claude` ينسخ الأدوار إلى `.claude/skills`، و`--host agents` إلى `.agents/skills`. لا يكتب فوق دور موجود بدون `--force`. الداشبورد يحتاج Node 20+، وكل مسارات الـ API وبث الأحداث تتطلب مصادقة: `crewloom dashboard` يكتب رمزًا مولّدًا في ملف للمالك وحده ويطبع مساره فقط، أو اضبط `CREWLOOM_DASHBOARD_TOKEN` صراحةً. اترك الربط الافتراضي على `127.0.0.1` ما لم تُهيّئ رمزًا. انظر [الداشبورد](dashboard/README.md).

## مسار برمجي قابل للتشغيل

أضفنا تنفيذًا معزولًا عبر <span dir="ltr">Docker</span>، وحالة استئناف، وحزمة تسليم بين الأدوار، وفحص جاهزية البيئة. المثال البرمجي ينفذ ست مراحل ويفحص التعامل مع العربية والإنجليزية. راجع [دليل التنفيذ](documentation/EXECUTION.md) و[إعداد المضيف](documentation/HOSTS.md). مثال التنفيذ يستخدم كودًا مرجعيًا جاهزًا؛ لا يثبت جودة توليد الوكيل.

## توليد ملفات عبر نموذج فعلي

[مثال التشغيل الآلي](examples/model-workflow/README.md) يولّد كودًا عبر <span dir="ltr">Codex</span> أو <span dir="ltr">Claude</span>، ثم يشغّل اختبارات داخل <span dir="ltr">Docker</span>. الأدوات تحتاج تسجيل الدخول المحلي للمضيف. [التقييم المتكرر](examples/evaluation/unicode-slug/HOST_TRIALS.md) يفصل توليد الملفات عن تصحيحها، ويسجّل المحاولات الفاشلة بوضوح. نجاح التوليد وحده ليس قبولًا لجودة الكود.

## ما الذي تم التحقق منه؟

راجع [سجل التحقق](documentation/VALIDATION.json) و[الأدلة](documentation/EVIDENCE.md) للفصل بين الفحوص المحلية وتنفيذ <span dir="ltr">Docker</span> والتجارب الفعلية على المضيفين.

[دراسة السياق الأولى](documentation/CONTEXT_STUDY.md#observed-outcome-of-the-first-frozen-run-2026-10-05) سجلت 36 محاولة: صُححت 17 محاولة من <span dir="ltr">Codex</span>، ولم تُصحح أي محاولة من <span dir="ltr">OpenCode</span>. كل محاولة مُصححة بالسورس الكامل اجتازت 11/11 اختبارًا، وكل محاولة مُصححة بالخريطة المختارة اجتازت 0/11. **النتيجة لا تثبت توفيرًا مفيدًا للتوكنز.** الخريطة وسيلة تنقل، وتحسين استرجاع الكود يحتاج تقييم جودة مستقلًا.

اختبارات مثال التطبيق تستخدم أشجار <span dir="ltr">Git</span> وتنفيذ <span dir="ltr">Docker</span> فعليًا، وتستبدل توليد المزوّد بكود مرجعي. [تجربة المزوّد الفعلية](examples/evaluation/application-pilot-20261005.json) فشلت ومنعت النشر، فلا تثبت تسليم تطبيق ناجح مولّد بالنموذج.

## التعديل الذاتي

[وضع التعديل الذاتي](documentation/SELF_EDITING.md) هو مسار تحسين الأدوار والأدوات والتوثيق الموجودة: تشخيص المشكلة، تعديل التنفيذ، التحقق، ثم تسجيل النتيجة. الاسم الإنجليزي: **Self-Editing Mode**. شغّله بطلب واضح لوكيلك مع تحديد المشروع والمشكلة؛ لا يضيف صلاحيات إلى المضيف.

## سياق المشروع

[سياق المشروع](documentation/PROJECT_CONTEXT.md) اختياري لكل مشروع، ويضيف هوية مشروع صالحة، وربطًا محليًا لنسخة العمل، وسياقًا مجمدًا لكل مهمة مع مراجع أسطر مُتحقَّق من بصمتها، ودروسًا لا ترفعها إلا أدلة تنفيذ مسجّلة.

<div dir="ltr">

```bash
crewloom project enter  --project /path/to/project --project-id sample-project --task-id login-fix --role context-guardian --seed src/auth.py
crewloom project status --project /path/to/project --project-id sample-project
crewloom project finish --project /path/to/project --project-id sample-project --task-id login-fix --evidence '[{"workflow": "login-flow", "step": "acceptance", "scope": "unit tests"}]'
```

</div>

استبدل المسار وهوية المشروع والمهمة و`src/auth.py` بالقيم الفعلية للمشروع المختار.

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
