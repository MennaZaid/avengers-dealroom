# Test persona 2: Daniel, PharmaStock (Nairobi, Kenya)

**Fictional persona for testing only.** Not a real person or company.

Daniel Otieno is a pharmacist in Nairobi with some Python skills. He wants a stock-tracking tool for small
independent pharmacies. Compared with persona 1 (Mona, Nadafa, Egyptian Arabic), this tests:

| Path | How |
|---|---|
| English conversation | All messages in English |
| B2B idea | Customers are pharmacies, not households |
| Market outside Egypt | Kenya; later stages should show "no verified source" where the registry has no Kenya pack |
| Word document | Upload `pharmastock-pitch.docx` (has a table) |
| Skipping a **required** field | Skip the budget question |
| Labelled lines mid-conversation | Answer with `city: Nairobi` while asked something else |
| Correction in the summary | Change the business model price |

## Script

**1. First message**

> I'm a pharmacist in Nairobi. I want to build a simple stock-tracking tool for small independent pharmacies, because they keep running out of common medicines while over-ordering slow ones.

Expected: idea, problem and target customer filled. The country is **not** filled ("Nairobi" alone is a city);
city may be filled.

**2. Answer the questions it asks**

| When asked about… | Type |
|---|---|
| Country | `Kenya` |
| Budget | `skip` ← required field skipped on purpose |
| Time | `About 10 hours a week, for 6 months, alongside my pharmacy job` |
| Skills | `I'm a licensed pharmacist and I can write basic Python. No designer yet.` |

**3. On the optional question**, upload **`pharmastock-pitch.docx`**.
Expected, marked "from document": business model, known competitors, technical preferences, values
(the values line is inside a Word table).

**4. Upload `pharmastock-pitch.docx` again.**
Expected: "I already read pharmastock-pitch.docx", and the pending question is repeated.

**5. Follow-up questions:** answer the first, skip the rest:

> Pharmacists themselves, usually the owner. They update stock at the end of each day.

**6. Summary corrections** (send as one message, two lines):

> business model: monthly subscription, 15 USD per pharmacy
> budget: 3,000 USD

**7. Confirm:** `yes`

## What to check

| Check | Expected |
|---|---|
| Language | All replies in English |
| Skills | Keeps "licensed pharmacist" **and** "basic Python" and "no designer yet" (persona 1 lost a detail here) |
| Skipped budget | Shown as unknown until step 6, then `3,000 USD` |
| Word table | Values = "patient data never leaves the pharmacy", from document |
| Same file twice | Read once; no follow-up question skipped |
| Tags | Country code `KE`, customer type `b2b`, revenue model subscription, an industry like healthcare or software |
| Follow-ups | Should ask things only Daniel knows, not research questions (persona 1 got research questions) |
| Saved | Confirmation message and a brief id |
