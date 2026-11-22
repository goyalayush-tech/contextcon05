import os
import unittest
from unittest import mock

from flightback import watcher
from flightback.crustdata import Crustdata, RateLimiter
from flightback.store import Store

NEWS = [{"article_url": "https://x/consumer", "article_title": "Consumer commission holds IndiGo liable for refund",
         "article_publish_date": "2026-09-16", "article_publisher_name": "India Legal"},
        {"article_url": "https://x/stock", "article_title": "IndiGo share price rises", "article_publish_date": "2026-11-08",
         "article_publisher_name": "Yahoo"}]


def summary(company_id=2247, news=NEWS):
    return {"notifications": [{"payload": {"notifications": [{"uid": "u", "record": {"crustdata_company_id": company_id,
                                                                                        "news": news}, "changes": []}]}}]}


class Router:
    """Fake transport keyed by URL fragment; records every call."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers, body):
        self.calls.append((url, body))
        for frag, payload in self.routes.items():
            if frag in url:
                return 200, {}, payload
        return 404, {}, {"error": "no route"}


def client(routes, store=None):
    store = store or Store(":memory:")
    cd = Crustdata(store, "airline-refresh", 20, api_key="k", transport=Router(routes),
                   limiter=RateLimiter({"core": 99, "web": 99, "social": 99, "autocomplete": 99}, sleep=lambda s: None))
    return cd, store


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"FLIGHTBACK_WATCH_ID": ""})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_body_tracks_news_added_for_every_airline_pull_only_with_expiry(self):
        b = watcher.watch_body()
        self.assertEqual(b["track"], {"field": "news", "type": "added"})
        self.assertEqual(len(b["entities"]["domains"]), 6)
        self.assertEqual(b["notifications"], [])
        self.assertIn("expires_at", b["config"])

    def test_ensure_creates_once_for_free_and_remembers_the_id(self):
        cd, store = client({"/watch/company": {"id": 57487}})
        self.assertIsNone(watcher.ensure_watch(cd, store))  # create=False never creates
        self.assertEqual(watcher.ensure_watch(cd, store, create=True), 57487)
        self.assertEqual(watcher.ensure_watch(cd, store, create=True), 57487)
        posts = [c for c in cd.transport.calls if c[1] is not None]
        self.assertEqual(len(posts), 1)
        self.assertEqual(cd.spent, 0.0)

    def test_sync_turns_news_into_leads_once(self):
        runs = {"runs": [{"id": 9, "status": "SUCCESS", "new_records_count": 1}]}
        cd, store = client({"/runs?limit": runs, "/runs/9/summary": summary()})
        store.setting_put(watcher.SETTING, "57487")
        first = watcher.sync(cd, store, {2247: "6E"})
        self.assertEqual((first["runs_read"], first["records"], first["leads_new"]), (1, 1, 1))
        self.assertEqual(store.leads_for("6E")[0]["title"], NEWS[0]["article_title"])
        again = watcher.sync(cd, store, {2247: "6E"})
        self.assertEqual((again["runs_read"], again["leads_new"]), (0, 0))
        self.assertEqual(cd.spent, 0.0)  # reading a watch is free

    def test_failed_run_is_skipped_and_retried_later(self):
        cd, store = client({"/runs?limit": {"runs": [{"id": 3, "status": "FAILED", "new_records_count": 0}]}})
        store.setting_put(watcher.SETTING, "57487")
        out = watcher.sync(cd, store, {2247: "6E"})
        self.assertEqual((out["runs_read"], out["skipped_failed_runs"]), (0, 1))
        self.assertFalse(store.watch_run_seen(57487, 3))

    def test_unmapped_company_is_ignored_not_guessed(self):
        cd, store = client({"/runs?limit": {"runs": [{"id": 1, "status": "SUCCESS", "new_records_count": 1}]},
                            "/runs/1/summary": summary(company_id=999)})
        store.setting_put(watcher.SETTING, "57487")
        out = watcher.sync(cd, store, {2247: "6E"})
        self.assertEqual((out["records"], out["leads_new"]), (0, 0))

    def test_no_watch_recorded(self):
        cd, store = client({})
        self.assertEqual(watcher.sync(cd, store, {})["status"], "no_watch")


if __name__ == "__main__":
    unittest.main()
