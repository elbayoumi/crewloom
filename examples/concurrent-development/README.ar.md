# مثال التطوير المتزامن: ledgerline

مثال كامل قابل للتشغيل لتطوير بالذكاء الاصطناعي على التوازي مع Crewloom. ثلاث مهام في
رسم بياني للتبعيات، كل مهمة يولّدها خط `model` حقيقي داخل شجرة عمل Git خاصة بها، وكل ملف
مولَّد يتحقّق منه أمر حقيقي داخل حاوية، ثم قبولٌ مشترك واحد، ثم تقدّم واحد مُراجَع على
الشجرة المفحوصة. التطبيق صغير لكنه حقيقي: يحسب ملخص فاتورة وخطة تنفيذ، بالعربية أو
الإنجليزية، من مستند JSON.

## التحضير

اختر مجلدًا ليس داخل شجرة عمل Git، ولا داخل مشروع آخر، ولا اسمًا بديلًا عبر رابط رمزي. على
macOS المسار `/tmp` ليس canonical؛ استخدم `/private/tmp`.

```bash
python3 examples/concurrent-development/setup_project.py \
  --destination /private/tmp/ledgerline \
  --project-id ledgerline-demo \
  --model-host openai \
  --model gpt-4.1
```

يرفض التحضير قبل أي كتابة: وجهة موجودة، أو وجهة يصل إليها(parent) عبر رابط رمزي، أو وجهة
داخل تثبيت Crewloom، أو داخل مشروع مربوط آخر، أو داخل شجرة Git أخرى، أو نموذج فارغ أو غير
محدد، أو مضيف مجهول، أو مضيف CLI مثبَّت بلا `--native-host-cli`، أو مضيف RPC معه. لا يختار
النموذج نيابة عنك ولا يرتد إلى مضيف آخر.

للمضيف المثبَّت مثل `opencode` أو `codex` أضف `--native-host-cli`؛ يُسجَّل هذا في المانيفست
المُودَع، ويحتاج التشغيل إلى `--allow-host-cli` أيضًا.

## التشغيل

```bash
PROJECT=/private/tmp/ledgerline
ID=ledgerline-demo

crewloom coordinator validate --project $PROJECT --project-id $ID --manifest coordinator.json
crewloom coordinator run      --project $PROJECT --project-id $ID --manifest coordinator.json
crewloom coordinator status   --project $PROJECT --project-id $ID --manifest coordinator.json
crewloom coordinator prepare  --project $PROJECT --project-id $ID --manifest coordinator.json
```

تعمل مهمتان بالتوازي، وتبدأ الثالثة بعد التحقق من الأولى والثانية. راجع الفرق الحقيقي قبل
التصريح:

```bash
git -C $PROJECT diff $BASE..$CANDIDATE
```

ثم سلّم اعتماد المراجع عبر البيئة أو الإدخال القياسي، ولا تمرره كوسيط:

```bash
export CREWLOOM_REVIEWER_TOKEN="$(cat $PROJECT/.crewloom/reviewer-token-example-reviewer)"

crewloom coordinator review  --project $PROJECT --project-id $ID --manifest coordinator.json \
  --expected-base $BASE --candidate-head $CANDIDATE --diff-sha256 $DIFF
crewloom coordinator publish --project $PROJECT --project-id $ID --manifest coordinator.json \
  --expected-base $BASE --candidate-head $CANDIDATE --diff-sha256 $DIFF
```

يرفض `publish` أي قرار غير مُراجَع، ثم ينقل الشجرة بخطوة `--ff-only` واحدة.

## استخدام التطبيق

```bash
cd $PROJECT
python3 src/app.py --data data/ledger_en.json --out artifacts/report.json
python3 src/app.py --data data/ledger_ar.json --out artifacts/report-ar.json --language ar
```

يرفض الأمر مستندًا غير صالح بخطأ JSON واحد على `stderr` ورقم خروج `2`، ولا يكتب ملفًا.

## الفشل والاستئناف والإلغاء

| الحالة | السلوك |
| --- | --- |
| فشل قبول مهمة | تصبح `failed`، وتتوقف كل مهمة تعتمد عليها، ولا يحدث دمج ولا نشر، ولا تتحرك الشجرة. |
| مقاطعة المتحكم | يفك القفل تلقائيًا؛ أعد `run`. المهام المتحققة لا تُنفَّذ مرتين. |
| الإلغاء | `crewloom coordinator cancel --project $PROJECT --project-id $ID --manifest coordinator.json` يوقف الإرسال ويحفظ العمل المتحقّق. |

كل شيء مسجَّل في `.crewloom/coordinators/ledgerline-batch/state.json`.

## القبول دون مزوّد

```bash
CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_development_example.py
```

يُستبدل فقط ناقل التوليد؛ أما Docker والتنفيذ والمراجعة وإثبات الإيداع فحقيقية. هذا يثبت
التنسيق والتحقق، لا جودة أي نموذج ولا زمنه ولا تكلفته.

التفاصيل الكاملة: [documentation/DEVELOPMENT_EXAMPLE.md](../../documentation/DEVELOPMENT_EXAMPLE.md)
و[COORDINATOR.md](../../documentation/COORDINATOR.md). English: [README.md](README.md).