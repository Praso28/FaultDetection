from __future__ import annotations

from rules.fault_catalog import FaultHypothesis, evaluate_rules
from agent.contracts import StateSnapshot


def infer_fault(snapshot: StateSnapshot) -> list[dict[str, object]]:
    hypotheses = evaluate_rules(snapshot)
    if not hypotheses:
        return []

    resolved = _resolve_overlaps(hypotheses)
    resolved_sorted = sorted(resolved, key=lambda h: h.confidence_base, reverse=True)

    return [
        {
            "fault": hypothesis.fault,
            "target_nf": hypothesis.target_nf,
            "confidence_base": hypothesis.confidence_base,
            "rule_hits": list(hypothesis.rule_hits),
        }
        for hypothesis in resolved_sorted
    ]


def _resolve_overlaps(hypotheses: list[FaultHypothesis]) -> list[FaultHypothesis]:
    grouped_by_nf: dict[str, list[FaultHypothesis]] = {}
    for item in hypotheses:
        grouped_by_nf.setdefault(item.target_nf, []).append(item)

    resolved: list[FaultHypothesis] = []
    for nf_hypotheses in grouped_by_nf.values():
        f2 = next((h for h in nf_hypotheses if h.fault == "F2"), None)
        f3 = next((h for h in nf_hypotheses if h.fault == "F3"), None)
        if f2 is not None and f3 is not None and "cpu_pct>80" in f2.rule_hits:
            nf_hypotheses = [h for h in nf_hypotheses if h.fault != "F3"]

        best_per_fault: dict[str, FaultHypothesis] = {}
        for hypothesis in nf_hypotheses:
            existing = best_per_fault.get(hypothesis.fault)
            if existing is None or hypothesis.confidence_base > existing.confidence_base:
                best_per_fault[hypothesis.fault] = hypothesis
        resolved.extend(best_per_fault.values())

    return resolved
