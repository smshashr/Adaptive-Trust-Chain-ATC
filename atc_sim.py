"""
atc_sim.py — Simulation core of the ASI-PLC interlock (Algorithm 2)

Companion code for:
    Ashraf, S. R. B., Rahman, H., Noche, B., and Gürpinar, T.
    "Adaptive Trust Chain: a permissioned blockchain framework for enforcing
    weld-parameter compliance at the controller level in green hydrogen
    infrastructure." Frontiers in Blockchain (under review).

This module is the single source of the Monte Carlo logic. It is imported by
Prototype.py (command line, diagnostic figures), Prototype_app.py (Streamlit),
paper_figures.py (Figure 5) and reproduce_results.py (numeric check).

Scope
-----
* The ASI is a production-permissive interlock, NOT a safety function. In the
  ATC design the hardware emergency stop and the other safety-related parts of
  the welding cell (ISO 13849-1) act on the relay independently of the ledger.
* Latencies are drawn from ASSUMED normal distributions (Section 3.4.3):
  N(275.2, 25) ms for all non-timeout runs and N(514.6, 20) ms for timeout runs.
  They are scenario parameters, not values calibrated to a published benchmark
  or measured on a fabrication floor.
* HMAC-SHA256 is computed for real; the Ed25519 Oracle signature is represented
  by a stand-in digest (SHA-256 over the HMAC). Production use would require a
  real Ed25519 key held in a hardware security module (Security Assumption SA2).

Algorithm 2 order (as in the manuscript)
---------------------------------------
Step 1  read OraclePayload
Step 2  heartbeat timeout              -> SOFT_LOCK (clears when heartbeat returns)
Step 3  HMAC / signature verification  -> HARD_LOCK
Step 4  monotonic nonce check          -> HARD_LOCK on a stale nonce
Step 5  HARD_LOCK cleared only by a council-signed, single-use reset token
Step 6  ComplianceBit := OraclePayload.compliant (result of checkCompliance)
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SEED = 2025
HEARTBEAT_THRESHOLD_MS = 500.0

# Assumed latency distributions (manuscript Section 3.4.3; Supplementary Table S1)
VALID_LATENCY_MEAN_MS = 275.2
VALID_LATENCY_SD_MS = 25.0
TIMEOUT_LATENCY_MEAN_MS = 514.6
TIMEOUT_LATENCY_SD_MS = 20.0

# Demonstration keys. In a deployment these live in an HSM (SA2) and with the
# governance council (SA3); they are hard-coded here only for reproducibility.
GATEWAY_KEY = b"ATC-QBFT-Besu-OracleKey-TuL-2025"
COUNCIL_KEY = b"ATC-Council-ResetKey-TuL-2025"


class PLCState(Enum):
    IDLE = "IDLE"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    SOFT_LOCK = "SOFT_LOCK"
    HARD_LOCK = "HARD_LOCK"


class FaultType(Enum):
    NONE = "none"              # valid credential, compliant parameters
    NON_COMPLY = "non_comply"  # non-compliant preheat
    MITM = "mitm"              # Oracle man-in-the-middle (signature failure)
    REPLAY = "replay"          # replayed payload (stale nonce)
    TIMEOUT = "timeout"        # heartbeat timeout


# (runs, fault, compliant payload?, reason) — executed in this order (Table S2)
DEFAULT_SCENARIO_PLAN: List[Tuple[int, FaultType, bool, str]] = [
    (120, FaultType.NONE, True, "COMPLIANT"),
    (50, FaultType.NON_COMPLY, False, "PREHEAT_LOW"),
    (10, FaultType.MITM, True, "COMPLIANT"),
    (10, FaultType.REPLAY, True, "COMPLIANT"),
    (10, FaultType.TIMEOUT, True, "COMPLIANT"),
]


@dataclass
class OraclePayload:
    compliant_flag: bool
    failure_reason: str
    weld_id: str
    timestamp_utc: int
    nonce: int
    latency_ms: float
    hmac_sig: str
    asym_sig: str


@dataclass
class ResetToken:
    """Council-signed, single-use reset token (Algorithm 2, Step 5; SA3)."""
    nonce: int
    signature: str


@dataclass
class PLCCycleResult:
    scenario_id: int
    fault_type: FaultType
    payload: OraclePayload
    state: PLCState
    compliance_bit: bool
    relay_on: bool
    latency_ms: float
    step_failures: List[str] = field(default_factory=list)


def _payload_body(compliant: bool, reason: str, weld_id: str, ts: int, nonce: int) -> bytes:
    return json.dumps(
        {"compliant": compliant, "reason": reason, "weld_id": weld_id, "ts": ts, "nonce": nonce},
        sort_keys=True,
    ).encode()


def issue_reset_token(nonce: int) -> ResetToken:
    """Council side: sign a single-use reset token with a fresh nonce."""
    sig = hmac_lib.new(COUNCIL_KEY, f"ATC-HARDLOCK-RESET:{nonce}".encode(), hashlib.sha256).hexdigest()
    return ResetToken(nonce=nonce, signature=sig)


class ASI_PLC:
    """Adaptive Smart Interlock — compliance-bit logic of Algorithm 2."""

    def __init__(self) -> None:
        self.state = PLCState.NON_COMPLIANT   # power-up default (Figure 2)
        self.compliance_bit = False           # fail-locked default
        self.hard_lock = False
        self.soft_lock = False
        self.last_nonce = 0                   # nonce ledger (LastNonce)
        self.last_admin_nonce = 0             # LastAdminNonce

    @property
    def relay_on(self) -> bool:
        return self.compliance_bit

    # Step 5 helper ----------------------------------------------------------
    def _token_valid(self, token: Optional[ResetToken]) -> bool:
        if token is None:
            return False
        expected = hmac_lib.new(
            COUNCIL_KEY, f"ATC-HARDLOCK-RESET:{token.nonce}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac_lib.compare_digest(expected, token.signature) and token.nonce > self.last_admin_nonce

    def council_reset(self, token: Optional[ResetToken]) -> bool:
        """Clear HardLock with a council-signed, single-use token.

        Returns True if the HardLock was cleared (or none was active). A token
        whose nonce is not greater than LastAdminNonce is rejected, so a token
        cannot be reused.
        """
        if not self.hard_lock:
            return True
        if not self._token_valid(token):
            return False
        self.hard_lock = False
        self.last_admin_nonce = token.nonce
        return True

    @staticmethod
    def _expected_hmac(p: OraclePayload) -> str:
        body = _payload_body(p.compliant_flag, p.failure_reason, p.weld_id, p.timestamp_utc, p.nonce)
        return hmac_lib.new(GATEWAY_KEY, body, hashlib.sha256).hexdigest()

    def process_cycle(self, p: OraclePayload) -> Tuple[PLCState, List[str]]:
        """One 500 ms PLC cycle (Algorithm 2, Steps 1-6)."""
        failures: List[str] = []

        # Step 2 — heartbeat timeout -> Soft Lock (clears once heartbeat restored)
        if p.latency_ms > HEARTBEAT_THRESHOLD_MS:
            self.soft_lock = True
            self.compliance_bit = False
            self.state = PLCState.SOFT_LOCK
            failures.append(f"STEP2_HEARTBEAT_TIMEOUT ({p.latency_ms:.1f} ms > 500 ms)")
            return self.state, failures
        self.soft_lock = False

        # Step 3 — HMAC-SHA256 and Oracle signature -> Hard Lock
        expected_hmac = self._expected_hmac(p)
        expected_sig = hashlib.sha256(expected_hmac.encode()).hexdigest()  # Ed25519 stand-in
        if not hmac_lib.compare_digest(p.hmac_sig, expected_hmac) or p.asym_sig != expected_sig:
            self.hard_lock = True
            self.compliance_bit = False
            self.state = PLCState.HARD_LOCK
            failures.append("STEP3_HMAC/SIG_FAIL (HardLock triggered)")
            return self.state, failures

        # Step 4 — monotonic nonce -> Hard Lock on a stale nonce
        if p.nonce <= self.last_nonce:
            self.hard_lock = True
            self.compliance_bit = False
            self.state = PLCState.HARD_LOCK
            failures.append(f"STEP4_REPLAY (nonce {p.nonce} <= LastNonce {self.last_nonce})")
            return self.state, failures
        self.last_nonce = p.nonce

        # Step 5 — an active Hard Lock blocks the cycle until a council reset
        if self.hard_lock:
            self.compliance_bit = False
            self.state = PLCState.HARD_LOCK
            failures.append("STEP5_HARDLOCK_ACTIVE (awaiting council reset)")
            return self.state, failures

        # Step 6 — Compliance Bit := result of checkCompliance (signed payload)
        self.compliance_bit = bool(p.compliant_flag)
        self.state = PLCState.COMPLIANT if self.compliance_bit else PLCState.NON_COMPLIANT
        if not self.compliance_bit:
            failures.append(f"STEP6_NON_COMPLIANT ({p.failure_reason})")
        return self.state, failures


class OracleGateway:
    """Builds signed payloads; draws one latency per payload from the assumed distributions."""

    BASE_TS = 1_760_000_000  # fixed epoch so that runs are fully deterministic

    def __init__(self, rng: np.random.Generator,
                 valid_mean: float = VALID_LATENCY_MEAN_MS, valid_sd: float = VALID_LATENCY_SD_MS,
                 timeout_mean: float = TIMEOUT_LATENCY_MEAN_MS, timeout_sd: float = TIMEOUT_LATENCY_SD_MS):
        self._rng = rng
        self._nonce = 0
        self._count = 0
        self.valid_mean, self.valid_sd = valid_mean, valid_sd
        self.timeout_mean, self.timeout_sd = timeout_mean, timeout_sd

    def build_payload(self, compliant: bool, reason: str, fault: FaultType,
                      replay_nonce: Optional[int] = None) -> OraclePayload:
        # REPLAY: the attacker retransmits a captured, validly signed payload whose
        # nonce the PLC has already accepted (replay_nonce = LastNonce); the
        # gateway's own counter is not advanced.
        if fault == FaultType.REPLAY:
            nonce = replay_nonce if replay_nonce is not None else self._nonce
        else:
            self._nonce += 1
            nonce = self._nonce
        self._count += 1
        ts = self.BASE_TS + self._count
        weld_id = hashlib.sha256(f"weld-{self._count}".encode()).hexdigest()[:16]

        if fault == FaultType.TIMEOUT:
            latency = float(self._rng.normal(self.timeout_mean, self.timeout_sd))
        else:
            latency = float(self._rng.normal(self.valid_mean, self.valid_sd))

        body = _payload_body(compliant, reason, weld_id, ts, nonce)
        hmac_sig = hmac_lib.new(GATEWAY_KEY, body, hashlib.sha256).hexdigest()
        asym_sig = hashlib.sha256(hmac_sig.encode()).hexdigest()
        if fault == FaultType.MITM:
            # tampered payload: the forwarded HMAC no longer matches the body
            hmac_sig = hashlib.sha256(b"forged" + body).hexdigest()

        return OraclePayload(compliant, reason, weld_id, ts, nonce, latency, hmac_sig, asym_sig)


def run_simulation(seed: int = SEED,
                   scenario_plan: Optional[Sequence[Tuple[int, FaultType, bool, str]]] = None,
                   gateway: Optional[OracleGateway] = None) -> List[PLCCycleResult]:
    """Monte Carlo check of the interlock logic (manuscript Section 3.4.3).

    Before each run HardLock (through a simulated council reset), SoftLock and
    the Compliance Bit are reset, so no lock state carries over between runs.
    The nonce ledger (LastNonce) is deliberately kept across runs; resetting it
    would make every replayed payload look fresh.
    """
    plan = list(scenario_plan) if scenario_plan is not None else DEFAULT_SCENARIO_PLAN
    rng = np.random.default_rng(seed)
    oracle = gateway or OracleGateway(rng)
    plc = ASI_PLC()
    results: List[PLCCycleResult] = []
    sid = 0
    admin_nonce = 0

    for count, fault, compliant, reason in plan:
        for _ in range(int(count)):
            if plc.hard_lock:
                admin_nonce += 1
                assert plc.council_reset(issue_reset_token(admin_nonce))
            plc.soft_lock = False
            plc.compliance_bit = False

            payload = oracle.build_payload(compliant, reason, fault, replay_nonce=plc.last_nonce)
            state, failures = plc.process_cycle(payload)
            results.append(PLCCycleResult(sid, fault, payload, state, plc.compliance_bit,
                                          plc.relay_on, payload.latency_ms, failures))
            sid += 1
    return results


def is_false_permit(r: PLCCycleResult) -> bool:
    """Compliance Bit TRUE although the payload was non-compliant, failed
    signature verification, carried a stale nonce, or arrived after 500 ms."""
    if not r.compliance_bit:
        return False
    return (r.fault_type in (FaultType.NON_COMPLY, FaultType.MITM, FaultType.REPLAY)
            or r.latency_ms > HEARTBEAT_THRESHOLD_MS)


def summarize(results: List[PLCCycleResult]) -> Dict:
    by = lambda f: [r for r in results if r.fault_type == f]
    valid = by(FaultType.NONE)
    lat = np.array([r.latency_ms for r in valid]) if valid else np.array([np.nan])
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.state.value] = counts.get(r.state.value, 0) + 1
    return {
        "n": len(results),
        "state_counts": counts,
        "valid_mean_ms": float(np.mean(lat)),
        "valid_p95_ms": float(np.percentile(lat, 95)),
        "valid_max_ms": float(np.max(lat)),
        "false_permits": sum(is_false_permit(r) for r in results),
        "false_negatives": sum(1 for r in valid if not r.compliance_bit),
        "timeout_runs": [(round(r.latency_ms, 1), r.state.value) for r in by(FaultType.TIMEOUT)],
        "by_fault": {f.value: {s.value: sum(1 for r in by(f) if r.state == s) for s in PLCState}
                     for f in FaultType},
    }


if __name__ == "__main__":
    s = summarize(run_simulation())
    print(json.dumps({k: v for k, v in s.items() if k != "by_fault"}, indent=2))
