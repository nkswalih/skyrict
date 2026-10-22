# Skyrict Brand Identity System

**Version:** 1.0 · **Theme:** Sky · **Last updated:** 22 October 2026

Skyrict is an AI Business Operating System. This document defines what the
brand stands for, how it speaks, and how it looks across the website, product,
docs, sales, and everything else that carries the name.

It is deliberately narrower than a mood board. Every rule here exists to make
Skyrict feel like one company: **grounded in operations, current on the market,
and clear about the next move.**

- **Visual source of truth:** [`apps/web/src/styles/globals.css`](../../apps/web/src/styles/globals.css)
- **Digital logo source:** [`apps/web/src/components/brand/logo.tsx`](../../apps/web/src/components/brand/logo.tsx)
- **UI specification:** [`docs/design-system/README.md`](../design-system/README.md)
- **Trademark policy:** [`TRADEMARK.md`](../../TRADEMARK.md)
- **Exported marks:** [`docs/brand/assets/`](assets/)

> If this document and the running product disagree, the running product is the
> current visual truth and this document is out of date. Fix both in the same
> pull request.

---

## 0. At a glance

| Attribute     | Definition                                                                  |
| ------------- | --------------------------------------------------------------------------- |
| Name          | **Skyrict**, one word, capital S                                            |
| Descriptor    | **AI Business Operating System**                                            |
| Category      | Business operations + market intelligence + AI agents in one decision loop  |
| Brand idea    | **The whole picture, in time.**                                             |
| Campaign line | **Make tomorrow's calls on today's signals.**                               |
| Promise       | See the whole picture while there is still time to act.                     |
| Audience      | Operating leaders at growing, multi-market businesses                       |
| Personality   | Clear · Composed · Grounded · Forward-looking                               |
| Creative mode | **Signal lines** — evidence, movement, and the line from signal to decision |
| Signature     | Sky-blue accent, 1px borders, mono labels, restrained radii, data as hero   |

---

## 1. Brand strategy

### 1.1 Purpose

**Give businesses the whole picture while there is still time to act.**

Most companies do not fail because they lack data. They fail because the
picture is split: operations live inside one set of systems, market movement
lives outside them, and the decision happens after both have gone stale.
Skyrict exists to close that gap.

### 1.2 Mission

**Connect operational truth and market context into decisions that are
grounded, timely, and explainable.**

- **Grounded** — the evidence comes from the customer's live operations and the
  actual market, not a generic model prior.
- **Timely** — the signal surfaces the week it moves, not the quarter after.
- **Explainable** — every proposed action carries the reasoning that supports
  it, so a human can check the logic before approving it.

### 1.3 Vision

**Every business operates as a node in a live market, not an isolated ledger.**

The long-term shift is not "more dashboards." It is businesses that read
external movement continuously, correlate it with their own operations, and
act with the same confidence they apply to internal reporting.

### 1.4 Positioning

For growing, multi-market businesses that make inventory, cash, and growth
decisions on stale internal reports, **Skyrict is the AI business operating
system that keeps operations and market signals in one live decision loop.**

Unlike ERPs that only record what happened, or intelligence tools that only
describe the market, Skyrict returns an explainable next move and the evidence
behind it.

**Frame of reference:** ERP and operations software, market intelligence and
trend tools, and generic AI copilots. Skyrict is the connection between them,
not a fourth category of dashboard.

### 1.5 Audience

| Priority       | Who                                                               | What they need from us                                                          |
| -------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Primary**    | COO, operations and supply-chain leads, finance leads, founder/MD | Confidence that stock, cash, and growth decisions reflect what is happening now |
| **Secondary**  | Sales and CRM leads, category and commercial managers             | Evidence that demand is moving before committing inventory or spend             |
| **Evaluators** | CTO, IT and security leads, implementation partners               | Proof of tenancy, permissions, integration, and open-source inspectability      |
| **Community**  | Developers, contributors, and self-hosters                        | A credible technical project with honest status and clear boundaries            |

**What they have in common:** they are accountable for a number that changes
weekly, and they are tired of reconciling tabs before a decision.

### 1.6 Value proposition and proof

| Claim                          | Proof                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------- |
| One system, not three products | ERP, Agents, and GMIE share one data plane and one event-driven workspace              |
| Decisions, not descriptions    | Agents return a proposed action with reasoning, confidence, and the evidence behind it |
| The market, read continuously  | Five public signal sources: Google Trends, YouTube, Reddit, GitHub, and news APIs      |
| Built for real operations      | Multi-tenant core, Row-Level Security, roles, MFA, and email verification              |
| Claims you can check           | Apache 2.0 source is public; unfinished pillars are labelled "in progress"             |
| Provider-agnostic intelligence | The LLM layer is not tied to a single model provider                                   |

### 1.7 Competitive contrast

|                     | Traditional ERP         | Market intelligence tool         | Generic AI copilot              | **Skyrict**                                      |
| ------------------- | ----------------------- | -------------------------------- | ------------------------------- | ------------------------------------------------ |
| View of the company | Isolated entity         | A subscriber to external reports | A chat box beside the real work | A node in a live market                          |
| Data                | Internal transactions   | External signals only            | Whatever fits in a prompt       | Internal operations + external signals           |
| Output              | Record of what happened | Description of the market        | Generated text                  | An explainable next move                         |
| Decision loop       | Human reads, then acts  | Human reads, then switches tools | Human copies context, then acts | Agents correlate, propose, and wait for approval |
| Trust               | Vendor claims           | Opaque scoring                   | Unverifiable reasoning          | Evidence, confidence, and public source          |

### 1.8 Brand idea

**The whole picture, in time.**

"Whole picture" is the product: operations and market in one frame. "In time"
is the value: the decision arrives while it can still change the outcome. Both
words matter. A complete picture that arrives late is a report. A fast signal
without context is noise.

The idea is internal strategy, not a headline to repeat verbatim. It should
shape what we build, what we publish, and what we refuse to claim.

### 1.9 Values and behaviours

| Value                       | What it means                                   | How it shows up                                                             |
| --------------------------- | ----------------------------------------------- | --------------------------------------------------------------------------- |
| **Evidence over assertion** | Show the number, the source, and the timestamp  | Recommendations cite signals; marketing claims link to proof                |
| **Time is the product**     | A signal is only useful before the decision     | We prioritise freshness, latency, and "what changed" over archive depth     |
| **Explain the call**        | A recommendation without reasoning is a command | Agents expose confidence and evidence; humans approve consequential actions |
| **Calm under load**         | Dense data does not have to feel loud           | Quiet surfaces, one accent, 1px borders, no alarmist colour                 |
| **Build in the open**       | Claims should be checkable                      | Public source, honest status labels, documented limitations                 |

### 1.10 Personality

Skyrict is the competent operator in the room: early, prepared, and unexcited
by its own technology.

| We are              | We are not   | Expression                                              |
| ------------------- | ------------ | ------------------------------------------------------- |
| **Clear**           | Simplistic   | Short sentences, concrete nouns, one idea per surface   |
| **Composed**        | Cold         | Confident without hype; calm when something is degraded |
| **Grounded**        | Conservative | Rooted in real operations, real units, real time frames |
| **Forward-looking** | Futuristic   | Points to the next move, not to science fiction         |

If a line sounds like it belongs to a different AI company, cut it. If it
sounds like it came from an operator who has closed a quarter, keep it.

---

## 2. Brand architecture and naming

### 2.1 Master brand

**Skyrict** is the master brand. Every product surface is endorsed by it. There
are no independent sub-brand logos, mascots, or competing wordmarks.

| Layer        | Name                     | Use                                                                    |
| ------------ | ------------------------ | ---------------------------------------------------------------------- |
| Master brand | **Skyrict**              | Company, platform, website, legal, all signatures                      |
| Operations   | **Skyrict ERP**          | Formal naming; "ERP" is acceptable after first mention                 |
| Automation   | **Skyrict Agents**       | Formal naming; "Agents" in navigation; "AI agents" in descriptive copy |
| Intelligence | **Skyrict Intelligence** | The product surface; **GMIE** is the engine behind it                  |

**GMIE** stands for **Global Market Intelligence Engine**. It is the
intelligence engine, not a separate product brand. Write the full name on first
use in external copy, then GMIE.

### 2.2 Naming rules

- **Skyrict** is one word, capital S. Never `SkyRict`, `Sky Rict`, or `SKYRICT`.
  In running text, write Skyrict without a trademark symbol; formal legal and
  licensed uses follow [`TRADEMARK.md`](../../TRADEMARK.md) for symbol placement.
- Do not create product names that compete with the master brand. "Skyrict
  Analytics" is acceptable as a descriptive label; "Skyrictly" is not.
- Do not call the platform "Skyrict OS" or "Skyrict AI". The descriptor is
  **AI Business Operating System**; the name is **Skyrict**.
- Use **the Skyrict platform** when a noun is required. Do not write "the
  Skyrict" on its own.
- Module names are not possessive: write "the Agents workspace", not "Agents'".
- Agent names are proper nouns: **Guardian**, **Coaching**. On first mention,
  write "the Guardian agent"; afterwards, "Guardian". "Coaching" is the second
  named agent, not a generic verb when capitalised.
- Repositories, packages, domains, and file paths are lowercase: `skyrict`,
  `@skyrict/web`, `skyrict.in`.
- The public site is **skyrict.in**. Sales contact is **sales@skyrict.in**.

### 2.3 Endorsement

Use **"Powered by Skyrict"** only for integrations and partner surfaces that
genuinely run on the platform. It is a factual endorsement, not a co-brand.
Never imply partnership, certification, or sponsorship without written
approval.

---

## 3. Verbal identity

### 3.1 Voice principles

1. **Lead with the decision, then the evidence.**
   Say what changed and what to do. Put the supporting numbers immediately
   after, not three paragraphs later.

2. **Write like an operator, not a vendor.**
   Use the words a COO uses: stock cover, cash, lead time, reorder point,
   margin, pipeline. Avoid abstract transformation language.

3. **Put units and time frames on every number.**
   `+18% week over week`, `2 days of cover`, `$9,400`, `09:42 UTC`. A number
   without a unit is decoration.

4. **Separate what is known, inferred, and unknown.**
   "Google Trends shows search up for a third week" is known. "Demand will
   hold through Friday" is inferred. "The competitor launch date is unconfirmed"
   is unknown. Do not blur the three.

5. **Cut the pedestal.**
   No hype, no urgency theatre, no adjectives doing the work of evidence. If a
   sentence survives only because it sounds impressive, delete it.

### 3.2 Tone by context

| Context            | Tone                                           | Example                                                               |
| ------------------ | ---------------------------------------------- | --------------------------------------------------------------------- |
| Marketing          | Confident, concrete, forward-looking           | "Make tomorrow's calls on today's signals."                           |
| Product UI         | Neutral, precise, second person                | "Stock covers 2 days. Reorder point is 5 units."                      |
| Docs               | Literal, sequential, no metaphors              | "Connect a source before creating an agent."                          |
| Support            | Direct, accountable, next step                 | "The feed is delayed. We're reconnecting; last sync was 09:42 UTC."   |
| Errors             | Cause, impact, recovery; never blame the user  | "We couldn't load the market feed. Retry, or use the 09:42 snapshot." |
| Security and legal | Sober, exact, no marketing rhythm              | "Data is isolated per workspace using Row-Level Security."            |
| Sales              | Specific, evidence-led, no artificial scarcity | "Here is the signal that would have changed last month's reorder."    |
| Social             | One observation, one implication               | "Search moved three weeks before stock did. That is the gap."         |

### 3.3 Messaging hierarchy

Use the highest level that fits the surface. Do not stack every level on one
page.

**1. Descriptor (always-on)**

> AI Business Operating System

Used in metadata, navigation context, footer, decks, and the first mention of
the company. It explains the category; it is not a campaign line.

**2. Brand idea (internal)**

> The whole picture, in time.

Used to judge work, not usually printed. It can appear in manifestos or
recruitment copy when the context explains it.

**3. Campaign line (external, time-bound)**

> Make tomorrow's calls on today's signals.

The current homepage and launch line. It is not a substitute for the descriptor
in legal, investor, or documentation contexts.

**4. One-liner**

> Skyrict connects your live operations to continuous market signals, so AI
> agents can return the next move with the evidence behind it.

**5. Short boilerplate (approx. 25 words)**

> Skyrict is an AI business operating system that connects live operations to
> market signals, so teams can act before a shift reaches stock or cash.

**6. Standard boilerplate (approx. 50 words)**

> Skyrict is an AI business operating system for growing, multi-market
> businesses. It connects live operations — inventory, orders, sales, cash, and
> payroll — to continuous market signals. AI agents read both, explain the
> evidence, and return the next move. One platform, one data plane.

**7. Full boilerplate (approx. 100 words)**

> Skyrict is an AI business operating system for growing, multi-market
> businesses. It connects live operations — inventory, orders, sales, cash, and
> payroll — to continuous market signals from search, video, community, code,
> and news. AI agents read both, explain the evidence, and return the next
> move. The platform combines ERP, Agents, and the Global Market Intelligence
> Engine on one data plane, with multi-tenant isolation, role-based access, and
> a provider-agnostic LLM layer. The source is open under Apache 2.0, so the
> claims can be checked in the code.

### 3.4 Pillar messages

| Pillar           | One-line promise                    | Proof to pair with it                                                        |
| ---------------- | ----------------------------------- | ---------------------------------------------------------------------------- |
| **ERP**          | Your operations, live.              | Inventory, orders, sales, cash, payroll, CRM, and approvals in one workspace |
| **Agents**       | Agents that explain themselves.     | Every recommendation carries signals, confidence, and a reasoning trail      |
| **Intelligence** | The market, read continuously.      | Five public sources; a shift surfaces the week it happens                    |
| **Platform**     | One data plane, not three products. | Shared tenancy, RLS, roles, MFA, and a single event-driven core              |

### 3.5 Proof points

Use these instead of adjectives. Keep the numbers current; if a claim changes,
change the copy in the same PR.

- Three pillars, one data plane: ERP, Agents, and GMIE.
- Five market signal sources: Google Trends, YouTube, Reddit, GitHub, and news
  APIs.
- Multi-tenant core with Row-Level Security.
- Owner, admin, and member roles.
- TOTP multi-factor authentication and one-time backup codes.
- Provider-agnostic LLM layer.
- Apache 2.0 source code, publicly inspectable.
- GMIE is in progress. Say so.

### 3.6 Vocabulary

| Prefer                 | Avoid                      | Reason                                                    |
| ---------------------- | -------------------------- | --------------------------------------------------------- |
| signal                 | insight, data point        | "Signal" implies movement and a decision window           |
| operations             | backend, plumbing          | Speak the operator's language                             |
| decision / next move   | actionable insight         | Name the outcome, not the deliverable                     |
| agent                  | AI assistant, copilot, bot | One category word; "copilot" implies a different product  |
| evidence / reasoning   | explainability, magic      | Describe what the user can inspect                        |
| live                   | real-time                  | "Real-time" is a latency claim; use it only when true     |
| connected source       | integration, connector     | Says what it does in plain language                       |
| workspace              | tenant, account (in UI)    | "Tenant" is architecture; "workspace" is the user's space |
| market intelligence    | market research            | Intelligence is continuous; research is a project         |
| open source            | open-source (as a noun)    | Hyphenate only as an adjective: "open-source platform"    |
| multi-tenant           | multitenant                | House style                                               |
| set up / log in (verb) | setup / login (verb)       | Nouns are "setup" and "login"                             |

**Banned in customer-facing copy:** revolutionize, unleash, supercharge,
seamless, effortless, cutting-edge, game-changing, 10x, transform, empower,
disrupt, AI-powered, magic, sentient, autonomous (unless the workflow truly is),
and "we're thrilled/excited to announce."

**Avoid anthropomorphism.** Agents do not think, want, feel, or decide. They
read, correlate, propose, flag, return, and wait for approval. This is a trust
issue, not a style preference.

### 3.7 Grammar and mechanics

- **Headlines:** sentence case. `Agents that explain themselves.` Not `Agents
That Explain Themselves.`
- **Eyebrows:** uppercase mono labels are the only all-caps text. Keep them to
  four words or fewer.
- **CTAs:** verb + object. `Create workspace`, `Start free`, `Book a demo`,
  `View the evidence`. Never `Submit`, `Learn more` alone, or `Click here`.
- **Contractions:** yes in marketing, product, and support. No in legal,
  security, and formal error disclosures.
- **Oxford comma:** yes.
- **Dashes:** use an em dash for an aside, sparingly. If a sentence needs two
  dashes, rewrite it. Use an en dash for ranges (`2–5 days`).
- **Numbers:** spell out one to nine in prose; use numerals for 10 and above,
  and for every metric, currency amount, percentage, or unit. In UI, use compact
  numerals (`$9.4K`, `+18% w/w`). In prose, use exact values (`$9,400`, "18%
  week over week").
- **Percentages:** no space before the sign. Use "percentage points" for a
  difference between percentages.
- **Currency:** symbol plus amount in product and marketing (`$9,400`). Use the
  ISO code on first mention in finance or cross-border contexts (`USD 9,400`).
- **Dates:** `22 October 2026` in product and docs; `October 22, 2026` in
  US-facing marketing. Pick one per surface and stay consistent.
- **Times:** 24-hour clock with a zone in product (`09:42 UTC`). Include the
  zone in marketing whenever freshness is the point.
- **Ranges:** `5–7 days`, not `5-7 days`.
- **Links:** descriptive text, never "here". `Read the security guide`.
- **Exclamation marks:** none in product or docs. Rare in marketing, and never
  in error states.
- **Apostrophes:** use curly apostrophes in prose where the publishing pipeline
  supports them; code and identifiers stay straight.

### 3.8 Copy patterns

**Headline formula**

> Verb + object + time or condition

Examples: `Make tomorrow's calls on today's signals.` `Your operations, live.`
`The market, read continuously.` `Agents that explain themselves.`

**Subhead formula**

> What it does + why it matters, in one or two sentences, under 30 words.

**Error message**

> What failed + why (if known) + what to do next. No "Oops".

**Empty state**

> What is missing + the one action that fixes it.

**Release note**

> What changed + who benefits + how to use it. No announcement throat-clearing.

**Social post**

> One observation + one implication. Link only if the reader needs the detail.

### 3.9 Before and after

| Before                                                                                                         | After                                                                                                      |
| -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| "Skyrict revolutionizes business operations with cutting-edge AI that seamlessly unlocks actionable insights." | "Skyrict connects your live operations to market signals. Agents return the next move, with the evidence." |
| "Oops! Something went wrong."                                                                                  | "We couldn't load the market feed. Google Trends didn't respond. Retry, or use the 09:42 snapshot."        |
| "No data available."                                                                                           | "No signals yet. Connect a source to start reading the market."                                            |
| "Get started today and unlock the power of AI!"                                                                | "Create workspace"                                                                                         |
| "We're thrilled to announce our new Guardian capabilities!"                                                    | "Guardian now flags stock cover below lead time, with the signal that moved."                              |
| "Our AI-powered platform empowers teams to make data-driven decisions."                                        | "Operations and market signals share one data plane, so the decision does not wait for an export."         |

---

## 4. Visual identity

### 4.1 Logo system

**Concept.** Four ascending bars rise to a signal point inside a rounded tile.
The bars read as a chart, a staircase, and a horizon. The dot is the signal you
act on. The tile is the sky; the dot is the decision.

The mark is geometric and quiet. It should feel measured, not playful. It is
never a mascot, never three-dimensional, and never animated beyond a simple
fade or draw-on.

#### Variants

| Variant               | Use                                                            |
| --------------------- | -------------------------------------------------------------- |
| **Horizontal lockup** | Default website header, footer, decks, email signature         |
| **Stacked lockup**    | Square or narrow formats, event panels, merchandise            |
| **Mark only**         | Favicon, app icon, social avatar, small product chrome         |
| **Wordmark only**     | Only when the mark is already visible nearby; never standalone |

The wordmark is **Bricolage Grotesque Semibold**, `tracking-tight`, sentence
case. Never reset it in another typeface, never add a tagline inside the lockup,
and never re-colour the wordmark independently of the mark.

#### Module tones

| Tone  | Gradient            | Ink       | Use                                            |
| ----- | ------------------- | --------- | ---------------------------------------------- |
| `sky` | `#aedef1 → #4cb6e1` | `#0a2f3e` | Default: corporate, marketing, workspace, docs |
| `erp` | `#6ee7b7 → #34d399` | `#04211a` | ERP shell and ERP navigation only              |
| `ai`  | `#c7d2fe → #6366f1` | `#1e1b4b` | Agents shell and agent-specific surfaces only  |

**The corporate signature is always Sky.** ERP and AI tones are product
wayfinding, not brand identities. Never use a module tone in the website
header, social avatar, invoices, email signatures, or sales decks. Intelligence
uses the Sky mark with the Intelligence UI accent (`#38bdf8`).

#### Clear space

Keep **half the mark height** clear on every side. For a 32px mark, that is
16px. For a horizontal lockup, measure from the outer edge of the whole unit.
Nothing enters that space: no text, no border, no image edge, no other logo.

#### Minimum sizes

| Asset             | Digital | Print |
| ----------------- | ------- | ----- |
| Mark only         | 16px    | 8mm   |
| Horizontal lockup | 96px    | 28mm  |
| Stacked lockup    | 72px    | 22mm  |

Below 24px, test the mark against the actual background. The four bars and dot
must remain distinct. If they blur, use a larger size or the mono version.

#### Placement

- Top-left in headers and documents, unless the format has a strong existing
  grid.
- Centred only in square or ceremonial formats (event slide, certificate,
  avatar).
- On photography, place the mark on a calm, solid area or a Deep scrim. Never
  on a busy focal point.
- Keep at least one mark-height of separation from navigation and page edges.

#### Misuse

Do not:

- rotate, skew, stretch, crop, or outline the mark;
- recolour the gradient, swap the ink, or apply a drop shadow, glow, or bevel;
- rearrange, add, or remove bars, or move the dot;
- set the wordmark in another typeface, weight, or case;
- add a tagline or URL inside the lockup, or place a trademark symbol inside the
  mark itself (follow [`TRADEMARK.md`](../../TRADEMARK.md) for legal placement);
- place the logo on a low-contrast or busy background;
- use the ERP or AI tone as the corporate signature;
- recreate the mark from memory or trace a screenshot.

### 4.2 Colour

The palette is a sky seen from an operations desk: pale paper, deep ink, and one
optimistic blue that marks what is live or actionable.

#### Brand palette

| Name        | Hex       | Role                                               |
| ----------- | --------- | -------------------------------------------------- |
| **Sky**     | `#87ceeb` | Brand accent, primary action, live/active signal   |
| **Horizon** | `#4cb6e1` | Gradient end, pressed state, secondary data series |
| **Mist**    | `#aedef1` | Tints, illustration, quiet fills                   |
| **Deep**    | `#0a2f3e` | Primary ink, dark panels, the campaign surface     |
| **Paper**   | `#f4fafd` | Default canvas                                     |
| **Cloud**   | `#e6f5fa` | Secondary surface, quiet cards                     |
| **Slate**   | `#176a8b` | Secondary text, metadata                           |
| **Line**    | `#cae9f6` | Default 1px border                                 |

#### Status palette

| Name     | Light     | Dark      | Use                                      |
| -------- | --------- | --------- | ---------------------------------------- |
| Positive | `#047857` | `#34d399` | Healthy, paid, completed, positive delta |
| Caution  | `#b45309` | `#fbbf24` | Attention, degraded, pending             |
| Stop     | `#dc2626` | `#f87171` | Errors, destructive actions              |
| Notice   | `#0369a1` | `#38bdf8` | Neutral notices, tips                    |

Status colour is never decorative and never the only carrier of meaning. Pair
it with a label, icon, or pattern.

#### Module accents

| World        | Light     | Dark      | Application                      |
| ------------ | --------- | --------- | -------------------------------- |
| ERP          | `#86efac` | `#55cf96` | ERP shell and navigation         |
| Agents       | `#a5b4fc` | `#8b93f8` | Agent conversations and runs     |
| Intelligence | `#38bdf8` | `#55c2ee` | Market and intelligence surfaces |

Module accents tint the UI; they do not replace the Sky brand accent in
marketing.

#### Dark surfaces

| Name   | Hex       | Role                   |
| ------ | --------- | ---------------------- |
| Night  | `#0b1119` | Dark canvas            |
| Panel  | `#111a24` | Cards and panels       |
| Raised | `#15202c` | Popovers and menus     |
| Ink    | `#e6edf5` | Primary text on dark   |
| Muted  | `#8fa3b8` | Secondary text on dark |

#### Usage ratio

Aim for **60 / 30 / 10** on any surface:

- **60%** Paper, white, or Night/Panel neutrals.
- **30%** Deep, Cloud, Mist, and borders.
- **10%** Sky, Horizon, and status or module accents combined.

Primary blue marks action and signal. It is not a background for body copy, not
a decorative section fill, and never the only thing distinguishing one element
from another.

#### Gradients

Only one gradient is approved: the **sky gradient**, `#aedef1 → #4cb6e1` at
135°, used in the mark and in small accents. Do not gradient text, large
backgrounds, buttons, or charts. Do not build "AI purple" gradients.

#### Contrast

Measured pairs from the current theme:

| Pair                      | Ratio | Result   |
| ------------------------- | ----- | -------- |
| Deep on Paper             | 13.39 | AAA body |
| Slate on Paper            | 5.74  | AA body  |
| Deep on Sky               | 8.10  | AAA body |
| Primary ink on Sky button | 9.76  | AAA body |
| Secondary ink on Cloud    | 10.15 | AAA body |
| Ink on Night              | 16.06 | AAA body |
| Muted on Night            | 7.31  | AAA body |
| Sky on Deep               | 8.10  | AAA body |
| Positive on white         | 5.48  | AA body  |
| Caution on white          | 5.02  | AA body  |
| Stop on white             | 4.83  | AA body  |
| Notice on white           | 5.93  | AA body  |

Minimums: **4.5:1** for body text, **3:1** for large text (24px+ or 19px bold)
and UI boundaries. Sky on Paper is a tint, not text. If you need Sky-coloured
words, use Slate or a darker step.

### 4.3 Typography

Three families, each with a job. Do not add a fourth.

| Role    | Family                  | Weights       | Use                                               |
| ------- | ----------------------- | ------------- | ------------------------------------------------- |
| Display | **Bricolage Grotesque** | 600           | Headlines, wordmark, large numbers, module titles |
| Text    | **Inter**               | 400, 500, 600 | Body, UI labels, tables, buttons                  |
| Mono    | **JetBrains Mono**      | 400, 500      | Eyebrows, IDs, timestamps, tabular data, code     |

**Stacks**

```css
--font-display:
    "Bricolage Grotesque", "Inter", ui-sans-serif, system-ui, sans-serif;
--font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
```

#### Marketing scale

| Style         | Size / line-height    | Tracking   | Use                          |
| ------------- | --------------------- | ---------- | ---------------------------- |
| Display XL    | 36 / 1.15, 48 at `sm` | -0.025em   | Campaign hero, one per page  |
| Display L     | 30 / 1.2, 36 at `sm`  | -0.025em   | Section opener               |
| Display M     | 24 / 1.3              | -0.025em   | Subsection, card headline    |
| Title         | 18 / 1.4              | 0          | Card title, pricing plan     |
| Body L        | 16–18 / 1.6           | 0          | Hero subhead, lead paragraph |
| Body          | 15 / 1.75             | 0          | Default prose                |
| Small         | 12 / 1.4              | 0          | Captions, legal, metadata    |
| Mono overline | 11–12 / 1.4           | 0.15–0.2em | Uppercase section label      |

#### Product scale

| Style      | Size / line-height | Weight   | Use                      |
| ---------- | ------------------ | -------- | ------------------------ |
| Page title | 24 / 1.3           | 600      | Workspace page header    |
| Heading    | 18 / 1.4           | 600      | Panel and card headings  |
| Body       | 14 / 1.5           | 400      | Default UI text          |
| Small      | 12 / 1.4           | 400/500  | Metadata, table headers  |
| Data       | 12–14 / 1.4        | 500 mono | Numbers, IDs, timestamps |

#### Type rules

- Sentence case everywhere except mono eyebrows.
- Maximum three weights on one screen.
- Body measure: 45–75 characters. Display measure: 12–20 words.
- Never use Bricolage for body copy or long labels.
- Use `tabular-nums` for money, quantities, percentages, and timestamps.
- Do not letter-space body text. Tracking is for display and mono labels only.
- Do not centre paragraphs longer than two lines.
- Do not use underlines except for links and active tab indicators.

### 4.4 Layout and grid

- **Grid:** 12 columns, max width 1152px (`max-w-6xl`), 24px gutters.
- **Margins:** 24px (`px-6`) across breakpoints.
- **Spacing base:** Tailwind's 4px scale. Use 8px increments for layout; reserve
  4px for icon-to-label gaps.
- **Section rhythm:** 64–96px vertical on desktop, 48–64px on mobile.
- **Alignment:** left-align long content; centre only short hero or ceremonial
  blocks.
- **Density:** one primary action per surface. Secondary actions are outline or
  ghost.
- **Borders:** 1px, `--border` or `--border` at 60–70% opacity. Prefer a border
  plus one surface step over a shadow.
- **Radii:** 6px chips, 8px compact controls, 10px buttons and inputs, 14px
  cards and panels, 18px feature tiles, 26px pills. Never mix square and heavily
  rounded cards on the same surface.
- **Elevation:** surface and border carry depth. Shadows are reserved for
  floating surfaces (menus, dialogs, toasts) and one optional long, soft shadow
  behind a hero product visual. Never stack shadows.

### 4.5 Graphic language

**Signal lines.** The recurring graphic motif is a line moving from left to
right: four ascending bars, a sparkline, a feed row, a timestamp. It represents
movement and the window to act. Use it once per surface, not as wallpaper.

**Data as hero.** Show the product doing the work: a live table, a signal feed,
an agent recommendation with reasoning. Annotate the one number that matters.
Avoid abstract "data" imagery that could belong to any company.

**Mono metadata.** Small uppercase mono labels (`LIVE`, `MARKET LAYER`,
`09:42 UTC`) anchor the interface and make it feel instrumented. Keep them
factual: no fake coordinates or decorative code.

**Rules and ticks.** Thin rules, table dividers, and small tick marks are part
of the brand. They make dense information feel organised without adding colour.

**Iconography.** Use Lucide, library-default 2px stroke, at 16px by default,
14px in compact controls, 12px inline, and 20px in empty states, in
`currentColor`. Do not mix filled and outline sets. The AI orbit glyph is
reserved for agent identity and must not become a general-purpose icon.

**Imagery.** If people appear, show real operators in real working environments:
natural light, calm posture, screens in context, a cool desaturated grade with a
sky cast. Prefer screens and artefacts over staged portraits. Never use robot
hands, glowing brains, humanoid AI, handshakes, or generic isometric servers.

**Illustration.** Diagrammatic only: flows, nodes, timelines, layers, and
corridors, drawn with 1px lines and sky tints. No characters, no 3D blobs, no
gradient meshes.

### 4.6 Motion

Motion explains change; it does not perform energy. Use the design-system
tokens rather than inventing durations.

| Token    | Duration | Use                                  |
| -------- | -------- | ------------------------------------ |
| Fast     | 150ms    | Hover, press, small toggles          |
| Base     | 200ms    | Colour and background transitions    |
| Enter    | 380ms    | Popovers, pop-in, section reveal     |
| Standard | 700ms    | Staged hero or product choreography  |
| Ambient  | 1.6–2.8s | Shimmer, scan, pulse, thinking sheen |

- Easing: `cubic-bezier(0.22, 1, 0.36, 1)` for entrances; `ease` or
  `ease-in-out` for colour and ambient loops.
- Entrances: 8–12px rise plus fade. No bounce, elastic, or spin.
- Stagger: 60ms between siblings, maximum four items.
- Ambient motion is allowed only for a single loading or live indicator. No
  infinite decorative motion in dense data views.
- Do not parallax, auto-scroll, or animate numbers on every viewport entry.
- Honour `prefers-reduced-motion`: remove transforms and loops, keep opacity
  changes under 120ms.
- Do not animate focus rings or delay interactive feedback.

### 4.7 Accessibility in brand expression

- Body text meets 4.5:1; large text and UI boundaries meet 3:1.
- Never use colour alone for status. Pair with text, icon, or pattern.
- Focus ring: visible 2px ring using `--ring`, with a 2px offset, on every
  interactive element.
- Targets: aim for 44×44px on touch; compact 24–32px controls are desktop-only.
- Do not put text in images unless it is also available as text.
- Provide alt text that states the takeaway, not the file name.
- Caption video and provide a transcript for audio.
- Test every brand surface in light and dark mode before release.
- Motion and contrast rules apply to marketing, not only the product.

---

## 5. Applications

| Surface              | Specification                                                                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Website**          | Horizontal Sky lockup top-left. One Display XL per page. Paper canvas, Deep text, Sky for primary action. One gradient maximum.                     |
| **Open Graph**       | 1200×630. Paper background, mark top-left, one headline, one proof number, Deep footer strip with `skyrict.in`. No logo watermark.                  |
| **Product**          | Base Sky for workspace; module tone only inside its shell. Status tokens for state. No marketing gradients. One primary action.                     |
| **Docs**             | Mark only in the sidebar. No hero gradients. Mono labels for versions and timestamps. Code blocks use a quiet surface, not Deep.                    |
| **Social avatar**    | Mark on Paper or Deep, centred, with 20% padding. No wordmark. Test at 32px.                                                                        |
| **Social posts**     | One headline, one number or chart, one line of context. Use the mark small and once. Do not put the logo on every image.                            |
| **Decks**            | 16:9, Paper background, 48px margins. Title in Display M, body in Inter 18. One Sky accent rule per slide. Page number and "Skyrict" in the footer. |
| **Email**            | 600px max width. Text-first. Deep headline, one Sky button, plain-text fallback. No image-only messages.                                            |
| **Email signature**  | Name, role, Skyrict, `skyrict.in`, `sales@skyrict.in` where relevant. Horizontal Sky lockup at 120px wide. No quotes or badges.                     |
| **Video**            | 16:9. Deep lower-third with Paper text and mono labels. Burned-in captions. No whooshes or EDM stings.                                              |
| **Events / swag**    | Mark only. Approved colours. No gradient on embroidery or low-resolution print. Merchandise requires permission under the trademark policy.         |
| **Co-branding**      | Equal visual height, 1px divider, "Powered by Skyrict" lockup. Do not imply partnership or certification without written approval.                  |
| **Invoices / legal** | Deep ink on white, horizontal Sky lockup, mono reference numbers, no campaign lines or gradients.                                                   |

---

## 6. Governance

### 6.1 Ownership

| Area                     | Owner                                                   |
| ------------------------ | ------------------------------------------------------- |
| Brand strategy and voice | Design lead / brand owner                               |
| Visual tokens and UI     | Frontend lead, with design review                       |
| Logo and exported assets | Design lead                                             |
| Legal and trademark use  | Maintainers, under [`TRADEMARK.md`](../../TRADEMARK.md) |

### 6.2 Sources of truth

1. **UI colour, type, spacing, and components:** `globals.css` and
   `docs/design-system/README.md`.
2. **Digital logo rendering:** `apps/web/src/components/brand/logo.tsx`.
3. **Exported marks:** `docs/brand/assets/`.
4. **Strategy, voice, and application rules:** this document.

When two sources disagree, fix them in one pull request. Do not let a slide
template become a fifth source of truth.

### 6.3 Change process

1. Open an issue describing the change and the surface it affects.
2. Update the token or asset, this document, and the affected application.
3. Check light mode, dark mode, the active module world, and contrast.
4. Get review from design and one engineer.
5. Update the version and changelog below.

### 6.4 Asset naming

```
skyrict-[asset]-[variant]-[colour].[ext]
```

Examples: `skyrict-mark-mono.svg`, `skyrict-avatar-paper.svg`,
`skyrict-lockup-horizontal-sky.svg`. Use lowercase, hyphens, and no spaces.
Keep editable source files alongside exports.

### 6.5 Review checklist

- [ ] The name is written **Skyrict**, one word, correct case.
- [ ] The descriptor is **AI Business Operating System** where a category is
      needed.
- [ ] The copy leads with the decision, then the evidence.
- [ ] Every number has a unit and a time frame.
- [ ] No banned hype words and no anthropomorphised agents.
- [ ] The corporate mark is Sky; module tones appear only in product chrome.
- [ ] Clear space and minimum size are respected.
- [ ] Body contrast is at least 4.5:1 in light and dark mode.
- [ ] Status is not conveyed by colour alone.
- [ ] The surface has one primary action.
- [ ] Motion respects `prefers-reduced-motion`.
- [ ] Unfinished capabilities are labelled "in progress", not implied live.

### 6.6 Legal

The code is Apache 2.0. The name, logo, and brand assets are governed separately
by [`TRADEMARK.md`](../../TRADEMARK.md). Do not alter the mark, use it in a
product name, or imply endorsement. Forks must remove Skyrict branding.

---

## Appendix A. Copy card

Keep this open when writing.

```
NAME        Skyrict
DESCRIPTOR  AI Business Operating System
IDEA        The whole picture, in time.
CAMPAIGN    Make tomorrow's calls on today's signals.
ONE-LINER   Skyrict connects your live operations to continuous market
            signals, so AI agents can return the next move with the
            evidence behind it.

VOICE       Lead with the decision. Use units. Separate known from inferred.
            Write like an operator. Cut the pedestal.

NEVER       revolutionize, unleash, supercharge, seamless, effortless,
            cutting-edge, game-changing, 10x, transform, empower, disrupt,
            AI-powered, magic, sentient, autonomous, "we're thrilled"

CTA         Create workspace · Start free · Book a demo · View the evidence
```

## Appendix B. Asset index

| Asset                   | Path                                         | Use                             |
| ----------------------- | -------------------------------------------- | ------------------------------- |
| Primary mark            | `docs/assets/skyrict_logo.svg`               | Default digital mark            |
| Mono knockout (light)   | `docs/brand/assets/skyrict-mark-mono.svg`    | One-colour print on light stock |
| Reverse knockout (dark) | `docs/brand/assets/skyrict-mark-reverse.svg` | One-colour print on dark stock  |
| Glyph                   | `docs/brand/assets/skyrict-mark-glyph.svg`   | Inline/small spots without tile |
| Social avatar           | `docs/brand/assets/skyrict-avatar-paper.svg` | Profile images, 1:1             |

Digital lockups should be rendered from the `Logo` component so the wordmark
uses the live font. Export a static lockup only when a vendor requires an SVG or
PNG; outline the wordmark before export and keep the editable source.

## Appendix C. Changelog

| Version | Date            | Change                                                                                    |
| ------- | --------------- | ----------------------------------------------------------------------------------------- |
| 1.0     | 22 October 2026 | Initial brand identity system: strategy, voice, visual identity, applications, governance |
