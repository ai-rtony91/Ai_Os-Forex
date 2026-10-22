"""Canonical public API for the AI_OS Orchestration Platform V1.

This module is intentionally a facade: domain logic remains in the established,
tested components.  Callers should depend on this module instead of composing
queue, dispatch, packet, resolution, spine, reporting, and countdown modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from automation.orchestration.aios_canonical_orchestration_spine_v1 import (
    build_orchestration_spine,
    render_orchestration_report,
)
from automation.orchestration.aios_codex_packet_builder import build_repository_aligned_apply_packet
from automation.orchestration.aios_codex_packet_from_queue import build_codex_packet_from_queue_item
from automation.orchestration.aios_packet_queue_planner import build_packet_queue_planner
from automation.orchestration.aios_work_countdown_v1 import (
    build_work_countdown,
    load_canonical_work_packet_inventory,
)
from automation.orchestration.aios_compound_work_braid_v1 import CompoundWorkBraidController
from automation.orchestration.runtime_queue.aios_development_dispatcher import build_dispatch_plan
from automation.orchestration.runtime_queue.aios_execution_packet_resolver import resolve_execution_packet

__all__ = ["OrchestrationPlatform", "create_platform"]


class OrchestrationPlatform:
    """Stable, side-effect-free entry point over canonical orchestration components."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def queue(self, evidence: dict[str, Any]) -> dict[str, Any]:
        return build_packet_queue_planner(evidence)

    def dispatch(self, queue_view: dict[str, Any], *, worker_capacity: int = 1) -> dict[str, Any]:
        return build_dispatch_plan(queue_view, worker_capacity=worker_capacity)

    def build_packet(self, **packet_fields: Any) -> dict[str, Any]:
        return build_repository_aligned_apply_packet(**packet_fields)

    def generate_packet(self, queue_item: dict[str, Any], **options: Any) -> dict[str, Any]:
        return build_codex_packet_from_queue_item(queue_item, **options)

    def resolve_packet(
        self,
        queue_item: dict[str, Any],
        repository_state: dict[str, Any],
        *,
        existing_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return resolve_execution_packet(queue_item, repository_state, existing_packets=existing_packets)

    def spine(self, *, as_of_utc: str | None = None) -> dict[str, Any]:
        return build_orchestration_spine(self.repo_root, as_of_utc=as_of_utc)

    def report(self, state: dict[str, Any]) -> str:
        return render_orchestration_report(state)

    def countdown(self, evidence: Any | None = None, **options: Any) -> dict[str, Any]:
        source = evidence if evidence is not None else load_canonical_work_packet_inventory(self.repo_root)
        return build_work_countdown(source, **options)

    def compound_work_braid(self, **options: Any) -> dict[str, Any]:
        """Build a deterministic, non-executing compound work plan."""
        return CompoundWorkBraidController(self.repo_root).build(**options)

    def govern_autonomy(
        self, evidence: dict[str, Any], *, generated_at_utc: str | None = None
    ) -> dict[str, Any]:
        """Return a non-mutating decision from the canonical autonomy governor."""
        from automation.orchestration.aios_autonomy_decision_governor import choose_next_decision

        return choose_next_decision(evidence, generated_at_utc=generated_at_utc)

    def master_runtime(self, **options: Any) -> dict[str, Any]:
        """Run the registered master-runtime coordinator through this facade."""
        from automation.orchestration.aios_master_runtime_v1 import AIOSMasterRuntime

        return AIOSMasterRuntime(self.repo_root, platform=self).execute(**options)

    def validate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate the shared platform contract without granting execution authority."""
        defects: list[str] = []
        if not isinstance(state, dict):
            defects.append("state_not_object")
        else:
            for field in ("schema", "status", "permissions", "protected_actions"):
                if field not in state:
                    defects.append(f"missing_{field}")
            for gate in ("permissions", "protected_actions"):
                values = state.get(gate, {})
                if not isinstance(values, dict) or any(value is not False for value in values.values()):
                    defects.append(f"unsafe_{gate}")
        return {
            "schema": "AIOS_ORCHESTRATION_PLATFORM_VALIDATION.v1",
            "status": "PASS" if not defects else "BLOCKED",
            "defects": defects,
            "grants_approval": False,
            "performs_mutation": False,
        }


def create_platform(repo_root: str | Path = ".") -> OrchestrationPlatform:
    """Create the canonical orchestration facade."""
    return OrchestrationPlatform(repo_root)
