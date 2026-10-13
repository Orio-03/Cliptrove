"""Which games you're likely to play next, learned from your own clip history.

A day with at least one clip of a game counts as a day you played it. That's a stand-in for real play time (you
can play without saving clips), so the predictions are about your clipping habits.

The model is a small logistic regression with two inputs per game: its momentum (days you played it, with recent
days counting more, fading over about two weeks) and how long it's been since you last played it. For every game
and every past day it learns how those relate to whether you played the game again within the next 7 days.

Simpler and richer versions were compared on real history (weeks the model hadn't seen): extra inputs such as
"days played in the last month" or "usual gap between sessions" didn't make it better, so they're left out. The
page shows how well it did on your own recent weeks, next to just guessing the game you played last.
"""
import datetime as dt
import math
from bisect import bisect_right

from .util import norm

HORIZON = 7  # days ahead
NOT_GAMES = {"desktop", "unsorted", "unknowngame"}
MAX_IDLE = 365  # games not played for longer than this aren't considered
MEMORY = 14  # days: how quickly momentum fades (about halves every 10 days)
FEATURES = [  # (name, what it means, for the page)
    ("momentum", "Momentum: days you played it, recent ones counting more"),
    ("since", "Days since you last played it"),
]


def play_days(clips):
    """{game: sorted day numbers (date ordinals) with at least one clip of it}."""
    days = {}
    for c in clips:
        if norm(c["game"]) in NOT_GAMES:
            continue
        try:
            when = dt.datetime.fromisoformat(c["recorded"])
        except (TypeError, ValueError):
            continue
        if when.tzinfo:
            when = when.astimezone()  # your local time
        days.setdefault(c["game"], set()).add(when.date().toordinal())
    return {g: sorted(s) for g, s in days.items()}


def count(seq, a, b):
    """How many days in seq fall in (a, b]."""
    return bisect_right(seq, b) - bisect_right(seq, a)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return (xs[n // 2] + xs[(n - 1) // 2]) / 2


class History:
    def __init__(self, days):
        self.days = days
        self.active = sorted({d for s in days.values() for d in s})

    def facts(self, game, t):
        """What's known about a game at the end of day t, or None if it hadn't been played yet."""
        seq = self.days[game]
        n = bisect_right(seq, t)
        if not n:
            return None
        gaps = [seq[j] - seq[j - 1] for j in range(max(1, n - 10), n)]  # its last 10 gaps between play days
        momentum = 0.0
        for j in range(n - 1, -1, -1):
            if t - seq[j] > 10 * MEMORY:
                break  # too long ago to matter
            momentum += math.exp(-(t - seq[j]) / MEMORY)
        return {"since": t - seq[n - 1], "week": count(seq, t - 7, t), "month": count(seq, t - 30, t),
                "total": n, "gap": median(gaps) if gaps else None, "momentum": momentum}

    @staticmethod
    def vector(f):
        return [math.log1p(f["momentum"]), math.log1p(f["since"])]

    def played(self, game, t):
        """Whether the game was played in the HORIZON days after day t."""
        return count(self.days[game], t, t + HORIZON) > 0

    def candidates(self, t):
        """(game, facts) for every game played before t and not too long ago."""
        for g in self.days:
            f = self.facts(g, t)
            if f and f["since"] <= MAX_IDLE:
                yield g, f

    def rows(self, start, end, step):
        X, y = [], []
        for t in range(start, end + 1, step):
            for g, f in self.candidates(t):
                X.append(self.vector(f))
                y.append(1.0 if self.played(g, t) else 0.0)
        return X, y


# ---------- logistic regression (Newton's method, no libraries needed) ----------

def sigmoid(z):
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def solve(A, b):
    """x for A x = b (Gaussian elimination with partial pivoting)."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c and M[r][c]:
                k = M[r][c] / M[c][c]
                M[r] = [a - k * e for a, e in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


class Model:
    def __init__(self, l2=1.0):
        self.l2 = l2
        self.mean = self.scale = self.w = None

    def prep(self, x):
        return [1.0] + [(v - m) / s for v, m, s in zip(x, self.mean, self.scale)]

    def fit(self, X, y, iters=25):
        k = len(X[0])
        self.mean = [sum(r[j] for r in X) / len(X) for j in range(k)]
        self.scale = [math.sqrt(sum((r[j] - self.mean[j]) ** 2 for r in X) / len(X)) or 1.0 for j in range(k)]
        Z = [self.prep(r) for r in X]
        k += 1
        w = [0.0] * k
        for _ in range(iters):
            H = [[0.0] * k for _ in range(k)]
            g = [0.0] * k
            for z, t in zip(Z, y):
                p = sigmoid(sum(a * b for a, b in zip(w, z)))
                r, s = p - t, p * (1 - p)
                for a in range(k):
                    g[a] += r * z[a]
                    za, Ha = z[a] * s, H[a]
                    for b in range(a, k):
                        Ha[b] += za * z[b]
            for a in range(k):
                for b in range(a):
                    H[a][b] = H[b][a]
                if a:  # keep weights small (not the intercept), so a short history doesn't give wild answers
                    H[a][a] += self.l2
                    g[a] += self.l2 * w[a]
            step = solve(H, g)
            w = [a - b for a, b in zip(w, step)]
            if max(abs(v) for v in step) < 1e-6:
                break
        self.w = w
        return self

    def prob(self, x):
        return sigmoid(sum(a * b for a, b in zip(self.w, self.prep(x))))


# ---------- what the page gets ----------

def ago(days):
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 60:
        return f"{days} days ago"
    if days < 730:
        return f"{round(days / 30.4)} months ago"
    return f"{round(days / 365)} years ago"


def followers(history):
    """{game: {next game: share}}: on your next day with clips after playing a game, what else you played."""
    by_day = {}
    for g, seq in history.days.items():
        for d in seq:
            by_day.setdefault(d, set()).add(g)
    out = {}
    days = history.active
    for d1, d2 in zip(days, days[1:]):
        if d2 - d1 > 14:
            continue  # a long break: not "next"
        for a in by_day[d1]:
            row = out.setdefault(a, {"_n": 0})
            row["_n"] += 1
            for b in by_day[d2] - {a}:
                row[b] = row.get(b, 0) + 1
    return {a: {b: n / row["_n"] for b, n in row.items() if b != "_n"} for a, row in out.items() if row["_n"] >= 4}


def reasons(f, game, follow, last_games):
    out = [f"Last played {ago(f['since'])}"]
    if f["week"] >= 2:
        out.append(f"Played on {f['week']} of the last 7 days")
    elif f["month"] >= 2:
        out.append(f"Played on {f['month']} days in the last month")
    gap = f["gap"]
    if gap and f["total"] >= 4 and gap <= 60 and f["since"] > gap * 1.2:
        out.append(f"Usually {round(gap)} {'day' if round(gap) == 1 else 'days'} between sessions")
    best = max(((follow.get(a, {}).get(game, 0), a) for a in last_games), default=(0, None))
    if best[0] >= 0.3:
        out.append(f"Often played after {best[1]}")
    if f["total"] >= 20 and f["since"] > 30:
        out.append(f"A regular: {f['total']} days with clips in all")
    return out[:3]


def ranking(history, model, t, by):
    cands = list(history.candidates(t))
    if by == "model":
        key = lambda gf: -model.prob(History.vector(gf[1]))
    else:  # the simple guess: whatever you played most recently
        key = lambda gf: (gf[1]["since"], -gf[1]["total"])
    return [g for g, _ in sorted(cands, key=key)]


def backtest(history, split, end, step=7):
    """Train only on days before `split`, then for each later week check the guesses against what you played."""
    X, y = history.rows(history.active[0] + 14, split - HORIZON, 2)
    if sum(y) < 10 or len(set(y)) < 2:
        return None
    model = Model().fit(X, y)
    base = sum(y) / len(y)
    top1, top3 = {"model": 0, "recent": 0}, {"model": 0, "recent": 0}
    err = [0.0, 0.0]  # squared error of the model's chances, and of always saying the average chance
    weeks = 0
    for t in range(split, end + 1, step):
        for g, f in history.candidates(t):
            hit = 1.0 if history.played(g, t) else 0.0
            err[0] += (model.prob(History.vector(f)) - hit) ** 2
            err[1] += (base - hit) ** 2
        played = {g for g in history.days if history.played(g, t)}
        if not played:
            continue  # nothing played that week, so nothing to guess
        weeks += 1
        for by in top1:
            order = ranking(history, model, t, by)
            top1[by] += bool(order[:1] and order[0] in played)
            top3[by] += bool(set(order[:3]) & played)
    if weeks < 4:
        return None
    return {"weeks": weeks, "top1": {k: v / weeks for k, v in top1.items()},
            "top3": {k: v / weeks for k, v in top3.items()},
            "skill": 1 - err[0] / err[1] if err[1] else 0.0,  # 0: no better than a flat guess, 1: perfect
            "from": dt.date.fromordinal(split).isoformat()}


def predict(clips, today=None, top=8):
    """Games most likely to be played in the next HORIZON days, with the reasons and how well this has worked
    on your own past weeks."""
    today = (today or dt.date.today()).toordinal()
    history = History(play_days(clips))
    active = [d for d in history.active if d <= today]
    if len(active) < 20 or len(history.days) < 2:
        return {"enough": False, "activeDays": len(active), "horizon": HORIZON}
    end = today - HORIZON  # the last day whose following week is fully known
    X, y = history.rows(active[0] + 14, end, 2)
    if sum(y) < 10 or len(set(y)) < 2:
        return {"enough": False, "activeDays": len(active), "horizon": HORIZON}
    model = Model().fit(X, y)
    # Check it on the most recent fifth of your clip days (and at least the last 8 weeks), with a model that
    # never saw them
    split = min(active[int(len(active) * 0.8)], end - 56)
    test = backtest(history, split, end) if active[0] + 60 < split < end else None

    follow = followers(history)
    last_day = active[-1]
    last_games = [g for g, seq in history.days.items() if count(seq, last_day - 1, last_day)]
    out = []
    for g, f in history.candidates(today):
        out.append({"game": g, "p": model.prob(History.vector(f)), "lastPlayed": f["since"],
                    "daysMonth": f["month"], "daysTotal": f["total"], "why": reasons(f, g, follow, last_games)})
    out.sort(key=lambda r: -r["p"])
    weights = sorted(({"feature": name, "label": label, "weight": w}
                      for (name, label), w in zip(FEATURES, model.w[1:])), key=lambda r: -abs(r["weight"]))
    return {"enough": True, "horizon": HORIZON, "predictions": out[:top], "backtest": test, "weights": weights,
            "trainedOn": {"rows": len(y), "activeDays": len(active), "games": len(history.days),
                          "lastClipDay": dt.date.fromordinal(last_day).isoformat()},
            "quiet": today - last_day}
