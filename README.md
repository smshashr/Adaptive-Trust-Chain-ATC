# Adaptive Trust Chain (ATC) — companion code

Companion code for the article

> Ashraf, S. R. B., Rahman, H., Noche, B., and Gürpinar, T. *Adaptive Trust Chain: a permissioned blockchain framework for enforcing weld-parameter compliance at the controller level in green hydrogen infrastructure.* Frontiers in Blockchain (under review).

Chair of Transport Systems and Logistics (TuL), University of Duisburg-Essen, Germany · Islamic University of Technology, Bangladesh · Quinnipiac University, USA

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23325469.svg)](https://doi.org/10.5281/zenodo.23325469)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Code: https://github.com/smshashr/Adaptive-Trust-Chain-ATC · Archived version: https://doi.org/10.5281/zenodo.23325469

---

## Scope

The ATC is a five-layer permissioned blockchain framework (QBFT consensus) in which a signed **Compliance Bit** from the ledger acts as a **production permissive** at a programmable logic controller (PLC): the welding relay may be energized only when the ledger confirms that the welder's credential, the equipment calibration and the measured weld parameters are compliant.

Please read the code with the same caveats as the article:

- **The ATC is a design, not a deployed system.** No prototype has been run on PLC hardware or a production network. The contract has not been audited.
- **The interlock is not a safety function.** Personnel and machine safety remain with the hardware emergency stop and the other safety-related parts of the welding cell (ISO 13849-1), which act on the relay independently of the ledger, the Oracle Gateway and the network.
- **All quantitative inputs are scenario assumptions** (Supplementary Table S1). The Monte Carlo latencies are drawn from *assumed* distributions, N(275.2, 25) ms and N(514.6, 20) ms; they are not calibrated to a published benchmark or measured in an industrial environment. The simulation is a plausibility check of the interlock logic, not a performance validation.
- The Weibull, fatigue and workforce models illustrate their assumed inputs; they are not estimates of real failure rates, crack growth in a specific weld, or workforce statistics.

---

## Repository structure

```
├── contracts/
│   └── WeldComplianceASC.sol     Algorithm 1 — Solidity 0.8.20 Adaptive Smart Contract
├── plc/
│   └── ASI_ComplianceBit.st      Algorithm 2 — IEC 61131-3 Structured Text compliance-bit logic
├── test/
│   └── WeldComplianceASC.test.js Hardhat tests of the contract against Algorithm 1
├── atc_sim.py                    Monte Carlo core of the ASI-PLC interlock (Section 3.4.3)
├── atc_models.py                 Weibull, Paris–Erdogan and DTMC scenario models
├── reproduce_results.py          Recomputes every reported number and checks it (PASS/FAIL)
├── paper_figures.py              Regenerates Figures 3–5 and Supplementary Figures S1–S2
├── Prototype.py                  Command-line Monte Carlo run + diagnostic figures D1–D5
├── Prototype_app.py              Interactive Streamlit front end (same core as Prototype.py)
├── ATC_Phase4_Simulator.html     Browser demonstrator (single weld, Monte Carlo, Weibull/PCR)
├── Images/
│   ├── Figure_1.png … Figure_5.png, Figure_S1.png, Figure_S2.png   figures as submitted
│   ├── reproduced/               output of paper_figures.py
│   └── diagnostics/              output of Prototype.py (not article figures)
├── hardhat.config.js, package.json
├── requirements.txt, run_atc_app.bat
├── CITATION.cff, LICENSE
└── README.md
```

| File | Article reference | Content |
| --- | --- | --- |
| `contracts/WeldComplianceASC.sol` | Section 3.2.3, Algorithm 1 | `checkCompliance` (view), `recordWeld`, `attachNDT`, credential and calibration registries, council-governed threshold updates |
| `plc/ASI_ComplianceBit.st` | Section 3.2.4, Algorithm 2, Figure 2 | Heartbeat, signature and nonce checks; Soft Lock and Hard Lock; council-signed single-use reset |
| `atc_sim.py`, `Prototype.py` | Sections 3.4.3 and 4.4, Figure 5, Supplementary Table S2 | Monte Carlo check (n = 200, seed 2025) |
| `atc_models.py` | Sections 3.4.1–3.4.2, 4.2–4.3, Figures 3–4, Table 6; Supplementary Notes S1–S2 | Mixed-population Weibull model; Paris–Erdogan crack growth; workforce DTMC |
| `reproduce_results.py` | all of the above | 67 reported values recomputed and compared |
| `paper_figures.py` | Figures 3, 4, 5, S1, S2 | Figures regenerated from the models |

Figures 1 (architecture) and 2 (state machine) are diagrams and are provided as images only.

---

## Quick start

```bash
# Python 3.10 or later
pip install -r requirements.txt

python reproduce_results.py     # recompute and check all reported values
python paper_figures.py         # regenerate Figures 3–5, S1, S2 into Images/reproduced/
python Prototype.py             # Monte Carlo summary + diagnostic figures into Images/diagnostics/
streamlit run Prototype_app.py  # interactive runs (Windows: run_atc_app.bat)
```

Smart-contract tests (Node.js 18 or later; Hardhat downloads solc 0.8.20 on first use):

```bash
npm install
npx hardhat test
```

The browser demonstrator `ATC_Phase4_Simulator.html` opens directly in a browser. Its JavaScript random-number generator differs from NumPy, so it does not reproduce Supplementary Table S2 run for run; use the Python scripts for the reported values.

---

## Reproducing the reported results

`python reproduce_results.py` prints one line per reported value and ends with `67/67 values reproduced at the reported precision.` It covers:

| Result | Reported values |
| --- | --- |
| Mixed-population Weibull model (β = 2.5, ηc = 50 yr, ηn = 8 yr) | P_fail(10) = 34.1% (PCR 0.60) and 4.2% (PCR 0.97), relative reduction 87.7%; at 30 years 54.6% and 26.6% (51.3%); 83.9% and 80.9% against PCR 0.70 and 0.75 |
| Table 6 sensitivity | nine parameter sets; 10-year reduction 78.7–90.4%; 30-year reduction 36.0–62.4% |
| Survival and hazard | R_c(10) = 0.98, R_c(30) = 0.76, R_n(10) = 0.17; hazard ratio (ηc/ηn)^β ≈ 98 |
| Monte Carlo (n = 200, seed 2025) | 121 COMPLIANT, 50 NON_COMPLIANT, 20 HARD_LOCK, 9 SOFT_LOCK; no false permits; valid-run latency mean 274.6 ms, 95th percentile 320.6 ms, maximum 348.6 ms; one timeout-scenario sample at 486.2 ms correctly permitted |
| Fatigue (Note S1) | fracture after 53.6 yr (C_air) and 13.4 yr (C_H = 4 C_air); a(30 yr) ≈ 1.6 mm |
| Workforce DTMC (Note S2) | H₂-ready share at year 10: 12.3% and 58.0%; stationary shares 22.6% and 90.0% |

### Monte Carlo design

Five scenario blocks are executed in a fixed order: 120 valid-credential runs, 50 runs with non-compliant preheat, 10 Oracle man-in-the-middle runs (tampered HMAC), 10 replay runs (a captured, validly signed payload whose nonce was already accepted) and 10 heartbeat-timeout runs. Before each run, HardLock (through a simulated council reset), SoftLock and the Compliance Bit are reset; the nonce ledger (LastNonce) is kept across runs so that replayed payloads remain detectable. A *false permit* is a run in which the Compliance Bit became TRUE although the payload was non-compliant, failed signature verification, carried a stale nonce, or arrived after the 500 ms threshold.

HMAC-SHA256 is computed for real. The Ed25519 Oracle signature is represented by a stand-in digest; a deployment would use a real Ed25519 key held in a hardware security module (Security Assumption SA2).

---

## Smart contract (`contracts/WeldComplianceASC.sol`)

- **`checkCompliance`** is a read-only (`view`) function that evaluates the five conditions of Algorithm 1 in order and returns the reason codes used in the article: `DID_INVALID` (credential not registered, revoked or expired; ISO 9606-1 two-year window), `CALIBRATION_EXPIRED`, `PREHEAT_LOW` (WPS minimum, ISO 15614-1), `INTERPASS_HIGH` (EN 1011-2 ceiling), `HUMIDITY_HIGH`, or `COMPLIANT`. Because it is a view call, the 500 ms permissive check never waits for block inclusion.
- **`recordWeld`** runs after the weld, off the real-time path. It re-evaluates `checkCompliance` on-chain from the logged parameters, increments the per-equipment sequence counter, derives `weldID = keccak256(welderDID ‖ equipmentID ‖ seq)` (not `block.timestamp`, which the block proposer can influence) and anchors the record, including non-compliant outcomes and their reason code.
- **`attachNDT`** (certifiers only) links the SHA-256 hash and IPFS CID of the NDT report to an existing weld record, once.
- **Threshold governance**: thresholds change only when a council proposal reaches ⌈2/3 × council size⌉ signatures, and never fewer than three. The contract does not adapt to new regulations automatically.
- Only hashes and pseudonymous identifiers are stored on-chain; personal data stay off-chain (article Section 5.3).

Example constructor arguments (fixed-point ×10): `minPreheat = 1000` (100.0 °C), `maxInterpass = 2500`, `minHumidity = 0` (stored, not evaluated), `maxHumidity = 800`, `minNDT = 900`.

## PLC logic (`plc/ASI_ComplianceBit.st`)

Vendor-neutral IEC 61131-3 Structured Text for the standard (non-safety) program of the PLC, 500 ms cycle, power-up default `ComplianceBit := FALSE`:

| Step | Check | Result |
| --- | --- | --- |
| 1 | Read the Oracle payload (OPC UA) | — |
| 2 | Heartbeat timeout (no new payload within 500 ms) | SOFT_LOCK; clears automatically when the heartbeat is restored |
| 3 | HMAC-SHA256 and Ed25519 signature | HARD_LOCK on failure |
| 4 | Monotonic nonce | HARD_LOCK on a stale nonce |
| 5 | Active Hard Lock | cleared only by a council-signed, single-use reset token (nonce > LastAdminNonce) |
| 6 | Compliance Bit | `ComplianceBit := OraclePayload.compliant` |

Signature verification is delegated to a vendor crypto/HSM function block whose results are mapped to the inputs `HmacValid`, `OracleSigValid` and `AdminTokenSigValid`. The file has not been compiled for or run on a specific PLC.

---

## Limitations

- No physical prototype or production network; all artefacts are design-level specifications and simulations.
- Latency distributions are assumed, not measured; field measurements under industrial network and electromagnetic conditions are required.
- The interlock cannot detect sensor drift or a physical bypass (bridged relay, welding set not connected to the interlock); these need metrological and organizational controls (article Table 5).
- Demonstration keys are hard-coded for reproducibility and must never be used outside this simulation.

---

## Citation

Please cite the article and the archived software version:

```bibtex
@software{ashraf2026atc_code,
  author    = {Ashraf, Sk. Riad Bin and Rahman, Hasibur and Noche, Bernd and G{\"u}rpinar, Tan},
  title     = {Adaptive Trust Chain (ATC): executable specification and reference smart contract},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23325469},
  url       = {https://doi.org/10.5281/zenodo.23325469}
}

@article{ashraf2026atc,
  author  = {Ashraf, Sk. Riad Bin and Rahman, Hasibur and Noche, Bernd and G{\"u}rpinar, Tan},
  title   = {Adaptive Trust Chain: a permissioned blockchain framework for enforcing
             weld-parameter compliance at the controller level in green hydrogen infrastructure},
  journal = {Frontiers in Blockchain},
  year    = {2026},
  note    = {Under review}
}
```

## Authors and contact

Sk. Riad Bin Ashraf, Hasibur Rahman, Bernd Noche, Tan Gürpinar
Correspondence: riad.ashraf@uni-due.de

## License

MIT (see [LICENSE](LICENSE)). This is a research prototype provided without warranty; it must not be used as-is in production, safety-related or regulatory contexts.
