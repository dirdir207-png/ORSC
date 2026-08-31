"""Seed the Meridian database with realistic sample financial data."""

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

DB = os.environ.get("DB_FILE", "savings_data.db")

# Deterministic preview reference date: every seeded record is dated relative to
# this fixed day so screenshots/baselines are reproducible and do not drift with
# the real calendar. Change it deliberately to re-baseline.
PREVIEW_TODAY = date(2026, 8, 20)


def now_iso():
    return datetime.combine(PREVIEW_TODAY, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z")


def days_ago_iso(days, hour=12):
    base = datetime.combine(PREVIEW_TODAY, datetime.min.time(), timezone.utc)
    return (base - timedelta(days=days, hours=hour)).isoformat().replace("+00:00", "Z")

def seed():
    from werkzeug.security import generate_password_hash

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # ── App tables ──────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS app_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS passkey_credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        credential_id BLOB NOT NULL UNIQUE,
        public_key BLOB NOT NULL,
        sign_count INTEGER DEFAULT 0,
        transports TEXT,
        aaguid TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_used_at TEXT,
        nickname TEXT,
        backup_eligible INTEGER DEFAULT 0,
        backup_state INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS webauthn_sessions (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        challenge BLOB NOT NULL,
        operation TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS webauthn_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rp_id TEXT NOT NULL,
        origin TEXT NOT NULL,
        is_valid INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS fcm_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT,
        server_key TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS fcm_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL UNIQUE,
        user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS history (date TEXT PRIMARY KEY, balance REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pocket_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pocket_id TEXT,
        pocket_name TEXT,
        group_id INTEGER,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS simplefin_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        access_url TEXT,
        sync_times TEXT,
        sync_timezone TEXT,
        sync_interval INTEGER DEFAULT 3600,
        last_sync_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS credit_card_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_name TEXT,
        last_four TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS credit_card_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER,
        description TEXT,
        amount REAL,
        date TEXT,
        category TEXT,
        FOREIGN KEY (card_id) REFERENCES credit_card_config(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS onboarding_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step TEXT,
        completed INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS crew_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        family_id TEXT,
        enabled INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS lunchflow_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        enabled INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS splitwise_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        enabled INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS splitwise_pocket_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pocket_id TEXT,
        friend_id INTEGER,
        friend_name TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS splitwise_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_id TEXT,
        description TEXT,
        amount REAL,
        date TEXT,
        settled INTEGER DEFAULT 0
    )''')
    conn.commit()

    # ── Test user ───────────────────────────────────────────────
    pw = generate_password_hash("preview123")
    c.execute("INSERT OR IGNORE INTO users (username, email, password_hash) VALUES (?, ?, ?)",
              ("preview", "preview@example.com", pw))
    conn.commit()

    # ── Meridian migrations (via FinancialRepository) ───────────
    from meridian.db import run_migrations
    run_migrations(DB)

    # ── Provider connection ─────────────────────────────────────
    now = now_iso()
    c.execute("""INSERT OR IGNORE INTO provider_connections
        (provider, external_id, display_name, status, last_attempted_at, last_successful_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("crew", "conn-preview-1", "Crew (Preview)", "healthy", now, now, now, now))
    conn_id = c.lastrowid

    # ── Accounts ────────────────────────────────────────────────
    accounts = [
        ("checking",  "Main Checking",    "checking",  3247.82, 3247.82, "USD"),
        ("savings",   "Emergency Fund",   "savings",   8512.40, 8512.40, "USD"),
        ("credit",    "Visa Rewards",     "credit",   -1423.56, 3576.44, "USD"),
        ("checking",  "Joint Checking",   "checking",  1892.15, 1892.15, "USD"),
    ]
    account_ids = []
    for ext, name, atype, bal, avail, cur in accounts:
        c.execute("""INSERT OR IGNORE INTO financial_accounts
            (connection_id, provider, external_id, name, account_type, balance,
             available_balance, currency, is_active, source_updated_at, synced_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (conn_id, "crew", ext, name, atype, bal, avail, cur, now, now, now, now))
        account_ids.append(c.lastrowid)
    conn.commit()

    # ── Transactions (30 days of realistic spending) ────────────
    checking_id = account_ids[0]
    savings_id  = account_ids[1]
    credit_id   = account_ids[2]

    txns = [
        # Income
        (checking_id, "crew", "tx-paycheck1",  3125.00, days_ago_iso(1),  days_ago_iso(1), "Paycheck — Acme Corp",             "Acme Corp",           "posted"),
        (checking_id, "crew", "tx-paycheck2",  3125.00, days_ago_iso(15), days_ago_iso(15),"Paycheck — Acme Corp",             "Acme Corp",           "posted"),

        # Savings transfer
        (savings_id,  "crew", "tx-saver1",     500.00,  days_ago_iso(2),  days_ago_iso(2),  "Transfer to Emergency Fund",       "Internal Transfer",   "posted"),

        # Groceries
        (credit_id,   "crew", "tx-walmart1",  -127.43,  days_ago_iso(1),  days_ago_iso(1),  "WAL-MART #2639",                   "Walmart",             "posted"),
        (credit_id,   "crew", "tx-walmart2",  -89.21,   days_ago_iso(4),  days_ago_iso(4),  "WAL-MART #2369",                   "Walmart",             "posted"),
        (credit_id,   "crew", "tx-trader",    -62.18,   days_ago_iso(7),  days_ago_iso(7),  "TRADER JOE'S #927",                "Trader Joe's",        "posted"),
        (credit_id,   "crew", "tx-walmart3",  -104.56,  days_ago_iso(10), days_ago_iso(10), "WAL-MART #2639",                   "Walmart",             "posted"),
        (credit_id,   "crew", "tx-aldi",      -43.87,   days_ago_iso(14), days_ago_iso(14), "ALDI #10294",                      "Aldi",                "posted"),

        # Dining
        (credit_id,   "crew", "tx-chipotle",  -14.23,   days_ago_iso(2),  days_ago_iso(2),  "CHIPOTLE ONLINE",                  "Chipotle",            "posted"),
        (credit_id,   "crew", "tx-ddonuts",   -6.89,    days_ago_iso(5),  days_ago_iso(5),  "DUNKIN #31027",                    "Dunkin'",             "posted"),
        (credit_id,   "crew", "tx-pizza",     -28.50,   days_ago_iso(8),  days_ago_iso(8),  "DOMINOS PIZZA 0412",               "Domino's",            "posted"),
        (credit_id,   "crew", "tx-starbucks",  -5.75,   days_ago_iso(3),  days_ago_iso(3),  "STARBUCKS STORE 14202",            "Starbucks",           "posted"),
        (credit_id,   "crew", "tx-mcdonalds", -11.34,   days_ago_iso(6),  days_ago_iso(6),  "MCDONALD'S F1693",                 "McDonald's",          "posted"),
        (credit_id,   "crew", "tx-fiveguys",  -18.90,   days_ago_iso(12), days_ago_iso(12), "FIVE GUYS NH 1826",                "Five Guys",           "posted"),
        (credit_id,   "crew", "tx-jersey",    -15.40,   days_ago_iso(9),  days_ago_iso(9),  "JERSEY MIKES 37006",               "Jersey Mike's",       "posted"),

        # Gas
        (credit_id,   "crew", "tx-shell1",    -52.31,   days_ago_iso(3),  days_ago_iso(3),  "SHELL OIL 116681373QPS",           "Shell",               "posted"),
        (credit_id,   "crew", "tx-shell2",    -48.72,   days_ago_iso(11), days_ago_iso(11), "SHELL OIL 116681373QPS",           "Shell",               "posted"),
        (credit_id,   "crew", "tx-cumberland",-38.45,   days_ago_iso(5),  days_ago_iso(5),  "CUMBERLAND FARMS 5543",            "Cumberland Farms",    "posted"),
        (credit_id,   "crew", "tx-exxon",     -44.10,   days_ago_iso(13), days_ago_iso(13), "GILFORD MOBIL M",                  "ExxonMobil",          "posted"),
        (credit_id,   "crew", "tx-circlek",   -35.20,   days_ago_iso(7),  days_ago_iso(7),  "CIRCLE K 07208",                   "Circle K",            "posted"),

        # Subscriptions
        (credit_id,   "crew", "tx-netflix",   -15.99,   days_ago_iso(1),  days_ago_iso(1),  "NETFLIX.COM",                      "Netflix",             "posted"),
        (credit_id,   "crew", "tx-spotify",   -10.99,   days_ago_iso(5),  days_ago_iso(5),  "SPOTIFY USA",                      "Spotify",             "posted"),
        (credit_id,   "crew", "tx-apple",     -9.99,    days_ago_iso(10), days_ago_iso(10), "APPLE.COM/BILL",                   "Apple",               "posted"),
        (credit_id,   "crew", "tx-adobe",     -54.99,   days_ago_iso(8),  days_ago_iso(8),  "ADOBE CREATIVE CLOUD",             "Adobe",               "posted"),
        (credit_id,   "crew", "tx-chatgpt",   -20.00,   days_ago_iso(12), days_ago_iso(12), "OPENAI CHATGPT",                   "OpenAI",              "posted"),

        # Bills (checking)
        (checking_id, "crew", "tx-rent",      -1800.00, days_ago_iso(1),  days_ago_iso(1),  "Rent Payment",                     "Landlord",            "posted"),
        (checking_id, "crew", "tx-eversource",-189.50,  days_ago_iso(5),  days_ago_iso(5),  "Eversource Energy",                "Eversource",          "posted"),
        (checking_id, "crew", "tx-xfinity",   -89.99,   days_ago_iso(8),  days_ago_iso(8),  "Xfinity Internet",                 "Comcast",             "posted"),
        (checking_id, "crew", "tx-verizon",    -85.00,  days_ago_iso(10), days_ago_iso(10), "Verizon Wireless",                 "Verizon",             "posted"),

        # Misc
        (credit_id,   "crew", "tx-cvs",       -12.49,  days_ago_iso(4),  days_ago_iso(4),  "CVS/PHARMACY #08931",              "CVS",                 "posted"),
        (credit_id,   "crew", "tx-walgreens",  -8.79,  days_ago_iso(6),  days_ago_iso(6),  "WALGREENS STORE 10010",            "Walgreens",           "posted"),
        (credit_id,   "crew", "tx-amazon",    -34.99,   days_ago_iso(2),  days_ago_iso(2),  "AMZN Mktp US",                     "Amazon",              "posted"),
        (checking_id, "crew", "tx-venmo-in",   75.00,  days_ago_iso(3),  days_ago_iso(3),  "Venmo: Stephen West received",     "Venmo",               "posted"),
    ]

    for acct, prov, ext, amt, occurred, posted, desc, merch, status in txns:
        c.execute("""INSERT OR IGNORE INTO financial_transactions
            (account_id, provider, external_id, amount, currency, occurred_at, posted_at,
             description, merchant, status, raw_description, source_updated_at, synced_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (acct, prov, ext, amt, occurred, posted, desc, merch, status, desc, now, now, now, now))
    conn.commit()

    # ── Commitments ─────────────────────────────────────────────
    commitments = [
        ("bill",     "Rent",            1, 1800.00, 1800.00, "2026-09-05", "monthly",  "active"),
        ("bill",     "Electric",        2,  189.50,  189.50, "2026-09-20", "monthly",  "active"),
        ("bill",     "Internet",        2,   89.99,   89.99, "2026-09-28", "monthly",  "active"),
        ("bill",     "Phone",           3,   85.00,   85.00, "2026-09-22", "monthly",  "active"),
        ("goal",     "Emergency Fund",  1, 10000.00, 8512.40, None,        None,       "active"),
        ("reserve",  "Car Maintenance", 3,  2000.00,  450.00, "2026-12-01", None,       "active"),
        ("buffer",   "Vacation Fund",   4,  3000.00, 1200.00, "2026-11-15", None,       "active"),
    ]

    for ctype, name, pri, target, funded, due, recurrence, status in commitments:
        c.execute("""INSERT INTO commitments
            (type, name, status, priority, currency, target_amount, target_date,
             funded_amount, due_date, recurrence, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?, ?)""",
            (ctype, name, status, pri, target, due, funded, due, recurrence, now, now))
    conn.commit()

    # ── Funding rules ───────────────────────────────────────────
    c.execute("SELECT id FROM commitments WHERE name = 'Rent'")
    rent_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Electric'")
    elec_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Internet'")
    inet_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Phone'")
    phone_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Emergency Fund'")
    emerg_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Car Maintenance'")
    car_id = c.fetchone()[0]
    c.execute("SELECT id FROM commitments WHERE name = 'Vacation Fund'")
    vac_id = c.fetchone()[0]

    rules = [
        (rent_id,  "calendar",   1800.00, None, "monthly", 5,  "2026-01-01", 1),
        (elec_id,  "calendar",    189.50, None, "monthly", 20, "2026-01-01", 2),
        (inet_id,  "calendar",     89.99, None, "monthly", 28, "2026-01-01", 2),
        (phone_id, "calendar",     85.00, None, "monthly", 22, "2026-01-01", 2),
        (emerg_id, "fixed_per_paycheck", 200.00, None, "biweekly", None, "2026-01-01", 1),
        (car_id,   "fixed_per_paycheck",  50.00, None, "biweekly", None, "2026-01-01", 3),
        (vac_id,   "fixed_per_paycheck", 100.00, None, "biweekly", None, "2026-01-01", 4),
    ]

    for cid, kind, amt, pct, cadence, dom, start, pri in rules:
        c.execute("""INSERT INTO funding_rules
            (commitment_id, kind, amount, percent, cadence, day_of_month, start_date,
             paused, skip_dates, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '[]', ?, ?, ?)""",
            (cid, kind, amt, pct, cadence, dom, start, pri, now, now))
    conn.commit()

    conn.close()

    # ── Asset & contract memory (Task 26) ─────────────────────────────
    from meridian.assets import Asset, AssetRepository, Warranty
    from meridian.contracts import Contract, ContractRepository, Obligation
    from meridian.evidence import EvidenceRepository
    from meridian.storage import DerivedKeyProvider, EncryptedBlobStore

    evidence_root = os.path.join(os.path.dirname(os.path.abspath(DB)), "evidence")

    def _evidence_key():
        conn = sqlite3.connect(DB)
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            row = conn.execute("SELECT value FROM app_config WHERE key='secret_key'").fetchone()
            if row:
                return row[0].encode()
            # Persist the same secret the app will reuse via
            # get_or_create_secret_key, so seed-then-boot and boot-then-seed
            # derive the same evidence encryption key.
            secret_key = os.urandom(24).hex()
            conn.execute("INSERT INTO app_config (key, value) VALUES ('secret_key', ?)", (secret_key,))
            conn.commit()
            return secret_key.encode()
        finally:
            conn.close()

    store = EncryptedBlobStore(evidence_root, DerivedKeyProvider(_evidence_key()))
    evidence = EvidenceRepository(DB)

    receipt_blob = store.put(b"Laptop receipt (preview)", mime_type="text/plain")
    receipt = evidence.add_item(
        source_kind="manual", source_id="preview-receipt",
        content_hash=receipt_blob.content_hash, mime_type="text/plain",
        size_bytes=receipt_blob.size_bytes, title="Laptop receipt",
    )
    policy_blob = store.put(b"Home policy declarations (preview)", mime_type="text/plain")
    policy = evidence.add_item(
        source_kind="manual", source_id="preview-policy",
        content_hash=policy_blob.content_hash, mime_type="text/plain",
        size_bytes=policy_blob.size_bytes, title="Home policy declarations",
    )

    assets = AssetRepository(DB)
    laptop = assets.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on="2026-08-01",
        purchase_price=1500, return_until="2026-08-31", maintenance_interval_days=180,
        replacement_reserve=1200, evidence_id=receipt.id, evidence_span="receipt",
        confidence=0.98,
    ))
    assets.save_warranty(Warranty(
        id=None, asset_id=laptop.id, provider="VendorCo", expires_on="2027-08-01",
        deductible=100, evidence_id=receipt.id, evidence_span="receipt", confidence=0.98,
    ))
    assets.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on="2026-06-15",
        purchase_price=800, return_until=None, maintenance_interval_days=None,
        replacement_reserve=500, evidence_id=None, evidence_span="owner:managed",
        confidence=1.0,
    ))

    contracts = ContractRepository(DB)
    home = contracts.save_contract(Contract(
        id=None, kind="insurance", name="Home policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on="2027-01-01", cancel_by="2026-11-30",
        escalation_percent=None, deductible=1000, evidence_id=policy.id,
        evidence_span="declarations", confidence=0.96,
    ))
    contracts.save_contract(Contract(
        id=None, kind="lease", name="Apartment lease", starts_on="2026-07-01",
        ends_on="2027-06-30", renews_on=None, cancel_by="2027-05-01",
        escalation_percent=3.0, deductible=None, evidence_id=None,
        evidence_span="owner:managed", confidence=1.0,
    ))
    contracts.save_obligation(Obligation(
        id=None, contract_id=home.id, name="Premium", amount=120.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=policy.id, evidence_span="declarations", confidence=0.96,
    ))

    evidence.add_link(evidence_id=receipt.id, target_kind="asset",
                      target_id=str(laptop.id), relation="supports", provenance="receipt")
    evidence.add_link(evidence_id=policy.id, target_kind="contract",
                      target_id=str(home.id), relation="supports", provenance="declarations")

    print(f"✅ Seeded {DB} with preview data")

if __name__ == "__main__":
    seed()
