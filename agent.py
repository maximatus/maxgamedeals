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
# Alertas via IsThereAnyDeal API
    try:
        itad_key = os.getenv("ITAD_API_KEY")
        
        # Endpoint ITAD: deals actuales filtrados por tiendas oficiales
        deals_url = "https://api.isthereanydeal.com/deals/v2"
        params = {
            "key": itad_key,
            "shops": "61,35,16",  # 61=Steam, 35=Epic, 16=GOG
            "country": "US",
            "type": "game",
            "priceMin": 40,
            "limit": 50,
        }
        r = requests.get(deals_url, params=params, timeout=10)
        data = r.json()
        items = data.get("list", [])
        
        for item in items:
            name = item.get("title", "")
            deal = item.get("deal", {})
            price_new = deal.get("price", {}).get("amount", 0)
            price_old = deal.get("regular", {}).get("amount", 0)
            discount = deal.get("cut", 0)
            shop = item.get("shop", {}).get("name", "")
            url = item.get("urls", {}).get("game", "")
            
            if price_old < deals_min_price or discount < deals_min_pct:
                continue
            
            in_watchlist = any(
                g["title"].lower() in name.lower() or name.lower() in g["title"].lower()
                for g in watchlist
            )
            if not in_watchlist:
                alerts.append(
                    f"🔥 *Oferta en {shop}: {name}*\n"
                    f"💰 Precio: ~~${price_old:.2f}~~ → *${price_new:.2f}*\n"
                    f"📉 Descuento: {discount}%\n"
                    f"🔗 {url}"
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
