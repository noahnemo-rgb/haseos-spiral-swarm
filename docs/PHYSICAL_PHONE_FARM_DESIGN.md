# Physical Phone-Farm Design Notes

**Status:** Living design artifact (not final engineering)  
**Date:** 2026-08-21  
**Software counterpart:** Software Nursery v0.1 (`usb_state.py`, `nursery.py`, QueenBee `/usb` / `/nursery` / `/farm`)  
**Audience:** Noah Nemo (HITL) and novice co-creators

This document sketches how the current **dual-mode Software Nursery** will later map onto a real, air-gapped Android phone farm. It is honest about what is decided and what is still open.

---

## 1. Purpose & Relationship to Software Nursery

The Software Nursery is the **development and test harness**. It already practices the same ideas we will use on hardware:

- Each **VirtualNode** is a seat that can hold a few infant snapshots.
- Each node’s durable image is a human-readable **USB-state JSON** file (`usb_states/<node_id>.json`).
- **Mount / eject** means “this seat is plugged into QueenBee’s farm bus” vs “the USB is unplugged and the node is offline.”
- **offline_queue** holds work that arrived while the node was away. A human reviews it; nothing auto-executes.

The physical phone farm is the **eventual embodiment** of that same model:

| Software today | Physical later |
| --- | --- |
| In-memory node (fast tests) | Not used on hardware (phones always have storage) |
| File-backed node | One phone + one USB volume |
| `usb_states/*.json` | Files on a real USB drive / adopted storage |
| QueenBee REPL `/usb …` | Same commands, plus OS-level “disk appeared / disappeared” |

We keep building and testing in software first. Hardware should not invent a second state format.

---

## 2. Target Hardware (initial)

- **Platform:** Android-first. No iOS, no mixed-OS first wave.
- **Primary phone family:** Samsung Galaxy **S20 / S20 FE** (or a closely similar used Exynos/Snapdragon S20-class handset). Enough RAM and USB-C for a nursery node; cheap enough to buy used.
- **Initial scale:** **4–8** used phones in one chassis or shelf.
- **Later concept:** expand toward a **20-node chassis** (same USB-state image, more seats).
- **Per-node storage:** one USB drive or USB-C volume per phone. That volume is the real counterpart of today’s USB-state JSON image. QueenBee never treats the phone’s internal flash as the sovereign transfer medium.

Power, cables, and a dummy load / charge board are part of the chassis, not part of infant memory.

---

## 3. Chassis & Physical Layout (sketch)

High-level only — not a parts list yet.

- **Form:** a shallow rack, wooden/metal shelf, or modular 3D-printed trays. Each tray is one node: phone + USB stick + labeled id (`node-01` …).
- **Power:** a shared USB-C PD or 5 V distribution rail with per-phone fuses or current limits. Phones stay powered; they do not roam the house Wi-Fi.
- **USB connectivity:** one host-facing USB path per node (hub or per-port controller) used **only** when QueenBee is allowed to see that node. Unplugging that path is the physical `/usb eject`.
- **Thermal / airflow:** S20-class phones in a tray need open sides and a slow fan or chimney. Do not stack phones face-to-face without airflow.
- **Physical security / air-gap:** chassis in a locked or supervised space. No always-on Ethernet/Wi-Fi dongle. Cellular radios stay off or airplane-mode by policy. The only deliberate data path is the USB volume.

This is a sketch. Exact rail, hub, and tray design is an open decision.

---

## 4. State Transfer Model

Today’s `USBState` schema (`schema_version` 0.1) is the contract:

- `node_id`, `mount_status`, `airgap_enforced`
- `infants[]` — plain dict snapshots
- `offline_queue[]` — work waiting while unplugged
- `competence_scores`, `experience_logs`, `academy_status`
- `integrity` — SHA-256 of the image minus the hash field itself

**Mapping onto real media:**

1. Each phone’s USB volume contains one (or a small folder of) USB-state JSON files, same fields as `usb_states/*.json`.
2. **Mount** = volume is visible to the QueenBee host **and** the operator runs `/usb mount <node_id>` (or a later udev helper that only *notifies*; it must not auto-train).
3. **Eject** = persist JSON to the volume, then unmount/unplug. The phone is offline. `offline_queue` may still grow on the image if we write tasks onto the stick before unplug, or when the stick is next written at a supervised bench.
4. **Migrate via USB** stays a walk: persist + eject source, carry or re-plug the volume, mount dest, assign snapshot. No infant internet.

QueenBee remains the single orchestrator. Phones do not call home.

---

## 5. Air-gap & Security Posture

- Nodes are **network-isolated by default**. No infant process gets a general internet socket.
- USB is the **deliberate, inspectable** transfer path. A human can open the JSON and read it (Memory Sovereignty).
- `/usb apply-queue` surfaces queued work for HITL review. It does **not** auto-train, auto-spawn, or auto-promote.
- Ethics First and Promotion Protocols still apply: durable learning starts as a candidate / logged experience; no hidden senior-roster writes.
- Physical loss of a stick is loss of that node’s USB image — keep a supervised export (`/export`) as a separate backup habit, not a second live network sync.

---

## 6. Open Questions / Next Decisions

1. **Phone acquisition:** exact S20 / S20 FE listings, carrier-lock risk, battery health minimum.
2. **USB media:** USB-C sticks vs USB-C hubs + USB-A sticks vs microSD-in-OTG. Capacity target (today’s sim uses `storage_mb: 1024`).
3. **Chassis sourcing:** buy a 3D-print tray, a used charging cabinet, or a simple shelf first?
4. **Power budget:** watts per phone at idle vs charge; whether the N150 QueenBee host and the farm share one UPS.
5. **Ready signal:** how a real node tells QueenBee “I am mounted and healthy” (ADB? file presence? LED?). Software today only knows `mount_status`.
6. **Android image policy:** stock ROM + airplane mode vs a locked-down custom profile. No decision yet.
7. **Recognition automation:** udev/systemd may *announce* a volume; it must not run `/train` or `/cycle` by itself.
8. **Labeling:** human-readable `node_id` on the tray, the stick, and the JSON must stay identical.

---

## 7. Mapping Table (software → physical)

| Software Nursery (now) | Physical farm (later) |
| --- | --- |
| `VirtualNode` | One Android phone in a labeled tray |
| USBState JSON image (`usb_states/*.json`) | Files on that node’s USB drive / volume |
| `/usb mount` | Plug in the USB path + QueenBee recognizes the volume |
| `/usb eject` | Persist JSON, unmount, unplug; phone stays powered but off the farm bus |
| `/usb assign` / `/export --to-node` | Write an infant snapshot onto that volume |
| `/usb migrate …` (via USB) | Walk the stick (or re-plug) from source seat to dest seat |
| `offline_queue` | Tasks waiting while the phone/volume is offline |
| `/usb apply-queue` | HITL reads those tasks after remount; optional `--clear` |
| `/farm cycle` | Readiness report only — training still `/train` and `/cycle` |
| `airgap_enforced: true` | No infant internet; USB is the data path |

---

## Node Wiring + Bring-Up Card (v0.1 — first physical node)

Bench card for node 1. Scannable. Robotics-ready habits without building the robot yet.

### Topology

```text
Farm PC / homelab
    │  USB 2.0 data  (rear root port preferred)
    ▼
Powered USB 2.0 hub  ←—— dedicated PSU  (NOT bus-powered)
    │  one cable per phone
    ▼
Android phone  (S20 / S20 FE class, OTG host)
    │  USB-C OTG adapter  (phone is HOST to the stick)
    ▼
Low-power USB 2.0 thumb drive  = ONE infant USB-state image
```

**Rules**

- One stick = one infant = one phone. No dual-seat.
- No USB data splitters.
- Powered hub is required on the motherboard↔phone side for anything beyond a single experimental phone on a PC port.
- Infant stick rides on phone OTG, not on a shared splitter with the farm cable.
- If that phone cannot charge and speak OTG at once, use a tested charge-while-OTG accessory or wireless charge + OTG — still one stick per phone.

### Node-1 kit (minimum)

| Qty | Item |
| --- | --- |
| 1× | OTG-capable S20 / S20 FE (or same family) |
| 1× | Powered 4- or 7-port USB 2.0 hub + brick |
| 1× | Short USB cable phone ↔ hub |
| 2× | Low-power USB 2.0 sticks (live + spare) |
| 1× | USB-C OTG adapter if sticks are USB-A |
| — | Labels: hub port, phone identity, stick serial, infant id |
| 1× | ESP32-S3 on the bench only (Blink / UART reservation — does **not** hold the sovereign image) |

### Bring-up checklist

1. Hub on its own PSU; host on a rear USB 2.0 port.
2. Phone on hub: charges; `adb devices` sees it.
3. Stick on phone OTG only; phone can read/write a file.
4. Record whether this exact phone does charge-while-OTG.
5. Unmount / eject, pull stick, remount; file intact.
6. Copy a QueenBee USB-state / export image onto the stick; treat it as that infant.
7. Label: `hub-port | phone | stick-serial | infant-id`.
8. ESP32-S3: power via USB, Blink only; do **not** mount the infant there.

### Label map (fill at the bench)

| Slot | Hub port | Phone ID | Stick serial | Infant id | Charge+OTG? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | |

### Embodiment port (reserve now, do not build the robot)

- **Body MCU:** ESP32-S3 preferred.
- **Contract:** UART 115200 8N1, 3.3 V, a HALT line, power FET later.
- **Commands (names only):** `PING`, `STATUS`, `ACT`, `HALT`.
- Default radios off. No public OTA.
- Senior Sovereign stays on the USB stick; ESP32 is nerves/muscles only.
- Same stick must be movable: farm phone → later phone-or-Pi robot brain.

### Non-goals (this card)

- No 20-port chassis purchase as step one
- No data splitters
- No sovereign image on ESP32 flash
- No QueenBee code changes in this slice
- No internet-default embodiment

### Status

Software Nursery v0.1 remains the software twin of this card. Physical node-1 is bring-up only.

---

*Software Nursery v0.1 is stable for the current software phase. Further software changes should stay incremental. Hardware work starts from this document, not from a second state format.*
