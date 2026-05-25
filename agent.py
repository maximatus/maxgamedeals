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
# Alertas via Steam + Epic
    try:
        seen_names = set()

        # Steam: featuredcategories
        r = requests.get(
            "https://store.steampowered.com/api/featuredcategories/?cc=US&l=en",
            timeout=10
        )
        data = r.json()
        steam_items = []
        for section in ["specials", "top_sellers", "new_releases"]:
            steam_items += data.get(section, {}).get("items", [])

        for item in steam_items:
            name = item.get("name", "")
            original = (item.get("original_price") or 0) / 100
            current = (item.get("final_price") or 0) / 100
            discount = item.get("discount_percent", 0)
            app_id = item.get("id", "")

            if not name or name in seen_names:
                continue
            seen_names.add(name)

            in_watchlist = any(
                g["title"].lower() in name.lower() or name.lower() in g["title"].lower()
                for g in watchlist
            )
            if not in_watchlist and original >= deals_min_price and discount >= deals_min_pct:
                alerts.append(
                    f"🔥 *Oferta Steam: {name}*\n"
                    f"💰 ~~${original:.2f}~~ → *${current:.2f}*\n"
                    f"📉 {discount}% off\n"
                    f"🔗 https://store.steampowered.com/app/{app_id}"
                )

        # Epic Games: ofertas con descuento
        r2 = requests.get(
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US",
            timeout=10
        )
        epic_data = r2.json()
        epic_games = epic_data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])

        for game in epic_games:
            name = game.get("title", "")
            if not name or name in seen_names:
                continue

            promotions = game.get("promotions") or {}
            offers = promotions.get("promotionalOffers", [])
            if not offers:
                continue

            offer_list = offers[0].get("promotionalOffers", []) if offers else []
            if not offer_list:
                continue

            discount_pct = offer_list[0].get("discountSetting", {}).get("discountPercentage", 0)
            if discount_pct == 0:
                discount_pct = 100  # gratis

            price_info = game.get("price", {}).get("totalPrice", {})
            original = price_info.get("originalPrice", 0) / 100
            current = price_info.get("discountPrice", 0) / 100

            if original < deals_min_price and discount_pct < 100:
                continue

            seen_names.add(name)
            in_watchlist = any(
                g["title"].lower() in name.lower() or name.lower() in g["title"].lower()
                for g in watchlist
            )
            if not in_watchlist:
                emoji = "🎁" if discount_pct == 100 else "🔥"
                label = "GRATIS" if discount_pct == 100 else f"{discount_pct}% off"
                alerts.append(
                    f"{emoji} *Epic: {name}*\n"
                    f"💰 ~~${original:.2f}~~ → *${current:.2f}*\n"
                    f"📉 {label}\n"
                    f"🔗 https://store.epicgames.com/en-US/p/{game.get('productSlug', '')}"
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
