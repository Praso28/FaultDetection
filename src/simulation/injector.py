from __future__ import annotations

from simulation.metrics_gen import generate_fault

DEFAULT_NF_BY_FAULT = {
    "F1": "SMF",
    "F2": "UPF",
    "F3": "UPF",
    "F4": "AMF",
    "F5": "NRF",
}


def inject_fault(fault_id: str, nf: str | None = None, seed: int = 42, count: int = 30):
    normalized_fault = fault_id.upper()
    if normalized_fault not in DEFAULT_NF_BY_FAULT:
        raise ValueError(f"Unsupported fault_id '{fault_id}'")
    target_nf = nf or DEFAULT_NF_BY_FAULT[normalized_fault]
    return generate_fault(fault_id=normalized_fault, nf=target_nf, seed=seed, count=count)
