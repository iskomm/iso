# Recon map: ProtoFlow (desktop: Windows, macOS, Linux)

Scope: AI-assisted schematic capture: plain-English prompt to editable
schematic, real parts, ERC, KiCad export. PCB layout, routing, simulation and
manufacturing output are mapped below but left as `could`.
For: a niche (still to choose, see "Open questions")
Date: 2026-10-30

> **Read this first: first-pass recon from search results only.** This
> session's network policy blocked `www.protoflow.ai` and `moge.ai`, so no
> page was opened directly. Everything below comes from search-engine
> summaries of the vendor's pages and from third-party listings. No
> screenshots were taken and no account was used. Screens and click counts
> are inferred from feature descriptions and marked as guesses. Re-run
> `/replica-recon` once the hosts are allowed, or once you can click through
> your own account, to confirm.

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | official product page | https://www.protoflow.ai/protoflow | full feature list (via search summary) |
| 2 | marketing site | https://www.protoflow.ai/ | free plan: "no card, no expiry", full editor and AI |
| 3 | pricing page | https://www.protoflow.ai/pricing | Pro: 50 AI credits/day, 250/rolling week; page may be stale |
| 4 | download page | https://www.protoflow.ai/download | free on all three OSes |
| 5 | docs: getting started | https://www.protoflow.ai/docs/getting-started | Win 10+, macOS 12+ (Apple Silicon and Intel), Ubuntu 20.04+ x64/ARM64; exe, dmg, AppImage/tar.gz |
| 6 | persona page | https://www.protoflow.ai/for/hardware-engineers | end-to-end workflow pitch |
| 7 | vendor blog | https://www.protoflow.ai/blog/schematic-capture-vs-layout-vs-routing | says it focuses on capture and feeds external autorouters (Quilter, DeepPCB) |
| 8 | vendor blog | https://www.protoflow.ai/blog/ai-pcb-design-2026-guide | warns connectivity hallucination is real, so ERC/DRC and a datasheet check are mandatory |
| 9 | vendor blog | https://www.protoflow.ai/blog/ai-circuit-board-design | prompt-to-fabricated-PCB flow |
| 10 | vendor comparisons | https://www.protoflow.ai/compare/easyeda-alternative , https://www.protoflow.ai/compare/kicad-alternative , https://www.protoflow.ai/compare/free-ai-pcb-design-tools | symbol and footprint editors, parts search, interop claims |
| 11 | directory listing | https://moge.ai/product/protoflow | independent one-paragraph description |
| 12 | competitor page | https://www.trycherryblossom.com/blog/protoflow-alternative | free AI limits 5 Basic + 10 Pro messages/day, 10 part-generator units/month; Pro $19.99/mo with 7-day trial. A competitor wrote this |
| 13 | Product Hunt | https://www.producthunt.com/products/protoflow-2/launches | maker: footprints follow IPC-7351B; a user praises the KiCad export |
| 14 | third-party tutorial | https://pcbcool.com/technical-guides/protoflow-pcb-design-tutorial/ | one-prompt walkthrough, not read |
| 15 | listings | https://sourceforge.net/software/product/ProtoFlow/ , https://slashdot.org/software/p/ProtoFlow/ | no user reviews yet |

Not used: the user's own account (none; check ProtoFlow's terms for a
"no competing products" clause before using one), walkthrough videos (none
found), changelog (not found), public API docs (none found).

## Core loop

Describe a circuit in plain English and get an editable schematic built from
real, orderable parts that passes an electrical rules check.

## Screens

All screens are inferred from feature descriptions. None have been seen.

| ID | screen | route / how to reach | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Sign in / account | first launch (guess: plans need an account) | identify the user and plan | form, OAuth buttons | none seen |
| S02 | Project home | after sign-in (guess) | open, create, import projects | project list, new-project button, import button | none seen |
| S03 | AI chat panel | inside the editor (guess: side panel) | prompt to schematic, iterate | chat thread, prompt box, file upload, model picker (Basic/Pro) | none seen |
| S04 | Schematic editor | open a project | edit the circuit | canvas, toolbar, property inspector, sheet tabs (guess) | none seen |
| S05 | Part search | from S04 | find and import real parts | search box, distributor filter (LCSC/DigiKey/Mouser), results table, part detail | none seen |
| S06 | Symbol editor | from a part or S05 | create or fix a symbol | canvas, pin table | none seen |
| S07 | Footprint editor | from a part or S05 | create or fix a footprint (IPC-7351B) | canvas, pad table, generator form | none seen |
| S08 | ERC results | run ERC from S04 | list electrical violations | violations list, jump-to-location | none seen |
| S09 | Simulation | from S04 | ngspice: op, transient, AC, DC sweep | analysis setup form, waveform plot | none seen |
| S10 | PCB editor | from S04 ("update PCB", guess) | board layout | canvas, layer panel, stackup manager, copper pour tool | none seen |
| S11 | Auto-router | from S10 | route the board | preset picker, layer filters, completion summary | none seen |
| S12 | DRC results | run DRC from S10 | list layout violations | violations list | none seen |
| S13 | 3D view | from S10 | inspect the assembled board | 3D viewport | none seen |
| S14 | Manufacturing export | from S10 | Gerber X2, Excellon, JLCPCB BOM and CPL | export dialog, file checklist | none seen |
| S15 | Interop import/export | from S02 or the file menu | KiCad, Altium, EAGLE | format picker, file dialog | none seen |
| S16 | Plan and AI usage | settings or limit prompt (guess) | show credits, upgrade | usage meter, plan cards | none seen |
| S17 | Settings | app menu (guess) | API keys, units, theme | form | none seen |

## Flows

Click counts were not measured because no account was available.

```
F01 Prompt to editable schematic (the core loop)
    S02 new project -> S03 describe circuit -> S04 review schematic -> S08 run ERC -> S04 fix
    happy path clicks: not measured
    edge: ambiguous prompt, part not in stock, AI wires a pin wrong (vendor says this happens),
          AI limit reached mid-generation (-> S16), offline

F02 Find and place a real part
    S04 -> S05 search -> pick part -> S04 place
    edge: part has no symbol or footprint (-> S06/S07), distributor API down, same MPN in two catalogues

F03 Hand off to KiCad
    S04 -> S15 export KiCad -> open in KiCad
    edge: custom footprints, multi-sheet designs, KiCad version differences

F04 Simulate a circuit                               (could)
    S04 -> S09 pick analysis -> run -> read plot
    edge: part has no SPICE model, simulation fails to converge

F05 Schematic to routed board                        (could)
    S04 -> S10 place -> S11 auto-route -> S12 DRC -> S13 3D check

F06 Order boards from JLCPCB                         (could)
    S12 clean -> S14 export Gerber, drill, BOM, CPL -> upload to the fab yourself

F07 Hit the AI limit
    S03 -> limit message -> S16 upgrade or wait for the daily reset
```

## Components

Inferred. replica-design will confirm these against screenshots.

| component | variants | states | used on |
| --- | --- | --- | --- |
| Editor canvas | schematic, PCB, symbol, footprint | empty, filled, selection, dragging, read-only during AI generation (guess) | S04, S06, S07, S10 |
| Toolbar | editor tools, view controls | default, active tool, disabled | S04, S06, S07, S10 |
| Property inspector | component, net, pad, layer | empty, single select, multi select | S04, S10 |
| Chat thread | user message, AI message, generation progress, error | streaming, done, failed, limit reached | S03 |
| Prompt box | with attachment, model picker | empty, typing, sending, disabled | S03 |
| Parts results table | per distributor | loading, results, no results, API error | S05 |
| Violations list | ERC, DRC | clean, warnings, errors | S08, S12 |
| Layer panel | copper, silk, mask, paste, outline | visible, hidden, active | S10, S13 |
| Waveform plot | transient, AC (Bode), DC sweep | empty, running, result, failed | S09 |
| 3D viewport | none | loading, ready | S13 |
| Export dialog | manufacturing, interop | ready, exporting, done, error | S14, S15 |
| Usage meter | daily, weekly | normal, near limit, at limit | S03, S16 |
| Modal, toast, button, input, select | standard | standard | all |

## Inferred data model

```
User          id, email, plan (free | pro), created_at
              evidence: pricing page tiers   confidence: medium

UsageQuota    user_id, day_count, week_count, resets_at, part_generator_count
              evidence: "50 credits/day, 250/rolling week", competitor page   confidence: medium

Project       id, owner_id, name, created_at, updated_at, source_format (native | kicad | eagle)
              evidence: KiCad/EAGLE import   confidence: guess

Sheet         id, project_id, name, order
              evidence: none (standard EDA)   confidence: guess

Part          id, mpn, manufacturer, distributor (lcsc | digikey | mouser), distributor_sku,
              datasheet_url, description, symbol_id, footprint_id, spice_model (nullable)
              evidence: parts search, "real parts", ngspice   confidence: high

Symbol        id, name, pins [number, name, electrical_type], graphics
              evidence: symbol editor   confidence: medium

Footprint     id, name, pads [number, shape, size, position, layers], courtyard, standard (IPC-7351B)
              evidence: footprint editor, maker comment   confidence: medium

ComponentInstance  id, sheet_id, part_id, refdes, value, position, rotation, pcb_position, pcb_layer
              evidence: standard EDA   confidence: high

Net           id, project_id, name, connections [component_instance_id, pin_number]
              evidence: ERC, connectivity warning   confidence: high

Board         id, project_id, outline, stackup [layer name, type, thickness], design_rules
              evidence: stackup manager, DRC   confidence: medium

Track / Via / Pour  id, board_id, net_id, layer(s), geometry
              evidence: auto-router, copper pours   confidence: medium

Violation     id, project_id, kind (erc | drc), severity, message, location
              evidence: ERC/DRC   confidence: high

SimulationRun id, project_id, analysis (op | tran | ac | dc), params, results
              evidence: ngspice analyses   confidence: medium

Conversation / Message  id, project_id, role, content, attachments, model (basic | pro)
              evidence: AI chat, uploads, model tiers   confidence: medium
```

Relationships: User 1-n Project, Project 1-n Sheet, Sheet 1-n
ComponentInstance, Part 1-n ComponentInstance, Part n-1 Symbol, Part n-1
Footprint, Project 1-n Net, Net n-n ComponentInstance pins, Project 1-1 Board,
Board 1-n Track/Via/Pour, Project 1-n Violation, Project 1-n SimulationRun,
Project 1-n Conversation.

## Feature matrix

See `features.csv`. Must: 10, should: 7, could: 13, skip: 4.

## Out of scope (cannot or should not be cloned)

- **Distributor catalogues.** LCSC, DigiKey and Mouser own their part data and
  prices. Use their official APIs with the user's own keys, under their
  terms, and don't store or redistribute bulk data.
- **ProtoFlow's library content.** Their symbols, footprints and SPICE models
  are theirs. Generate footprints with your own IPC-7351B code and use
  manufacturer or open libraries with compatible licences.
- **The JLCPCB relationship.** Writing JLCPCB's public BOM/CPL format is
  fine. Any partner deal is not a feature you can rebuild.
- **Their AI pipeline.** Prompts, fine-tunes and models aren't visible. Build
  your own generation step with your own model provider.
- **Brand.** Name, logo, site copy and comparison pages. replica-brand handles this.

Open-source pieces the clone *can* use directly: ngspice (simulation) and the
KiCad file formats (documented). Check the Altium and EAGLE formats' terms
before building converters.

## Size

Screens 17, flows 7, entities 13. Hard parts:

1. **Correct AI connectivity.** The vendor itself warns the AI can wire pins
   wrong. You need a pipeline that grounds every pin in a real datasheet and
   symbol, plus ERC as a hard gate.
2. **The editor canvas.** A fast, correct schematic editor (selection, wiring,
   undo, net connectivity) is a large build by itself. The PCB editor and
   auto-router are larger still.
3. **Parts and footprints.** Three distributor APIs plus footprint generation
   to IPC-7351B, with symbols and footprints that agree pin for pin.

Also hard: KiCad export fidelity, desktop packaging for three OSes, ngspice
integration.

Size: the **full product is XL. Rescope it.** The recommended slice
(prompt to schematic, parts, ERC, KiCad export, free plan with an AI limit)
is **L**: a quarter, if you skip the PCB editor and let KiCad handle layout.
That matches the original's own claim that it focuses on capture.

## Open questions

- **Which niche?** You chose "a niche" but not which one. A narrow niche
  shrinks this a lot: for example, a fixed parts library for one domain
  (Arduino/ESP32 shields, audio, repair and retrofit boards for electronics
  service shops), or one board class (2-layer, through-hole, hobby).
- **Desktop or web?** The original is a desktop app. A web app is faster to
  ship and update. replica-architect should decide this.
- **Verify the details.** The prices, AI limits and screen layout all need a
  direct look at protoflow.ai, or at the app itself, before replica-design starts.
