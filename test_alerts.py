import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import alerts
import engine
from db import PantryDB

T = date(2026, 10, 6)


def active_with(items):
    db = PantryDB(":memory:")
    for name, days in items:
        db.add_item(name, "Other", 1, "pcs", 10, T + timedelta(days=days), today=T)
    return engine.enrich(db.items("active"), T)


class BuildAlertTests(unittest.TestCase):
    def test_none_when_nothing_due(self):
        self.assertIsNone(alerts.build_alert(active_with([("Rice", 100)]), 2))
        self.assertIsNone(alerts.build_alert(active_with([]), 2))

    def test_lists_due_items_in_order_with_wording(self):
        subject, body = alerts.build_alert(active_with([("Milk", 1), ("Peas", -1), ("Bread", 0), ("Rice", 90)]), 2)
        self.assertIn("3 item(s)", subject)
        self.assertLess(body.index("Peas"), body.index("Bread"))
        self.assertLess(body.index("Bread"), body.index("Milk"))
        self.assertIn("EXPIRED 1 day ago", body)
        self.assertIn("expires TODAY", body)
        self.assertIn("expires tomorrow", body)
        self.assertNotIn("Rice", body)

    def test_includes_rescue_recipes(self):
        _, body = alerts.build_alert(active_with([("Milk", 1)]), 2, [{"name": "Kheer", "rescues": ["milk"]}])
        self.assertIn("Kheer", body)


class SendTests(unittest.TestCase):
    @patch("alerts.smtplib.SMTP_SSL")
    def test_email_sent_via_smtp(self, smtp):
        server = smtp.return_value.__enter__.return_value
        alerts.send_email("Subj", "Body", "me@gmail.com", "app pass", "you@example.com")
        server.login.assert_called_once_with("me@gmail.com", "app pass")
        sent = server.send_message.call_args[0][0]
        self.assertEqual((sent["To"], sent["From"], sent["Subject"]), ("you@example.com", "me@gmail.com", "Subj"))

    def test_email_validation(self):
        with self.assertRaises(ValueError):
            alerts.send_email("s", "b", "", "", "you@example.com")
        with self.assertRaises(ValueError):
            alerts.send_email("s", "b", "me@gmail.com", "pw", "not-an-email")


if __name__ == "__main__":
    unittest.main()
