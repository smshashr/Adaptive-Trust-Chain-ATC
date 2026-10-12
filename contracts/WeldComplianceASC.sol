// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title WeldComplianceASC
 * @notice Adaptive Smart Contract — Regulatory Enforcement Kernel of the
 *         Adaptive Trust Chain (ATC) framework for green hydrogen infrastructure.
 *
 * @dev Reference implementation of Algorithm 1 in:
 *      Ashraf, S. R. B., Rahman, H., Noche, B., and Gürpinar, T.
 *      "Adaptive Trust Chain: a permissioned blockchain framework for
 *      enforcing weld-parameter compliance at the controller level in green
 *      hydrogen infrastructure." Frontiers in Blockchain (under review).
 *
 *      Target: EVM-compatible permissioned network with QBFT consensus
 *      (e.g. Hyperledger Besu). Research prototype — not audited and not
 *      deployed; see README for scope and limitations.
 *
 *      Thresholds are taken from the qualified welding procedure specification
 *      and applied within ISO 9606-1, ISO 15614-1, EN 1011-2, ISO 3834-2 and,
 *      for pressure vessels, EN 13445. They change ONLY when the governance
 *      council approves an update; the contract does not adapt to new
 *      regulations automatically.
 *
 * @dev Design notes
 *      - checkCompliance() is a read-only (view) function, so the 500 ms
 *        permissive check never waits for block inclusion.
 *      - recordWeld() is executed after the weld: it re-evaluates
 *        checkCompliance() against the logged parameters, increments the
 *        per-equipment sequence counter, derives the weldID and anchors the
 *        record, including non-compliant outcomes (Algorithm 1, Steps 7-10).
 *      - attachNDT() links the NDT result hash and IPFS CID after inspection
 *        (Algorithm 1, Steps 11-12).
 *      - Threshold updates need at least two thirds of the governance council
 *        and never fewer than MIN_SIGNATORIES signatures (Table 3).
 *      - The credential registry is keyed by hashes of W3C DIDs; only hashes
 *        and pseudonymous identifiers are stored on-chain (GDPR, Section 5.3).
 */
contract WeldComplianceASC {

    // ─────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────

    event ComplianceGranted(
        bytes32 indexed welderDID,
        bytes32 indexed weldID,
        bytes32          equipmentID,
        uint256          timestamp
    );

    event ComplianceDenied(
        bytes32 indexed welderDID,
        bytes32 indexed weldID,
        bytes32          failureReason,
        uint256          timestamp
    );

    event WeldRecorded(
        bytes32 indexed weldID,
        bytes32 indexed welderDID,
        bytes32          equipmentID,
        bytes32          ndtHash,
        string           ipfsCid,
        uint256          timestamp
    );

    event ThresholdUpdated(
        bytes32 indexed paramName,
        uint256          oldValue,
        uint256          newValue,
        address          updatedBy,
        uint256          timestamp
    );

    event CredentialRegistered(
        bytes32 indexed welderDID,
        uint256          expiry,
        address          registrar
    );

    event CredentialRevoked(
        bytes32 indexed welderDID,
        address          registrar
    );

    event CalibrationSet(
        bytes32 indexed equipmentID,
        uint256          calibrationExpiry,
        address          registrar
    );

    event GovernanceProposalSubmitted(
        bytes32 indexed proposalID,
        bytes32          paramName,
        uint256          proposedValue,
        address          proposer
    );

    event GovernanceProposalExecuted(
        bytes32 indexed proposalID,
        uint256          signatoryCount
    );

    /// @notice Emitted when NDT inspection report is linked to a weld record
    event NDTLinked(
        bytes32 indexed weldID,
        bytes32          ndtHash,
        string           ipfsCid
    );

    // ─────────────────────────────────────────────────────────────────────
    // Failure reason codes (returned as bytes32 for gas efficiency)
    // ─────────────────────────────────────────────────────────────────────

    // Codes as in Algorithm 1 of the manuscript
    bytes32 public constant REASON_COMPLIANT    = "COMPLIANT";
    bytes32 public constant REASON_DID_INVALID  = "DID_INVALID";          // not registered, revoked or expired
    bytes32 public constant REASON_CALIBRATION  = "CALIBRATION_EXPIRED";
    bytes32 public constant REASON_PREHEAT      = "PREHEAT_LOW";
    bytes32 public constant REASON_INTERPASS    = "INTERPASS_HIGH";
    bytes32 public constant REASON_HUMIDITY     = "HUMIDITY_HIGH";

    // ─────────────────────────────────────────────────────────────────────
    // Governance constants
    // ─────────────────────────────────────────────────────────────────────

    uint256 public constant MIN_SIGNATORIES = 3;   // floor; the 2/3 quorum applies above it
    uint256 public constant CERT_VALIDITY   = 2 * 365 days; // ISO 9606-1: 2-year window

    // ─────────────────────────────────────────────────────────────────────
    // Compliance threshold struct (updatable via multi-sig governance)
    // ─────────────────────────────────────────────────────────────────────

    struct ComplianceThresholds {
        uint256 minPreheatTemp;   // °C × 10 (fixed-point, ISO 15614-1 / EN 1011-2)
        uint256 maxInterpassTemp; // °C × 10
        uint256 minHumidity;      // % RH × 10  (EN 1011-2 lower bound)
        uint256 maxHumidity;      // % RH × 10  (EN 1011-2 upper bound)
        uint256 minNDTCoverage;   // % × 10 (ISO 17635)
    }

    ComplianceThresholds public thresholds;

    // ─────────────────────────────────────────────────────────────────────
    // Registries
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Welder credential registry: DID hash → certificate expiry (Unix ts)
    mapping(bytes32 => uint256) public welderRegistry;

    /// @notice Revoked welder credentials (DID no longer active)
    mapping(bytes32 => bool) public welderRevoked;

    /// @notice Equipment calibration registry: equipmentID → calibration expiry (Unix ts)
    mapping(bytes32 => uint256) public calibrationExpiry;

    /// @notice Per-equipment weld sequence counter (incremented on recordWeld)
    mapping(bytes32 => uint256) public weldSequence;

    /// @notice Structural Passport store: weldID → StructuralPassport
    mapping(bytes32 => StructuralPassport) public structuralPassports;

    // ─────────────────────────────────────────────────────────────────────
    // Structural Passport entry (weld-level DPP record, aligned with ESPR 2024/1781)
    // ─────────────────────────────────────────────────────────────────────

    struct StructuralPassport {
        bytes32 welderDID;
        bytes32 equipmentID;
        uint256 preheatTemp;
        uint256 interpassTemp;
        uint256 humidity;
        bytes32 batchID;       // Production batch identifier (Algorithm 1 Step 10)
        bytes32 ndtHash;       // SHA-256 of NDT result file, stored on IPFS
        string  ipfsCid;       // IPFS content address for full NDT report
        uint256 timestamp;
        uint256 sequenceNo;
        bool    compliant;
        bytes32 reason;        // checkCompliance() reason code at recordWeld time
    }

    // ─────────────────────────────────────────────────────────────────────
    // Multi-sig governance
    // ─────────────────────────────────────────────────────────────────────

    struct GovernanceProposal {
        bytes32 paramName;
        uint256 proposedValue;
        uint256 signatureCount;
        bool    executed;
        mapping(address => bool) signed;
    }

    mapping(bytes32 => GovernanceProposal) private _proposals;

    /// @notice Authorised governance council members (notified bodies, regulators)
    mapping(address => bool) public governanceCouncil;

    /// @notice Number of active council members (for the 2/3 quorum)
    uint256 public councilSize;

    /// @notice Authorised credential registrars (GSI/SLV personnel, QWI)
    mapping(address => bool) public credentialRegistrars;

    /// @notice Authorised NDT certifiers (inspection body personnel)
    mapping(address => bool) public ndtCertifiers;

    address public owner;

    // ─────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @param _minPreheat   ISO 15614-1 minimum preheat temperature (°C × 10)
     * @param _maxInterpass ISO 15614-1 maximum inter-pass temperature (°C × 10)
     * @param _minHumidity  Retained for governance; minimum humidity (% RH × 10) — not evaluated in checkCompliance
     * @param _maxHumidity  EN 1011-2 maximum ambient humidity (% RH × 10)
     * @param _minNDT       ISO 17635 minimum NDT coverage (% × 10)
     */
    constructor(
        uint256 _minPreheat,
        uint256 _maxInterpass,
        uint256 _minHumidity,
        uint256 _maxHumidity,
        uint256 _minNDT
    ) {
        owner = msg.sender;
        governanceCouncil[msg.sender]   = true;
        councilSize                      = 1;
        credentialRegistrars[msg.sender] = true;
        ndtCertifiers[msg.sender]        = true;

        thresholds = ComplianceThresholds({
            minPreheatTemp:   _minPreheat,
            maxInterpassTemp: _maxInterpass,
            minHumidity:      _minHumidity,
            maxHumidity:      _maxHumidity,
            minNDTCoverage:   _minNDT
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "ATC: not owner");
        _;
    }

    modifier onlyCouncil() {
        require(governanceCouncil[msg.sender], "ATC: not governance council");
        _;
    }

    modifier onlyRegistrar() {
        require(credentialRegistrars[msg.sender], "ATC: not registrar");
        _;
    }

    modifier onlyCertifier() {
        require(ndtCertifiers[msg.sender], "ATC: not NDT certifier");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Algorithm 1: checkCompliance (VIEW — no state change)
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Evaluate all compliance conditions for a planned weld operation.
     *         Called by the Oracle gateway BEFORE each weld; result sets the
     *         ASI-PLC Compliance Bit.
     *
     * @dev    This is a pure VIEW function — no storage writes, no events.
     *         State is written separately via recordWeld() after physical
     *         completion, keeping the critical latency path minimal.
     *
     * @param welderDID    keccak256 hash of welder's W3C DID
     * @param equipmentID  keccak256 hash of equipment identifier
     * @param preheatTemp  Measured pre-heat temperature (°C × 10)
     * @param interpassT   Measured inter-pass temperature (°C × 10)
     * @param humidity     Measured ambient humidity (% RH × 10)
     *
     * @return compliant   TRUE if all five conditions pass (Algorithm 1, Steps 1-6)
     * @return reason      Coded failure reason (or REASON_COMPLIANT on pass)
     *
     * @dev NDT hash is NOT checked here — NDT results are available only after
     *      physical inspection and are linked post-weld via attachNDT() (Steps 11-12).
     */
    function checkCompliance(
        bytes32 welderDID,
        bytes32 equipmentID,
        uint256 preheatTemp,
        uint256 interpassT,
        uint256 humidity
    )
        public
        view
        returns (bool compliant, bytes32 reason)
    {
        // Step 1 — Welder DID active and within validity window (ISO 9606-1: 2 years)
        if (
            welderRegistry[welderDID] == 0 ||
            welderRevoked[welderDID] ||
            block.timestamp > welderRegistry[welderDID]
        ) {
            return (false, REASON_DID_INVALID);
        }

        // Step 2 — Equipment calibration still valid
        if (block.timestamp > calibrationExpiry[equipmentID]) {
            return (false, REASON_CALIBRATION);
        }

        // Step 3 — Pre-heat temperature minimum (ISO 15614-1 / EN 1011-2 WPS minimum)
        if (preheatTemp < thresholds.minPreheatTemp) {
            return (false, REASON_PREHEAT);
        }

        // Step 4 — Inter-pass temperature ceiling (EN 1011-2)
        if (interpassT > thresholds.maxInterpassTemp) {
            return (false, REASON_INTERPASS);
        }

        // Step 5 — Ambient humidity: above maximum set for procedure (EN 1011-2)
        if (humidity > thresholds.maxHumidity) {
            return (false, REASON_HUMIDITY);
        }

        // Step 6 — All checks passed
        return (true, REASON_COMPLIANT);
    }

    // ─────────────────────────────────────────────────────────────────────
    // recordWeld — write Structural Passport entry after physical completion
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Record a completed weld operation to the Structural Passport.
     *         Called after the weld, off the real-time path. The compliance
     *         outcome is RE-EVALUATED on-chain from the logged parameters
     *         (Algorithm 1, Step 7); it is not supplied by the caller.
     *
     * @param welderDID    keccak256 hash of welder DID
     * @param equipmentID  keccak256 hash of equipment ID
     * @param preheatTemp  Recorded pre-heat temperature (°C × 10)
     * @param interpassT   Recorded inter-pass temperature (°C × 10)
     * @param humidity     Recorded humidity (% RH × 10)
     * @param batchID      Production batch identifier (keccak256) — Algorithm 1 Step 10
     *
     * @return weldID      keccak256(welderDID ‖ equipmentID ‖ seq)
     *                     where seq = weldSequence[equipmentID]++ (Algorithm 1, Steps 8-9).
     *                     Sequence counter is used — NOT block.timestamp — to avoid
     *                     block-proposer timestamp manipulation on QBFT networks.
     *
     * @dev NDT hash is NOT recorded here; it is linked after inspection via attachNDT().
     */
    function recordWeld(
        bytes32 welderDID,
        bytes32 equipmentID,
        uint256 preheatTemp,
        uint256 interpassT,
        uint256 humidity,
        bytes32 batchID
    )
        external
        onlyRegistrar
        returns (bytes32 weldID)
    {
        // Algorithm 1 Step 7: (ok, reason) ← checkCompliance(logged parameters)
        // NOTE: evaluated at the block time of recordWeld, i.e. after the weld.
        (bool compliant, bytes32 reason) =
            checkCompliance(welderDID, equipmentID, preheatTemp, interpassT, humidity);

        // Algorithm 1 Step 8: seq ← weldSequence[equipmentID]++
        uint256 seq = weldSequence[equipmentID];
        weldSequence[equipmentID] = seq + 1;

        // Algorithm 1 Step 9: weldID ← keccak256(welderDID ‖ equipmentID ‖ seq)
        // Uses per-equipment sequence counter — NOT block.timestamp — to ensure
        // deterministic, manipulation-resistant weld identity derivation.
        weldID = keccak256(abi.encodePacked(welderDID, equipmentID, seq));

        // Algorithm 1 Step 10: weldRecord[weldID] ← {welderDID, equipmentID, parameters, batchID, ok, reason}
        StructuralPassport storage sp = structuralPassports[weldID];
        sp.welderDID     = welderDID;
        sp.equipmentID   = equipmentID;
        sp.preheatTemp   = preheatTemp;
        sp.interpassTemp = interpassT;
        sp.humidity      = humidity;
        sp.batchID       = batchID;
        sp.timestamp     = block.timestamp;
        sp.sequenceNo    = seq;
        sp.compliant     = compliant;
        sp.reason        = reason;
        // ndtHash and ipfsCid are left empty — filled later via attachNDT()

        if (compliant) {
            emit ComplianceGranted(welderDID, weldID, equipmentID, block.timestamp);
        } else {
            emit ComplianceDenied(welderDID, weldID, reason, block.timestamp);
        }

        emit WeldRecorded(
            weldID, welderDID, equipmentID, bytes32(0), "", block.timestamp
        );

        return weldID;
    }

    // ─────────────────────────────────────────────────────────────────────
    // attachNDT — Algorithm 1, Steps 11-12
    // Link NDT inspection report to an existing weld record (post-weld)
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Attach an NDT inspection report to an existing weld record.
     *         Called by an authorised NDT certifier after physical inspection.
     *         Implements Algorithm 1, Steps 11-12.
     *
     * @dev    - Requires the weld record to exist (welderDID != 0).
     *         - Requires the ndtHash slot to be empty (one-time write — immutable
     *           once set, preventing post-certification tampering).
     *         - onlyCertifier: restricted to inspection body personnel.
     *
     * @param weldID   keccak256 weld identifier (returned by recordWeld)
     * @param ndtHash  SHA-256 of the NDT result file (bytes32)
     * @param ipfsCid  IPFS content address for the full NDT report
     */
    function attachNDT(
        bytes32 weldID,
        bytes32 ndtHash,
        string  calldata ipfsCid
    )
        external
        onlyCertifier
    {
        // Algorithm 1 Step 11: REQUIRE weldRecord[weldID] exists AND ndtHash is empty
        StructuralPassport storage sp = structuralPassports[weldID];
        require(sp.welderDID != bytes32(0), "ATC: weld record not found");
        require(sp.ndtHash == bytes32(0),   "ATC: NDT already attached");
        require(ndtHash != bytes32(0),      "ATC: ndtHash must not be zero");

        // Algorithm 1 Step 12: write ndtHash and ipfsCid; emit NDTLinked
        sp.ndtHash  = ndtHash;
        sp.ipfsCid  = ipfsCid;

        emit NDTLinked(weldID, ndtHash, ipfsCid);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Credential registry management
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Register or renew a welder's DID-based certificate.
     * @param welderDID   keccak256 hash of the welder's W3C DID
     * @param expiryTs    Certificate expiry as Unix timestamp
     */
    function registerWelder(bytes32 welderDID, uint256 expiryTs)
        external
        onlyRegistrar
    {
        require(expiryTs > block.timestamp, "ATC: expiry must be future");
        require(
            expiryTs <= block.timestamp + CERT_VALIDITY + 30 days,
            "ATC: expiry exceeds ISO 9606-1 two-year window"
        );
        welderRegistry[welderDID] = expiryTs;
        welderRevoked[welderDID]  = false;
        emit CredentialRegistered(welderDID, expiryTs, msg.sender);
    }

    /**
     * @notice Revoke a welder's DID-based credential (e.g. withdrawn qualification).
     */
    function revokeWelder(bytes32 welderDID) external onlyRegistrar {
        welderRevoked[welderDID] = true;
        emit CredentialRevoked(welderDID, msg.sender);
    }

    /**
     * @notice Register or update the calibration validity of a welding set.
     * @param equipmentID  keccak256 hash of equipment identifier
     * @param expiryTs     End of the calibration validity (Unix ts); 0 marks it invalid
     */
    function setCalibration(bytes32 equipmentID, uint256 expiryTs)
        external
        onlyRegistrar
    {
        calibrationExpiry[equipmentID] = expiryTs;
        emit CalibrationSet(equipmentID, expiryTs, msg.sender);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Multi-signature threshold governance
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Propose a threshold update. It is executed once at least two
     *         thirds of the council (and never fewer than MIN_SIGNATORIES
     *         members) have signed. Thresholds never change automatically.
     *
     * @param paramName     Human-readable parameter name (bytes32)
     * @param proposedValue New threshold value
     * @return proposalID   keccak256(paramName ‖ proposedValue ‖ block.timestamp)
     */
    function proposeThresholdUpdate(bytes32 paramName, uint256 proposedValue)
        external
        onlyCouncil
        returns (bytes32 proposalID)
    {
        proposalID = keccak256(
            abi.encodePacked(paramName, proposedValue, block.timestamp, msg.sender)
        );
        GovernanceProposal storage p = _proposals[proposalID];
        p.paramName      = paramName;
        p.proposedValue  = proposedValue;
        p.executed       = false;
        p.signed[msg.sender] = true;
        p.signatureCount = 1;

        emit GovernanceProposalSubmitted(proposalID, paramName, proposedValue, msg.sender);
        return proposalID;
    }

    /**
     * @notice Co-sign a pending threshold update proposal.
     */
    function signProposal(bytes32 proposalID) external onlyCouncil {
        GovernanceProposal storage p = _proposals[proposalID];
        require(!p.executed, "ATC: already executed");
        require(!p.signed[msg.sender], "ATC: already signed");
        require(p.paramName != bytes32(0), "ATC: unknown proposal");
        p.signed[msg.sender] = true;
        p.signatureCount += 1;

        if (p.signatureCount >= requiredSignatures()) {
            _executeProposal(proposalID, p);
        }
    }

    /**
     * @notice Signatures needed to execute a proposal: ceil(2/3 · councilSize),
     *         but never fewer than MIN_SIGNATORIES.
     */
    function requiredSignatures() public view returns (uint256) {
        uint256 twoThirds = (2 * councilSize + 2) / 3;
        return twoThirds > MIN_SIGNATORIES ? twoThirds : MIN_SIGNATORIES;
    }

    function _executeProposal(bytes32 proposalID, GovernanceProposal storage p) internal {
        p.executed = true;
        bytes32 key   = p.paramName;
        uint256 value = p.proposedValue;
        uint256 old;

        if      (key == "minPreheatTemp")   { old = thresholds.minPreheatTemp;   thresholds.minPreheatTemp   = value; }
        else if (key == "maxInterpassTemp") { old = thresholds.maxInterpassTemp;  thresholds.maxInterpassTemp = value; }
        else if (key == "minHumidity")      { old = thresholds.minHumidity;       thresholds.minHumidity      = value; }
        else if (key == "maxHumidity")      { old = thresholds.maxHumidity;       thresholds.maxHumidity      = value; }
        else if (key == "minNDTCoverage")   { old = thresholds.minNDTCoverage;    thresholds.minNDTCoverage   = value; }
        else revert("ATC: unknown parameter");

        emit ThresholdUpdated(key, old, value, msg.sender, block.timestamp);
        emit GovernanceProposalExecuted(proposalID, p.signatureCount);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Access control management
    // ─────────────────────────────────────────────────────────────────────

    function addCertifier(address certifier) external onlyOwner {
        ndtCertifiers[certifier] = true;
    }

    function removeCertifier(address certifier) external onlyOwner {
        require(certifier != owner, "ATC: cannot remove owner");
        ndtCertifiers[certifier] = false;
    }

    function addCouncilMember(address member) external onlyOwner {
        require(!governanceCouncil[member], "ATC: already council member");
        governanceCouncil[member] = true;
        councilSize += 1;
    }

    function removeCouncilMember(address member) external onlyOwner {
        require(member != owner, "ATC: cannot remove owner");
        require(governanceCouncil[member], "ATC: not council member");
        governanceCouncil[member] = false;
        councilSize -= 1;
    }

    function addRegistrar(address registrar) external onlyOwner {
        credentialRegistrars[registrar] = true;
    }

    function removeRegistrar(address registrar) external onlyOwner {
        credentialRegistrars[registrar] = false;
    }

    // ─────────────────────────────────────────────────────────────────────
    // View helpers
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Return the Structural Passport for a given weldID.
     */
    function getPassport(bytes32 weldID)
        external
        view
        returns (StructuralPassport memory)
    {
        return structuralPassports[weldID];
    }

    /**
     * @notice Check whether a welder's DID certificate is currently valid.
     */
    function isCertValid(bytes32 welderDID) external view returns (bool) {
        return (
            welderRegistry[welderDID] != 0 &&
            !welderRevoked[welderDID] &&
            block.timestamp <= welderRegistry[welderDID]
        );
    }

    /**
     * @notice Return certificate expiry timestamp for a given welder DID.
     */
    function certExpiry(bytes32 welderDID) external view returns (uint256) {
        return welderRegistry[welderDID];
    }
}
