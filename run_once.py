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

    # fetch current products and persist to DB
    seen = {}
    for url in monitor.category_urls:
        prods = monitor.fetch_products_from_url(url)
        for p in prods:
            seen[p['product_id']] = p
            # persist observation to DB
            try:
                monitor.db.upsert(p['product_id'], p['name'], p['url'], p.get('stock'))
            except Exception:
                pass

    # compute 3-day trends: increased shortage and demand
    increased_shortage = monitor.increased_shortage_last_days(days=3, threshold=5)
    increased_demand = monitor.increased_demand_last_days(days=3, min_drop=5)

    # send report
    from bot import format_report
    text = format_report(increased_shortage=increased_shortage, increased_demand=increased_demand)
    send_telegram(token, chat_id, text)

    # write current minimal state for compatibility (product_id -> stock)
    new_state = {pid: (p.get('stock') if isinstance(p.get('stock'), int) else None) for pid, p in seen.items()}
    with open('state.json', 'w') as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
