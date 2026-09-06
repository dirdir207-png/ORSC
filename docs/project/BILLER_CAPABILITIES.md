# Connected Biller System — Capability Research (R33/R34)

Date: 2026-09-06
Branch: `feat/meridian-implementation` (ORSC `dirdir207-png/ORSC`)
Scope: is a connected-biller system that **swaps the debit/credit card paying a
bill** feasible with the available provider surface? Verdict + evidence.

## Executive verdict

Constructing a connected-biller system with **debit/credit card-payment-method
switching** is **NOT feasible against the current Crew provider surface**, and
is only feasible today as a **separate, vetted third-party integration**
(Pinwheel Bill Switch + Plaid) — which the recovery program (R34) explicitly
defers ("until a vetted partner and explicit bank-action authority exist").

**Recommendation: DROP the card-swap biller as a Crew-native feature.** Keep
the read-only biller **monitoring** scope (R33) as the realistic deliverable; do
NOT build card-swap against Crew (no underlying mutation exists), and do NOT
add a third-party (Pinwheel/Plaid) connector without a vetted partner,
credentials, and bank-action authority — all of which are out of scope and
gated.

---

## Part 1 — Crew provider surface: no card-swap capability

Evidence gathered from the WorkAssistant repo (`operations/*.graphql`,
`src/crew_work_assistant/*`):

### What Crew's write layer actually supports (authorized mutations)

`src/crew_work_assistant/write_operations/`:
- `update_bill.graphql` → `UpdateBill` — fields: `id, name, amount,
  reservedAmount, paused, frequency, frequencyInterval, anchorDate,
  reassignmentRule`. **No payment-method / card field.**
- `update_bill_reserve_settings.graphql` → `UpdateBillReserveSettings` — fields:
  funding subaccounts, surplus subaccount, frequency, bufferDays. **Pocket
  funding only, no payment instrument.**
- `create_autopilot_rule.graphql` → autopilot rules (round-up transfers, etc.).
- `internal_transfer.graphql` → internal money movement.

`crew_write_cli.py` allowlist: `_OPERATIONS = ("update_bill",
"update_bill_reserve_settings", "create_autopilot_rule")`.

### What is ONLY a label, not a real mutation

`src/crew_work_assistant/base44.py` / `proposals.py` reference a catalog of
proposal actions including `create_bill`, `delete_bill`,
`set_card_spend_source`. **No captured GraphQL mutation exists for any of
these** (verified: no `createBill`/`setCardSpendSource` `.graphql` document, no
mutation in the repo). `proposals.py` only validates expected param names
(`set_card_spend_source: {card_id, pocket_id}`) — it does **not** know the real
Crew operation. Per `CREW_MUTATION_INVENTORY.md`: *"Do not infer mutation names
from labels."*

### Bills are not tied to payment cards in the Crew read model

`updateBill` (the only bill mutation) carries no card reference. Bill amount /
frequency / funding-subaccounts exist, but **which external card pays a bill is
not a field Crew exposes for mutation.** There is no `payBill`, no
`charge`, no `autopay`, no `setBillPaymentMethod` anywhere in the Crew GraphQL
surface we can observe.

### Conclusion for Crew-native

The capability "assign a debit/credit card to a bill and switch it" has **no
backing Crew mutation**. Building it would mean fabricating an operation that
doesn't exist — which the recovery program forbids (never infer or invent
mutations; never submit an unverified financial action).

---

## Part 2 — Third-party route: feasible but partner-gated

The market DOES have a purpose-built capability:

### Pinwheel Bill Switch (docs.pinwheelapi.com/public/docs/implement-bill-switch)

- Lets a user switch a bill from an existing bank account / credit card to a
  different card or bank account **in the same session**.
- Automatically detects recurring bills/subscriptions from external transactions
  (via **Plaid**, either the app's own Plaid account via Processor tokens or
  Pinwheel's own Plaid account).
- Requires:
  - A **Pinwheel API secret** (vendor account, paid).
  - A **Plaid account** (own or Pinwheel's) for external transaction access.
  - The **user's external bank/card credentials** (they log in through Link).
  - Link SDK v3.x (web/iOS/Android) and API version `2025-07-08+`.
  - Debit/credit card details (`card_number`, `cvc`, `expiration`, zip, billing
    address) provided to Pinwheel to create the Link token.
- Emits `account.added` / `bill_switch.added` webhooks (with `is_integrated_switch`
  true for automated switches, false for manual instructions).
- Notable limit: **"long tail" merchants** with no `platform_id` integration are
  routed to a catch-all "Other (merchant)" and may require a **manual** switch
  (instructions only) — i.e., end-to-end automation is not universal.

### Other references
- Lithic (lithic.com/industries/bill-pay) — card-issuer bill-pay.
- Fiskil / Switch Kit — bank-account switching (ACH), not card-per-bill.
- These are all **commercial vendor integrations** with cost, credentials, and
  external-account linkage. None change the underlying fact that **Crew does not
  expose card-per-bill switching**.

---

## Part 3 — What R33/R34 already require (and why card-swap is deferred)

From `RECOVERY_TASKS.json`:

- **R33 — Scope connected biller MONITORING against real capabilities**
  - "Record actual provider coverage/pricing/access and grant; **do not assume
    utilities or all liabilities are supported**."
  - "**No second bill identity and no automatic payment-method switching.**"
  - Monitor = due/current/statement/autopay/health read-only; changes enter review.
- **R34 — Gate biller switching and payment separately**
  - "Decision/spec only **until a vetted partner and explicit bank-action
    authority exist**."
  - "No live financial test"; reversal/fee/idempotency/uncertain-outcome
    documentation. "Never emulate overdraft by UI arithmetic."

The program already concluded: **monitoring (read-only) is the buildable slice;
executing payment-method switching is explicitly gated behind a partner +
authority** that does not exist today.

---

## Feasibility matrix

| Path | Card-swap supported? | What it needs | Verdict |
|---|---|---|---|
| Crew-native bill mutation | ❌ No field/mutation | — | **Infeasible — drop** |
| Crew-native `set_card_spend_source` | ❌ Label only, no mutation | Capture exact op from Crew web app | **Infeasible** (unverified/invented) |
| Pinwheel Bill Switch + Plaid | ✅ Yes (vendor) | Vendor account + API key, Plaid, user's external credentials, Link SDK, vetted partner + bank-action authority | **Feasible but partner-gated / cost / out of scope** |
| Read-only biller monitoring (R33) | N/A (read-only) | Provider read access + grant | **Buildable — the realistic deliverable** |

## Recommendation

1. **Drop** Crew-native card-swap biller — definitively infeasible (no backing
   mutation; would require fabricating one, which the program forbids).
2. **Keep** the R33 read-only biller **monitoring** slice as the realistic
   connected-biller feature (due/current/amount/statement/health into review).
3. **Do not** add a Pinwheel/Plaid card-swap connector now — it needs a vetted
   partner, vendor credentials, and explicit bank-action authority, all of which
   the owner has not provided and R34 explicitly defers. If the owner later
   obtains a Pinwheel/Plaid account and wants this, it becomes a separate,
   gated feature — not part of Crew-native biller work.
