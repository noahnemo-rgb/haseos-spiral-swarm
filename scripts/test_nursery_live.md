# Live Nursery End-to-End Test Protocol

Use this once **llama-server / Bonsai** is up at `http://127.0.0.1:8080`.

The Software Nursery commands themselves do not need the model. This protocol also
touches one inference-backed command so we know QueenBee and Bonsai are talking.

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

## 3. Nursery + USB flow (no `--talk` unless you want a slow Bonsai turn)

```
/nursery
/usb create e2e-mem memory
/usb create e2e-usb file
/infants
/usb assign e2e-mem Infant_Sovereign_000
/usb migrate Infant_Sovereign_000 e2e-mem e2e-usb
/usb list
/farm status
/farm cycle 1
```

## 4. Offline queue → Wading Pool (HITL only)

These items must be placed on the node first. From a second shell
(or after you add a tiny helper), queue two dicts, **or** in the REPL
after creating `e2e-usb`, you can eject/mount once the queue exists.

If you are at a Python prompt in the same project:

```python
from queenbee_integration import get_nursery
n = get_nursery().get_node("e2e-usb")
n.queue_offline({"id": "live-1", "type": "review", "summary": "Live HITL: watch the hive entrance."})
n.queue_offline({"id": "live-2", "type": "note", "summary": "Live HITL: do not auto-train."})
n.persist()
```

Then in QueenBee:

```
/usb eject e2e-usb
/usb mount e2e-usb
/usb apply-queue e2e-usb
/usb apply-queue e2e-usb --to-pool
/pool
/usb apply-queue e2e-usb --to-pool --clear
/pool
```

Expect:

- Mount notes that offline tasks exist.
- `--to-pool` copies tagged `candidate` rows into `wading_pool.json` (`candidates` list).
- `/train` still only uses the original nursery/wading tasks, not candidates.
- `--clear` drains the node queue after a successful copy.

## 5. Confirm inference is alive (one classic command)

Pick **one** (HTTP is slow on N150):

```
/summary Infant_Sovereign_000
```

or, if you explicitly want a model turn:

```
/train --talk Infant_Sovereign_000
```

`/summary` is enough if the infant already exists; `/train --talk` proves Bonsai replies.

## 6. Cleanup (optional)

```
/usb delete e2e-mem
/usb delete e2e-usb
/nursery
```

Do **not** expect `/usb apply-queue --to-pool` to spawn, train, or promote anyone.
