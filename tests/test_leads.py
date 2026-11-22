import unittest

from flightback.leads import LABEL, classify, extract_leads, news_from_enrich

# Real titles returned by Crustdata Company Enrich (news) for IndiGo on 22 Nov 2026.
REAL = [
    ("Flight rescheduling cannot justify denial of boarding, Delhi consumer Commission holds IndiGo liable", "2026-09-16", True),
    ("IndiGo delayed flight, then denied passenger boarding; told to refund fare, pay compensation", "2026-09-07", True),
    ("`No empathy': consumer panel fines IndiGo 35K for separating pregnant woman from her husband", "2026-09-08", True),
    ("IndiGo posts Rs 1,900 crore quarterly loss as fuel costs surge", "2026-11-05", False),
    ("IndiGo Shares Rise 4.7% On Oil Plunge", "2026-11-05", False),
    ("Delhi-Bound IndiGo Flight Diverted To Lucknow After Pilot Declares Mid-Air Emergency", "2026-09-15", False),
    ("InterGlobe Aviation Cuts Flight Frequencies Amid ATF Price Hike", "2026-09-09", False),
    ("IndiGo shares fall after delay in order cancellation", "2026-10-01", False),  # weak words inside market chatter
    ("IndiGo cancels 40 flights at Delhi as fog hits", "2026-12-01", True),         # weak word, no market noise
    ("Air India cancels Saudi flights till THIS date amid Saudi-Houthi war, offers full refunds", "2026-10-30", True),
    ("SpiceJet flights delayed after check-in disruption, flyers stranded at Delhi airport", "2026-09-19", True),
    ("Air India Gets DGCA Approval for Flying Academy in Amravati", "2026-11-02", False),
    ("India's domestic air passenger traffic decline likely to ease in October", "2026-10-29", False),
    ("Airlines urge govt to unlock delayed ECLGS funds", "2026-10-05", False),
    ("Akasa Air announces new fuel surcharge amid rising ATF prices; check how much passengers will pay", "2026-10-08", False),
]


class LeadTests(unittest.TestCase):
    def test_classifier_on_real_titles(self):
        for title, _, expect in REAL:
            self.assertEqual(bool(classify(title)), expect, title)

    def test_extract_dedupes_sorts_and_labels(self):
        news = [{"article_url": f"https://x/{i}", "article_title": t, "article_publish_date": d, "article_publisher_name": "P"}
                for i, (t, d, _) in enumerate(REAL)]
        news.append(dict(news[0]))  # duplicate URL
        leads = extract_leads(news, "6E", "test")
        self.assertEqual(len(leads), 6)
        self.assertEqual([l["published"] for l in leads], sorted([l["published"] for l in leads], reverse=True))
        self.assertTrue(all(l["label"] == LABEL and l["code"] == "6E" for l in leads))

    def test_items_without_url_or_title_are_dropped(self):
        self.assertEqual(extract_leads([{"article_title": "refund ruling"}, {"article_url": "u"}, None, "junk"], "6E", "t"), [])

    def test_news_from_enrich_handles_empty(self):
        self.assertEqual(news_from_enrich([]), [])
        self.assertEqual(news_from_enrich([{"matches": [{"company_data": {"news": [{"a": 1}]}}]}]), [{"a": 1}])
        self.assertEqual(news_from_enrich([{"matches": []}]), [])


if __name__ == "__main__":
    unittest.main()
