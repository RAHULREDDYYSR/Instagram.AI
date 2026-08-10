"""Update statuses for an explicit Telegram shortcode batch."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from . import store
except ImportError:
    import store  # type: ignore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update Telegram reel statuses")
    parser.add_argument("status", choices=["RECEIVED", "PROCESSED", "ANALYZED", "FAILED"])
    parser.add_argument("shortcodes", nargs="+", help="Exact Telegram reel shortcodes")
    args = parser.parse_args(argv)

    # The whole load -> mutate -> save cycle runs under the Telegram store lock
    # so a concurrent fetch cycle can never silently drop these status updates.
    with store.store_lock():
        data = store.load_store()
        updated = []
        missing = []
        for shortcode in dict.fromkeys(sc.strip() for sc in args.shortcodes if sc.strip()):
            if store.update_reel_status(shortcode, args.status, store=data, save=False):
                updated.append(shortcode)
            else:
                missing.append(shortcode)
        store.save_store(data)
    print(json.dumps({
        "status": args.status,
        "updated": updated,
        "missing": missing,
    }, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
