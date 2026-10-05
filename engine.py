"""Pure logic: no Streamlit, no database. Easy to test."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

URGENT_DAYS = 2   # 0-2 days left  -> "Use soon"
WATCH_DAYS = 7    # 3-7 days left  -> "Watch"

STAPLES = {"salt", "oil", "water", "sugar", "turmeric", "cumin", "chilli powder",
           "garam masala", "pepper", "soy sauce", "cardamom"}

SYNONYMS = {
    "dahi": "yogurt", "curd": "yogurt", "yoghurt": "yogurt",
    "aloo": "potato", "tamatar": "tomato", "pyaz": "onion", "palak": "spinach",
    "chawal": "rice", "dal": "lentil", "daal": "lentil", "matar": "pea",
    "green pea": "pea", "chana": "chickpea", "gobi": "cauliflower",
    "chilly": "chilli", "chili": "chilli", "green chilli": "chilli",
    "atta": "wheat flour", "flour": "wheat flour", "doodh": "milk",
    "anda": "egg", "bell pepper": "capsicum", "shimla mirch": "capsicum",
    "cottage cheese": "paneer",
}

SHELF_LIFE_DAYS = {
    "milk": 3, "yogurt": 6, "paneer": 5, "bread": 4, "egg": 21, "tomato": 6,
    "spinach": 4, "potato": 21, "onion": 30, "carrot": 14, "cauliflower": 6,
    "capsicum": 7, "cabbage": 10, "banana": 4, "cucumber": 5, "pea": 5,
    "coriander": 4, "lemon": 10, "ginger": 20, "apple": 14, "mushroom": 4,
    "rice": 180, "lentil": 180, "chickpea": 180, "wheat flour": 90,
}

UNIT_TO_GRAMS = {"kg": 1000, "g": 1, "L": 1000, "ml": 1}   # pcs/pack cannot be converted
UNITS = ["g", "kg", "ml", "L", "pcs", "pack"]
CATEGORIES = ["Vegetables", "Fruits", "Dairy", "Grains & Pulses", "Bakery",
              "Meat & Eggs", "Packaged", "Other"]
STATUS_EMOJI = {"Expired": "🔴 Expired", "Use soon": "🟠 Use soon",
                "Watch": "🟡 Watch", "Fresh": "🟢 Fresh"}


def _singular(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("oes"):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def normalize(name: str) -> str:
    """'Tomatoes ' -> 'tomato', 'Dahi' -> 'yogurt'. Used on both pantry and recipe names."""
    s = " ".join(re.sub(r"[^a-z\s]", " ", str(name).lower()).split())
    if s in SYNONYMS:
        return SYNONYMS[s]
    s = _singular(s)
    return SYNONYMS.get(s, s)


def suggest_shelf_days(name: str, default: int = 7) -> int:
    return SHELF_LIFE_DAYS.get(normalize(name), default)


def status_label(days_left: int) -> str:
    if days_left < 0:
        return "Expired"
    if days_left <= URGENT_DAYS:
        return "Use soon"
    if days_left <= WATCH_DAYS:
        return "Watch"
    return "Fresh"


def enrich(df: pd.DataFrame, today: date) -> pd.DataFrame:
    """Add days_left and status_label columns."""
    out = df.copy()
    if out.empty:
        out["days_left"] = pd.Series(dtype="int64")
        out["status_label"] = pd.Series(dtype="object")
        return out
    out["days_left"] = (pd.to_datetime(out["expiry"]) - pd.Timestamp(today)).dt.days.astype(int)
    out["status_label"] = out["days_left"].map(status_label)
    return out


def use_first(active: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Items to use first: soonest expiry, ties broken by higher value."""
    return active.sort_values(["days_left", "price"], ascending=[True, False]).head(n)


def money_at_risk(active: pd.DataFrame) -> dict:
    soon = active[(active["days_left"] >= 0) & (active["days_left"] <= URGENT_DAYS)]
    expired = active[active["days_left"] < 0]
    return {"at_risk": float(soon["price"].sum()), "expired_value": float(expired["price"].sum()),
            "soon_count": int(len(soon)), "expired_count": int(len(expired))}


def load_recipes(path: Path | None = None) -> list[dict]:
    path = path or Path(__file__).with_name("recipes.json")
    return json.loads(path.read_text(encoding="utf-8"))


def find_recipes(active: pd.DataFrame, recipes: list[dict], diet: str = "any",
                 max_minutes: int | None = None, min_coverage: float = 0.6) -> list[dict]:
    """Rank recipes by how much expiring food they rescue. Expired food is never suggested."""
    have: dict[str, dict] = {}
    for row in active.itertuples():
        if row.days_left < 0:
            continue
        entry = have.setdefault(normalize(row.name), {"days": row.days_left, "ids": []})
        entry["days"] = min(entry["days"], row.days_left)
        entry["ids"].append(int(row.id))

    results = []
    for r in recipes:
        if diet == "veg" and r["diet"] != "veg":
            continue
        if max_minutes is not None and r["time"] > max_minutes:
            continue
        needed = {normalize(i): i for i in r["ingredients"] if normalize(i) not in STAPLES}
        matched = [k for k in needed if k in have]
        if not matched:
            continue
        coverage = len(matched) / len(needed)
        if coverage < min_coverage:
            continue
        rescues = [k for k in matched if have[k]["days"] <= URGENT_DAYS]
        weight = sum(3 if have[k]["days"] <= URGENT_DAYS else 2 if have[k]["days"] <= WATCH_DAYS else 1
                     for k in matched)
        results.append({
            "name": r["name"], "time": r["time"], "diet": r["diet"], "steps": r["steps"],
            "have": [needed[k] for k in matched],
            "missing": [needed[k] for k in needed if k not in have],
            "rescues": [needed[k] for k in rescues],
            "item_ids": sorted({i for k in matched for i in have[k]["ids"]}),
            "coverage": coverage,
            "score": round(coverage * 10 + weight * 1.5 + len(rescues) * 3, 2),
        })
    return sorted(results, key=lambda x: (-x["score"], x["time"]))


def waste_summary(all_items: pd.DataFrame) -> dict:
    done = all_items[all_items["status"].isin(["used", "wasted"])]
    used, wasted = done[done["status"] == "used"], done[done["status"] == "wasted"]
    saved, lost = float(used["price"].sum()), float(wasted["price"].sum())
    grams = wasted.apply(lambda r: r["quantity"] * UNIT_TO_GRAMS.get(r["unit"], 0), axis=1).sum() if len(wasted) else 0
    total = saved + lost
    return {"saved": saved, "lost": lost, "waste_rate": lost / total if total else 0.0,
            "used_count": int(len(used)), "wasted_count": int(len(wasted)),
            "wasted_kg": float(grams) / 1000}


def weekly_trend(all_items: pd.DataFrame) -> pd.DataFrame:
    """Money used vs wasted per week (index = week start label)."""
    done = all_items[all_items["status"].isin(["used", "wasted"]) & all_items["resolved_on"].notna()]
    if done.empty:
        return pd.DataFrame(columns=["used", "wasted"])
    d = done.assign(week=pd.to_datetime(done["resolved_on"]).dt.to_period("W-SUN").dt.start_time)
    pivot = d.pivot_table(index="week", columns="status", values="price", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(columns=["used", "wasted"], fill_value=0).sort_index()
    pivot.index = pivot.index.strftime("%d %b")
    return pivot
