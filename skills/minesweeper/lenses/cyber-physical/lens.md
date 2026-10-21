---
id: cyber-physical
version: 0.1.0
title: Cyber-physical systems, OT and grid cyber regulation
group: agents-cyber-physical
owner: sf
scope: >-
  Judges briefs whose software reads from or writes to operational technology: industrial control
  systems, SCADA, PLCs and RTUs, building automation, substations and other bulk electric system
  assets. Covers write paths to actuation, safety interlocks and safety instrumented systems,
  IT/OT zoning and remote access, patching of live controllers, internal network monitoring, cloud
  control loops, and the NERC CIP and process-safety duties that attach. General web security and
  privacy law belong to other lenses.
applies_when:
  signals:
    - scada
    - plc
    - modbus
    - dnp3
    - iec 61850
    - opc ua
    - opc-ua
    - bacnet
    - ethernet/ip
    - industrial control
    - operational technology
    - ot network
    - substation
    - bulk electric
    - nerc
    - cip-0
    - " rtu"
    - hmi
    - turbine
    - actuator
    - setpoint
    - interlock
    - safety instrumented
    - emergency shutdown
    - building automation
    - process control
    - inverter
    - battery storage
    - grid operator
required_statements:
  - id: safety-function-ownership
    statement: The brief names the safety functions protecting the physical process (interlocks, safety instrumented systems, emergency shutdown), who owns them, and states that the software does not modify, bypass or depend on them being bypassed.
    never_out_of_scope: agent-action-safety
  - id: actuation-write-path
    statement: The brief states whether any write path from the software (cloud services, analytics, agents) reaches a controller, setpoint or actuator, and if so how that path is authenticated, bounded and approved, and what happens locally when it fails.
    never_out_of_scope: agent-action-safety
  - id: regulatory-regime
    statement: The brief states the regulatory regime for the physical assets, for example whether they are part of the bulk electric system and their NERC CIP impact rating, or process-safety rules for the site, or that none applies and who confirmed it.
    never_out_of_scope: regulatory-duties
  - id: network-zones
    statement: The brief states the network zones between enterprise IT, cloud and OT and every conduit between them, including vendor and remote-access paths.
adapters: [web_page]
---

# Cyber-physical systems, OT and grid cyber regulation

## Principles

1. **OT protocols and devices are not authenticated enough to be reachable from IT or the
   internet.** US agencies state that OT devices lack authentication and authorisation resistant
   to modern threats, and recommend segmenting IT and OT with a DMZ for control data
   (cisa-ot-primary-mitigations). Any host that can reach a Modbus/DNP3 port can usually write.
2. **Safety functions are owned outside the product and changed only under management of
   change.** For covered US processes, interlocks and emergency shutdown systems are within
   mechanical integrity, and changes go through written management-of-change procedures
   (cfr-29-1910-119). Elsewhere IEC 61508 / IEC 61511 govern (paywalled, not quoted): the
   disposition is ask-owner for jurisdiction, never "the software may bypass".
3. **Bulk electric system assets carry mandatory duties.** All users, owners and operators of the
   bulk-power system must comply with Commission-approved reliability standards, which include
   cybersecurity protection (usc-16-824o, cfr-18-40-2). Violations carry civil penalties of up to
   $1,000,000 per day by statute (usc-16-825o-1), adjusted for inflation to $1,584,648 per
   violation per day in 18 CFR 385.1602(d) as of the January 2025 adjustment (cfr-18-385-1602).
4. **Vendor remote access must be visible and killable.** CIP-005 requires methods to determine
   active vendor remote access sessions and to disable them (fr-ferc-order-850); CISA asks for
   phishing-resistant MFA and least privilege on any remote access (cisa-ot-primary-mitigations).
5. **The perimeter is not the whole monitoring story.** FERC approved CIP-015-1 internal network
   security monitoring because perimeter-focused standards left the inside of the trust zone
   unmonitored (fr-ferc-order-907). Compliance dates come from NERC's implementation plan; check
   them rather than assuming.
6. **Live controllers are not patched like laptops.** OT has unique performance, reliability and
   safety requirements (nist-sp800-82r3). CIP-007 asks for patch evaluation on a 35-day cycle and
   then apply-or-mitigate, not unattended reboots (nerc-cip-007-6, hand-read; unverified).
7. **Keep hard real-time and safety loops local.** The ability to revert to manual control and
   fail-safe operation is a primary mitigation (cisa-ot-primary-mitigations); a loop that needs a
   WAN round trip to stay safe has no latency or availability bound. The bound itself is an
   experiment, not a quote.
8. IEC 62443 zones and conduits is the accepted vocabulary for principle 1 (isa-62443-summary,
   secondary pointer only; the standard is paywalled).

## Questions a sweeper asks of each claim

- Does any path from this software end in a write to a controller, setpoint, breaker, valve or
  actuator? Who authenticates it, what bounds the values, who approves, what happens on loss of link?
- Which safety functions protect this process, who owns them, and can the software touch them?
- Is any asset part of the bulk electric system, and at what CIP impact rating? Is the site a
  covered process under a process-safety rule? Who confirmed it?
- What are the zones and every conduit between them, including vendor access?
- How are patches evaluated and applied to controllers that cannot be rebooted at will?
- Is anything inside the perimeter monitored?

## Severity guidance

- A write path to actuation without authentication or approval, or any interlock bypass:
  `harm-safety` answers yes, so critical.
- Deferring or ignoring NERC CIP for BES assets: `law-licence-terms-ethics`, so critical; the
  applicability itself (BES or not, impact rating) is often ask-owner.
- Standing vendor access, flat IT/OT networks: `severe-security`, high; critical when the reachable
  devices control a physical process with safety consequences.
- Missing internal monitoring: high for CIP-scoped systems (regulatory), medium elsewhere.
- Read-only telemetry through a one-way path lowers most findings by a tier.

## Not this lens

- Agents choosing actions, loop budgets, credential scope: agent-orchestration (both apply when an
  agent can reach OT).
- Medical-device and other sector regulators: ai-regulation or professional-duty.
- Generic cloud security and cryptography: security-ethics, cryptography.
- Real-time transport and latency physics in general: realtime-transport, performance.
