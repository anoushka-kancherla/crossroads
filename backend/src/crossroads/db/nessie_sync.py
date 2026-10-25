"""Reading a customer's bank figures back from Nessie into the database, and replacing the rows an earlier
demo seed made from the in-memory fake. Used by the seed script and by the customer API's sync route.
It lives in `db` so the customer API never has to import the seed (or the internal API)."""

from __future__ import annotations

import psycopg

from ..adapters.nessie import NessieClient

FAKE_PREFIX = "fake-"


def is_real(nessie: NessieClient) -> bool:
    """True for the live Nessie client, False for the in-memory fake."""
    return bool(getattr(nessie, "real", False))


def is_fake_id(nessie_id: str | None) -> bool:
    return bool(nessie_id) and nessie_id.startswith(FAKE_PREFIX)


def read_back(conn: psycopg.Connection, nessie: NessieClient, nessie_cid: str) -> None:
    """Make the tables mirror what Nessie returns for one Nessie customer, and mark the accounts with
    where they came from ('nessie' for the live API, 'demo' for the fake)."""
    source = "nessie" if is_real(nessie) else "demo"
    for acct in nessie.get_accounts(nessie_cid):
        conn.execute(
            "UPDATE accounts SET kind = %s, balance = %s, source = %s, synced_at = now() "
            "WHERE nessie_account_id = %s",
            (acct.kind, acct.balance, source, acct.id),
        )
        if acct.kind != "checking":
            continue
        for b in nessie.get_bills(acct.id):
            conn.execute(
                "UPDATE bills SET payee = %s, monthly_amount = %s WHERE nessie_bill_id = %s",
                (b.payee, b.amount, b.id),
            )
        for d in nessie.get_deposits(acct.id):
            conn.execute(
                "UPDATE income SET deposited_on = %s, monthly_amount = %s WHERE nessie_deposit_id = %s",
                (d.on, d.amount, d.id),
            )
        for t in nessie.get_purchases(acct.id):
            conn.execute(
                "UPDATE transactions SET amount = %s, category = %s WHERE nessie_purchase_id = %s",
                (t.amount, t.category, t.id),
            )


def reset_demo_rows(conn: psycopg.Connection, customer_id: str) -> bool:
    """Forget a customer's Nessie ids and bank rows when they came from the in-memory fake (their ids start
    with 'fake-'), so a seed with the real client creates them in the real service instead. The id decides,
    not the `source` flag: a customer with real ids is never touched, even if a crash left the flag at its
    default, so no one is ever created twice. Returns True when rows were reset."""
    row = conn.execute("SELECT nessie_customer_id FROM customers WHERE id = %s", (customer_id,)).fetchone()
    if row is None or not is_fake_id(row[0]):
        return False
    for table in ("transactions", "income", "bills", "accounts"):
        conn.execute(f"DELETE FROM {table} WHERE customer_id = %s", (customer_id,))
    conn.execute("UPDATE customers SET nessie_customer_id = NULL WHERE id = %s", (customer_id,))
    return True
