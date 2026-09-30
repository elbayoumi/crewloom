# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية تكاملات MCP

```
[طلب تكامل] → [بحث: modelcontextprotocol/servers ثم awesome] → قرار: جاهز/مخصص
  → [validate_mcp_config.py = PASS] → [تركيب uvx/npx | بناء FastMCP scoped]
  → [list-tools + استدعاء حي] → [config نهائي بـ env placeholders]
```

## حدود الاختصاص

| المهارة | نطاقها | الفرق |
|---|---|---|
| `mcp-integration-builder` (هنا) | تركيب سيرفرات MCP جاهزة + بناء مخصصة scoped | يبني طبقة البروتوكول نفسها |
| `machine-control-operator` | تشغيل تطبيقات الجهاز المحلية | يشغّل التطبيق، لا يبني سيرفر بروتوكول |
| `tech-stack-architect` | اختيار الستاك وتقييم الصعوبة | يقرر **إيه** الستاك، لا ينفّذ التكامل |
| `network-infra-engineer` | طبقة الشبكة للسيرفرات (DNS/SSL/proxy) | يشغّل الوصلة، لا أدوات MCP فوقها |

المرجع الرسمي للتعليم لا للإنتاج وحده — تحذير `modelcontextprotocol/servers` نفسه.
