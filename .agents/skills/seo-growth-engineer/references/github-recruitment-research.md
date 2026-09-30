# مذكرة بحث GitHub — توظيف seo-growth-engineer (فحص حي بتاريخ 2026-09-24 UTC)

## نطاق البحث
- الدور: تنفيذ SEO عضوي (عناقيد كلمات، موجز مقال، إيقاع نشر، تتبع ترتيب، ربط داخلي) — بلا مدفوع وبلا تدقيق تقني.
- الاستعلامات: "SEO content brief automation agent skill repo 2026" و"keyword clustering rank tracking Python open source" عبر بحث الويب الحي + جلب صفحات GitHub الأصلية.
- القيد: البوابة المطلوبة stdlib فقط بلا اعتماديات مدفوعة (SerpAPI/SE Ranking/DataForSEO مرفوضة كاعتماد إلزامي).

## جدول المقارنة

| المستودع والمصدر | ملاءمة المهمة | دليل الانتشار | الصيانة | جودة التنفيذ | الإبداع العملي | الترخيص والمتطلبات | القرار |
| --- | --- | --- | --- | --- | --- | --- | --- |
| iannuttall/seo — https://github.com/iannuttall/seo | متوسطة: تدقيق تقني + GSC/GA4 + MCP؛ لا موجز كاتب جاهز | 534 نجمة / 42 fork (وقت الجلب 2026-09-24)؛ تنزيلات npm غير متحقق | نشط: 644 commit، issue واحدة مفتوحة | عالية: CLI + MCP + تقارير JSON منفصلة الدليل عن الاستنتاج | عقد الصدق (فصل الدليل/المشتق، لا صفر مختلق) — يُقتبس كمبدأ | Apache-2.0؛ يتطلب Node 22 + Google OAuth + مزودون مدفوعون اختياراً | استبعاد كاعتماد؛ تكييف مبدأ فصل الدليل عن الاستنتاج فقط |
| seranking/seo-skills — https://github.com/seranking/seo-skills | عالية للمخرج: seo-content-brief + seo-keyword-cluster + أمثلة BRIEF حقيقية مؤرخة | 148 نجمة / 37 fork (وقت الجلب 2026-09-24) | نشط: 96 commit؛ أمثلة مايو 2026 | عالية: 26 مهارة + install.sh + هيكل outputs مؤرخ | هيكل الموجز الجاهز للكاتب + تسلسل فجوة→عنقود→موجز — يُقتبس كهيكل | MIT؛ يتطلب SE Ranking MCP مدفوع (OAuth + أرصدة API) | استبعاد كاعتماد؛ تكييف هيكل الموجز فقط |
| didierphmartin/skills SEO/seo-content-brief — https://github.com/didierphmartin/skills/blob/main/SEO/seo-content-brief/SKILL.md | عالية جداً للموجز: عنوان + ميتا + H2/H3 بأهداف كلمات + PAA + ربط داخلي + وضعي NEW/IMPROVE | 0 نجمة / 0 fork (وقت الجلب 2026-09-24) | غير متحقق (تاريخ آخر commit غير مفحوص) | متوسطة: سكريبت audit.py + قواعد كثافة + استبعاد نطاقات؛ استخراج HTML ثابت فقط | وضعا NEW/IMPROVE (احتفظ/قوِّ مقابل أضف) — يُقتبس كفكرة | الترخيص غير متحقق؛ يتطلب مفتاح SerpAPI مدفوع | استبعاد كاعتماد (ترخيص + مفتاح مدفوع)؛ تكييف شكل الموجز ووضعي NEW/IMPROVE |
| johnoconnor0/keyword-clustering — https://github.com/johnoconnor0/keyword-clustering | عالية للعناقيد: kmeans/agglomerative/hdbscan/graph + ربط صفحات + فجوات + تنافس داخلي | 5 نجوم / 0 fork (وقت الجلب 2026-09-24) | 13 commit؛ اختبارات pytest + CI | عالية: CLI + تقارير CSV/Markdown + لوحة Streamlit | كشف التنافس الداخلي (cannibalization) وربط الكلمات بالصفحات — يُقتبس كمفهوم | MIT؛ يتطلب embeddings ثقيلة (transformers/UMAP) | استبعاد كاعتماد (اعتماديات ثقيلة)؛ تكييف مفهوم العنقود→صفحة→فجوة يدوياً |

## القرار
- لا اعتماد مباشر لأي مستودع (كل مرشح يحتاج مفتاحاً مدفوعاً أو اعتماديات ثقيلة تخالف قيد stdlib).
- ما كُيّف: شكل الموجز (didierphmartin + seranking) + مفهوم عنقود→صفحة→فجوة (johnoconnor0) + عقد الصدق (iannuttall) — بلا نسخ كود.
- التجربة: لم تُشغَّل مرشحات خارجية (مخالفة قيد stdlib)؛ بدلها بُنيت بوابة `scripts/check_seo_content_packet.py` محلياً وفُحصت live (النتائج في `brain/COMPLETED.md`).
