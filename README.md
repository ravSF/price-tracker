# 🏷 PriceWatch — Automated Price Tracker

A free, fully automated price tracker that checks your products daily and emails you when prices drop.

**Stack:** GitHub Actions (scheduler) · Python (scraper) · GitHub Pages (dashboard) · Gmail (alerts)

---

## One-Time Setup (takes ~10 minutes)

### Step 1 — Create a GitHub account
Go to [github.com](https://github.com) and sign up for a free account.

### Step 2 — Create a new repository
1. Click **New** (top left, green button)
2. Name it `price-tracker` (or anything you like)
3. Set it to **Public** (required for free GitHub Pages)
4. Click **Create repository**

### Step 3 — Upload the files
Upload all files from this folder into your new repo:
- `index.html`
- `price_tracker.py`
- `products.json`
- `price_history.json`
- `.github/workflows/daily.yml`

You can drag-and-drop them in the GitHub web interface, or use GitHub Desktop.

> ⚠️ The `.github/workflows/` folder structure must be exact. Create the folders manually if needed.

### Step 4 — Enable GitHub Pages (your dashboard)
1. Go to your repo → **Settings** → **Pages**
2. Under "Source", select **Deploy from a branch**
3. Choose branch: **main**, folder: **/ (root)**
4. Click **Save**
5. After ~1 minute, your dashboard is live at:
   `https://YOUR-USERNAME.github.io/price-tracker/`

### Step 5 — Set up Gmail alerts

#### Create a Gmail App Password
1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** (required)
3. Search for "App passwords" → Create one
4. Name it "Price Tracker", copy the 16-character password

#### Add secrets to your GitHub repo
1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each of these:

| Secret Name         | Value                              |
|---------------------|------------------------------------|
| `GMAIL_USER`        | your Gmail address (e.g. `you@gmail.com`) |
| `GMAIL_APP_PASSWORD`| the 16-char App Password from above |
| `ALERT_EMAIL`       | email address to receive alerts (can be same as above) |

### Step 6 — Test it!
1. Go to your repo → **Actions** tab
2. Click **Daily Price Check** → **Run workflow** → **Run workflow**
3. Watch it run! Check your email after it completes.

---

## Using the Dashboard

Open your GitHub Pages URL and you'll see the **PriceWatch** dashboard.

- **Add a product:** Fill in the name, optional URL, and your target price → click **Add to Tracker**
- **Remove a product:** Click the **✕ Remove** button on any card
- **Price history:** Each card shows a sparkline chart of price history over time
- **Alerts:** Cards glow green when a product is at or below your target price

> 💡 **Important:** The dashboard saves your product list in your browser's localStorage.
> To make it permanent (and for the Python script to find your products), you also need to
> commit `products.json` to your GitHub repo after adding/removing products.
>
> **Easy way:** After updating the dashboard, copy your product list by opening your browser
> console (F12) and typing: `localStorage.getItem('pricewatch_products')`
> Then paste that into `products.json` in your GitHub repo.

---

## Adjusting the Schedule

The default schedule is **8:00 AM UTC** daily. To change it, edit `.github/workflows/daily.yml`:

```yaml
- cron: "0 8 * * *"   # minute hour day month weekday
```

Examples:
- `"0 12 * * *"` → noon UTC daily
- `"0 8 * * 1-5"` → 8am UTC weekdays only
- `"0 8,20 * * *"` → 8am and 8pm UTC daily

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No email received | Check GitHub Actions logs; verify secrets are set correctly |
| Wrong price scraped | Add the direct product URL to get more accurate results |
| Action fails | Check the Actions tab for error details |
| Dashboard not loading | Make sure GitHub Pages is enabled (Step 4) |
