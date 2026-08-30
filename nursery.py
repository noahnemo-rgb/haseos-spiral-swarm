#!/usr/bin/env python3
"""
Software Nursery — dual-mode virtual phone-farm.

Two kinds of virtual node, one USB-state format:

  * mode="memory"  — fast RAM node for development
  * mode="file"    — JSON USB image on disk (future physical USB)

QueenBee stays the orchestrator. This module does not import QueenBee.
Infants stay plain dicts. Air-gapped by default (no internet on nodes).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import usb_state

DEFAULT_REGISTRY = "nursery_state.json"
DEFAULT_USB_DIR = "usb_states"


def _infant_id(infant: dict | str) -> str:
    if isinstance(infant, dict):
        iid = infant.get("id")
        if not iid:
            raise ValueError("infant dict is missing an id")
        return str(iid)
    return str(infant)


class VirtualNode:
    """One simulated phone / USB seat.

    Always keeps a working USB-state dict in RAM for speed.
    File mode can also load/save that dict as a JSON USB image.
    """

    def __init__(
        self,
        node_id: str,
        mode: str = "memory",
        path: str | None = None,
        hardware_profile: str = "sim-virtual",
        state: dict | None = None,
        load_existing: bool = True,
    ):
        self.node_id = node_id
        self.mode = mode
        self.hardware_profile = hardware_profile
        if state is not None:
            self.state = usb_state.from_dict(state)
        elif load_existing and path and Path(path).is_file():
            self.state = usb_state.load(path)
        else:
            self.state = usb_state.create_empty(
                node_id,
                mode=mode,
                path=path,
                hardware_profile=hardware_profile,
            )
        self.state["node_id"] = node_id
        self.state["mode"] = mode
        if path:
            self.state["path"] = str(path)

    # --- mount / eject / persist (USB plug semantics) ---

    def mount(self, path: str | None = None) -> dict:
        """Bring the node online.

        Pass an explicit path to plug in that USB image (load from disk).
        With no path, the current in-memory state is what gets mounted.
        """
        if path:
            dest = Path(path)
            if dest.is_file():
                loaded = usb_state.load(dest)
                loaded["node_id"] = self.node_id
                loaded["mode"] = self.mode
                self.state = loaded
            self.state["path"] = str(dest)
        self.state["mount_status"] = "mounted"
        usb_state.touch(self.state)
        return self.summary()

    def persist(self, path: str | None = None) -> str | None:
        """Write the current RAM state to a JSON USB image (optional for memory)."""
        dest = path or self.state.get("path")
        if not dest:
            if self.mode == "memory":
                return None
            raise ValueError(f"node {self.node_id} has no USB path to persist")
        usb_state.save(self.state, dest)
        return str(dest)

    def eject(self, persist: bool = True, path: str | None = None) -> dict:
        """Unplug the USB. Node goes ejected/offline. Queue stays on the image."""
        if persist:
            dest = path or self.state.get("path")
            if dest:
                self.persist(dest)
            elif self.mode == "file":
                raise ValueError(f"node {self.node_id} cannot persist on eject without a path")
        self.state["mount_status"] = "ejected"
        usb_state.touch(self.state)
        return self.summary()

    # --- infants stay plain dicts ---

    def assign_infant(self, infant: dict) -> dict:
        """Copy a plain infant dict onto this node if there is capacity."""
        if not isinstance(infant, dict):
            raise TypeError("infant must be a plain dict")
        if self.state["mount_status"] != "mounted":
            raise RuntimeError(f"node {self.node_id} is not mounted; cannot assign")
        iid = _infant_id(infant)
        if iid in self.infant_ids():
            raise ValueError(f"infant {iid} is already on node {self.node_id}")
        cap = int(self.state["capacity"]["max_infants"])
        if len(self.state["infants"]) >= cap:
            raise RuntimeError(f"node {self.node_id} is at capacity ({cap})")
        payload = copy.deepcopy(infant)
        self.state["infants"].append(payload)
        self._refresh_infant_sidecars(payload)
        usb_state.touch(self.state)
        return payload

    def _refresh_infant_sidecars(self, payload: dict) -> None:
        iid = _infant_id(payload)
        if payload.get("competence_score") is not None:
            self.state["competence_scores"][iid] = payload.get("competence_score")
        experiences = payload.get("experiences")
        if isinstance(experiences, list):
            self.state["experience_logs"][iid] = copy.deepcopy(experiences)
        review = payload.get("last_academy_review")
        if not isinstance(review, dict):
            review = {}
        history = payload.get("promotion_history")
        if not isinstance(history, list):
            history = []
        self.state["academy_status"][iid] = {
            "promoted": bool(payload.get("promoted")),
            "promotion_time": payload.get("promotion_time"),
            "promotion_reason": payload.get("promotion_reason"),
            "promotion_events": len(history),
            "last_recommendation": review.get("recommendation") or "",
            "reviewed_at": review.get("reviewed_at") or "",
            "status": payload.get("status") or "?",
        }
        self.state.setdefault("memory_manifest", {})[iid] = usb_state.infant_memory_card(payload)

    def sync_infant(self, infant: dict) -> dict | None:
        """Replace a stored snapshot in place (sleep/wake and later live updates)."""
        if not isinstance(infant, dict):
            raise TypeError("infant must be a plain dict")
        iid = _infant_id(infant)
        for index, stored in enumerate(self.state.get("infants") or []):
            if stored.get("id") != iid:
                continue
            payload = copy.deepcopy(infant)
            self.state["infants"][index] = payload
            self._refresh_infant_sidecars(payload)
            usb_state.touch(self.state)
            persisted = False
            if self.mode == "file" or self.state.get("path"):
                try:
                    self.persist()
                    persisted = True
                except ValueError:
                    persisted = False
            return {
                "node_id": self.node_id,
                "status": payload.get("status"),
                "persisted": persisted,
                "mount_status": self.state.get("mount_status"),
            }
        return None

    def remove_infant(self, infant_id: str) -> dict:
        """Take an infant off this node and return the dict."""
        iid = str(infant_id)
        kept = []
        found = None
        for infant in self.state["infants"]:
            if infant.get("id") == iid:
                found = infant
            else:
                kept.append(infant)
        if found is None:
            raise KeyError(f"infant {iid} is not on node {self.node_id}")
        self.state["infants"] = kept
        self.state["competence_scores"].pop(iid, None)
        self.state["experience_logs"].pop(iid, None)
        self.state["academy_status"].pop(iid, None)
        self.state.get("memory_manifest", {}).pop(iid, None)
        usb_state.touch(self.state)
        return found

    def get_infants(self) -> list[dict]:
        return copy.deepcopy(self.state.get("infants") or [])

    def infant_ids(self) -> list[str]:
        return [str(infant.get("id")) for infant in self.state.get("infants") or []]

    # --- offline queue (work waiting while the USB is unplugged) ---

    def queue_offline(self, task: dict) -> dict:
        if not isinstance(task, dict):
            raise TypeError("offline task must be a dict")
        item = copy.deepcopy(task)
        self.state["offline_queue"].append(item)
        usb_state.touch(self.state)
        return item

    def apply_offline_queue(self) -> list[dict]:
        """Return the queued tasks and clear the queue (caller decides what to do)."""
        queued = copy.deepcopy(self.state.get("offline_queue") or [])
        self.state["offline_queue"] = []
        usb_state.touch(self.state)
        return queued

    def is_mounted(self) -> bool:
        return self.state.get("mount_status") == "mounted"

    def is_airgapped(self) -> bool:
        """Nodes never get a live internet path. Eject also takes them off the farm bus."""
        return bool(self.state.get("airgap_enforced", True))

    def summary(self) -> dict:
        cards = [
            usb_state.infant_memory_card(infant)
            for infant in (self.state.get("infants") or [])
            if isinstance(infant, dict)
        ]
        active = sum(1 for card in cards if card.get("status") == "ACTIVE")
        sleeping = sum(1 for card in cards if card.get("sleeping"))
        rich = sum(
            1
            for card in cards
            if card.get("experiences") or card.get("has_academy_review") or card.get("promotion_events")
        )
        competence = 0
        for card in cards:
            try:
                competence += int(card.get("competence") or 0)
            except (TypeError, ValueError):
                pass
        return {
            "node_id": self.node_id,
            "mode": self.mode,
            "path": self.state.get("path"),
            "mount_status": self.state.get("mount_status"),
            "airgap_enforced": bool(self.state.get("airgap_enforced", True)),
            "mounted": self.is_mounted(),
            "infant_ids": self.infant_ids(),
            "infant_count": len(self.infant_ids()),
            "infant_active": active,
            "infant_sleeping": sleeping,
            "rich_memory": rich,
            "competence_total": competence,
            "offline_queue": len(self.state.get("offline_queue") or []),
            "hardware_profile": self.hardware_profile,
            "integrity": (self.state.get("integrity") or "")[:12],
            "infant_memory": cards,
        }


class Nursery:
    """Manager for a small farm of VirtualNodes.

    Registry file (nursery_state.json) remembers which nodes exist.
    USB images live under usb_states/ by default.
    """

    def __init__(
        self,
        registry_path: str | Path = DEFAULT_REGISTRY,
        usb_dir: str | Path = DEFAULT_USB_DIR,
    ):
        self.registry_path = Path(registry_path)
        self.usb_dir = Path(usb_dir)
        self.usb_dir.mkdir(parents=True, exist_ok=True)
        self.nodes: dict[str, VirtualNode] = {}
        self._load_registry()

    def _default_path(self, node_id: str) -> str:
        return str(self.usb_dir / f"{node_id}.json")

    def _registry_blob(self) -> dict:
        nodes = {}
        for node_id, node in self.nodes.items():
            nodes[node_id] = {
                "node_id": node_id,
                "mode": node.mode,
                "path": node.state.get("path"),
                "hardware_profile": node.hardware_profile,
                "mount_status": node.state.get("mount_status"),
            }
        return {"nodes": nodes}

    def _save_registry(self) -> None:
        self.registry_path.write_text(
            json.dumps(self._registry_blob(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_registry(self) -> None:
        if not self.registry_path.is_file():
            return
        try:
            blob = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for node_id, meta in (blob.get("nodes") or {}).items():
            path = meta.get("path")
            mode = meta.get("mode") or "memory"
            node = VirtualNode(
                node_id,
                mode=mode,
                path=path,
                hardware_profile=meta.get("hardware_profile") or "sim-virtual",
            )
            # Restore last known plug status without forcing a remount.
            if meta.get("mount_status") in usb_state.MOUNT_STATUSES:
                node.state["mount_status"] = meta["mount_status"]
                usb_state.touch(node.state)
            self.nodes[node_id] = node

    def create_node(
        self,
        node_id: str,
        mode: str = "memory",
        path: str | None = None,
        hardware_profile: str = "sim-virtual",
        auto_mount: bool = False,
    ) -> VirtualNode:
        if node_id in self.nodes:
            raise ValueError(f"node {node_id} already exists")
        if mode not in usb_state.MODES:
            raise ValueError(f"mode must be memory or file, got {mode!r}")
        if mode == "file" and not path:
            path = self._default_path(node_id)
        node = VirtualNode(
            node_id,
            mode=mode,
            path=path,
            hardware_profile=hardware_profile,
            load_existing=False,
        )
        self.nodes[node_id] = node
        if auto_mount:
            node.mount()
        if mode == "file":
            node.persist(path)
        self._save_registry()
        return node

    def get_node(self, node_id: str) -> VirtualNode:
        node = self.nodes.get(node_id)
        if node is None:
            raise KeyError(f"node not found: {node_id}")
        return node

    def list_nodes(self) -> list[dict]:
        return [node.summary() for node in self.nodes.values()]

    def delete_node(
        self,
        node_id: str,
        persist_final: bool = False,
        remove_image: bool = False,
    ) -> dict:
        """Unregister a node. With remove_image=True, also delete its USB JSON file."""
        node = self.get_node(node_id)
        path = node.state.get("path")
        if persist_final:
            try:
                node.persist()
            except ValueError:
                pass
        del self.nodes[node_id]
        removed_image = False
        if remove_image and path:
            image = Path(path)
            if image.is_file():
                image.unlink()
                removed_image = True
        self._save_registry()
        return {
            "node_id": node_id,
            "path": path,
            "removed_image": removed_image,
        }

    def mount(self, node_id: str, path: str | None = None) -> dict:
        summary = self.get_node(node_id).mount(path)
        self._save_registry()
        return summary

    def eject(self, node_id: str, persist: bool = True) -> dict:
        summary = self.get_node(node_id).eject(persist=persist)
        self._save_registry()
        return summary

    def assign_infant(self, node_id: str, infant: dict) -> dict:
        payload = self.get_node(node_id).assign_infant(infant)
        self._save_registry()
        return payload

    def sync_infant(self, infant: dict) -> list[dict]:
        """Update every node that currently holds this infant. Persist file images."""
        results = []
        for node in self.nodes.values():
            row = node.sync_infant(infant)
            if row:
                results.append(row)
        if results:
            self._save_registry()
        return results

    def migrate_infant(
        self,
        infant: dict | str,
        from_node: str,
        to_node: str,
        via_usb: bool = True,
    ) -> dict:
        """Move one infant between nodes.

        via_usb=True (default): air-gapped USB hand-off
          1. Confirm dest has room
          2. Take infant off the source (the USB now carries it)
          3. Persist + eject the source (node goes offline)
          4. Mount dest if needed and assign the infant
          5. Persist dest if it has a path

        via_usb=False: same move in RAM only (still no network).
        """
        src = self.get_node(from_node)
        dst = self.get_node(to_node)
        iid = _infant_id(infant)
        if iid not in src.infant_ids():
            raise KeyError(f"infant {iid} is not on node {from_node}")
        dest_cap = int(dst.state["capacity"]["max_infants"])
        if len(dst.infant_ids()) >= dest_cap:
            raise RuntimeError(f"node {to_node} is at capacity")

        payload = src.remove_infant(iid)

        if via_usb:
            # Source USB is written, then unplugged. Dest receives the walk-over.
            if src.mode == "file" or src.state.get("path"):
                src.persist()
            src.eject(persist=bool(src.state.get("path")))
            if not dst.is_mounted():
                dst.mount()
            dst.assign_infant(payload)
            if dst.mode == "file" or dst.state.get("path"):
                dst.persist()
        else:
            if not dst.is_mounted():
                dst.mount()
            dst.assign_infant(payload)

        self._save_registry()
        return {
            "infant_id": iid,
            "from_node": from_node,
            "to_node": to_node,
            "via_usb": via_usb,
            "from_status": src.state.get("mount_status"),
            "to_status": dst.state.get("mount_status"),
        }

    def farm_status(self) -> dict:
        summaries = self.list_nodes()
        return {
            "total_nodes": len(summaries),
            "mounted": sum(1 for row in summaries if row["mounted"]),
            "ejected": sum(1 for row in summaries if row["mount_status"] == "ejected"),
            "total_infants": sum(row["infant_count"] for row in summaries),
            "nodes": summaries,
        }

    def farm_cycle(self, n: int = 1) -> dict:
        """Report which mounted nodes have infants ready.

        Real training still goes through QueenBee /train and /cycle.
        """
        ready = []
        for node in self.nodes.values():
            if node.is_mounted() and node.infant_ids():
                ready.append(
                    {
                        "node_id": node.node_id,
                        "infant_ids": node.infant_ids(),
                    }
                )
        return {
            "n": n,
            "ready": ready,
            "note": "Training still goes through QueenBee /train and /cycle",
        }


def demo() -> None:
    """Small walk-through used by `python3 nursery.py`."""
    usb_dir = Path(DEFAULT_USB_DIR)
    usb_dir.mkdir(parents=True, exist_ok=True)

    farm = Nursery(registry_path=DEFAULT_REGISTRY, usb_dir=usb_dir)
    # Fresh demo: drop leftover demo seats if a previous run left them.
    for leftover in ("ram-alpha", "usb-beta"):
        if leftover in farm.nodes:
            farm.delete_node(leftover, persist_final=False)

    print("nursery demo starting")
    ram = farm.create_node("ram-alpha", mode="memory", auto_mount=True)
    print(f"  created in-memory node {ram.node_id} mounted={ram.is_mounted()}")

    usb = farm.create_node("usb-beta", mode="file", auto_mount=True)
    print(f"  created file-backed node {usb.node_id} path={usb.state.get('path')}")

    dummy = {
        "id": "Infant_Sovereign_DEMO",
        "status": "ACTIVE",
        "sandbox_tier": "nursery",
        "task": "Watch the virtual hive entrance.",
        "promoted": False,
        "competence_score": 1,
        "experiences": [
            {
                "timestamp": "2026-08-21T00:00:00",
                "task": "Watch the virtual hive entrance.",
                "summary": "assigned at demo spawn",
            }
        ],
    }
    farm.assign_infant("ram-alpha", dummy)
    print(f"  assigned {dummy['id']} → ram-alpha")

    print("  farm_status before migration:")
    print(json.dumps(farm.farm_status(), indent=2))

    move = farm.migrate_infant(dummy, "ram-alpha", "usb-beta", via_usb=True)
    print("  migrated via USB:")
    print(json.dumps(move, indent=2))

    print("  farm_status after migration:")
    print(json.dumps(farm.farm_status(), indent=2))
    print("  farm_cycle:")
    print(json.dumps(farm.farm_cycle(1), indent=2))
    print("nursery demo OK")


if __name__ == "__main__":
    demo()
