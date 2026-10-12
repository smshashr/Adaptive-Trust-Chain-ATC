// Functional tests of WeldComplianceASC against Algorithm 1 of the manuscript.
// Run:  npm install && npx hardhat test
const { expect } = require("chai");
const { ethers, network } = require("hardhat");
const b32 = (s) => ethers.encodeBytes32String(s);
const id = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));
const now = async () => (await ethers.provider.getBlock("latest")).timestamp;

describe("WeldComplianceASC", function () {
  let c, owner, m1, m2, m3, outsider, W, E;
  beforeEach(async () => {
    [owner, m1, m2, m3, outsider] = await ethers.getSigners();
    const F = await ethers.getContractFactory("WeldComplianceASC", owner);
    // minPreheat 100.0 °C, maxInterpass 250.0 °C, minHumidity (unused), maxHumidity 80.0 %RH, minNDT 90.0 %
    c = await F.deploy(1000, 2500, 0, 800, 900);
    W = id("did:example:welder-1"); E = id("equipment-1");
    const t = await now();
    await c.registerWelder(W, t + 365 * 86400);
    await c.setCalibration(E, t + 180 * 86400);
  });

  it("Steps 1-6: reason codes as in Algorithm 1", async () => {
    let r = await c.checkCompliance(W, E, 1200, 2000, 500);
    expect(r[0]).to.equal(true); expect(r[1]).to.equal(b32("COMPLIANT"));
    r = await c.checkCompliance(id("unknown"), E, 1200, 2000, 500); expect(r[1]).to.equal(b32("DID_INVALID"));
    r = await c.checkCompliance(W, id("other-eq"), 1200, 2000, 500); expect(r[1]).to.equal(b32("CALIBRATION_EXPIRED"));
    r = await c.checkCompliance(W, E, 900, 2000, 500); expect(r[1]).to.equal(b32("PREHEAT_LOW"));
    r = await c.checkCompliance(W, E, 1200, 2600, 500); expect(r[1]).to.equal(b32("INTERPASS_HIGH"));
    r = await c.checkCompliance(W, E, 1200, 2000, 850); expect(r[1]).to.equal(b32("HUMIDITY_HIGH"));
  });

  it("expired DID and expired calibration fail locked", async () => {
    await network.provider.send("evm_increaseTime", [200 * 86400]); await network.provider.send("evm_mine");
    let r = await c.checkCompliance(W, E, 1200, 2000, 500); expect(r[1]).to.equal(b32("CALIBRATION_EXPIRED"));
    await network.provider.send("evm_increaseTime", [200 * 86400]); await network.provider.send("evm_mine");
    r = await c.checkCompliance(W, E, 1200, 2000, 500); expect(r[1]).to.equal(b32("DID_INVALID"));
  });

  it("revoked DID returns DID_INVALID", async () => {
    await c.revokeWelder(W);
    const r = await c.checkCompliance(W, E, 1200, 2000, 500); expect(r[1]).to.equal(b32("DID_INVALID"));
  });

  it("Steps 7-10: recordWeld re-evaluates compliance on-chain and stores non-compliant outcomes", async () => {
    const bt = id("batch-7");
    const id0 = ethers.keccak256(ethers.solidityPacked(["bytes32","bytes32","uint256"], [W, E, 0]));
    await expect(c.recordWeld(W, E, 900, 2000, 500, bt))
      .to.emit(c, "ComplianceDenied").withArgs(W, id0, b32("PREHEAT_LOW"), await now() + 1);
    const p0 = await c.getPassport(id0);
    expect(p0.compliant).to.equal(false); expect(p0.reason).to.equal(b32("PREHEAT_LOW")); expect(p0.sequenceNo).to.equal(0n);
    await c.recordWeld(W, E, 1200, 2000, 500, bt);
    const id1 = ethers.keccak256(ethers.solidityPacked(["bytes32","bytes32","uint256"], [W, E, 1]));
    const p1 = await c.getPassport(id1);
    expect(p1.compliant).to.equal(true); expect(p1.sequenceNo).to.equal(1n);
    await expect(c.connect(outsider).recordWeld(W, E, 1200, 2000, 500, bt)).to.be.revertedWith("ATC: not registrar");
  });

  it("Steps 11-12: attachNDT is one-time and certifier-only", async () => {
    await c.recordWeld(W, E, 1200, 2000, 500, id("b"));
    const wid = ethers.keccak256(ethers.solidityPacked(["bytes32","bytes32","uint256"], [W, E, 0]));
    const h = id("ndt-report");
    await expect(c.connect(outsider).attachNDT(wid, h, "bafy...")).to.be.revertedWith("ATC: not NDT certifier");
    await expect(c.attachNDT(wid, h, "bafy...")).to.emit(c, "NDTLinked");
    await expect(c.attachNDT(wid, h, "bafy...")).to.be.revertedWith("ATC: NDT already attached");
    await expect(c.attachNDT(id("nope"), h, "x")).to.be.revertedWith("ATC: weld record not found");
  });

  it("governance: ceil(2/3) of council, never fewer than 3", async () => {
    for (const m of [m1, m2, m3]) await c.addCouncilMember(m.address);   // council = 4
    expect(await c.requiredSignatures()).to.equal(3n);
    const tx = await c.proposeThresholdUpdate(b32("minPreheatTemp"), 1100);
    const ev = (await tx.wait()).logs.map(l => c.interface.parseLog(l)).find(e => e && e.name === "GovernanceProposalSubmitted");
    const pid = ev.args.proposalID;
    await c.connect(m1).signProposal(pid);
    expect((await c.thresholds()).minPreheatTemp).to.equal(1000n);      // 2 of 4: not yet
    await c.connect(m2).signProposal(pid);                                // 3 of 4 ≥ ceil(8/3)=3
    expect((await c.thresholds()).minPreheatTemp).to.equal(1100n);
    await expect(c.connect(m3).signProposal(pid)).to.be.revertedWith("ATC: already executed");
    await expect(c.connect(outsider).proposeThresholdUpdate(b32("minPreheatTemp"), 1)).to.be.revertedWith("ATC: not governance council");
  });

  it("governance quorum grows with council size", async () => {
    const s = await ethers.getSigners();
    for (let i = 1; i <= 5; i++) await c.addCouncilMember(s[i].address);  // council = 6
    expect(await c.requiredSignatures()).to.equal(4n);
  });
});
