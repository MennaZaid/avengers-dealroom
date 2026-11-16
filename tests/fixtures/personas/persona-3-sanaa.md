# Test persona 3: Hoda, Sanaa (Aswan, Egypt)

**Fictional persona for testing only.** Not a real person or company.

Hoda is a commerce graduate in Aswan. She wants an online marketplace for handmade goods (kilim rugs, palm-leaf
baskets, pottery) made by women artisans in Aswan and Luxor, sold to buyers in Cairo and abroad.
Compared with personas 1 (Nadafa) and 2 (PharmaStock), this tests the paths they did not:

| Path | How |
|---|---|
| Arabic mixed with English words | "marketplace", "handmade", "Instagram" inside Egyptian Arabic |
| Inferred country confirmed in dialect | "Aswan" -> bot asks "is it Egypt?" -> reply `ايوه` |
| PDF upload | `sanaa-plan.pdf` |
| Marketplace (two-sided) idea | Artisans supply, buyers pay a commission |
| Unlabelled Arabic correction | `غير الميزانية لـ 25 ألف جنيه` |
| Tag correction | `industry: handmade_crafts, retail_ecommerce` |
| Edit after confirmation -> version 2 | Change the city after confirming |
| Cancelled edit | Change the budget, then `إلغاء` |

## Script

**1. First message** (one message):

> أنا هدى من أسوان. عايزة أعمل marketplace أونلاين للمنتجات الـ handmade اللي بتعملها الستات في أسوان والأقصر، زي الكليم والخوص والفخار. المشكلة إن الستات دول مش لاقيين طريقة يبيعوا برة قريتهم غير عن طريق وسطاء بياخدوا معظم المكسب.

Expected: idea and problem filled; replies in Arabic; the bot asks whether the country is مصر (it was only
implied by "أسوان").

**2. Answer what it asks**

| When asked about… | Type |
|---|---|
| "Is the country مصر?" | `ايوه` |
| Target customers | `ناس في القاهرة وبرة مصر بيحبوا المنتجات اليدوية الأصلية` |
| Budget | `20 ألف جنيه بس` |
| Time | `يومين في الأسبوع لمدة سنة` |
| Skills | `أنا خريجة تجارة وشاطرة في التصوير والتسويق على انستجرام` |
| "So far I noted …" (if it appears) | type the full answer from this table, or `نعم` if it is already complete |

**3. On the optional question**, upload **`sanaa-plan.pdf`**. Expected, marked "من المستند": business model
(12% commission), known competitors, technical preferences, values.

**4. Follow-up questions:** answer the first, skip the rest:

> الستات هيصوروا المنتجات وأنا هعمل الإعلان والشحن من أسوان

**5. In the summary**, send these one at a time:

> غير الميزانية لـ 25 ألف جنيه

> industry: handmade_crafts, retail_ecommerce

If the target customers show the **artisans** (the supply side) instead of the buyers, correct it with the
Arabic label. In the live run on 2026-11-16 the model picked the artisans from the first message:

> العملاء المستهدفون: ناس في القاهرة وبرة مصر بيحبوا المنتجات اليدوية الأصلية

**6. Confirm:** `ايوه`

**7. Edit after confirming:**

> خلي المدينة الأقصر

then `نعم`. Expected: "تم الحفظ كنسخة 2 (تم تغيير: المدينة)".

**8. Cancelled edit:** `تعديل`, then `budget: 1 EGP`, then `إلغاء`.
Expected: back to version 2, budget still 25 ألف.

## What to check

| Check | Expected |
|---|---|
| Language | Every reply in Arabic, with Arabic field names |
| Country | Asked as a yes/no question, then saved as مصر (confirmed by founder) |
| PDF | 4 optional fields filled, marked from document |
| Correction without a label | Budget becomes "25 ألف جنيه" |
| Tags | Industries exactly `handmade_crafts, retail_ecommerce` (set by founder); customer type `b2c` or `b2b2c`; revenue model `commission`; country code `EG` |
| Follow-ups | Only things Hoda knows; market questions under "أسئلة ستبحث عنها مرحلة الاكتشاف" |
| `ايوه` | Accepted as yes everywhere |
| Version 2 | Saved with change note "Edited by founder: city"; `GET /onboarding/briefs/{id}` shows history v1, v2 |
| Cancel | Version stays 2; budget unchanged |
