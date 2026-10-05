"""PantryPulse - Streamlit app. Run with:  streamlit run app.py"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Make the bundled package importable no matter where Streamlit is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

import alerts
import engine
from db import PantryDB

st.set_page_config(page_title="PantryPulse", page_icon="🥬", layout="wide")


@st.cache_resource
def get_db() -> PantryDB:
    return PantryDB(os.environ.get("PANTRY_DB", "pantry.db"))


@st.cache_data
def get_recipes() -> list:
    return engine.load_recipes()


db, recipes, today = get_db(), get_recipes(), date.today()


def secret(name: str) -> str:
    """Read a credential from Streamlit secrets, falling back to environment variables."""
    try:
        value = st.secrets[name]
    except Exception:
        value = os.environ.get(name, "")
    return str(value) if value else ""

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🥬 PantryPulse")
    st.caption("Use what you have. Waste less. Save money.")
    cur = st.text_input("Currency symbol", value="₹", max_chars=3)
    diet = st.radio("Recipe diet", ["Any", "Vegetarian only"])
    max_time = st.slider("Max cooking time (min)", 5, 60, 45, step=5)
    st.divider()
    if st.button("Load sample data"):
        added = db.seed_sample(today)
        if added:
            st.success(f"Loaded {added} demo items.")
        else:
            st.info("Pantry isn't empty; clear it first.")
    confirm = st.checkbox("I want to delete everything")
    if st.button("Clear all data", disabled=not confirm):
        db.clear()
        st.rerun()
    st.caption("UNEP's Food Waste Index estimates Indian households waste about 50 kg of food per person each year.")

all_items = db.items()
active = engine.enrich(db.items("active"), today)

st.title("What should I use before it goes bad?")
tab_dash, tab_add, tab_pantry, tab_cook, tab_impact, tab_alert = st.tabs(
    ["📊 Dashboard", "➕ Add item", "🧺 Pantry", "🍳 Cook now", "🌍 Impact", "🔔 Alerts"])

# -------------------------------------------------------------- dashboard
with tab_dash:
    if active.empty:
        st.info("Your pantry is empty. Add an item, or press **Load sample data** in the sidebar.")
    else:
        risk = engine.money_at_risk(active)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Items in pantry", len(active))
        c2.metric("Use within 2 days", risk["soon_count"])
        c3.metric("Value at risk", f"{cur}{risk['at_risk']:,.0f}")
        c4.metric("Already expired", risk["expired_count"], delta=f"{cur}{risk['expired_value']:,.0f}",
                  delta_color="inverse")
        if risk["expired_count"]:
            st.warning("Some items have expired. Check them, then mark them as wasted in the **Pantry** tab.")

        left, right = st.columns([3, 2])
        with left:
            st.subheader("Use these first")
            top = engine.use_first(active, 6).copy()
            top["Status"] = top["status_label"].map(engine.STATUS_EMOJI)
            top["Qty"] = top.apply(lambda r: f"{r['quantity']:g} {r['unit']}", axis=1)
            top["Days left"] = top["days_left"]
            st.dataframe(top[["name", "Qty", "Days left", "Status"]].rename(columns={"name": "Item"}),
                         hide_index=True, width="stretch")
        with right:
            st.subheader("Freshness mix")
            counts = active["status_label"].value_counts().reindex(
                ["Expired", "Use soon", "Watch", "Fresh"], fill_value=0)
            st.bar_chart(counts)

# --------------------------------------------------------------- add item
with tab_add:
    st.subheader("Add a grocery item")
    a1, a2 = st.columns(2)
    name = a1.text_input("Item name", placeholder="e.g. Tomatoes, Dahi, Spinach")
    category = a2.selectbox("Category", engine.CATEGORIES)
    b1, b2, b3 = st.columns(3)
    qty = b1.number_input("Quantity", min_value=0.0, value=1.0, step=0.5)
    unit = b2.selectbox("Unit", engine.UNITS)
    price = b3.number_input(f"Price paid ({cur})", min_value=0.0, value=0.0, step=5.0)
    suggested = engine.suggest_shelf_days(name) if name.strip() else 7
    expiry = st.date_input("Use-by date", value=today + timedelta(days=suggested), key=f"expiry_{suggested}")
    if name.strip():
        st.caption(f"Suggested shelf life for '{name.strip()}': about {suggested} days. Edit the date if the pack says otherwise.")
    if st.button("Add to pantry", type="primary"):
        try:
            db.add_item(name, category, qty, unit, price, expiry, today=today)
            st.success(f"Added {name.strip()}.")
            st.rerun()
        except ValueError as err:
            st.error(str(err))

# ----------------------------------------------------------------- pantry
with tab_pantry:
    if active.empty:
        st.info("Nothing here yet.")
    else:
        statuses = st.multiselect("Filter by status", list(engine.STATUS_EMOJI), default=list(engine.STATUS_EMOJI))
        view = active[active["status_label"].isin(statuses)].copy()
        view["Status"] = view["status_label"].map(engine.STATUS_EMOJI)
        view["Qty"] = view.apply(lambda r: f"{r['quantity']:g} {r['unit']}", axis=1)
        view["Price"] = view["price"].map(lambda p: f"{cur}{p:,.0f}")
        st.dataframe(view[["name", "category", "Qty", "Price", "expiry", "days_left", "Status"]].rename(
            columns={"name": "Item", "category": "Category", "expiry": "Use by", "days_left": "Days left"}),
            hide_index=True, width="stretch")

        st.subheader("Update an item")
        labels = {int(r.id): f"{r.name} ({r.quantity:g} {r.unit}) - {r.status_label}" for r in active.itertuples()}
        chosen = st.selectbox("Pick an item", list(labels), format_func=labels.get)
        k1, k2, k3 = st.columns(3)
        if k1.button("✅ Used it"):
            db.set_status(chosen, "used", today)
            st.rerun()
        if k2.button("🗑️ Wasted it"):
            db.set_status(chosen, "wasted", today)
            st.rerun()
        if k3.button("❌ Delete (added by mistake)"):
            db.delete(chosen)
            st.rerun()

# --------------------------------------------------------------- cook now
with tab_cook:
    st.subheader("Recipes that rescue your food")
    st.caption("Ranked by how much expiring food they use. Expired items are never suggested. "
               "Oil, salt, spices and water are assumed to be in your kitchen.")
    ideas = engine.find_recipes(active, recipes, diet="veg" if diet.startswith("Veg") else "any",
                                max_minutes=max_time)
    if not ideas:
        st.info("No recipe matches yet. Add more items, or raise the cooking-time limit in the sidebar.")
    for idx, rec in enumerate(ideas[:8]):
        badge = f"  ·  rescues {', '.join(rec['rescues'])}" if rec["rescues"] else ""
        with st.expander(f"{rec['name']}  ·  {rec['time']} min{badge}", expanded=(idx == 0)):
            st.progress(rec["coverage"], text=f"You have {rec['coverage']:.0%} of the ingredients")
            st.markdown("**You have:** " + ", ".join(rec["have"]))
            if rec["missing"]:
                st.markdown("**Missing:** " + ", ".join(rec["missing"]))
            for n, step in enumerate(rec["steps"], 1):
                st.markdown(f"{n}. {step}")
            if st.button("🍽️ I cooked this (mark ingredients used)", key=f"cook_{idx}"):
                for item_id in rec["item_ids"]:
                    db.set_status(item_id, "used", today)
                st.rerun()

# ----------------------------------------------------------------- impact
with tab_impact:
    summary = engine.waste_summary(all_items)
    if summary["used_count"] + summary["wasted_count"] == 0:
        st.info("Mark items as used or wasted to see your impact.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Food used", f"{cur}{summary['saved']:,.0f}")
        m2.metric("Food wasted", f"{cur}{summary['lost']:,.0f}")
        m3.metric("Waste rate", f"{summary['waste_rate']:.0%}")
        m4.metric("Weight wasted", f"{summary['wasted_kg']:.1f} kg")
        trend = engine.weekly_trend(all_items)
        if not trend.empty:
            st.subheader("Weekly: used vs wasted")
            st.bar_chart(trend)
        st.caption("Weight counts only items measured in g, kg, ml or L. A falling waste rate is the goal.")

# ----------------------------------------------------------------- alerts
with tab_alert:
    st.subheader("Expiry alerts")
    within = st.slider("Alert me about items expiring within (days)", 1, 5, 2)
    ideas_for_alert = engine.find_recipes(active, recipes, diet="veg" if diet.startswith("Veg") else "any")
    alert = alerts.build_alert(active, within, ideas_for_alert)
    if alert is None:
        st.success("Nothing needs attention right now. 🎉")
    else:
        subject, body = alert
        st.markdown("**Preview of the message:**")
        st.code(body, language=None)
        to_email = st.text_input("Send to email", placeholder="you@example.com")
        if st.button("📧 Send email"):
            try:
                alerts.send_email(subject, body, secret("EMAIL_SENDER"), secret("EMAIL_APP_PASSWORD"), to_email)
                st.success(f"Email sent to {to_email.strip()}.")
            except Exception as err:
                st.error(f"Could not send email: {err}")
    st.caption("Sender email and app password are read from Streamlit secrets, never from the code. See the README.")
