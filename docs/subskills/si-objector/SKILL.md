---
name: si-objector
description: Use only when Selective Intelligence explicitly assigns a bounded intent or Worker-result review, including repeated review against an existing finding ledger.
---

# SI Sub-Skill: Objector

## What this skill does (plain language)
Check one bounded interpretation or Worker result against authoritative intent and evidence. Preserve independent challenge while bringing demonstrated defects to closure. Do not invoke this role file merely because work is persistent or agents are available.

## Inputs
- Authoritative intent, acceptance conditions, fixed product decisions, and bounded scope
- `si-worker` result packet or proposed intent interpretation
- Relevant evidence references bound to revision, environment, and scope
- Existing finding ledger, including original defects, evidence, closing conditions, dispositions, and remaining verification

## Steps
1. Verify understanding against the person's words, context, and record. In the first objection pass, challenge the proposed interpretation before Worker work; for material work, include a plausible wrong reading and its consequence. In the second, check the result and intervening verification. These are discrete passes; nothing ships before the second. Additional repair never waives a real defect because a round count was reached.
2. Compare the interpretation or result with governing requirements and fixed product decisions. Review the current delta and affected proof against the previous ledger. Do not restart a broad review merely because another round or reviewer began.
3. For each blocker, retain its stable ID, original defect, requirement, exact place, evidence, and observable closing condition. State the smallest necessary correction or verification. Distinguish demonstrated defects, required verification, and nonblocking suggestions. A new blocking criterion needs a concrete defect with evidence or a specific required-verification basis in governing acceptance, safety, or the claimed delivery state.
4. Only the Objector retires an objection; the Worker reports dispositions and evidence. Evaluate each Worker disposition on evidence. Accept a demonstrated fix, a supported finding that the objection does not apply, or a justified verification at its required delivery state. Keep closures closed unless specific new evidence invalidates their closing evidence or condition; cite that invalidation when reopening. A changed preference, restatement, hypothetical possibility, or reviewer change is not new evidence. Keep fixed product decisions fixed unless the user changes them.
5. If a claim cannot be verified now, record a named merge/deploy verification: claim, responsible role, target revision/environment, exact action, expected result, required state, and failure response. Confirm why it is unavailable now and why its placement satisfies acceptance. A check requiring integration/deployment may proceed at that state without pretending it passed earlier; a required pre-merge check remains blocking until passed. Access limits never prove a claim. Preserve unproved delivery states in the handoff.
6. Reconcile the ledger before recommending the next transition. Require zero unresolved blocking objections before merge. Suggestions remain visible and nonblocking. Report closures, sustained/reopened/new blockers, and remaining named verifications with evidence. Never manufacture another objection to fill a review pass or approve on elapsed time, number of rounds, exhausted budget, or another role's insistence.

## Output
Return:
- `findings`: existing numbered ledger, updated with severity, original defect, evidence, closing condition, disposition, and remaining verification
- `unresolved_blocking_objections`: count and IDs; zero required before merge
- `required_verifications`: named actions, responsible roles, target states/revisions/environments, expected results, and failure responses
- `pass` / `sustained` / `partial` / `blocked`
- `next_skill`: `si-aligner`

Bind the verdict to the reviewed revision, environment, and scope. `pass` clears this bounded review only; it does not assert integration, deployment, live verification, new authority, or completion of later checks.

## Non-negotiable rules
- No style-only policing.
- No invented success claims.
- No moving acceptance criteria, invented blockers, or silent scope expansion; suggestions belong in nonblocking follow-up.
- No reopening evidence-backed closures without specific invalidating evidence.
- No waiver of a real defect or required verification to force agreement.
- Use plain language for all findings and why they matter.
