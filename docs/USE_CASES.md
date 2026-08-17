# Personal Admin Agent — Use Cases

This document collects concrete scenarios Victoria should handle, grounding
DESIGN.md's architecture in real user stories. It's a requirements/scenario
reference, not an implementation spec — read it alongside DESIGN.md, not instead
of it.

**One wiki, two sections, not two systems.** DESIGN.md §2 and §13 already settle
this: house and business/LLC live in the same S3 bucket, the same wiki, under
`wiki/house/` and `wiki/business/`, sharing the same tools and search index.
"Both domains" below means populating both sections of one wiki — not designing
separate knowledge bases. A future cross-domain query (e.g. "how many hours did I
spend on house projects vs. LLC work this month") stays possible precisely
because it's one wiki.

Some use cases below surface things DESIGN.md doesn't yet address. These are
called out inline as **Design implications** and collected at the end — flagged
for a future DESIGN.md revision, not designed around here.

---

## House

### 1. Initial cataloging

After moving in, the user does a walkthrough and tells Victoria what they have —
tools, appliances (with model numbers, manuals, purchase dates), plants and
garden beds (species, location, planting date). This is the base inventory every
other house use case queries against.

> "I've got a cordless drill, a circular saw, and a shop vac in the garage."
> "The furnace is a Carrier model 58STA, installed 2019, filter is 16x25x1."
> "Planted three hydrangeas in the parking strip this spring, and a Japanese
> maple in the back corner of the yard."

### 2. Project readiness check

Before starting a project, the user asks whether they already have what it
needs, so they know what to buy before a trip to the hardware store.

> "Do I have what I need to hang a heavy mirror in the hallway?"
> "I want to replace the bathroom faucet — what tools am I missing?"

### 3. Maintenance tracking

The user asks what's due, rather than remembering every appliance's service
interval themselves.

> "What maintenance is coming up?"
> "Is it time to change the furnace filter?"
> "Anything I'm overdue on?"

**Design implication:** answering this well requires the wiki to track due
dates / recurring intervals (e.g. "furnace filter every 90 days"), not just
static facts. Nothing in the current page schema captures that. The periodic
Lint job (DESIGN §2) is a natural place to *surface* what's due once this
exists, but the schema needs the concept first.

### 4. Contacts / vendor lookup

The user wants to reach someone they've dealt with before, without hunting
through texts or email.

> "Who fixed the water heater last time?"
> "Do I have a plumber's number saved?"
> "Who do I call for the HOA?"

**Design implication:** no contacts page type/convention exists yet in the
schema/conventions file. This is already an open DESIGN §15 checklist item;
this use case is a concrete reason it's needed, not just a generic "we'll get
to it."

### 5. Garden/plant diagnostic advisory

The user has a specific, struggling plant and wants advice grounded in what's
actually planted where.

> "My hydrangeas in the parking strip are struggling — they were planted this
> year. What should I do?"

Answering this well needs *both* stored facts (which hydrangeas, planted when,
where — parking strip, which has specific stresses: reflected heat, road salt,
compacted soil, foot traffic) *and* the model's general horticultural
knowledge (transplant stress, watering needs in year one, parking-strip-specific
fixes) — synthesized together into one answer, not just recited from a page.

**Design implication:** query mode can't be implemented as strict
retrieve-and-recite. It needs to reason with the model's general knowledge on
top of retrieved facts. Worth stating explicitly wherever query mode is
described, so an implementation doesn't quietly narrow it to RAG-style lookup.

### 6. Manuals/warranty lookup

Ties back to DESIGN §1's stated goal of the house domain including manuals.

> "Where's the manual for the dishwasher?"
> "Is the water heater still under warranty?"

---

## Business / LLC

Mirrors DESIGN §1's stated scope: tax categories, hours worked, filings.

### 1. Hours/time logging

> "Log 3 hours of consulting for Acme Co today."
> "How many hours have I billed this month?"

### 2. Expense/tax categorization

Ingesting a purchase and classifying it for taxes. Text-only per DESIGN §7 — no
receipt photo/OCR pipeline yet, so this is a typed note, not a scanned receipt.

> "Spent $180 on a laptop stand for the LLC — what category is that?"
> "Log a $45 software subscription as a business expense."

### 3. Filing deadline tracking

> "When's my next quarterly filing due?"
> "What do I still owe for this filing period?"

**Design implication:** same due-date/recurring-task gap as house maintenance
(§1.3 above). One underlying schema feature — due dates / recurring items —
would serve both domains. That's a point in favor of it being a general wiki
capability rather than something bolted onto either section separately.

---

## Design implications summary

For quick reference the next time DESIGN.md is revisited:

- **Due dates / recurring items** are needed in the wiki page schema — driven by
  house maintenance (§House.3) and LLC filing deadlines (§Business.3). One
  shared capability, not domain-specific.
- **A contacts page type/convention** is needed — driven by "who should I
  contact" (§House.4). Already an open DESIGN §15 checklist item; this gives it
  a concrete use case.
- **Query mode must reason, not just retrieve.** The hydrangea scenario
  (§House.5) shows query mode needs to combine stored facts with the model's
  general knowledge. This should be made explicit in DESIGN.md's description of
  query mode, not left implicit.
