# Meridian migration and rollback

Meridian is now the only primary application shell. Legacy Bills, Expenses,
Pockets, Family, Cards, Credit, Splitwise, and Account entry points redirect to
the matching Meridian workspace. Provider adapters and approval-gated mutation
services remain in place; only their duplicate presentation surfaces are
retired.

## Before upgrading

1. Stop the application and broker.
2. Copy the SQLite database and its `-wal` and `-shm` companions, if present,
   while the application is stopped.
3. Record the currently deployed image tag or Git commit.
4. Confirm the backup is readable with `sqlite3 <backup> 'PRAGMA integrity_check;'`.
5. Keep Crew credentials and broker capability files outside images and source
   control. A database backup contains encrypted broker credentials, not the
   macOS Keychain key needed to decrypt them.

## Upgrade and data audit

1. Start the new image against a copy of production data first. Meridian applies
   versioned migrations automatically and does not mutate provider source data.
2. Sign in and verify Today, Plan, Activity, and Accounts load without exposing
   external identifiers or credentials.
3. Compare account balances and transaction totals with the previous deployment.
4. Confirm owned-account transfers, credit-card payments, refunds, and Splitwise
   reimbursements are each represented once.
5. Confirm every legacy bill or pocket is visible as a Commitment, Account, or
   explicit migration-review item.
6. Inspect Connections freshness. A partial or failed provider must retain the
   last trustworthy records and display a degraded state.
7. Exercise mobile and desktop navigation. Financial changes must remain inert
   proposals until separately approved and executed.

Do not use a real financial mutation as an acceptance test.

## Redirect map

| Legacy entry | Meridian destination |
|---|---|
| Activity | Activity |
| Bills / Expenses / Pockets / Goals | Plan |
| Family / Cards / Credit / Splitwise / Account | Accounts |

Both legacy `?tab=` bookmarks and direct legacy paths use this mapping.

## Rollback

1. Stop the new application before replacing its database.
2. Preserve the post-upgrade database for diagnosis.
3. Restore the pre-upgrade database files together as one set.
4. Deploy the recorded pre-Meridian image or commit.
5. Start the broker and application, then perform read-only health and balance
   checks before allowing any financial action.

Never downgrade an already-migrated database in place. Restore the matched
backup instead.
