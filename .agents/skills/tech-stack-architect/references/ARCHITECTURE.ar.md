# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية مهندس اختيار المكدس التقني (Tech Stack Architect Architecture)

```
[طلب توصية] → [استلام inputs (3 أسئلة)] → [Decision Tree في references/tech-decision-tree.md]
  → [تطبيق القواعد: ARCHITECTURE + CHALLENGES + Playbook]
  → [توليد التوصية بالقالب الرسمي]
  → [Grading Difficulty (1-5) + Testing Requirements]
  → [تسجيل في COMPLETED + Challenges لو جديد]
```

## مصادر الحقيقة (Single Sources of Truth)

| المدخل | المصدر |
|---|---|
| المعمارية المعتمدة | `01_Development/Brain/ARCHITECTURE.md` |
| الحوادث المرجعية | `01_Development/Brain/CHALLENGES.md` |
| القواعد الدائمة | `01_Development/Engineering_Standards_Playbook.md` |
| Decision Tree الكامل | `references/tech-decision-tree.md` |
| Testing Standards + QA Automation | [`qa-test-automation-engineer`](../../qa-test-automation-engineer) |

## حدود الاختصاص (لتفادي تداخل triggers)

| المهارة | نطاقها | الفرق |
|---|---|---|
| `tech-stack-architect` (أنا) | اختيار الـ stack + Difficulty grading | لا يكتب كود، لا يصمم UI |
| `delivery-director` | تنفيذ + SOW + Sprint management | يستلم توصيتي ويبني عليها |
| `frontend-ux-auditor` | فحص جودة كود الواجهات | يفحص الكود المبني على stackي |
| `growth-director` | تسعير + عرض سعر | يستخدم Difficulty Grade لتقدير effort |

## الاختبار الذاتي (Self-Validation)

كل توصية قبل التسليم لازم تجتاز:
1. ✅ **الـ stack مذكور في ARCHITECTURE** أو بموافقة خطية
2. ✅ **مبرر تقني محدد** (مش "مشهور" أو "سهل")
3. ✅ **ربط بحادث/مرجع** في CHALLENGES لو Grade ≥ 3
4. ✅ **Testing requirements محددة** (من جدول Grading)
5. ✅ **Risks مُدرجة** (لو Grade ≥ 3)
