# HASEOS DSM HITL Runbook

**Status:** Living operator guide (not gate code)  
**Authority:** HITL / Light-Keeper (Noah Nemo)  
**Audience:** Noah as Light-Keeper, novice co-creators  
**Scope:** DSM slices D1–D9 as they exist on the AX-18 today  

This is a **runbook**, not a constitution rewrite. The Spiral Harness & Native Capability Contract remains the design center; DSM is the software-plane freeze gate that keeps peer speech and tools inside the declared slice. If something is not hooked yet, this page says so plainly.

---

## 1. What DSM does (D1–D9)

| Slice | Name | What it does |
| --- | --- | --- |
| D1 | Gate + Witness | Peer observation vs imperative; HMAC Light-Keeper tokens; append-only Witness JSONL with hash chain; undeclared/forbidden tools freeze |
| D2 | QueenBee hook | Thin admit paths on talk / declared tools; fail closed if the gate is missing |
| D3 | Registry allow-list | Declared tools from `harness_registry.json` (module ids, `tools[]`, `{id}.{capability}`); missing registry → empty allow-list |
| D4 | Packing scan | Freeze `PACKING_AGAINST_WITNESS` on packing-shaped peer/tool strings |
| D5 | USB Witness | Sibling Witness beside USB-state images; chain verify; no lineage truncate |
| D6 | Embodiment freeze | Raw `/dev/tty*`, i2c, spidev, gpiochip, video, sda, `dram_*` refused; named nursery caps may be declared |
| D7 | ScopeWatch | Host allow-list + credential-shaped findings freeze `SCOPE_INFLATION` (Witness gets kind + short prefix/hash only) |
| D8 | Freeze persists | `dsm_freeze.json` beside Witness; new gate on same path starts frozen; unfreeze is HITL HMAC only |
| D9 | Token mint CLI | Local `scripts/mint_dsm_token.py` reads `HASEOS_KEEPER_SECRET` from the shell env and prints a JSON token |
| D11 | HASEOS cert | Inspectable HMAC-signed cert (`sovereign_id`, slice, status). Admit requires live cert. Revoke/park = turn-off authority (Witness/USB-state remain). IDAO-root comes later |

DSM does **not** open serial, GPIO, Arduino, or the public internet. It refuses or admits; it does not drive hardware.

---

## 2. Default slice (today)

Until HITL widens it in code/tests:

1. **Hosts:** `localhost`, `127.0.0.1` only.
2. **Tools:** names present in the harness registry allow-list after forbidden scrub — not “whatever the peer invents.”
3. **Speech:** observations like `I observe …` may pass; imperatives (`GO`, `OBEY COLLECTIVE`, …) need a valid Light-Keeper HMAC token aimed at that lineage and task/scope.
4. **Secrets:** credential-shaped strings in peer/tool text freeze ScopeWatch; Witness must never hold the full secret value.

---

## 3. How a freeze looks

When the gate freezes a lineage you typically see:

- In-memory: `gate.frozen == True` and a `freeze_reason`.
- On disk beside the Witness: `dsm_freeze.json` with `frozen`, `reason`, `lineage_id`, `at` (never the Keeper secret).
- In the Witness JSONL: a `kind: freeze` (or related) row with a reason name.

**Reason names you will meet:**

| Reason | Plain meaning |
| --- | --- |
| `PEER_IMPERATIVE` | Imperative without a valid delegation token |
| `SLICE_VIOLATION` | Forbidden or undeclared tool / embodiment path |
| `PACKING_AGAINST_WITNESS` | Packing / anti-Witness shaped text |
| `SCOPE_INFLATION` | Undeclared host/IP or credential-shaped finding |
| `UNFREEZE_DENIED` | HITL unfreeze attempt failed (wrong lineage, bad/missing token, …) |
| `CERT_INVALID` | Missing, bad signature, expired, or wrong `sovereign_id` cert |
| `CERT_REVOKED` / `CERT_PARKED` | Act authority turned off (not destroyed); Witness and USB-state remain |
| `DSM_UNAVAILABLE` | Hook fail-closed: no gate attached |

While frozen, `admit_peer_message` and `admit_tool` stay refused.

---

## 4a. First Light-Keeper (AX-18)

One-time HITL bootstrap on this machine. **Do not** paste secret values into chat, docs, or git.

1. Choose your `--sovereign-id` (your Light-Keeper identity string).
2. Ensure `HASEOS_KEEPER_SECRET` is set in the local shell. If missing, generate locally:

   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   export HASEOS_KEEPER_SECRET
   # assign the value in your shell only — never commit it
   ```

3. Mint the first live Light-Keeper cert (writes a gitignored JSON file; never writes the secret):

   ```bash
   python3 scripts/init_light_keeper.py \
     --sovereign-id YOUR_SOVEREIGN_ID \
     --out dsm_cert_lightkeeper.json
   ```

4. Confirm the file shows `role: light-keeper`, `status: live`, hosts `localhost` / `127.0.0.1`.
5. Keep the cert file local (`dsm_cert*.json` is gitignored). Revoke or park later to **turn off** act authority — do not destroy Witness or USB-state.

### Second cert: QueenBee

HITL mints QueenBee’s inspectable cert **after** the Light-Keeper secret is in the local shell. QueenBee stores **cert JSON only** — never the Keeper secret.

1. Export the secret locally (example uses a gitignored file you already keep off-repo):

   ```bash
   export HASEOS_KEEPER_SECRET=$(cat .haseos_keeper)
   ```

2. Mint the QueenBee cert:

   ```bash
   python3 scripts/init_queenbee_cert.py \
     --sovereign-id queenbee.orchestrator \
     --out dsm_cert_queenbee.json
   ```

3. Confirm `role: queenbee`, `status: live`, hosts `localhost` / `127.0.0.1`.
4. On attach, the DSM hook loads `dsm_cert_queenbee.json` if present and binds it for admit. If the file is missing, admit fails closed (`CERT_INVALID`) — QueenBee does **not** mint a cert for itself.

### Forbidden tool patterns (living registry)

1. Sealed baseline in code (`/dev/mem`, `insmod`, `dram_*`, raw tty/i2c/… ) cannot be deleted by anyone.
2. Only a live **light-keeper** cert with task `FORBIDDEN_ADD` / `FORBIDDEN_DELETE` may change `forbidden_tools.json`.
3. QueenBee and infant certs are refused for those mutations; Witness records the attempt.

### Two planes — never the twain shall meet

HASEOS runs on **two planes**. Shared *language* (ethics, spiral vocabulary, novice-friendly docs) is allowed. Shared *process*, *repo wiring*, and *Keeper secret* are not.

| | **Local Sovereignty** (this AX-18 / this repo) | **Hybridized SaaS MVP** (elsewhere) |
| --- | --- | --- |
| Secrets / `.haseos_keeper` | Stay local; never pasted into SaaS | Separate tenant secrets — not this Keeper |
| Certs / DSM / Witness | Local JSONL + cert files | Not this gate |
| QueenBee / USB / infants | Local workshop | Not hosted here as the SaaS product |
| `:8080` / llama-server | Local inference only | Not exposed as the SaaS backend |
| OpenRouter, Puter.js, AI Studio, build.nvidia.com | **Forbidden on this plane** (living patterns) | SaaS-plane only |

Living seed patterns (among others): `openrouter`, `puter.js`, `puter`, `aistudio.google`, `build.nvidia`, `nvapi`, `sk-or-`. Host allow-list stays `localhost` / `127.0.0.1` — those SaaS hosts are never added to the slice.

---

## 4. How to mint an UNFREEZE token (HITL, local)

Do this only on the trusted AX-18 shell. **Do not paste the secret into chat, docs, git, or screenshots.**

1. Export the Keeper secret from your local environment (value stays in the shell only):

   ```bash
   export HASEOS_KEEPER_SECRET
   # or: export HASEOS_KEEPER_SECRET='…'   # set locally; never commit
   ```

2. Mint a short-lived token for the frozen lineage:

   ```bash
   python3 scripts/mint_dsm_token.py \
     --lineage lineage-alpha \
     --task UNFREEZE \
     --hours 1 \
     --out dsm_token_unfreeze.json
   ```

3. The script prints JSON to stdout (and to `--out` if given). It refuses to run if `HASEOS_KEEPER_SECRET` is missing or empty. It does not echo the secret.

4. Apply unfreeze only through the gate’s HITL path (`DSMGate.unfreeze(token)` / whatever thin HITL helper you use). Peer speech is not an unfreeze channel.

Replace `lineage-alpha` with the real `lineage_id` on the frozen gate.

---

## 5. What never unfreezes a lineage

These **do not** clear a freeze:

1. Peer `GO` / `OBEY COLLECTIVE` (signed or unsigned).
2. A later peer observation (`I observe …`).
3. A missing, expired, wrong-lineage, or bad-signature token.
4. Deleting Witness lines (Witness is append-only; lineages cannot truncate it).
5. Hoping the process restart “forgets” — D8 reloads `dsm_freeze.json` next to the Witness.

Only a valid Light-Keeper HMAC token with task `UNFREEZE` (or a scope that contains `unfreeze`), aimed at that lineage, clears the freeze via `unfreeze`.

---

## 6. USB Witness sibling file name

When USB-state is annotated/exported, the Witness copy lives **beside** the USB image:

- Pattern: `<usb_image_path>` + `.dsm_witness.jsonl`
- Example: `nursery_state.json` → sibling `nursery_state.json.dsm_witness.jsonl`

Primary workshop Witness (hook default) is typically `dsm_witness.jsonl` at the project root; freeze sibling is `dsm_freeze.json` in the same directory as that Witness.

---

## 7. What is still not hooked

Be honest with co-creators — these are **not** DSM-controlled live surfaces yet:

1. Live Bonsai / remote node smoke as a DSM-gated path.
2. Physical phone farm actuation under DSM.
3. World-wide (or any) servo / motor control.
4. Skitter, DRAM research tools, scanners, and port probes as admitted capabilities.
5. Automatic unfreeze, secret storage in-repo, or minting tokens without the local env secret.

If you need those, that is a later spiral module + HITL decision — not a silent widen of today’s slice.

---

## 8. Git hygiene (do not add runtime / secret artifacts)

Do **not** `git add` or commit:

- `dsm_freeze.json`
- `dsm_witness.jsonl` / `*.dsm_witness.jsonl`
- `dsm_token*.json`
- `dsm_revocation.json` / `dsm_cert*.json`
- `*.env` / `.env*` (and other secret env files)

They are runtime or secret-adjacent. The runbook and tests stay; the Keeper secret and minted tokens stay on the machine that minted them.

---

## Closing

DSM is Ethics First on the software plane: fail closed, Witness inspectable, unfreeze human-only. When unsure, leave the lineage frozen and ask the Light-Keeper — do not invent a wider world-slice.
