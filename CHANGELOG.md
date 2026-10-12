# Changelog

## 1.1.0 — 2026-10

Aligns the repository with the Frontiers in Blockchain submission.

- **Single simulation core.** `atc_sim.py` now holds the Monte Carlo logic used by `Prototype.py`, `Prototype_app.py`, `paper_figures.py` and `reproduce_results.py`. Previously `Prototype.py` used N(275.0, 25.1) ms and gave 274.4 / 320.5 / 348.7 ms; it now uses the reported N(275.2, 25) ms and reproduces 274.6 / 320.6 / 348.6 ms.
- **Algorithm 2 order.** Signature verification (Step 3) now precedes the nonce check (Step 4), as in the manuscript; Hard Lock reset uses a council-signed, single-use token. Replay runs retransmit a captured, validly signed payload whose nonce the PLC already accepted. Runs are fully deterministic.
- **Analytical models in Python.** `atc_models.py` implements the mixed-population Weibull model (Equations 1–2, Table 6), the Paris–Erdogan model (Note S1, closed form) and the workforce DTMC (Note S2).
- **`reproduce_results.py`** recomputes 67 reported values and reports PASS/FAIL. **`paper_figures.py`** regenerates Figures 3–5, S1 and S2. Submitted figures are in `Images/`.
- **Smart contract.** `recordWeld` re-evaluates `checkCompliance` on-chain instead of accepting a caller-supplied flag and stores the reason code; `ComplianceDenied` reports the actual reason (previously always `PREHEAT_BELOW_MIN`); reason codes match Algorithm 1 (`DID_INVALID`, `CALIBRATION_EXPIRED`, `PREHEAT_LOW`, `INTERPASS_HIGH`, `HUMIDITY_HIGH`); calibration is stored as an expiry timestamp; credentials can be revoked; threshold updates need ⌈2/3⌉ of the council (minimum 3). Hardhat tests added. Moved to `contracts/`.
- **PLC specification.** `plc/ASI_ComplianceBit.st` rewritten without `GOTO` (not part of IEC 61131-3 ST), following Algorithm 2 step by step, with a timer-based heartbeat and a council-signed single-use reset; described as a production permissive in the standard (non-safety) program.
- **Wording.** Removed references to IEEE Access, the former title, IEEE-version section/figure numbers, a "SIL 2-rated safety PLC", automatic regulatory updates and latency values "from published benchmarks".
- Removed `gen_final_figs.py` (IEEE-version figures with different latency inputs) and `index.html` (unrelated personal page). Added `CITATION.cff`, `CHANGELOG.md`, `.gitignore`, `package.json`, `hardhat.config.js`.

## 1.0.0

Initial release (archived at https://doi.org/10.5281/zenodo.23322427; superseded by this version).
