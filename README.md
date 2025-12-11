
```markdown
# uzum-bots
This project scans Uzum category pages periodically and notifies a Telegram chat about products that show high demand (recent stock drops) and products in short supply.

Quick start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export TELEGRAM_BOT_TOKEN=<your-token>
export TELEGRAM_CHAT_ID=<your-chat-id>
# Optional: override categories to scan (comma-separated)
export UZUM_CATEGORY_URLS="https://uzum.uz/category/phones,https://uzum.uz/category/laptops"
```

3. Run the bot (runs check immediately and every 30 minutes):

```bash
python bot.py
```

Notes and customization

- The scraper uses simple heuristics to find product links and nearby stock text. Uzum site structure may differ; to improve accuracy, update `monitor.py` parsing logic in `_parse_listing`.
- The monitor stores observations in `uzum_monitor.db`. It computes demand/shortage by comparing the last two observations for each product.
- For production use consider running the script under a process manager (systemd, docker, supervisord) or containerizing it.

If you want, I can:
- adapt the parser to exact Uzum HTML structure;
- add Dockerfile / systemd unit;
- add more robust message formatting or batched updates.

**Deploy (24/7)**

You can run the bot 24/7 using `systemd` on a VPS or using Docker with restart policy. Two quick options:

- Systemd (preferred on a Linux VPS): copy `deploy/uzum-bot.service` to `/etc/systemd/system/uzum-bot.service`, edit paths and `EnvironmentFile` to point to your repo and `.env`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now uzum-bot.service
sudo journalctl -u uzum-bot -f
```

- Docker (works on any host with Docker): build and run using the included `Dockerfile` and `docker-compose.yml`.

Build & run with Docker:
```bash
docker build -t uzum-bot .
docker run -d --name uzum-bot --restart unless-stopped --env-file .env -v $(pwd)/uzum_monitor.db:/app/uzum_monitor.db uzum-bot
docker logs -f uzum-bot
```

Or with docker-compose:
```bash
docker-compose up -d
docker-compose logs -f
```

Notes:
- Ensure `.env` contains `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` and is not committed to git.
- On systemd, the service will restart automatically if it crashes or after host reboots.
- On Docker, `--restart unless-stopped` keeps the container running across reboots.

```
