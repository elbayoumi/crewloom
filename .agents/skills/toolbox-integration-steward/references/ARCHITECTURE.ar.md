# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية أمين صندوق الأدوات

`CODE_REGISTRY.md` + `tools/definitions/*.json` في Git هما عقد المصدر؛ قاعدة PostgreSQL نسخة تشغيلية عبر `import_registry_direct.py` و`vault.py sync`. موقع Code Vault يقرأ القاعدة ويعرض `/skills` و`/` وأوامر التشغيل وسجل `tool_runs`.

التدفق: بحث عن أصل قائم → فحص CLI والمالك → صف سجل + تعريف JSON → `vault.py validate` و`check-contract` → مزامنة DB → تحقق واجهة حي → تحديث Brain. `pre-commit` وCI يمنعان إضافة سكربت تشغيلي بلا عقد موقع.

حدود التشغيل: `runnable=true` للأدوات ذات مدخلات قابلة للتحقق وأثر محلي محدود؛ الباقي `runnable=false` مع `usage_notes` وخطوات يدوية. لا تُعد نسخة DB أو ظهور البطاقة دليلاً على نجاح التنفيذ.

طبقة الخدمات: `tools/services/*.json` تجمع الأدوات المراجعة في مسارات ذات إصدار ومدخلات صريحة. `lib/service_platform/` يتحقق من العقد وينفذ عبر `executeTool` فقط، ويحفظ `service_runs` و`service_run_steps`؛ `/services` و`/services/runs/<id>` تعرض المسار والنتيجة. اختبار التعريفات في بوابة commit وCI يرفض مرجع أداة غير موجود. التفاصيل وحدود التنفيذ المتزامن في `code-vault/docs/SERVICE_PLATFORM_ARCHITECTURE.md`.
