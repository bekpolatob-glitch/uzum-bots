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


def format_report(high_demand, short_supply):
    lines = []
    t = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    lines.append(f"Uzum monitor report — {t}\n")

    if high_demand:
        lines.append("<b>High demand (recent stock drops)</b>:\n")
        for p in high_demand[:15]:
            delta = p.get('demand_delta')
            pct = p.get('demand_pct')
            extra = []
            if delta is not None:
                extra.append(f"Δ{delta}")
            if pct is not None:
                extra.append(f"{pct}%")
            extra_s = ' (' + ', '.join(extra) + ')' if extra else ''
            lines.append(f"• <a href=\"{p['url']}\">{p['name']}</a> — stock: {p.get('stock')}{extra_s}")
    else:
        lines.append("No high-demand products detected.\n")

    if short_supply:
        lines.append("\n<b>Short supply (low/none)</b>:\n")
        for p in short_supply[:15]:
            lines.append(f"• <a href=\"{p['url']}\">{p['name']}</a> — stock: {p.get('stock')}")
    else:
        lines.append("\nNo short-supply products detected.")

    return "\n".join(lines)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.')
        return

    monitor = UzumMonitor(category_urls=getattr(config, 'CATEGORY_URLS', None))

    # run immediately, then every 30 minutes
    while True:
        try:
            high, short = monitor.run_check()
            text = format_report(high, short)
            send_telegram(token, chat_id, text)
            logging.info('Report sent — %d high, %d short', len(high), len(short))
        except Exception as e:
            logging.exception('Error during check: %s', e)

        # sleep 30 minutes
        time.sleep(1800)


if __name__ == '__main__':
    main()
