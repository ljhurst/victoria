# Wiki conventions

This file lives at the wiki root (alongside `index.md` and `log.md`) and is
prompt-cached into every `remember` and `consolidate` call (DESIGN.md §12). It's
the only place page format is defined — deliberately not a rigid schema.
The wiki is data in files first; structure comes from consistent habits
(headings, lists, frontmatter), not enforced field types.

## File & directory layout

Start flat, one page per **category**, not per entity:

```
wiki/
  house/
    tools.md
    plants.md
    appliances.md
    contacts.md
  business/
    hours.md
    expenses.md
    filings.md
```

Each top-level directory under `wiki/` is a **domain**, and each domain has a
matching `##` section in `index.md` (a `home-office/` directory is listed
under `## Home Office`). A domain is one broad area of life. File into an
existing domain when the note is about that area; when it's about a
different area (vehicles or travel, say), start a new domain rather than
stretching an existing one to cover it. Name it short and lowercase
(hyphenated if it's more than one word), and don't split one area into
several overlapping domains.

Within a category page, separate entities with `##` headings:

```markdown
## Cordless drill

Bought 2024, Ryobi 18V. Kept in the garage, top shelf.

## Circular saw
...
```

**Splitting a category page**: when a category page grows large enough that
it stops being skimmable (rough judgment call, not a hard count — a few dozen
entities is a reasonable point to start considering it), it can be split into
a directory:

```
wiki/house/tools.md          →  wiki/house/tools/index.md
                                 wiki/house/tools/power-tools.md
                                 wiki/house/tools/hand-tools.md
```

`remember` never does this on its own — it always writes into the current
best-fit page and, if that page looks like it's grown unwieldy, says so in
its return summary. Splitting is a deliberate reorganization decision made by
`consolidate` (or the user, directly) — it's judgment-heavy in a way that
shouldn't happen silently in the middle of filing an unrelated fact.

## Page format

Every page (category page or, after a split, sub-page) starts with minimal
YAML frontmatter, then a markdown body:

```markdown
---
title: Tools
tags: [garage, hardware]
last-updated: 2026-08-16
---

## Cordless drill
...
```

- `title` — required.
- `tags` — optional, freeform, whatever's useful for `search_wiki` to match on
  later. Not a controlled vocabulary.
- `last-updated` — set automatically whenever `remember` or `consolidate`
  writes the page. Don't edit it.
- No other required fields. Don't invent structured fields for things like
  due dates, warranty expiry, or filing deadlines — write them as normal
  prose or a bullet list under a heading that names what it is:

  ```markdown
  ### Maintenance
  - Furnace filter (16x25x1): replace every ~90 days, last done 2026-06-01
  - Gutter cleaning: due each fall
  ```

  This keeps "what's due" answerable the same way everything else in this
  wiki is answerable — by `search_wiki` finding the page and the calling
  model reading and reasoning over the prose — not by a query language the
  wiki format has to support.

## Writing style

A page is a reference of facts, not a narrative. Keep it short and plain.

- State facts only, as short bullets or one-line sentences, in neutral wording.
- Include every fact the note states, and nothing it doesn't. Don't add
  background, context, conclusions or verdicts ("confirmed", "works well").
- No hedges or suggestions ("might", "consider", "try", "probably", "maybe").
  If the note itself is unsure, record that as the fact: "unknown whether the
  garage unit takes the same size".
- No open questions, ideas for next time, or to-do lists. A deadline or
  recurring schedule the note gives ("replace every 90 days") is a fact;
  record it.
- State each fact once on the page.
- Use absolute dates ("2026-10-23"), never "recently" or "currently".
- Keep a recipe's or procedure's ingredients and steps. Record a test result
  as one dated line.
- One topic per `##` heading.
- When `remember` adds to an existing page, it leaves the existing text as it
  is. Nothing removes a stated fact.

## Linking

Use plain relative markdown links between pages, not `[[wiki-link]]` syntax —
this keeps every page renderable in any ordinary markdown viewer (no
Obsidian-style resolver required):

```markdown
See also [hydrangea care notes](plants.md#hydrangeas-parking-strip).
```

Every category page should be linked from `index.md`. Sub-pages (after a
split) should be linked from their category's `index.md`, which itself stays
linked from the top-level `index.md`.

## What `remember` does

1. `search_wiki` for existing related pages
2. Decide: append/edit within an existing category page, or create a new
   category page if none fits
3. Write in the format above and follow the writing style — heading per entity,
   frontmatter kept current
4. Update `index.md` if a new category page was created
5. Update `search.db`
6. Return a short summary: which page, new-entity-vs-updated-existing, and a
   note if the page looks like a splitting candidate

## What `consolidate` does

- Flags contradictions and stale claims across pages
- Flags orphan pages (not linked from any `index.md`)
- Flags pages that break the writing style (padding, hedges, open questions,
  repeated facts) — reports them, doesn't rewrite them
- Proposes or performs category-page splits when a page has grown unwieldy
  (§ Splitting, above)
