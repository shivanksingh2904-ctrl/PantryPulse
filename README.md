# 🥬 PantryPulse

A Streamlit app that helps a household **waste less food and save money**.

**The problem:** UNEP's Food Waste Index (2021) estimates households are the biggest source of
food waste, about 50 kg per person per year in India. Most of it is food that simply gets forgotten
until it spoils.

**What it does**
- Tracks what you buy, its price and its use-by date (with auto-suggested shelf life).
- Ranks **what to use first** and shows the **value at risk** in the next 2 days.
- Suggests **recipes that rescue expiring food** (never suggests expired items; handles names like *dahi = yogurt*).
- One click marks ingredients as used after you cook.
- **Impact tab:** money used vs wasted, waste rate, kg wasted, weekly trend.

## Run it
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Open the sidebar and press **Load sample data** to explore with demo groceries.

## Run the tests (no Streamlit needed)
```bash
python -m unittest test_pantrypulse -v
```

## Project layout (flat - all files in the repo root)
```
app.py               Streamlit UI (5 tabs)
engine.py            Pure logic: status, recipe ranking, waste stats (pandas)
db.py                SQLite storage (stdlib sqlite3)
recipes.json         17 editable recipes - add your own!
test_pantrypulse.py  13 unit tests
requirements.txt
```
Data is stored in `pantry.db` (change with the `PANTRY_DB` environment variable).

## Ideas to extend
- Add your regional recipes to `recipes.json`.
- Barcode / receipt scanning for faster entry.
- Email or WhatsApp reminders for items expiring tomorrow.
- Note: on Streamlit Community Cloud the file system is temporary, so use an external DB there.
