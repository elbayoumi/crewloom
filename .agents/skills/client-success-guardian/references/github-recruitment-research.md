# مذكرة بحث GitHub — توظيف `client-success-guardian` (يا حفيظ)

- تاريخ الفحص: 2026-09-24 | النطاق: أتمتة نجاح العملاء/خطر التسرّب/لعب الاحتفاظ + أدوات NPS.
- المصدران: بحث ويب حي (8 نتائج GitHub) + جلب حي لصفحة المرشح الأول للتثبت.

## جدول المقارنة

| المستودع والمصدر | ملاءمة المهمة | دليل الانتشار | الصيانة | جودة التنفيذ | الإبداع العملي | الترخيص والمتطلبات | القرار |
|---|---|---|---|---|---|---|---|
| `citizenjosh/customer-success-skills` — https://github.com/citizenjosh/customer-success-skills (جلب حي 2026-09-24) | عالية: مكتبة playbook لوكلاء CS (churn-stop + expansion blueprints) — نفس مخرج يا حفيظ | 13★ / 2 forks (مثبت حي) — الأعلى نجوماً ضمن المرشحين | 7 commits — مستودع حديث صغير، نشاطه غير متحقق بعد الجلب | README + `skills-library/` + `SKILLS_REGISTRY.json` — محتوى لعب لا كود منفَّذ قابل للاختبار هنا | فكرة "Value Receipts" (إثبات ROI بالأدلة) — يطابق قاعدة الإثبات في لعب التوسّع | REPlexus Community License v1.0 — استخدام شخصي/داخلي فقط، الاستشارات التجارية محظورة — **لا يصلح لإعادة الاستخدام الحرفي في عمل الوكالة** | **تكييف الفكرة فقط**: حزمة بالأدلة + فصل خطر/توسّع |
| `evanpaliotta/199os-customer-success-mcp` — https://github.com/evanpaliotta/199os-customer-success-mcp (بحث ويب فقط) | متوسطة: health scoring + تنبؤ تسرّب + 54 أداة RevOps — أوسع من حاجة الدور | 1★ / 0 forks (غير متحقق مستقلاً) | 50 commit (غير متحقق مستقلاً) | يدّعي FastMCP + Postgres/Redis + تكاملات Zendesk/Intercom — ثقيل، لم يُختبر | فصل صريح: مراقبة صحة / احتفاظ ومخاطر / نمو وتوسّع — بُنية مخرجات مفيدة | MIT حسب شارات README (نص الترخيص غير متحقق) + اعتماديات ثقيلة تتعارض مع قيد stdlib-only | **مرفوض لإعادة الاستخدام** (بنية تحتية زائدة)؛ الفكرة المتبناة: فصل مخرجات الصحة عن التوسّع |
| `customerscore/Customerscore---AI-renewal-flow` — https://github.com/customerscore/Customerscore---AI-renewal-flow (بحث ويب فقط) | عالية جزئياً: تقسيم Churn Risk / Expansion / Neutral + توجيه بشري مقابل أتمتة — يطابق خطوتي 3 و4 في المهارة | 5★ / 1 fork (غير متحقق مستقلاً) | 9 commits (غير متحقق مستقلاً) | قالب n8n بصري (.json) — لم يُختبر (لا بيئة n8n في الوكالة) | فكرة "المحايد = لا إجراء" — تطابق مبدأ "الفجوة تُبلَّغ لا تُخمَّن" | قالب n8n يتطلب بيئة n8n + مفاتيح CRM — غير متوفرة | **تكييف الفكرة فقط**: ثلاثية (خطر/توسّع/محايد-بلا-إجراء) |
| `amontaywelch/Customer_Churn_Risk_Prediction` — https://github.com/amontaywelch/Customer_Churn_Risk_Prediction (بحث ويب فقط) | منخفضة: نموذج XGBoost سلوكي يحتاج telemetry لا نملكه (فتح تطبيق/إيميلات/خصومات) | 0★ / 0 forks (غير متحقق مستقلاً) | 19 commit (غير متحقق مستقلاً) | يدّعي recall 95.6% (رقم المؤلف — غير متحقق) — لا بيانات سلوكية للعملاء لتشغيله | قائمة مرتبة حسب الاحتمال تُعرض على فريق الاحتفاظ أسبوعياً — مبدأ ترتيب مفيد | غير متحقق | **مرفوض** (لا بيانات تشغيل)؛ المبدأ المتبنى: قائمة خطر مرتبة بالأدلة دون درجات مخترعة |
| `iamstevenpearson/customer-success-portfolio` — https://github.com/iamstevenpearson/customer-success-portfolio (بحث ويب فقط) | منخفضة: SOPs ثابتة (onboarding/QBR/turnaround) — مرجع نصي لا أتمتة | 4★ / 1 fork (غير متحقق مستقلاً) | 50 commit (غير متحقق مستقلاً) | ملفات Markdown فقط — لا كود يُختبر | لعبة "إنقاذ عميل غاضب" — Choreography يدوية لا تناسب سكريبت stdlib | All rights reserved (© 2026) — لا إعادة استخدام | **مرجع فقط** |

## القرار
- لا إعادة استخدام كود مباشرة من أي مرشح (قيود: stdlib-only + ترخيص REPlexus غير التجاري + غياب بنية nn/telemetry).
- الأفكار المكيَّفة في `scripts/retention_packet.py`: حقول مثبتة بالأدلة فقط، فصل أعلام الخطر عن قائمة التوسّع، المحايد/المجهول = فجوة مُبلَّغة.
