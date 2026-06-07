#!/usr/bin/env python3
"""
Price Tracker - Daily price checker with email alerts

Products 1-3: checked via both ScraperAPI AND SerpAPI (all results listed, lowest highlighted)
Products 4+:  checked via ScraperAPI only
Alert fires if ANY listed price hits or drops below target.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
PRODUCTS_FILE  = Path("products.json")
HISTORY_FILE   = Path("price_history.json")
TODAY          = datetime.utcnow().strftime("%Y-%m-%d")

GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASS     = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_TO       = os.environ.get("ALERT_EMAIL", GMAIL_USER)

SCRAPER_KEY    = os.environ.get("SCRAPER_API_KEY", "")   # scraperapi.com
SERP_KEY       = os.environ.get("SERP_API_KEY", "")      # serpapi.com

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def clean_price(raw: str) -> float | None:
    import re
    m = re.search(r"[\d]+\.?\d*", raw.replace(",", "").replace("$", "").strip())
    if m:
        try:
            v = float(m.group())
            return v if v > 0.5 else None
        except ValueError:
            pass
    return None

# ── ScraperAPI ────────────────────────────────────────────────────────────────

def fetch_via_scraperapi(product: dict) -> dict | None:
    """
    Fetch price + shipping from a product URL via ScraperAPI.
    Returns {"source": "ScraperAPI", "retailer": ..., "price": float, "shipping": str, "url": str}
    """
    if not SCRAPER_KEY:
        print("  ⚠ SCRAPER_API_KEY not set — skipping ScraperAPI")
        return None

    url = product.get("url", "").strip()
    name = product.get("name", "")

    if not url:
        # No URL: use ScraperAPI's Google Shopping endpoint
        return fetch_scraperapi_google_shopping(name)

    try:
        api_url = f"https://api.scraperapi.com/?api_key={SCRAPER_KEY}&url={requests.utils.quote(url, safe=':/?=&')}&render=true"
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        price = None
        shipping = "Unknown"

        # --- Detect retailer ---
        retailer = "Unknown"
        if "amazon.com" in url:
            retailer = "Amazon"
            for sel in [".a-price .a-offscreen", "#priceblock_ourprice",
                        "#priceblock_dealprice", "#price_inside_buybox",
                        "span.a-price-whole"]:
                el = soup.select_one(sel)
                if el:
                    p = clean_price(el.get_text())
                    if p:
                        price = p
                        break
            # Amazon shipping
            ship_el = soup.select_one("#deliveryMessageMirId, #mir-layout-DELIVERY_BLOCK")
            if ship_el:
                t = ship_el.get_text(" ", strip=True)
                if "free" in t.lower():
                    shipping = "Free"
                elif "$" in t:
                    s = clean_price(t)
                    shipping = f"${s:.2f}" if s else "Unknown"
            else:
                shipping = "Unknown"

        elif "dickssportinggoods.com" in url:
            retailer = "Dick's Sporting Goods"
            for sel in ["[data-testid='saleprice']", ".final-price", ".product-price"]:
                el = soup.select_one(sel)
                if el:
                    p = clean_price(el.get_text())
                    if p:
                        price = p
                        break

        elif "justbats.com" in url:
            retailer = "JustBats"
            for sel in [".product-price", ".price-box .price", ".special-price .price"]:
                el = soup.select_one(sel)
                if el:
                    p = clean_price(el.get_text())
                    if p:
                        price = p
                        break

        else:
            # Generic fallback
            import re
            retailer = url.split("/")[2].replace("www.", "").split(".")[0].title()
            candidates = soup.find_all(string=re.compile(r"\$\s*\d{2,}"))
            for c in candidates[:8]:
                p = clean_price(str(c))
                if p and p > 5:
                    price = p
                    break

        if price is None:
            print(f"  ⚠ ScraperAPI: could not extract price from {url[:60]}")
            return None

        return {
            "source":   "ScraperAPI",
            "retailer": retailer,
            "price":    price,
            "shipping": shipping,
            "url":      url,
        }

    except Exception as e:
        print(f"  ⚠ ScraperAPI error: {e}")
        return None


def fetch_scraperapi_google_shopping(name: str) -> dict | None:
    """Use ScraperAPI to scrape Google Shopping when no URL is given."""
    if not SCRAPER_KEY:
        return None
    try:
        q = requests.utils.quote(f"{name} buy")
        target = f"https://www.google.com/search?q={q}&tbm=shop"
        api_url = f"https://api.scraperapi.com/?api_key={SCRAPER_KEY}&url={requests.utils.quote(target, safe=':/?=&')}"
        resp = requests.get(api_url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        import re
        # Google Shopping price spans
        for el in soup.find_all("span", string=re.compile(r"\$\d+")):
            p = clean_price(el.get_text())
            if p and p > 5:
                return {
                    "source":   "ScraperAPI",
                    "retailer": "Google Shopping",
                    "price":    p,
                    "shipping": "Unknown",
                    "url":      "",
                }
    except Exception as e:
        print(f"  ⚠ ScraperAPI Google Shopping error: {e}")
    return None

# ── SerpAPI ───────────────────────────────────────────────────────────────────

def fetch_via_serpapi(product: dict) -> list[dict]:
    """
    Search Google Shopping via SerpAPI.
    Returns a list of {"source": "SerpAPI", "retailer": ..., "price": float, "shipping": str, "url": str}
    (multiple results possible — we return all of them)
    """
    if not SERP_KEY:
        print("  ⚠ SERP_API_KEY not set — skipping SerpAPI")
        return []

    name = product.get("name", "")
    results = []

    try:
        params = {
            "engine":  "google_shopping",
            "q":       name,
            "api_key": SERP_KEY,
            "num":     5,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("shopping_results", [])[:5]:
            raw_price = item.get("price", "")
            price = clean_price(str(raw_price)) if raw_price else None
            if price is None:
                continue

            # Shipping
            shipping_raw = item.get("shipping", "")
            if not shipping_raw:
                shipping = "Unknown"
            elif "free" in str(shipping_raw).lower():
                shipping = "Free"
            else:
                s = clean_price(str(shipping_raw))
                shipping = f"${s:.2f}" if s else str(shipping_raw) or "Unknown"

            results.append({
                "source":   "SerpAPI",
                "retailer": item.get("source", "Unknown"),
                "price":    price,
                "shipping": shipping,
                "url":      item.get("link", ""),
            })

    except Exception as e:
        print(f"  ⚠ SerpAPI error: {e}")

    return results

# ── Per-product fetch ─────────────────────────────────────────────────────────

def get_all_prices(product: dict, index: int) -> list[dict]:
    """
    Returns a list of price results for a product.
    Products 0-2 (1st-3rd): ScraperAPI + SerpAPI
    Products 3+: ScraperAPI only
    Each result: {source, retailer, price, shipping, url}
    """
    results = []

    # ScraperAPI (always)
    scraper_result = fetch_via_scraperapi(product)
    if scraper_result:
        results.append(scraper_result)

    # SerpAPI (first 3 products only)
    if index < 3:
        serp_results = fetch_via_serpapi(product)
        results.extend(serp_results)

    return results

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email_alert(alerts: list[dict]):
    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠ Gmail credentials not set — skipping email alert.")
        return

    subject = f"🏷 Price Alert: {len(alerts)} product(s) hit your target!"

    product_blocks = ""
    for a in alerts:
        rows = ""
        for r in a["results"]:
            is_lowest = r["price"] == a["lowest_price"]
            highlight = "background:#f0fff4;font-weight:bold" if is_lowest else ""
            lowest_badge = " ⭐ lowest" if is_lowest else ""
            buy_link = f'<a href="{r["url"]}" style="color:#2b6cb0">Buy →</a>' if r.get("url") else "—"
            rows += f"""
            <tr style="{highlight}">
              <td style="padding:7px 10px;border-bottom:1px solid #eee">{r['retailer']}{lowest_badge}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #eee">{r['source']}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #eee;color:#276749">${r['price']:.2f}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #eee">{r['shipping']}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #eee">{buy_link}</td>
            </tr>"""

        product_blocks += f"""
        <div style="margin-bottom:28px">
          <h3 style="margin:0 0 4px;font-size:15px">{a['name']}</h3>
          <p style="margin:0 0 8px;font-size:12px;color:#718096">
            Target: <strong>${a['target']:.2f}</strong> &nbsp;·&nbsp;
            Lowest found: <strong style="color:#276749">${a['lowest_price']:.2f}</strong>
          </p>
          <table width="100%" cellspacing="0" style="border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="background:#f7fafc;font-size:11px;color:#718096">
                <th style="padding:6px 10px;text-align:left">Retailer</th>
                <th style="padding:6px 10px;text-align:left">Source</th>
                <th style="padding:6px 10px;text-align:left">Price</th>
                <th style="padding:6px 10px;text-align:left">Shipping</th>
                <th style="padding:6px 10px;text-align:left">Link</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    html = f"""
    <html><body style="font-family:sans-serif;color:#1a202c;max-width:640px;margin:auto">
      <h2 style="background:#1a202c;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0;margin:0">
        🏷 Price Drop Alert · {TODAY}
      </h2>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <p style="margin-bottom:20px">
          The following products have dropped to or below your target price.
          Highlighted rows ⭐ show the lowest price found.
        </p>
        {product_blocks}
        <p style="font-size:11px;color:#a0aec0;margin-top:16px;border-top:1px solid #eee;padding-top:12px">
          Sent by PriceWatch · prices are approximate and may vary
        </p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ALERT_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, ALERT_TO, msg.as_string())

    print(f"✉ Alert email sent to {ALERT_TO}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    products = load_json(PRODUCTS_FILE, [])
    history  = load_json(HISTORY_FILE, {})

    if not products:
        print("No products to track. Add some via the dashboard.")
        return

    alerts = []

    for idx, product in enumerate(products):
        pid    = product["id"]
        name   = product["name"]
        target = float(product.get("target_price", 0))

        label = "(ScraperAPI + SerpAPI)" if idx < 3 else "(ScraperAPI only)"
        print(f"\n🔍 [{idx+1}] {name} {label}")

        results = get_all_prices(product, idx)

        if not results:
            print(f"  ✗ No prices retrieved.")
            continue

        prices = [r["price"] for r in results]
        lowest = min(prices)

        for r in results:
            flag = " ← LOWEST" if r["price"] == lowest else ""
            print(f"  {r['source']:12} {r['retailer']:25} ${r['price']:.2f}  shipping: {r['shipping']}{flag}")

        # Store lowest price in history
        if pid not in history:
            history[pid] = []
        history[pid].append({"date": TODAY, "price": lowest, "results": results})
        history[pid] = history[pid][-90:]

        # Alert if ANY price hits target
        triggering = [r for r in results if target > 0 and r["price"] <= target]
        if triggering:
            prev = history[pid][-2]["price"] if len(history[pid]) >= 2 else lowest
            alerts.append({
                "name":         name,
                "target":       target,
                "lowest_price": lowest,
                "results":      results,
                "previous":     prev,
            })
            print(f"  🎉 ALERT triggered! Lowest: ${lowest:.2f} (target: ${target:.2f})")

    save_json(HISTORY_FILE, history)
    print(f"\n✅ History saved → {HISTORY_FILE}")

    if alerts:
        send_email_alert(alerts)
    else:
        print("📭 No alerts triggered today.")

if __name__ == "__main__":
    main()
