# مذكرة بحث GitHub — `short-form-paid-booster` (فحص 2026-09-20 UTC)

## النطاق
دور: تضخيم مدفوع لريل جاهز على TikTok/Snap/Reels. الاستعلامات: "TikTok Ads API automation Python 2026".
رُوجعت المهارات القائمة وCODE_REGISTRY أولاً: `budget_pacer.py` يُعاد استخدامه (لا سكريبت موازٍ)، ولا مهارة تغطي TikTok paid.

## المقارنة

| المستودع والمصدر | ملاءمة المهمة | دليل الانتشار | الصيانة | جودة التنفيذ | الإبداع العملي | الترخيص والمتطلبات | القرار |
|---|---|---|---|---|---|---|---|
| `tiktok/tiktok-business-api-sdk` (الرسمية) | عالية — إطلاق campaigns/adgroups/ads + تقارير | رسمي من TikTok (مرجع المنصة نفسها) | نشط (إصدارات متتابعة) | SDK كامل Python/JS/Java + أمثلة إطلاق | غير متحقق (بنية تحتية لا فكرة) | يتطلب App ID/Secret/Access Token حقيقياً | **اعتماد للإطلاق** |
| `hyperfx-ai/marketing-skills` (tiktok-ads/SKILL.md) | عالية جداً — سكيل TikTok Ads end-to-end (validation + benchmarks + reporting) | غير متحقق (لا نجوم مسجلة) | غير متحقق | توثيق إجرائي مفصّل (objective/billing/placement/frequency + حد $50) | قاعدة "benchmarks قبل التسعير" + إطلاق paused أولاً — أُخذت للمهارة | يتطلب Hyper MCP مدفوعاً — **لا يُعتمد كاعتمادية**، يُقتبس المنهج فقط | **اقتباس المنهج** |
| `dhawalshah/tiktok-ads-mcp` | متوسطة — قراءة حملات + benchmarks + fatigue عبر MCP | غير متحقق | نشط 2026 (OAuth 2.1 + FastMCP) | أدوات قراءة غنية (benchmarks/fatigue/reach/pixels) | Creative fatigue + benchmarks — أُخذت كفكرة P2 | يتطلب TikTok OAuth + GCP للوضع البعيد | **مرجع للتقارير** |
| `Buer2333/tiktok-ads-mcp` | متوسطة — قراءة فقط (6 أدوات) | منخفض (0 نجوم، مساهمان) | دفع 2026-03 | FastMCP نظيف لكن read-only فقط | غير متحقق | MIT + TikTok credentials | مستبعد (أضعف من dhawalshah للتقارير) |
| `ndinevski/ads-manager` | منخفضة — SDK موحّد TikTok+Facebook + رفع S3 | منخفض | تحديث 2024 | تغطية واسعة لكن طبقة إضافية فوق الرسمي | التوحيد ثنائي المنصة — لا حاجة له (الفصل مقصود هنا) | اعتمادية وسيطة غير ضرورية | مستبعد |

## التجربة
`scripts/check_boost_gate.py` (منطق البوابة الخاص بالمهارة، مكتبة قياسية): 4 حالات فعلية —
`--platform tiktok --budget 50` → PASS exit 0؛
`--platform tiktok --budget 30` → FAIL exit 2 (تحت الحد)؛
`--platform x --budget 50` → رفض usage؛
brief يحوي `[TBD]` → FAIL exit 2. الاعتماد على TikTok API الحقيقي غير متحقق (يتطلب حساب إعلاني حقيقياً — يُختبر عند أول حملة عميل معتمدة).
