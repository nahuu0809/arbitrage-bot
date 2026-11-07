from __future__ import annotations

import os
import sys

from ppi_client.ppi import PPI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.config import get_config


def main() -> int:
    cfg = get_config()
    ppi_cfg = cfg.ppi
    sandbox = cfg.is_sandbox

    print(f"[SMOKE] mode={cfg.mode} sandbox={sandbox}")
    client = PPI(sandbox=sandbox)
    api_client = getattr(client, "_PPI__apiClient")
    rest_client = api_client.get_rest_client()
    base_url = getattr(rest_client, "_RestClient__API_BASE_URL", None)
    print(f"[SMOKE] sdk_base_url={base_url}")

    try:
        client.account.login_api(ppi_cfg.username, ppi_cfg.password)
        print("[SMOKE] login=OK")
    except Exception as e:
        print(f"[SMOKE] login=FAIL: {e}")
        return 1

    try:
        accounts = client.account.get_accounts()
        print(f"[SMOKE] accounts={len(accounts)}")
        if accounts:
            first_account = accounts[0].get("accountNumber", "")
            print(f"[SMOKE] first_account={first_account}")
        else:
            print("[SMOKE] no accounts returned")
            return 1
    except Exception as e:
        print(f"[SMOKE] get_accounts=FAIL: {e}")
        return 1

    try:
        quote = client.marketdata.current("GGAL", "Acciones", "A-24HS")
        print(f"[SMOKE] current=OK price={quote.get('price')}")
    except Exception as e:
        print(f"[SMOKE] current=FAIL: {e}")
        return 1

    try:
        book = client.marketdata.book("GGAL", "Acciones", "A-24HS")
        bids = len(book.get("bids", []) or [])
        offers = len(book.get("offers", []) or [])
        print(f"[SMOKE] book=OK bids={bids} offers={offers}")
    except Exception as e:
        print(f"[SMOKE] book=FAIL: {e}")
        return 1

    print("[SMOKE] SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
