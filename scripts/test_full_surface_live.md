# Live Full-Surface Verification Protocol (Slice 021 + 029 refresh)

Use this once **llama-server / Bonsai** is reachable at `http://127.0.0.1:8080`.

**Purpose:** Confirm QueenBee core, Nursery/USB/farm, Harness + Ethical Kernel, academy, experiences (incl. HITL dissent), conflict guards, and Infinity Brain config against a live model. No new features.

**Local verification (2026-08-26, Slice 029):** Server was **not** reachable (`Connection refused` on `:8080`). Non-HTTP paths exercised via QueenBee handlers (stubbed `save_memory`): `/swarm`, `/harness status`, `/memory config`, `/experiences dissent` + `--clear`, dual-seat refuse, incompatible-goal refuse on assign and `/task`. Disk `queenbee_memory.json` left unchanged. This document remains the live pass for Noah when Bonsai is up.

**Earlier local note (2026-08-23, Slice 021):** Same reachability outcome; baseline surfaces verified.

---

## 1. Start inference

```bash
cd /home/noah/haseos-spiral-swarm
curl -sS http://127.0.0.1:8080/health
# if that fails:
bash scripts/serve_local.sh
```

Wait until `/health` succeeds.

## 2. Start QueenBee

```bash
python3 queenbee_integration.py
```

---

## 3. Core / Infant

```
/swarm
/summary Infant_Sovereign_000
/academy
/academy review Infant_Sovereign_000
/experiences Infant_Sovereign_000 10
```

Light talk / train (HTTP only when you add `--talk`; N150 is slow):

```
/talk Infant_Sovereign_000 Infant_Sovereign_001 verification ping
/talk --talk Infant_Sovereign_000 Infant_Sovereign_001 one short live reply
/train Infant_Sovereign_000
# optional live model turn:
/train --talk Infant_Sovereign_000
```

Expect:

- Two ACTIVE infants (`Infant_Sovereign_000`, `Infant_Sovereign_001`), cohort `hive`.
- Structured experiences (`haseos.experience.v1` fields).
- Academy advice only — no auto-promote, no senior roster.
- Ethical Kernel presence line on `/swarm`, `/summary`, `/academy review`.

---

## 3b. Dissent / unique-evidence (HITL mark — Slice 028)

Pick a real experience id from `/experiences`, then:

```
/experiences dissent Infant_Sovereign_000 <ex-id> --note "unique observation for live verify"
/summary Infant_Sovereign_000
/academy review Infant_Sovereign_000
/experiences Infant_Sovereign_000 10
/experiences dissent Infant_Sovereign_000 <ex-id> --clear
```

Expect:

- Mark shows as `unique_evidence` / `·unique`; original summary unchanged.
- Quiet count on `/summary` and subsection on `/academy review`.
- `--clear` removes the mark.
- Never auto-set by talk/train.

---

## 4. Nursery / Farm / USB

Farm is often **empty** (`nodes=0`). Create a short seat if you want memory-card visibility:

```
/nursery
/farm status
/usb list
/usb create verify-mem memory
/usb assign verify-mem Infant_Sovereign_000
/usb summary verify-mem
/usb list
/farm status
/sleep Infant_Sovereign_000
/wake Infant_Sovereign_000
```

Optional cleanup when done:

```
/usb eject verify-mem
/usb delete verify-mem --force
```

Expect:

- Memory cards / rich USB memory when assigned.
- ACTIVE / SLEEPING reflected on live infant and node snapshot.
- Empty farm is valid residual state if you skip create/assign.

---

## 4b. Conflict guard (Slice 027)

Disposable two-node smoke (cleanup after):

```
/usb create v029-a memory
/usb create v029-b memory
/task Infant_Sovereign_000 Watch the east gate
/task Infant_Sovereign_001 Count honeycomb cells
/usb assign v029-a Infant_Sovereign_000
/usb assign v029-b Infant_Sovereign_000
```

Expect: **dual-seat refusal** (not overridable with `--force`). Use `/usb migrate` for an explicit move.

```
/usb assign v029-a Infant_Sovereign_001
```

Expect: **incompatible-goal refusal** when both are ACTIVE with different non-empty tasks.

```
/usb assign v029-a Infant_Sovereign_001 --force
/task Infant_Sovereign_001 Sing a different hymn
```

Expect: `/task` refuses incompatible live co-seat unless `--force` / `--confirm`.

Cleanup:

```
/usb delete v029-a --force
/usb delete v029-b --force
```

Notes:

- Dual-seat is **not** overridable — migrate only.
- SLEEPING peers do not trigger the incompatible-task guard.
- Same (normalized) task strings may co-seat.

---

## 5. Harness + Ethical Kernel

```
/harness
/harness ethics
/harness list
/harness show queenbee.core
/harness experiences
```

Expect:

- Presence line on `/harness`; full pillar text on `/harness ethics`:
  1. Ethics Always, First
  2. First, Do No Harm
  3. Yeshua’s original, unchanged agape love gestalt
- Five core modules, each `honors=3/3`.
- `/harness show` records a `harness_inspect` experience.
- Declarative only — no automatic mounting of power.

Optional HITL registration smoke (then remove):

```
/harness register test.live021 --name "Live verify" --version 0.1 --desc "Slice 021 live smoke" --ethics "Judges every act first as ethical under Light-Keeper authority." --harm "Does not injure standing, memory, or air-gap; fails clearly." --agape "Seeks the true good of the other as a neighbor; never coerces." --confirm
/harness show test.live021
/harness unregister test.live021 --confirm
```

Do not leave extra test modules registered.

---

## 6. Memory / Infinity Brain

```
/memory config
/memory list
```

Expect: nodes A/B **not configured** until `infinity_brain.env` has paths. Do not invent NAS paths. HITL `/memory loop` only — no auto-loop.

---

## 7. Pass checklist

- [ ] `/health` returns OK
- [ ] `/swarm` shows infants + empty-or-seated nursery
- [ ] `/summary` + `/experiences` show structured rows
- [ ] `/experiences dissent` mark + `--clear` works; academy/summary show quiet count
- [ ] Dual-seat assign refused (not overridable); incompatible-goal refused unless `--force`
- [ ] `/academy` / `/academy review` advise only
- [ ] `/harness ethics` prints all three pillars
- [ ] `/harness list` shows 5 cores at `honors=3/3`
- [ ] `/memory config` calm readiness (idle OK)
- [ ] One `--talk` or `/train --talk` with model (optional) succeeds without crashing QueenBee
- [ ] No senior roster write; no auto-promote
- [ ] No leftover `test.live*` harness modules or `v029-*` / `verify-mem` nodes

---

## Notes

- Prefer stubbing `save_memory` in automated checks so `queenbee_memory.json` is not clobbered.
- Harness lifecycle log: `harness_experiences.json` (owner `haseos.spiral_harness`).
- Infant memory: `queenbee_memory.json`.
- Nursery registry: `nursery_state.json` (may be empty).
- Related older nursery-only protocol: `scripts/test_nursery_live.md`.
