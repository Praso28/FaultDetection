from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib import request

from agent.contracts import StateSnapshot


DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"


@dataclass(frozen=True)
class LLMConfig:
    model: str = DEFAULT_MODEL
    url: str = DEFAULT_OLLAMA_URL
    timeout_seconds: int = 10


def generate_explanation(
    state_snapshot: StateSnapshot,
    fault: str,
    confidence: float,
    *,
    use_llm: bool = False,
    llm_config: LLMConfig = LLMConfig(),
    requester: Callable[[str, str, LLMConfig], str] | None = None,
) -> str:
    """Generate explanation text only. This function must not decide or mutate actions."""
    deterministic = _deterministic_explanation(state_snapshot, fault, confidence)
    if not use_llm:
        return deterministic

    prompt = _build_prompt(state_snapshot, fault, confidence)
    llm_requester = requester or _ollama_request
    try:
        candidate = llm_requester(prompt, llm_config.model, llm_config)
    except Exception:
        return deterministic

    cleaned = (candidate or "").strip()
    if not cleaned:
        return deterministic
    return cleaned


def _deterministic_explanation(state_snapshot: StateSnapshot, fault: str, confidence: float) -> str:
    fault_id = fault.upper()
    target_nf, details = _extract_relevant_details(state_snapshot, fault_id)
    reason = _fault_reason(fault_id)
    details_text = ", ".join(details) if details else "no strong metric detail available"
    return (
        f"Diagnosis={fault_id} on {target_nf}; confidence={confidence:.3f}. "
        f"Reasoning: {reason}. Observed signals: {details_text}."
    )


def _build_prompt(state_snapshot: StateSnapshot, fault: str, confidence: float) -> str:
    raw = state_snapshot.to_dict()
    return (
        "You are generating an explanation for an already-determined deterministic diagnosis. "
        "Do not suggest or decide actions. Keep it concise and technical.\n"
        f"Fault: {fault}\n"
        f"Confidence: {confidence:.3f}\n"
        f"Snapshot: {json.dumps(raw, separators=(',', ':'))}\n"
        "Return only the explanation text."
    )


def _ollama_request(prompt: str, model: str, config: LLMConfig) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        config.url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=config.timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("response", "")).strip()


def _extract_relevant_details(state_snapshot: StateSnapshot, fault: str) -> tuple[str, list[str]]:
    preferred_nf = {
        "F1": "SMF",
        "F2": "UPF",
        "F3": "UPF",
        "F4": "AMF",
        "F5": "NRF",
    }.get(fault)

    if preferred_nf and preferred_nf in state_snapshot.states:
        nf = preferred_nf
    elif state_snapshot.states:
        nf = next(iter(state_snapshot.states.keys()))
    else:
        return (preferred_nf or "UNKNOWN", [])

    s = state_snapshot.states[nf]
    details: list[str] = []
    if s.latency_ms is not None:
        details.append(f"latency_ms={s.latency_ms}")
    if s.cpu_pct is not None:
        details.append(f"cpu_pct={s.cpu_pct}")
    if s.packet_loss_pct is not None:
        details.append(f"packet_loss_pct={s.packet_loss_pct}")
    if s.request_rate is not None:
        details.append(f"request_rate={s.request_rate}")
    if s.queue_length is not None:
        details.append(f"queue_length={s.queue_length}")
    if s.session_drop_count is not None:
        details.append(f"session_drop_count={s.session_drop_count}")
    if s.connection_refused is not None:
        details.append(f"connection_refused={s.connection_refused}")
    if s.error_log_count is not None:
        details.append(f"error_log_count={s.error_log_count}")
    return nf, details


def _fault_reason(fault: str) -> str:
    reasons = {
        "F1": "SMF-down pattern: session drops and/or connection refusal",
        "F2": "UPF congestion pattern: high latency with high cpu and packet loss",
        "F3": "network degradation pattern: high latency and packet loss while cpu stays normal",
        "F4": "traffic surge pattern: elevated request rate and queue length",
        "F5": "configuration anomaly pattern: error logs with mostly normal metrics",
    }
    return reasons.get(fault, "unclassified deterministic pattern")
