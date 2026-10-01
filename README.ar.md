# Crewloom

![Crewloom](assets/crewloom-banner.svg)

[English](README.md) · [المهارات](documentation/SKILLS.md) · [الأدوات](documentation/TOOLS.md) · [أمثلة التشغيل](examples/README.md)

أدوات وإجراءات لتنظيم شغل وكلاء الذكاء الاصطناعي داخل الريبو: تختار الدور، توفر بيانات المشروع، تحفظ الذاكرة، وتفحص المخرجات.

- **42 دليل دور بالإنجليزية** و**150 مراجع تفصيلية** تتضمن إجراءات المصدر بالعربية.
- **14 أداة Python** للفحوص والسياق وقياس الموارد والتوقيت والإنفاق.
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
pip install -e .
crewloom install --host claude --target /path/to/project --skill frontend-ux-auditor
crewloom dashboard
```

`--host claude` ينسخ الأدوار إلى `.claude/skills`، و`--host agents` إلى `.agents/skills`. لا يكتب فوق دور موجود بدون `--force`. الداشبورد يحتاج Node 20+ وبلا مصادقة، فاستخدمه على localhost فقط. انظر [الداشبورد](dashboard/README.md).

## مسار برمجي قابل للتشغيل

أضفنا تنفيذًا معزولًا عبر Docker، وحالة استئناف، وحزمة تسليم بين الأدوار، وفحص جاهزية البيئة. المثال البرمجي ينفذ ست مراحل ويفحص التعامل مع العربية والإنجليزية. راجع [دليل التنفيذ](documentation/EXECUTION.md) و[إعداد المضيف](documentation/HOSTS.md). مثال التنفيذ يستخدم كودًا مرجعيًا جاهزًا؛ لا يثبت جودة توليد الوكيل.

## توليد ملفات عبر نموذج فعلي

[مثال التشغيل الآلي](examples/model-workflow/README.md) يولّد كودًا عبر Codex أو Claude، ثم يشغّل اختبارات داخل Docker. الأدوات تحتاج تسجيل الدخول المحلي للمضيف. [التقييم المتكرر](examples/evaluation/unicode-slug/HOST_TRIALS.md) يفصل توليد الملفات عن تصحيحها، ويسجّل المحاولات الفاشلة بوضوح. نجاح التوليد وحده ليس قبولًا لجودة الكود.
