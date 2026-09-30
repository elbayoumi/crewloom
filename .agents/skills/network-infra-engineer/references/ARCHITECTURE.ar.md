# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية إعداد الشبكة (Network Setup Architecture)

```
[VPS من tech-stack-architect] → [DNS: A/CNAME] → [SSL/TLS: certbot/منصة]
  → [Nginx reverse proxy + Docker network] → [Firewall: منافذ 80/443/SSH فقط]
  → [ربط CI/CD بالسيرفر الحي] → [verify_domain_deployment.py = PASS]
  → [تسليم لـ frontend-ux-auditor بند 16 للتحقق البعدي المستمر]
```

## حدود الاختصاص (لتفادي تداخل triggers)

| المهارة | نطاقها | الفرق |
|---|---|---|
| `network-infra-engineer` (هنا) | تشغيل الطبقة الشبكية لسيرفرات العملاء الفعلية (DNS/SSL/Proxy/Firewall/CI-to-host) | ينفّذ الوصلة الشبكية نفسها |
| `tech-stack-architect` | اختيار الاستضافة/الستاك (VPS مين، أي مزوّد) | يقرر **إيه** الاستضافة، لا يُشغّلها |
| `machine-control-operator` | جهاز المالك المحلي فقط | لا يلمس سيرفرات عملاء بعيدة |
| `frontend-ux-auditor` (بند 16) | تحقق بعدي دوري إن النشر الحي مطابق للكود | يرصد لو الوصلة انقطعت لاحقاً، لا يُنشئها |

## سلسلة السبب الحقيقية لوجود هذه المهارة

`01_Development/Brain/CHALLENGES.md` (project-supplied: `CHALLENGES.md`)
و[`frontend-ux-auditor/brain/CHALLENGES.md`](../../frontend-ux-auditor/brain/CHALLENGES.md)
مرجع 9: المستودع مكانش مربوط بنشر تلقائي، فالسيرفر الحي فضل يخدم كاش عمره 5
ساعات بينما الوكيل بيعلن الإصلاح "تم" 3 مرات متتالية. `frontend-ux-auditor`
بند 16 اكتشف العَرَض (النشر الحي مش مطابق)، لكن محدش كان مسؤولاً عن **إصلاح
الوصلة الشبكية نفسها** — الفجوة دي بالظبط اللي هذه المهارة بتسدها.

## أدوات الفحص المعتمدة

- `dig`/`nslookup` — التحقق الفعلي من سجلات DNS، لا افتراض.
- `curl -vI https://<domain>` — فحص سلسلة الشهادة ورأس الاستجابة.
- `scripts/verify_domain_deployment.py` (project-supplied: `verify_domain_deployment.py`) —
  بوابة آلية موحّدة (DNS + SSL + رد حي غير افتراضي)، مكتبة قياسية فقط. تحقق فعلي:
  `python3 scripts/verify_domain_deployment.py --domain` شُغِّل على 3 دومينات
  حقيقية — دومين IANA المرجعي المخصص للتوثيق (PASS كامل، exit 0)،
  `expired.badssl.com` (FAIL صحيح على الشهادة، exit 1)، ودومين غير موجود
  (FAIL صحيح على DNS، exit 1).
- `ufw status` أو لوحة Security Group للمزوّد السحابي — توثيق المنافذ المفتوحة.
