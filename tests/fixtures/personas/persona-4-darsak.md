# Test persona 4: Noura, Darsak (Jeddah -> UAE)

**Fictional persona for testing only.** Not a real person or company.

Noura is a maths teacher from Jeddah. She wants an online tutoring platform for high-school maths and physics,
paid monthly by parents. She will launch in the UAE, not Saudi Arabia. Compared with personas 1-3, this tests:

| Path | How |
|---|---|
| Gulf Arabic | "أبي أسوي"، "عيالهم"، "ما عندنا" |
| **Rejecting** an inferred value | Bot assumes Saudi Arabia from "جدة"; she answers "لا، الإمارات" |
| Country outside Egypt in Arabic | Country code should become `AE` |
| Short value picked up in passing | "معلمة رياضيات" -> bot asks for the full skills |
| Two required fields skipped | Budget and time, filled later in the summary |
| Arabic label while collecting | `نموذج العمل: ...` typed on the optional question |
| Two Arabic labels on one line | `الميزانية: ... الوقت المتاح: ...` |
| Arabic tag label | `القطاعات: education, software_saas` |
| Follow-up answered later | `q2: ...` in the summary |
| `.md` upload **after** confirming | Starts an edit; saved as version 2 |
| Document can't override the founder | The notes say "Country: Switzerland"; the founder's answer stays |

## Script

**1. First message** (one message):

> هلا، أنا نورة معلمة رياضيات من جدة. أبي أسوي منصة دروس خصوصية أونلاين لطلاب الثانوي في الرياضيات والفيزياء، لأن الأهالي يدفعون مبالغ كبيرة للمدرسين الخصوصيين وما يقدرون يتابعون مستوى عيالهم.

Expected: replies in Arabic; idea and problem filled; the bot asks whether the country is السعودية (only
implied by "جدة").

**2. Answer what it asks**

| When it asks… | Type |
|---|---|
| "Is the country السعودية?" | `لا، الإمارات` |
| Target customers | `أولياء أمور طلاب الثانوي في دبي والشارقة` |
| Budget | `تخطي` |
| Time | `تخطي` |
| "So far I noted skills: معلمة رياضيات…" (or the skills question) | `أنا معلمة رياضيات من ١٠ سنين، وأختي مصممة، وما عندنا مبرمج` |
| Any other "so far I noted…" | `نعم` |

**3. On the optional question**, type (Arabic label, no upload):

> نموذج العمل: اشتراك شهري يدفعه ولي الأمر

**4. Follow-up questions:** answer the first, skip the rest:

> الأهالي هم اللي بيدفعون، والطالب هو اللي يستخدم المنصة

**5. In the summary**, send these one at a time:

> الميزانية: 40 ألف درهم الوقت المتاح: 15 ساعة في الأسبوع لمدة 8 شهور

> القطاعات: education, software_saas

> q2: لسه ما كلمت أحد

(If there is no q2, skip that line.)

**6. Confirm:** `تمام`

**7. After confirming, upload `darsak-notes.md`**, then reply `نعم`.

**8. Send `تمام` once more.**

## What to check

| Check | Expected |
|---|---|
| Language | Every reply in Arabic with Arabic field names |
| Inferred country | Asked as a question; after "لا، الإمارات" the country is الإمارات and the tag `country_code` is `AE` (not `SA`) |
| Skills | Keeps "١٠ سنين", "أختي مصممة" and "ما عندنا مبرمج" |
| Skipped budget/time | "غير معروف" until step 5, then both set from the one line |
| Business model | "اشتراك شهري يدفعه ولي الأمر", answered (not from document) |
| Tags | Industries exactly `education, software_saas` (founder); revenue model `subscription`; languages `ar, en` |
| Follow-ups | Only things Noura knows; market/price/law questions listed for research |
| q2 | Saved as "لسه ما كلمت أحد" |
| Version 1 | Saved on `تمام` |
| `.md` after confirming | Reply says it found known competitors and values (**not** country); the brief opens for editing |
| Document vs founder | Country stays الإمارات; budget stays 40 ألف درهم; nothing is confirmed until you reply |
| Version 2 | Saved after `نعم`, change note lists known competitors and values |
| Step 8 | "Nothing changed", stays version 2 |
