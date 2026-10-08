# BigData Lead Platform

A tool that helps real estate sales teams organize their customer lists and decide who to call first.

Customer data usually ends up scattered across dozens of Excel and CSV files, each with its own format, full of duplicates and missing details. This project pulls everything into one place, cleans it up, fills in the gaps, and then scores every customer so the sales team knows where to focus.

It also includes a Facebook Ads module that tracks spending, measures the quality of the leads each campaign brings in, and suggests which campaigns to scale up or pause.

**Note:** This repository contains source code only. No customer data is included.

## What it does

**1. Collects and cleans data**
Reads large batches of Excel/CSV files, fixes Vietnamese encoding issues, normalizes phone numbers and names, and removes duplicate customers. If a mapping file is provided, it also links phone numbers to the matching Facebook accounts.

**2. Enriches profiles**
Pulls in extra information from Facebook scraping tool exports and Google search results, then merges it into existing customer profiles.

**3. Scores customers**
Uses machine learning to group customers with similar traits, then gives each one a score from 0 to 10. Customers scoring 8 or higher are marked as VIP and should be contacted first.

**4. Analyzes Facebook Ads**
Connects to your ad account and Facebook Page to show cost per lead, click-through rate, ad frequency, and more. It recommends pausing weak campaigns and increasing the budget for strong ones. By default it only shows suggestions and never changes live ads.

**5. Shows results in a dashboard**
Two browser-based dashboards are included:
- Main dashboard (port 5000): customer list, detailed profiles, ad management.
- Analytics dashboard (port 8502): data health, customer groups, combined profiles.

## Installation

Requires Python 3.10 or newer.

```bash
git clone https://github.com/leozuki/bigdata-platform.git
cd bigdata-platform

python -m venv .venv
.venv\Scripts\activate          # On macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
pip install streamlit
```

Next, create your config file from the template:

```bash
copy .env.example .env          # On macOS/Linux: cp .env.example .env
```

Open `.env` and fill in your details. The main settings are:

- `DATABASE_URL`: where data is stored. Uses SQLite by default, so nothing extra to install.
- `RAW_DATA_DIR`: folder containing your original Excel/CSV files.
- `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`: needed only if you want to look up extra information on Google.
- `META_...`: your Facebook app, ad account, and Page details.
- `ADS_DRY_RUN=true`: show suggestions only, without touching live ads. Keep this on until you've reviewed the results carefully.
- `ADS_MOCK_MODE=true`: use fake data, handy for trying things out before connecting a Facebook account.

The `.env` file holds passwords and access keys, so it is excluded from Git. Never share it.

## Usage

**Process data**

```bash
python main.py                                   # Run all steps
python main.py --phase 1 --raw-dir D:/MyData     # Collect and clean data only
python main.py --phase 2 --fb-csv facebook.csv   # Enrich profiles only
python main.py --phase 3                         # Score customers only
```

**Open the dashboards**

```bash
python start.py               # Main dashboard: http://localhost:5000
python start.py --streamlit   # Analytics dashboard: http://localhost:8502
python start.py --both        # Open both
```

On Windows you can also just double-click `start.bat`.

**Try it with sample data**

If you don't have real data yet, generate some fake data to test with:

```bash
python tests/generate_sample_data.py
pytest tests/
```

## Project structure

```
main.py               Runs the data processing steps
start.py, start.bat   Launches the dashboards
dashboard/            Main dashboard (Flask)
src/
  phase1_pipeline/    Collect, clean, link phone numbers to Facebook
  phase2_enrichment/  Add information from Facebook and Google
  phase3_scoring/     Group and score customers
  analytics/          Customer analysis models
  ads_engine/         Facebook Ads analysis and optimization
  dashboard/          Analytics dashboard (Streamlit)
tests/                Tests and sample data generator
data/                 Empty; holds your data locally
```

## About personal data

This system works with personal information such as phone numbers, names, and social media accounts. When using it, please:

- Only process data you are legally allowed to collect and use, in line with Vietnam's Decree 13/2023/ND-CP on personal data protection and any other laws that apply to you.
- Follow Facebook's and Google's terms of service.
- Keep your data inside the `data/` folder on your machine. This folder is configured so it never gets pushed to GitHub.

## Built with

Python, pandas, scikit-learn, SQLAlchemy, Flask, Streamlit, Facebook Business SDK.
