import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from typing import List, Dict, Optional

DB_PATH = 'uzum_monitor.db'
LOGGER = logging.getLogger(__name__)


def _normalize_stock(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.replace('\xa0', ' ')
    # try to find numbers
    m = re.search(r"(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except:
            return None
    # detect explicit out of stock
    if 'нет' in text.lower() or 'sold out' in text.lower() or 'out of stock' in text.lower():
        return 0
    return None


class MonitorDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT,
            url TEXT,
            last_stock INTEGER,
            last_seen TIMESTAMP
        )
        ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            stock INTEGER,
            ts TIMESTAMP
        )
        ''')
        self.conn.commit()

    def upsert(self, product_id, name, url, stock):
        ts = datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute('SELECT last_stock FROM products WHERE product_id=?', (product_id,))
        row = c.fetchone()
        if row is None:
            c.execute('INSERT INTO products(product_id,name,url,last_stock,last_seen) VALUES (?,?,?,?,?)', (product_id, name, url, stock, ts))
        else:
            c.execute('UPDATE products SET name=?, url=?, last_stock=?, last_seen=? WHERE product_id=?', (name, url, stock, ts, product_id))
        c.execute('INSERT INTO history(product_id,stock,ts) VALUES (?,?,?)', (product_id, stock, ts))
        self.conn.commit()

    def get_last_two(self, product_id):
        c = self.conn.cursor()
        c.execute('SELECT stock, ts FROM history WHERE product_id=? ORDER BY ts DESC LIMIT 2', (product_id,))
        return c.fetchall()

    def get_history_since(self, product_id, since_iso=None):
        c = self.conn.cursor()
        if since_iso:
            c.execute('SELECT stock, ts FROM history WHERE product_id=? AND ts>=? ORDER BY ts ASC', (product_id, since_iso))
        else:
            c.execute('SELECT stock, ts FROM history WHERE product_id=? ORDER BY ts ASC', (product_id,))
        return c.fetchall()

    def list_all_products(self):
        c = self.conn.cursor()
        c.execute('SELECT product_id, name, url, last_stock FROM products')
        return [{'product_id': r[0], 'name': r[1], 'url': r[2], 'stock': r[3]} for r in c.fetchall()]


class UzumMonitor:
    def __init__(self, category_urls: Optional[List[str]] = None):
        # default to uzum main page — user can adjust config file
        self.category_urls = category_urls or ['https://uzum.uz/']
        self.db = MonitorDB()

    def _parse_listing(self, html: str, base_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, 'html.parser')
        products = []

        # heuristic: find product links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/product/' in href or '/p/' in href:
                name = a.get_text(strip=True)
                if not name:
                    continue
                url = href if href.startswith('http') else base_url.rstrip('/') + '/' + href.lstrip('/')
                # try to find nearby stock info
                stock = None
                parent = a.parent
                text = ''
                if parent:
                    text = parent.get_text(' ', strip=True)
                stock = _normalize_stock(text)
                pid = re.sub(r'[^0-9a-zA-Z_-]', '_', url)
                products.append({'product_id': pid, 'name': name, 'url': url, 'stock': stock})

        return products

    def fetch_products_from_url(self, url: str) -> List[Dict]:
        try:
            r = requests.get(url, timeout=20, headers={'User-Agent': 'uzum-monitor-bot/1.0'})
            if r.status_code != 200:
                LOGGER.warning('Failed to fetch %s -> %s', url, r.status_code)
                return []
            return self._parse_listing(r.text, url)
        except Exception as e:
            LOGGER.exception('Fetch error for %s: %s', url, e)
            return []

    def run_check(self):
        # gather products
        seen = {}
        for url in self.category_urls:
            prods = self.fetch_products_from_url(url)
            for p in prods:
                seen[p['product_id']] = p

        # persist and analyze
        for p in seen.values():
            self.db.upsert(p['product_id'], p['name'], p['url'], p['stock'])

        # analysis heuristics
        all_products = self.db.list_all_products()
        high_demand = []
        short_supply = []

        for p in all_products:
            hist = self.db.get_last_two(p['product_id'])
            last_stock = None
            prev_stock = None
            if hist:
                last_stock = hist[0][0]
                if len(hist) > 1:
                    prev_stock = hist[1][0]

            # short supply: explicit 0 or small number
            if last_stock is not None and last_stock <= 5:
                item = p.copy()
                item['stock'] = last_stock
                short_supply.append(item)

            # high demand: compute delta and attach score
            if prev_stock is not None and last_stock is not None:
                delta = prev_stock - last_stock
                if prev_stock > 0 and delta >= max(3, int(prev_stock * 0.1)):
                    item = p.copy()
                    item['stock'] = last_stock
                    item['prev_stock'] = prev_stock
                    item['demand_delta'] = delta
                    # relative percent
                    try:
                        item['demand_pct'] = round((delta / prev_stock) * 100)
                    except Exception:
                        item['demand_pct'] = None
                    high_demand.append(item)

        # sort both lists by severity
        # sort high demand by largest absolute delta desc, short supply by smallest stock asc
        high_demand.sort(key=lambda x: x.get('demand_delta', 0), reverse=True)
        short_supply.sort(key=lambda x: (x.get('stock') is None, x.get('stock') if x.get('stock') is not None else 999))

        return high_demand, short_supply

    def increased_shortage_last_days(self, days: int = 3, threshold: int = 5):
        """Return products where shortage increased in last `days` days.
        
        Shortage = stock <= threshold. Detect products that were NOT in shortage
        3 days ago but ARE in shortage now.
        """
        from datetime import timedelta
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        increased = []
        all_products = self.db.list_all_products()

        for p in all_products:
            hist = self.db.get_history_since(p['product_id'], since_iso=since)
            if not hist:
                continue
            # hist sorted asc: take first (oldest) and last (newest)
            first_stock = hist[0][0]
            last_stock = hist[-1][0]
            if first_stock is None or last_stock is None:
                continue
            # was NOT in shortage, now IS in shortage
            was_ok = first_stock > threshold
            is_short = last_stock <= threshold
            if was_ok and is_short:
                item = p.copy()
                item['stock_then'] = first_stock
                item['stock_now'] = last_stock
                item['delta'] = last_stock - first_stock
                increased.append(item)

        increased.sort(key=lambda x: x.get('stock_now', 999))
        return increased

    def increased_demand_last_days(self, days: int = 3, min_drop: int = 5):
        """Return products where demand increased (stock dropped) in last `days` days.
        
        Detect products with significant stock drop: >= min_drop or >= 10% of initial.
        """
        from datetime import timedelta
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        demand = []
        all_products = self.db.list_all_products()

        for p in all_products:
            hist = self.db.get_history_since(p['product_id'], since_iso=since)
            if not hist:
                continue
            # hist sorted asc: take first (oldest) and last (newest)
            first_stock = hist[0][0]
            last_stock = hist[-1][0]
            if first_stock is None or last_stock is None:
                continue
            try:
                delta = int(first_stock) - int(last_stock)
            except Exception:
                continue
            if first_stock > 0 and delta >= max(min_drop, int(first_stock * 0.1)):
                item = p.copy()
                item['stock_then'] = first_stock
                item['stock_now'] = last_stock
                item['delta'] = delta
                try:
                    item['delta_pct'] = round((delta / first_stock) * 100)
                except Exception:
                    item['delta_pct'] = None
                demand.append(item)

        demand.sort(key=lambda x: x.get('delta', 0), reverse=True)
        return demand

    def top_sellers_last_days(self, days: int = 7, min_sold: int = 5):
        """Return products that sold well in the last `days` days.

        Heuristic: compute earliest and latest stock in the period; sold = earliest - latest.
        """
        from datetime import datetime, timedelta

        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sellers = []
        all_products = self.db.list_all_products()
        for p in all_products:
            hist = self.db.get_history_since(p['product_id'], since_iso=since)
            if not hist:
                continue
            # hist sorted asc: take first and last
            first_stock = hist[0][0]
            last_stock = hist[-1][0]
            if first_stock is None or last_stock is None:
                continue
            sold = 0
            try:
                sold = int(first_stock) - int(last_stock)
            except Exception:
                continue
            if sold >= min_sold:
                item = p.copy()
                item['sold'] = sold
                try:
                    item['sold_pct'] = round((sold / first_stock) * 100)
                except Exception:
                    item['sold_pct'] = None
                sellers.append(item)

        sellers.sort(key=lambda x: x.get('sold', 0), reverse=True)
        return sellers
