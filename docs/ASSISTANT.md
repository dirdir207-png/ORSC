# SimpleCrew Local Assistant

Turn plain English into action proposals for owner approval.

## Usage

```bash
./venv/bin/python assistant.py "move $50 from checking to rent for october"
```

Output:
```
✓ Proposed (b16d6fd2…):
    Move $50.00 from Checking → Rent (memo: 'October')
Approve it in the app: Account → Pending Actions (approvals expire after 1 hour).
```

Supported phrasing: `move|transfer|send $AMOUNT from SOURCE to DEST [for MEMO]`.
Quoted names work: `"emergency fund"`. Amounts accept `$`, decimals, `dollars`.

## How it stays safe

- The assistant can only **propose**. Approval and execution happen exclusively in your logged-in app session.
- Proposals are inert JSON records; nothing moves until you click Approve.
- Approved actions expire after 1 hour if not executed.
- Requests require a local capability key (`X-Local-Key`) auto-managed next to the app's config; possession allows proposing only — it is not a Crew credential and cannot move money by itself.
- Names resolve via the app's existing lookups; unknown names fail loudly rather than guessing.

## Options

| Flag | Purpose |
|---|---|
| `--url` | Target instance (default `http://127.0.0.1:8080`) |
| `--key` / env `SIMPLECREW_LOCAL_KEY` | Explicit capability key (default: auto-read from `./data/savings_data.db`) |
| `--db` | Database path for key lookup |
