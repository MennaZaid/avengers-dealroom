# Phase 3, step 3: MVP plan

Brief id: `3e540c9c-0f6b-43ed-b4f6-aabf69c1c037`

**Profile Builder**: Create your professional online presence effortlessly.

Template: **directory** (follows the product spec's offer kind). Drafted by: model Fanar-C-2-27B.

## Screens

- **Browse** (`home`): covers R1
- **Add a listing** (`add`): covers R1, R2, R3
- **My listings** (`list`): covers -
- **Feedback** (`feedback`): covers -

## Flows

Browse
Add a listing -> My listings
My listings -> Feedback

## Main record: profile

| Field | Type | Required | Requirement |
|---|---|---|---|
| Name | text | yes | R1 (must) |
| Email Address | text | yes | R1 (must) |
| Phone Number | number | no | R1 (must) |
| CV Template | select (Template A, Template B, Template C) | yes | R2 (must) |
| Portfolio Template | select (Notion Portfolio A, Notion Portfolio B, Notion Portfolio C) | yes | R3 (must) |

## Fits the founder's constraints

- One HTML file, no server and no hosting cost: fits any budget (budget: 3000egp).
- No programming needed to run or change the copy: the founder edits text, not code.

## Out of scope

- Real-time collaboration features
- Advanced customization options beyond template selection

## Assumptions (not checked)

- ASSUMPTION: Users will be able to download their chosen templates after selecting them.
