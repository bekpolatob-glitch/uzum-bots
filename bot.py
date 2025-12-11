import os
import time
import logging
from datetime import datetime
from monitor import UzumMonitor
import requests
from dotenv import load_dotenv
import config

load_dotenv()

logging.basicConfig(level=logging.INFO)


def send_telegram(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    if not resp.ok:
        logging.error("Telegram send failed: %s %s", resp.status_code, resp.text)
    return resp


def format_report(increased_shortage=None, increased_demand=None):
    lines = []
    t = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    lines.append(f"Uzum Monitor Report (3-day analysis) — {t}\n")

    if increased_shortage:
        lines.append("<b>Increased shortage (last 3 days)</b>:\n")
        for p in increased_shortage[:15]:
            then = p.get('stock_then')
            now = p.get('stock_now')
            extra = f" ({then} → {now})"
            lines.append(f"• <a href=\"{p['url']}\">{p['name']}</a>{extra}")
    else:
        lines.append("No products with increased shortage.\n")

    if increased_demand:
        lines.append("\n<b>Increased demand (last 3 days)</b>:\n")
        for p in increased_demand[:15]:
            delta = p.get('delta')
            pct = p.get('delta_pct')
            then = p.get('stock_then')
            now = p.get('stock_now')
            extra = [f"Δ{delta}"]
            if pct is not None:
                extra.append(f"{pct}%")
            extra_s = ' (' + ', '.join(extra) + f", {then} → {now})"
            lines.append(f"• <a href=\"{p['url']}\">{p['name']}</a> — {extra_s}")
    else:
        lines.append("\nNo products with increased demand.")

    return "\n".join(lines)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.')
        return

    monitor = UzumMonitor(category_urls=getattr(config, 'CATEGORY_URLS', None))

    # run immediately, then every 3 days
    while True:
        try:
            increased_shortage = monitor.increased_shortage_last_days(days=3, threshold=5)
            increased_demand = monitor.increased_demand_last_days(days=3, min_drop=5)
            text = format_report(increased_shortage=increased_shortage, increased_demand=increased_demand)
            send_telegram(token, chat_id, text)
            logging.info('Report sent — %d shortage increase, %d demand increase', len(increased_shortage), len(increased_demand))
        except Exception as e:
            logging.exception('Error during check: %s', e)

        # sleep 3 days
        time.sleep(259200)


if __name__ == '__main__':
    main()
