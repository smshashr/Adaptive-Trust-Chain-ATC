(*
 * ASI_ComplianceBit.st
 * IEC 61131-3 Structured Text — Adaptive Smart Interlock (ASI)
 * Compliance-bit logic of Algorithm 2
 *
 * Reference specification for:
 *   Ashraf, S. R. B., Rahman, H., Noche, B., and Gürpinar, T.
 *   "Adaptive Trust Chain: a permissioned blockchain framework for enforcing
 *   weld-parameter compliance at the controller level in green hydrogen
 *   infrastructure." Frontiers in Blockchain (under review).
 *
 * SCOPE — PRODUCTION PERMISSIVE, NOT A SAFETY FUNCTION
 *   The ASI decides whether a weld may START on the basis of process-quality
 *   conditions. Personnel and machine safety remain with the hardware
 *   emergency stop and the other safety-related parts of the welding cell
 *   (ISO 13849-1), which act on the relay independently of the ledger, the
 *   Oracle Gateway and the network. On a safety PLC this program runs in the
 *   STANDARD (non-safety) program, never in the safety program.
 *
 * Cycle: 500 ms.  Power-up default: ComplianceBit := FALSE (fail-locked).
 *
 * Algorithm 2 (as in the manuscript)
 *   Step 1  read OraclePayload from the Oracle Gateway (OPC UA)
 *   Step 2  heartbeat timeout            -> SoftLock (clears when heartbeat restored)
 *   Step 3  HMAC-SHA256 / Ed25519 check  -> HardLock
 *   Step 4  monotonic nonce check        -> HardLock on a stale nonce
 *   Step 5  HardLock cleared only by a council-signed, single-use reset token
 *   Step 6  ComplianceBit := OraclePayload.compliant
 *
 * Cryptographic verification (HMAC_VERIFY, SIG_VERIFY) is performed by a
 * vendor crypto/HSM function block; its results are mapped to the inputs
 * HmacValid, OracleSigValid and AdminTokenSigValid below. This file is a
 * vendor-neutral specification and has not been run on PLC hardware.
 *)

TYPE ASI_State :
(
    ST_NON_COMPLIANT := 0,   (* power-up default; relay not permitted *)
    ST_COMPLIANT     := 1,   (* relay may be energized                *)
    ST_SOFT_LOCK     := 2,   (* heartbeat loss; clears automatically  *)
    ST_HARD_LOCK     := 3    (* signature failure or replay; latched  *)
);
END_TYPE

TYPE OraclePayload :
STRUCT
    compliant  : BOOL;    (* result of ASC.checkCompliance (read-only call)   *)
    reason     : DWORD;   (* coded reason (COMPLIANT, PREHEAT_LOW, ...)       *)
    nonce      : UDINT;   (* monotonically increasing; covered by signatures *)
    timestamp  : UDINT;   (* Unix time (s)                                    *)
END_STRUCT
END_TYPE

PROGRAM ASI_ComplianceBit

VAR CONSTANT
    HEARTBEAT_TIMEOUT : TIME := T#500MS;
END_VAR

VAR_INPUT
    (* From the OPC UA subscription to the Oracle Gateway *)
    NewPayload         : BOOL;           (* rising edge: a new payload arrived    *)
    Payload            : OraclePayload;
    (* From the crypto/HSM function block (evaluated on Payload) *)
    HmacValid          : BOOL;           (* HMAC_VERIFY(Payload, SharedKey)       *)
    OracleSigValid     : BOOL;           (* SIG_VERIFY(Payload, OraclePublicKey)  *)
    (* Council reset request (Security Assumption SA3) *)
    AdminReset         : BOOL;
    AdminTokenNonce    : UDINT;
    AdminTokenSigValid : BOOL;           (* SIG_VERIFY(AdminToken, CouncilPublicKey) *)
    AdminID            : DWORD;
END_VAR

VAR_OUTPUT
    ComplianceBit      : BOOL := FALSE;  (* permissive to the welding relay       *)
    State              : ASI_State := ST_NON_COMPLIANT;
    SoftLock           : BOOL := FALSE;
    HardLock           : BOOL := FALSE;
    SecurityEvent      : BOOL := FALSE;  (* pulse: HMAC/SIG fail or replay        *)
    ResetEvent         : BOOL := FALSE;  (* pulse: HardLock cleared by council    *)
END_VAR

VAR
    LastNonce          : UDINT := 0;     (* nonce ledger; never reset in operation *)
    LastAdminNonce     : UDINT := 0;
    HeartbeatTimer     : TON;
    NewPayloadEdge     : R_TRIG;
    CycleDone          : BOOL;
    (* diagnostics *)
    SoftLockCount      : UDINT := 0;
    HardLockCount      : UDINT := 0;
    LastResetAdminID   : DWORD := 0;
END_VAR

(* ── Step 1: read payload; heartbeat timer restarts on every new payload ── *)
NewPayloadEdge(CLK := NewPayload);
HeartbeatTimer(IN := NOT NewPayloadEdge.Q, PT := HEARTBEAT_TIMEOUT);

CycleDone     := FALSE;
SecurityEvent := FALSE;
ResetEvent    := FALSE;

(* ── Step 2: heartbeat timeout -> Soft Lock ─────────────────────────────── *)
IF HeartbeatTimer.Q THEN
    IF NOT SoftLock THEN
        SoftLockCount := SoftLockCount + 1;
    END_IF;
    SoftLock      := TRUE;
    ComplianceBit := FALSE;
    State         := ST_SOFT_LOCK;
    CycleDone     := TRUE;
ELSE
    SoftLock := FALSE;                       (* clears once heartbeat restored *)
END_IF;

(* Only a newly received payload is evaluated in Steps 3, 4 and 6 *)
IF NOT CycleDone AND NewPayloadEdge.Q THEN

    (* ── Step 3: HMAC-SHA256 and Ed25519 signature -> Hard Lock ────────── *)
    IF NOT HmacValid OR NOT OracleSigValid THEN
        HardLock      := TRUE;
        ComplianceBit := FALSE;
        State         := ST_HARD_LOCK;
        SecurityEvent := TRUE;               (* Log_Security_Event: 'HMAC/SIG FAIL' *)
        HardLockCount := HardLockCount + 1;
        CycleDone     := TRUE;

    (* ── Step 4: monotonic nonce -> Hard Lock on a stale nonce ─────────── *)
    ELSIF Payload.nonce <= LastNonce THEN
        HardLock      := TRUE;
        ComplianceBit := FALSE;
        State         := ST_HARD_LOCK;
        SecurityEvent := TRUE;               (* Log_Security_Event: 'REPLAY - stale nonce' *)
        HardLockCount := HardLockCount + 1;
        CycleDone     := TRUE;
    ELSE
        LastNonce := Payload.nonce;
    END_IF;
END_IF;

(* ── Step 5: Hard Lock persists until a council-signed, single-use token ── *)
IF HardLock THEN
    (* a lock latched in this cycle cannot be cleared in the same cycle *)
    IF NOT SecurityEvent AND AdminReset AND AdminTokenSigValid
       AND (AdminTokenNonce > LastAdminNonce) THEN
        HardLock         := FALSE;
        LastAdminNonce   := AdminTokenNonce;  (* token cannot be reused *)
        LastResetAdminID := AdminID;
        ResetEvent       := TRUE;             (* Log_Reset(NOW, AdminID) *)
        ComplianceBit    := FALSE;            (* a new verified payload is required *)
        State            := ST_NON_COMPLIANT;
    ELSE
        ComplianceBit := FALSE;
        State         := ST_HARD_LOCK;
    END_IF;
    CycleDone := TRUE;
END_IF;

(* ── Step 6: Compliance Bit := result of checkCompliance (signed payload) ─ *)
IF NOT CycleDone AND NewPayloadEdge.Q THEN
    ComplianceBit := Payload.compliant;
    IF ComplianceBit THEN
        State := ST_COMPLIANT;
    ELSE
        State := ST_NON_COMPLIANT;
    END_IF;
END_IF;

(* Between payloads the last verified decision is held while the heartbeat
   is alive; any lock forces the permissive to FALSE. *)
IF SoftLock OR HardLock THEN
    ComplianceBit := FALSE;
END_IF;

END_PROGRAM
