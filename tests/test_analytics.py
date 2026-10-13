import datetime as dt
import random
import unittest

from cliptrove import analytics

TODAY = dt.date(2026, 10, 13)


def clip(game, day, hour=20):
    when = dt.datetime.combine(day, dt.time(hour)).astimezone()
    return {"game": game, "recorded": when.isoformat(timespec="seconds")}


def history():
    rng = random.Random(1)
    clips = []
    for i in range(400):  # two years-ish of habits
        day = TODAY - dt.timedelta(days=i)
        if i < 40 and rng.random() < 0.8:
            clips.append(clip("Hot", day))  # played most days lately
        if i % 7 == 3 and rng.random() < 0.9:
            clips.append(clip("Weekly", day))  # a weekly game
        if 150 < i < 300 and rng.random() < 0.6:
            clips.append(clip("Old", day))  # played a lot, then dropped
        if rng.random() < 0.1:
            clips.append(clip("Desktop", day))  # not a game
    return clips


class Predict(unittest.TestCase):
    def test_ranks_recent_habits_first(self):
        r = analytics.predict(history(), today=TODAY)
        self.assertTrue(r["enough"])
        games = [p["game"] for p in r["predictions"]]
        self.assertEqual(games[0], "Hot")
        self.assertLess(games.index("Weekly"), games.index("Old"))
        self.assertNotIn("Desktop", games)
        for p in r["predictions"]:
            self.assertTrue(0 < p["p"] < 1)
            self.assertTrue(p["why"])
        self.assertGreater(r["predictions"][0]["p"], 0.5)

    def test_backtest_beats_a_flat_guess(self):
        r = analytics.predict(history(), today=TODAY)
        test = r["backtest"]
        self.assertIsNotNone(test)
        self.assertGreater(test["weeks"], 4)
        self.assertGreater(test["skill"], 0)
        self.assertGreaterEqual(test["top3"]["model"], 0.5)

    def test_momentum_raises_the_chance_and_time_away_lowers_it(self):
        r = analytics.predict(history(), today=TODAY)
        w = {x["feature"]: x["weight"] for x in r["weights"]}
        self.assertGreater(w["momentum"], 0)
        self.assertLess(w["since"], 0)

    def test_too_little_history(self):
        clips = [clip("A", TODAY - dt.timedelta(days=i)) for i in range(5)]
        self.assertFalse(analytics.predict(clips, today=TODAY)["enough"])

    def test_days_are_local_and_counted_once(self):
        day = dt.date(2025, 1, 2)
        days = analytics.play_days([clip("A", day, 9), clip("A", day, 23), clip("Unsorted", day)])
        self.assertEqual(days, {"A": [day.toordinal()]})


class Fit(unittest.TestCase):
    def test_learns_the_direction_of_a_signal(self):
        rng = random.Random(2)
        X = [[rng.uniform(-2, 2)] for _ in range(500)]
        y = [1.0 if rng.random() < analytics.sigmoid(2 * x[0]) else 0.0 for x in X]
        m = analytics.Model(l2=0.1).fit(X, y)
        self.assertGreater(m.prob([1.5]), 0.8)
        self.assertLess(m.prob([-1.5]), 0.2)


if __name__ == "__main__":
    unittest.main()
