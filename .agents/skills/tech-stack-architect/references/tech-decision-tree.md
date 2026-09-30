# 🏗️ شجرة اختيار المكدس التقني (Tech Stack Decision Tree)
## المعيار المعتمد لمشاريع Crewloom — يُحدّث من حوادث حقيقية فقط

> 🚨 **مبدأ:** كل قاعدة هنا اتبنت من حادثة في مشروع فعلي أو قرار هندسي موثق في `01_Development/Brain/ARCHITECTURE.md`. مفيش "AI قال ده" — كل اختيار مرجعه ملف أو حادثة.

---

## 🧭 المدخلات (Inputs) — يُسأل عنها قبل أي توصية

### فرع المطاعم والكافيهات (إلزامي عند `restaurant`/`café`)

قبل اختيار stack عام، استخدم `BASE_PROJECT_TAXONOMY.md` (project-supplied: `BASE_PROJECT_TAXONOMY.md`):

```text
منيو وإطلاق سريع فقط → FOOD_MENU_LITE_FB (Firebase، READY)
تشغيل بطاولات/QR/حالات/صلاحيات/Postgres → FOOD_OPS_ADV_PG (READY)
```

يجب أن يظهر `Base ID` في التوصية وفي Delta Analysis. لا تستخدم اسم `restaurant base`
بلا suffix، ولا تخلط Firebase وPostgres في عميل واحد بدون قرار Migration موثق.

1. **نوع الخدمة** (من `Client_Project_Delivery_Workflow.md`):
   - `mvp` — منتج جديد من الصفر، تسليم 6-8 أسابيع
   - `retainer` — صيانة/تطوير لمنتج موجود
   - `custom` — مشروع مخصص بمواصفات خاصة
   - `marketing` — صفحة هبوط / حملة / موقع بسيط

2. **طبيعة المنتج** (decision key):
   - Web app (لوحة تحكم، SaaS، portal)
   - Mobile app (iOS, Android, cross-platform)
   - Landing page / Marketing site
   - E-commerce
   - Internal tool / Admin dashboard
   - API / Backend only
   - AI/ML pipeline
   - Real-time / Chat / Collaboration

3. **حجم التوقع** (scale):
   - صغير: < 1K مستخدم، 1-3 devs
   - متوسط: 1K-50K مستخدم، 3-10 devs
   - كبير: 50K+ مستخدم، team dedicated

4. **متطلبات خاصة** (constraints):
   - RTL Arabic أولوي؟
   - Real-time updates؟
   - Offline support؟
   - SEO حرج؟
   - فريق موجود له خبرة في stack معين؟

---

## 🌳 شجرة القرار الأساسية (The Tree)

```
[نوع الخدمة: marketing?]
  ├── YES → Marketing Site / Landing Page
  │         ↓
  │   [SEO حرج + أداء تحميل أولي؟]
  │   ├── YES → Next.js 15 (App Router) + Static Export أو SSG
  │   └── NO  → Astro (content-heavy) أو Next.js 15
  │
  └── NO → [طبيعة المنتج]
            ↓
            ├── Mobile App
            │   ├── فريق cross-platform مطلوب؟ → Flutter (راجع skill 13)
            │   ├── Native iOS ضروري؟ → Swift + Xcode
            │   ├── Native Android ضروري؟ → Kotlin + Android Studio
            │   └── Web-first PWA يكفي؟ → Next.js 15 + PWA manifest
            │
            ├── Web App (Dashboard / SaaS / Portal)
            │   ├── فريق < 3 devs + سرعة إطلاق → Next.js 15 (Full-stack App Router)
            │   ├── فريق كبير + microservices مطلوب → NestJS (Backend) + Next.js (FE) + PostgreSQL
            │   ├── Python AI/ML في الـ core → FastAPI (Backend) + Next.js (FE) + PostgreSQL + Redis
            │   ├── Real-time (chat / collaboration) → Next.js 15 + Go (Realtime Engine) [راجع skill 16]
            │   └── E-commerce → Next.js 15 + Medusa.js أو Shopify Hydrogen
            │
            ├── API / Backend Only
            │   ├── TypeScript-first team → NestJS أو Fastify
            │   ├── Python + AI/ML → FastAPI
            │   ├── Go (high-perf) → Gin أو Echo
            │   └── Microservices → NestJS (orchestration) + Go (workers)
            │
            ├── AI/ML Pipeline
            │   ├── LLM integration → Python (FastAPI) + LangChain/LlamaIndex
            │   ├── Vision/Image ML → Python (FastAPI) + PyTorch
            │   └── Inference at scale → Go wrapper حول Python model
            │
            └── Real-time / Chat
                ├── Voice/Video (WebRTC) → Go (signaling) + Next.js (UI) + Redis (presence)
                └── Text collaboration → Next.js + Go realtime + CRDT (Yjs)
```

---

## 🗂️ جدول المكدسات المعتمدة (Approved Stacks)

| Stack | Use Case | Strengths | When NOT to use |
|---|---|---|---|
| **Next.js 15 Full-Stack** | Web app متوسط، MVP، Dashboard | App Router + RSC + Edge + TypeScript + Zod | نظام real-time ثقيل، أو Python AI/ML في الـ core |
| **Next.js 15 + NestJS** | SaaS متوسط-كبير، team > 5 devs | فصل FE/BE، DI، microservices-ready | MVP سريع، فريق صغير |
| **Next.js 15 + FastAPI** | AI/ML product، Python-first team | Python ecosystem (PyTorch, LangChain) | فريق TS-only |
| **Next.js 15 + Go Realtime** | Chat، collaboration، tracking | WebSocket عالي الأداء | مش real-time |
| **Flutter** | Mobile cross-platform | iOS + Android من كود واحد، Crewloom skill 13 | Web app فقط |
| **Astro** | Marketing site content-heavy | Static + islands، SEO ممتاز | Web app تفاعلي |
| **NestJS alone** | API only | Modular، TypeScript DI | لو محتاج UI سريع |
| **FastAPI alone** | Python microservice | AI/ML ecosystem | Frontend |
| **Go (Gin/Echo)** | High-perf microservice | أداء، concurrency | مش للمبتدئين |

---

## 📏 Difficulty Grading (تقييم صعوبة المشروع)

### المستوى 1 — Starter (أسبوع 1-2)
- Landing page، موقع تعريفي، Marketing site
- نموذج اتصال + email
- CMS بسيط (Sanity/Contentful)
- **Stack المعتاد:** Next.js 15 + Static Export أو Astro
- **مؤشرات:** 1 dev، 0 integrations معقدة، 0 auth

### المستوى 2 — MVP Standard (6-8 أسابيع)
- Dashboard بإدارة CRUD
- Auth (NextAuth/Clerk)
- 1-2 integrations (Stripe, SendGrid, S3)
- Database واحد (Postgres)
- **Stack المعتاد:** Next.js 15 Full-Stack + Postgres + Drizzle/Prisma
- **مؤشرات:** 2-3 devs، 5-10 pages، 1-2 external APIs

### المستوى 3 — Multi-Service SaaS (10-16 أسبوع)
- Multi-tenant، Role-Based Access Control (RBAC)
- 3+ integrations
- Background jobs، Webhooks
- Real-time updates
- **Stack المعتاد:** Next.js 15 + NestJS أو FastAPI + Postgres + Redis + n8n
- **مؤشرات:** 3-5 devs، 20+ pages، 5+ integrations

### المستوى 4 — Enterprise / Regulated (16-24 أسبوع)
- Multi-region deployment
- Audit logging، SOC2/GDPR compliance
- Complex RBAC + Permissions Registry
- Real-time + Background workers + AI
- **Stack المعتاد:** Next.js 15 + NestJS + Go workers + Postgres + Redis + Elasticsearch (توصية نظرية لمشروع مستقبلي بهذا الحجم — لسه محدش استخدمها فعلياً)
- **مؤشرات:** 5-10 devs، dedicated DevOps، compliance requirements

### المستوى 5 — Platform / Infrastructure (24+ أسبوع)
- Microservices architecture
- Kubernetes / Service Mesh
- Multi-database (Polyglot persistence)
- Event-driven (Kafka/RabbitMQ)
- **Stack المعتاد:** حسب الـ domain، غالباً Go/Rust core + TypeScript edges
- **مؤشرات:** 10+ devs، dedicated platform team

---

## 🧪 متطلبات الـ Testing (لكل مستوى)

| المستوى | Unit Tests | Integration | E2E | Load Test | Security Audit |
|---|---|---|---|---|---|
| 1 | اختياري | يدوي | يدوي | ❌ | ❌ |
| 2 | ✅ (Vitest) | ✅ (API routes) | ✅ (Playwright) | ❌ | يدوي |
| 3 | ✅ + 80% coverage | ✅ + DB | ✅ + Auth flows | ✅ (k6) | ✅ (OWASP top 10) |
| 4 | ✅ + Contract tests | ✅ + Microservices | ✅ + Multi-tenant | ✅ + Stress | ✅ + Pen test |
| 5 | ✅ + Mutation testing | ✅ + Service contracts | ✅ + Disaster recovery | ✅ + Chaos engineering | ✅ + Compliance audit |

**راجع:** [`qa-test-automation-engineer`](../../qa-test-automation-engineer) — ينفّذ الجدول أعلاه فعلياً حسب مستوى المشروع.

---

## 🚨 قواعد صارمة (Hard Rules)

1. **ممنوع** تستخدم stack جديد بدون `validate_skill.py` يمر + مراجعة `01_Development/Brain/CHALLENGES.md` لحوادث مشابهة.
2. **ممنوع** تختار stack بناءً على "الترند" — لازم يكون له سبب تقني أو حادث موثق.
3. **لازم** يكون الـ stack مذكور حرفياً في `01_Development/Brain/ARCHITECTURE.md` أو يُضاف إليه بموافقة المدير الهندسي.
4. **لو العميل عنده stack موجود** (في Retainer): الـ Tech Selector يقيّم الحالة، لا يستبدل. Migration تكلفة كبيرة.
5. **لو المشروع الحكومي/Enterprise:** المستوى 4+ افتراضي، compliance من Sprint 1.

---

## 📋 قالب التوصية (Recommendation Output)

```markdown
## 🎯 توصية Tech Stack — <اسم المشروع>

**المستوى:** <1-5>
**النوع:** <web|mobile|api|ml|realtime>
**Stack المقترح:** <الـ stack>

### المبررات (3 نقاط على الأكثر)
1. <سبب تقني محدد>
2. <سبب عملي (تيم/وقت/تكلفة)>
3. <سبب حادث موثق في CHALLENGES أو حالة شبيهة>

### البدائل المرفوضة
- <stack آخر>: <لماذا لا>

### متطلبات الـ Testing
- [ ] <list from grade table>

### مخاطر معروفة
- <أي مخاطر مع حلول معتمدة>

### روابط مرجعية
- [ARCHITECTURE.md] القسم <X>
- [CHALLENGES.md] التحدي <Y>
- أي تجربة عميل مشابهة
```

---

## 🔗 روابط مرجعية

- `01_Development/Brain/ARCHITECTURE.md` (project-supplied: `ARCHITECTURE.md`) — المعمارية المعتمدة
- `01_Development/Brain/CHALLENGES.md` (project-supplied: `CHALLENGES.md`) — حوادث حقيقية
- `01_Development/Engineering_Standards_Playbook.md` (project-supplied: `Engineering_Standards_Playbook.md`) — قواعد دائمة
- [`qa-test-automation-engineer`](../../qa-test-automation-engineer) — اختبار وإطلاق (يحل محل مرجعين وهميين سابقين، راجع `brain/CHALLENGES.md` التحدي 1)
- **Go realtime:** لا يوجد موظف/مهارة مخصصة بعد — لو المشروع Real-time فعلياً، يُطلب توظيف عبر `skill-forge-recruiter` قبل البدء، لا الاعتماد على مرجع غير موجود
- **Flutter mobile:** لا يوجد موظف/مهارة مخصصة بعد — نفس الإجراء أعلاه قبل قبول مشروع Flutter

---

**آخر تحديث:** 2026-09-05 — الإصدار 1.0
**المؤلف:** Crewloom (Crewloom) — تعيين جديد
