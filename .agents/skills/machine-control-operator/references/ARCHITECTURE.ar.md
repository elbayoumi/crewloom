# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية التحكم في الجهاز (Machine Control Architecture)

```
[المستخدم: أمر واحد]
        ↓
[machine-control-operator: التوجيه والحوكمة]
   ├─→ [المستوى 1: ملفات + Shell] terminal/read/write/patch (الأرخص — يُفضّل دائماً)
   ├─→ [المستوى 2: GUI أصلي] computer_use عبر cua-driver (خلفية أولاً، capture→act→verify)
   └─→ [المستوى 3: ويب] browser_* للمحتوى (computer_use للـ chrome فقط)
        ↓
[سجل التدقيق brain/ops_audit_log.jsonl] + [مزامنة البرين]
```

## مبادئ ملزمة

1. **الأرخص أولاً:** أي مهمة تُنجز بـ Shell/ملفات يُحظر تنفيذها عبر GUI.
2. **الخلفية أولاً:** `foreground` تصعيد برد فعل `verdict` فقط + موافقة منفصلة.
3. **التحقق قبل التكرار:** مدخل `confirmed` لا يُعاد؛ `unverifiable` يُعاد التقاطه أولاً.
4. **التدقيق إلزامي:** كل عملية مغيّرة للحالة تُسجل في `ops_audit_log.jsonl`.
5. **الأمان من SOP الـ IT:** يُطبق `07_IT-Systems/IT_Security_Compliance_SOP.md`
   (لا أسرار في نصوص، لا مشاركة مفاتيح خاصة، 2FA إلزامي للحسابات).

## تحقق التشغيل — 2026-09-13
وضع dry-run لا يكتب السجل، و4 اختبارات منها append في ملف مؤقت؛ نسخة السجل الحقيقي لم تتغير في تجربة preview. الاختبارات الآلية مسجلة في المشغل المشترك للـpre-commit وCI.
