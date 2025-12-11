import os
import json
import logging
from monitor import UzumMonitor
from bot import format_report, send_telegram

logging.basicConfig(level=logging.INFO)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables')

    monitor = UzumMonitor()

    # fetch current products
    seen = {}
    for url in monitor.category_urls:
        prods = monitor.fetch_products_from_url(url)
        for p in prods:
            seen[p['product_id']] = p

    # load previous state (product_id -> stock)
    old_state = {}
    if os.path.exists('state.json'):
        try:
            with open('state.json', 'r') as f:
                old_state = json.load(f)
        except Exception:
            old_state = {}

    high_demand = []
    short_supply = []

    for pid, p in seen.items():
        prev = old_state.get(pid)
        last = p.get('stock')
        # short supply
        if last is not None and last <= 5:
            item = p.copy()
            item['stock'] = last
            short_supply.append(item)

        # high demand: compare prev->last
        if isinstance(prev, int) and isinstance(last, int):
            delta = prev - last
            if prev > 0 and delta >= max(3, int(prev * 0.1)):
                item = p.copy()
                item['stock'] = last
                item['prev_stock'] = prev
                item['demand_delta'] = delta
                try:
                    item['demand_pct'] = round((delta / prev) * 100)
                except Exception:
                    item['demand_pct'] = None
                high_demand.append(item)

    # send report if anything interesting (or always send — here we send always)
    text = format_report(high_demand, short_supply)
    send_telegram(token, chat_id, text)

    # write current state for next run
    new_state = {pid: (p.get('stock') if isinstance(p.get('stock'), int) else None) for pid, p in seen.items()}
    with open('state.json', 'w') as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
