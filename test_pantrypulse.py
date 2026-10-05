import unittest
from datetime import date, timedelta

import engine
from db import PantryDB

T = date(2026, 10, 6)


def make_db():
    db = PantryDB(":memory:")
    return db


class EngineTests(unittest.TestCase):
    def test_normalize_handles_plurals_and_synonyms(self):
        self.assertEqual(engine.normalize("Tomatoes "), "tomato")
        self.assertEqual(engine.normalize("Dahi"), "yogurt")
        self.assertEqual(engine.normalize("Green peas"), "pea")
        self.assertEqual(engine.normalize("Chillies"), "chilli")

    def test_status_boundaries(self):
        self.assertEqual(engine.status_label(-1), "Expired")
        self.assertEqual(engine.status_label(0), "Use soon")
        self.assertEqual(engine.status_label(2), "Use soon")
        self.assertEqual(engine.status_label(3), "Watch")
        self.assertEqual(engine.status_label(8), "Fresh")

    def test_shelf_life_suggestion(self):
        self.assertEqual(engine.suggest_shelf_days("Milk"), 3)
        self.assertEqual(engine.suggest_shelf_days("Mystery food"), 7)

    def test_enrich_empty_frame(self):
        out = engine.enrich(make_db().items("active"), T)
        self.assertIn("days_left", out.columns)
        self.assertTrue(out.empty)


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        self.recipes = engine.load_recipes()

    def _active(self):
        return engine.enrich(self.db.items("active"), T)

    def test_expired_items_never_suggested(self):
        self.db.add_item("Spinach", "Vegetables", 250, "g", 30, T - timedelta(days=1), today=T)
        self.db.add_item("Paneer", "Dairy", 200, "g", 90, T - timedelta(days=1), today=T)
        self.assertEqual(engine.find_recipes(self._active(), self.recipes), [])

    def test_expiring_food_ranks_first(self):
        for n, d in [("Spinach", 1), ("Paneer", 1), ("Onion", 20), ("Tomato", 20),
                     ("Ginger", 20), ("Garlic", 20), ("Rice", 200)]:
            self.db.add_item(n, "Other", 1, "pcs", 10, T + timedelta(days=d), today=T)
        ideas = engine.find_recipes(self._active(), self.recipes)
        self.assertEqual(ideas[0]["name"], "Palak Paneer")
        self.assertEqual(sorted(ideas[0]["rescues"]), ["paneer", "spinach"])
        self.assertEqual(ideas[0]["missing"], [])

    def test_veg_filter_and_time_filter(self):
        for n in ["Egg", "Onion", "Tomato", "Chilli"]:
            self.db.add_item(n, "Other", 1, "pcs", 5, T + timedelta(days=2), today=T)
        names_any = [r["name"] for r in engine.find_recipes(self._active(), self.recipes)]
        names_veg = [r["name"] for r in engine.find_recipes(self._active(), self.recipes, diet="veg")]
        self.assertIn("Egg Bhurji", names_any)
        self.assertNotIn("Egg Bhurji", names_veg)
        self.assertEqual(engine.find_recipes(self._active(), self.recipes, max_minutes=5), [])

    def test_synonym_matching_dahi_as_yogurt(self):
        for n in ["Dahi", "Cucumber", "Onion"]:
            self.db.add_item(n, "Other", 1, "pcs", 5, T + timedelta(days=1), today=T)
        names = [r["name"] for r in engine.find_recipes(self._active(), self.recipes)]
        self.assertIn("Raita", names)


class DBAndSummaryTests(unittest.TestCase):
    def test_validation(self):
        db = make_db()
        with self.assertRaises(ValueError):
            db.add_item("  ", "Other", 1, "pcs", 1, T)
        with self.assertRaises(ValueError):
            db.add_item("Milk", "Dairy", 0, "L", 1, T)
        with self.assertRaises(ValueError):
            db.add_item("Milk", "Dairy", 1, "L", -5, T)

    def test_status_changes_and_delete(self):
        db = make_db()
        i = db.add_item("Milk", "Dairy", 1, "L", 60, T, today=T)
        db.set_status(i, "used", T)
        self.assertEqual(len(db.items("active")), 0)
        self.assertEqual(db.items("used").iloc[0]["resolved_on"], T.isoformat())
        db.delete(i)
        self.assertTrue(db.items().empty)
        with self.assertRaises(ValueError):
            db.set_status(i, "bogus", T)

    def test_waste_summary_numbers(self):
        db = make_db()
        a = db.add_item("Milk", "Dairy", 1, "L", 60, T, today=T)
        b = db.add_item("Bread", "Bakery", 1, "pack", 40, T, today=T)
        c = db.add_item("Paneer", "Dairy", 500, "g", 100, T, today=T)
        db.set_status(a, "used", T); db.set_status(b, "wasted", T); db.set_status(c, "wasted", T)
        s = engine.waste_summary(db.items())
        self.assertEqual((s["saved"], s["lost"]), (60.0, 140.0))
        self.assertAlmostEqual(s["waste_rate"], 0.7)
        self.assertAlmostEqual(s["wasted_kg"], 0.5)   # pack is not convertible, paneer 500 g is

    def test_empty_summary_is_zero(self):
        s = engine.waste_summary(make_db().items())
        self.assertEqual((s["saved"], s["lost"], s["waste_rate"]), (0.0, 0.0, 0.0))

    def test_seed_is_idempotent_and_trend_works(self):
        db = make_db()
        self.assertGreater(db.seed_sample(T), 0)
        self.assertEqual(db.seed_sample(T), 0)
        trend = engine.weekly_trend(db.items())
        self.assertEqual(list(trend.columns), ["used", "wasted"])
        self.assertFalse(trend.empty)
        active = engine.enrich(db.items("active"), T)
        risk = engine.money_at_risk(active)
        self.assertEqual(risk["expired_count"], 1)       # green peas
        self.assertGreater(risk["at_risk"], 0)
        self.assertEqual(engine.use_first(active, 1).iloc[0]["days_left"], -1)


if __name__ == "__main__":
    unittest.main()
