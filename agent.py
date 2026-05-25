import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GAMES_FILE = "games.json"
CHECK_INTERVAL = 6 * 60 * 60  # cada 6 horas

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_steam_price(title):
    try:
        search_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(title)}&l=en&cc=US"
        r = requests.get(search_url, timeout=10)
        results = r.json().get("items", [])
        if not results:
            return None
        app_id = results[0]["id"]

        detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=US&l=en"
        r2 = requests.get(detail_url, timeout=10)
        data = r2.json().get(str(app_id), {}).get("data", {})
        price_data = data.get("price_overview")
        if not price_data:
            return None

        return {
            "title": data.get("name", title),
            "original": price_data["initial"] / 100,
            "current": price_data["final"] / 100,
            "discount_pct": price_data["discount_percent"],
            "url": f"https://store.steampowered.com/app/{app_id}"
        }
    except Exception:
        return None

def check_games():
    with open(GAMES_FILE) as f:
        config = json.load(f)

    watchlist = config["watchlist"]
    threshold = config["alert_threshold_pct"]
    deals_min_price = config["deals_alert"]["min_original_price"]
    deals_min_pct = config["deals_alert"]["min_discount_pct"]

    alerts = []

    for game in watchlist:
        price = get_steam_price(game["title"])
        if not price:
            continue

        discount = price["discount_pct"]
        current = price["current"]
        original = price["original"]
        max_price = game["max_price"]

        # Alerta si bajó más del threshold respecto al precio que tenías
        if original > 0 and max_price > 0:
            drop_from_base = ((max_price - current) / max_price) * 100
            if drop_from_base >= threshold and current < max_price:
                alerts.append(
                    f"🎮 *{price['title']}*\n"
                    f"💰 Precio: ~~${original:.2f}~~ → *${current:.2f}*\n"
                    f"📉 Descuento: {discount}% (bajó {drop_from_base:.0f}% de tu precio base)\n"
                    f"🔗 {price['url']}"
                )

# Alertas de juegos caros con descuento (no en tu lista)
    try:
        seen_ids = set()
        featured_items = []

        # Endpoint 1: featuredcategories (ofertas destacadas Steam)
        top_url = "https://store.steampowered.com/api/featuredcategories/?cc=US&l=en"
        r = requests.get(top_url, timeout=10)
        specials = r.json().get("specials", {}).get("items", [])
        for item in specials[:50]:
            app_id = item.get("id")
            if app_id and app_id not in seen_ids:
                seen_ids.add(app_id)
                featured_items.append(item)

        # Endpoint 2: search por juegos con descuento alto
        search_url = "https://store.steampowered.com/search/results/?filter=topsellers&specials=1&cc=US&l=en&json=1&count=50"
        r2 = requests.get(search_url, timeout=10)
        search_items = r2.json().get("items", [])
        for item in search_items:
            app_id = item.get("logo", "").split("/")[5] if item.get("logo") else None
            name = item.get("name", "")
            price_str = item.get("price", "")
            discount_str = item.get("discount_block", "")
            # Extraer discount del item
            discount_pct = item.get("discount_pct", 0)
            original_price = item.get("original_price", 0) / 100 if item.get("original_price") else 0
            final_price = item.get("price", 0) / 100 if isinstance(item.get("price"), int) else 0

            if name and discount_pct >= deals_min_pct and original_price >= deals_min_price:
                in_watchlist = any(g["title"].lower() in name.lower() or name.lower() in g["title"].lower() for g in watchlist)
                if not in_watchlist:
                    alerts.append(
                        f"🔥 *Oferta: {name}*\n"
                        f"💰 Precio: ~~${original_price:.2f}~~ → *${final_price:.2f}*\n"
                        f"📉 Descuento: {discount_pct}%"
                    )

        # Procesar featured_items
        for item in featured_items:
            original = item.get("original_price", 0) / 100
            current = item.get("final_price", 0) / 100
            discount = item.get("discount_percent", 0)
            name = item.get("name", "")
            in_watchlist = any(g["title"].lower() in name.lower() or name.lower() in g["title"].lower() for g in watchlist)
            if not in_watchlist and original >= deals_min_price and discount >= deals_min_pct:
                alerts.append(
                    f"🔥 *Oferta destacada: {name}*\n"
                    f"💰 Precio: ~~${original:.2f}~~ → *${current:.2f}*\n"
                    f"📉 Descuento: {discount}%\n"
                    f"🔗 https://store.steampowered.com/app/{item.get('id')}"
                )
    except Exception:
        pass
    if alerts:
        mensaje = "🛒 *Alertas de precios de juegos*\n\n" + "\n\n".join(alerts)
        send_telegram(mensaje)
        print(f"Enviadas {len(alerts)} alertas.")
    else:
        print("Sin alertas nuevas.")

def main():
    print("Agente de precios iniciado...")
    while True:
        check_games()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
