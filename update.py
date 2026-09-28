#!/usr/bin/env python3
"""
RoV Pro League team tracker — data updater.

ดึงข้อมูลจาก Liquipedia API แล้วคำนวณสถิติทั้งหมดออกเป็น data/stats.json
ข้อมูลต้นทาง: Liquipedia (CC-BY-SA) — https://liquipedia.net/honorofkings/

วิธีใช้:
    python3 update.py                    # ใช้ค่าตั้งต้น (Bacon Time, RPL 2026 Winter)
    python3 update.py --team "KOG"       # เปลี่ยนทีมที่ติดตาม
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------- config
WIKI = "https://liquipedia.net/honorofkings/api.php"
UA = "RoVFanTracker/1.0 (personal fan dashboard; contact: fan@example.com)"

CURRENT_PAGE = "RoV Pro League/2026/Winter/Group Stage"
PREVIOUS_PAGE = "RoV Pro League/2026/Summer/Group Stage"
CURRENT_LABEL = "Winter 2026"
PREVIOUS_LABEL = "Summer 2026"
DEFAULT_TEAM = "Bacon Time"

# ชื่อย่อในวิกิ -> ชื่อที่แสดง
TEAM_ALIAS = {
    "fs": "FULL SENSE", "full sense": "FULL SENSE",
    "bru": "Buriram United", "buriram united esports": "Buriram United",
    "kog": "KOG", "king of gamers club": "KOG",
    "tenacity": "Tenacity",
    "ea": "eArena", "earena": "eArena",
    "bac": "Bacon Time", "bacon time": "Bacon Time",
    "solyx": "SOLYX",
    "godji check": "Godji Check", "godji": "Godji Check",
    "hd": "Hydra", "hydra": "Hydra", "hydra esports": "Hydra",
}

MATCHES_PER_TEAM = 16          # double round robin, 9 teams
PLAYOFF_SLOTS = 4
SIMS = 30000                   # Monte Carlo runs


# ---------------------------------------------------------------- fetch
def fetch_wikitext(page: str) -> str:
    """ดึง wikitext จาก Liquipedia API (ต้องใช้ gzip + custom user-agent ตาม API terms)"""
    url = f"{WIKI}?action=parse&page={urllib.parse.quote(page)}&format=json&prop=wikitext"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"Liquipedia error for {page}: {payload['error']}")
    return payload["parse"]["wikitext"]["*"]


# ---------------------------------------------------------------- parse
def norm_hero(name: str) -> str:
    return re.sub(r"[' ]|\(marksman\)|\(mage\)|\(tank\)", "", name.strip().lower())


def parse_matches(wikitext: str) -> list[dict]:
    """แกะทุกแมตช์ออกมาเป็น dict พร้อมผลรายเกม พิก แบน ฝั่ง และความยาว"""
    blocks = re.findall(
        r"\|M\d+=\{\{Match(.*?)(?=\n\s*\|M\d+=\{\{Match|\n\}\}\s*\n(?:\{\{|=|\|)|\Z)",
        wikitext, re.S,
    )
    out = []
    for blk in blocks:
        teams = [TEAM_ALIAS.get(t.strip().lower(), t.strip())
                 for t in re.findall(r"TeamOpponent\|([^}|]+)", blk)]
        if len(teams) != 2:
            continue
        date_m = re.search(r"\|date=([^\n|]*)", blk)
        mvp_m = re.search(r"\|mvp=([^\n|]*)", blk)
        potm_m = re.search(r"Player of the Match: \{\{Player\|([^|}]+)", blk)

        games = []
        for raw_map in re.findall(r"\|map\d+=\{\{Map(.*?)\n\s*\}\}", blk, re.S):
            win_m = re.search(r"\|winner=(\w+)", raw_map)
            if not win_m or win_m.group(1) not in "12":
                continue
            len_m = re.search(r"\|length=(\d+):(\d+)", raw_map)
            s1 = re.search(r"\|team1side=(\w+)", raw_map)
            s2 = re.search(r"\|team2side=(\w+)", raw_map)
            games.append({
                "winner": int(win_m.group(1)),
                "length": int(len_m.group(1)) * 60 + int(len_m.group(2)) if len_m else None,
                "sides": {1: s1.group(1) if s1 else None, 2: s2.group(1) if s2 else None},
                "picks": {i: [norm_hero(h) for h in re.findall(rf"\|t{i}h\d=([^\n|]+)", raw_map)]
                          for i in (1, 2)},
                "bans": {i: [norm_hero(h) for h in re.findall(rf"\|t{i}b\d=([^\n|]+)", raw_map)]
                         for i in (1, 2)},
            })

        date_raw = (date_m.group(1).strip() if date_m else "")
        out.append({
            "teams": teams,
            "games": games,
            "played": bool(games),
            "date": re.sub(r"\{\{Abbr/ICT\}\}", "ICT", date_raw).strip(),
            "mvps": [x.strip() for x in mvp_m.group(1).split(",") if x.strip()] if mvp_m else [],
            "potm": potm_m.group(1).strip() if potm_m else None,
        })
    return out


# ---------------------------------------------------------------- standings
def build_standings(matches: list[dict]) -> list[dict]:
    rec = defaultdict(lambda: {"w": 0, "l": 0, "gw": 0, "gl": 0})
    for m in matches:
        if not m["played"]:
            continue
        a, b = m["teams"]
        ga = sum(1 for g in m["games"] if g["winner"] == 1)
        gb = len(m["games"]) - ga
        rec[a]["gw"] += ga; rec[a]["gl"] += gb
        rec[b]["gw"] += gb; rec[b]["gl"] += ga
        if ga > gb:
            rec[a]["w"] += 1; rec[b]["l"] += 1
        else:
            rec[b]["w"] += 1; rec[a]["l"] += 1

    rows = []
    for team, r in rec.items():
        rows.append({
            "team": team, "w": r["w"], "l": r["l"],
            "gw": r["gw"], "gl": r["gl"], "diff": r["gw"] - r["gl"],
            "points": r["w"],
            "remaining": MATCHES_PER_TEAM - r["w"] - r["l"],
        })
    rows.sort(key=lambda x: (-x["points"], -x["diff"], x["l"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
        row["max_points"] = row["points"] + row["remaining"]
    return rows


# ---------------------------------------------------------------- team diagnostics
def team_side(match: dict, team: str) -> int:
    return 1 if match["teams"][0] == team else 2


def diagnostics(matches: list[dict], team: str) -> dict:
    mine = [m for m in matches if m["played"] and team in m["teams"]]

    series, by_game_no = [], defaultdict(lambda: [0, 0])
    lg_by_game_no = defaultdict(lambda: [0, 0])
    closeout = [0, 0]
    trailing = [0, 0]
    leading = [0, 0]
    deciders = [0, 0]

    for m in matches:
        if not m["played"]:
            continue
        for n, g in enumerate(m["games"], 1):
            for side in (1, 2):
                lg_by_game_no[n][0] += 1
                lg_by_game_no[n][1] += (g["winner"] == side)

    for m in mine:
        side = team_side(m, team)
        res = [1 if g["winner"] == side else 0 for g in m["games"]]
        opp = m["teams"][1] if side == 1 else m["teams"][0]
        series.append({
            "opponent": opp,
            "date": m["date"].split(" - ")[0],
            "flow": "".join("W" if x else "L" for x in res),
            "score": f"{sum(res)}-{len(res) - sum(res)}",
            "won": sum(res) > len(res) - sum(res),
        })
        for n, x in enumerate(res, 1):
            by_game_no[n][0] += 1
            by_game_no[n][1] += x
        w = l = 0
        for x in res:
            if w == 2 and l < 2:                 # เกมที่มีโอกาสปิดซีรีส์
                closeout[0] += 1; closeout[1] += x
            if w or l:
                (leading if w > l else trailing)[0] += 1
                (leading if w > l else trailing)[1] += x
            if w == 2 and l == 2:                # เกมตัดสิน
                deciders[0] += 1; deciders[1] += x
            if x: w += 1
            else: l += 1

    # ---- win rate ตามความยาวเกม
    buckets = [("ต่ำกว่า 12 นาที", 0, 720), ("12–16 นาที", 720, 960),
               ("16–20 นาที", 960, 1200), ("เกิน 20 นาที", 1200, 10**9)]
    by_length, lg_by_length = [], {}
    for label, lo, hi in buckets:
        n = w = 0
        ln = lw = 0
        for m in matches:
            if not m["played"]:
                continue
            for g in m["games"]:
                if g["length"] is None or not (lo <= g["length"] < hi):
                    continue
                for s in (1, 2):
                    ln += 1; lw += (g["winner"] == s)
                if team in m["teams"]:
                    s = team_side(m, team)
                    n += 1; w += (g["winner"] == s)
        by_length.append({"label": label, "n": n, "w": w,
                          "wr": round(w / n * 100) if n else None,
                          "league_wr": round(lw / ln * 100) if ln else None})

    # ---- ฝั่งแมพ
    sides = {}
    for s_name in ("blue", "red"):
        n = w = ln = lw = 0
        for m in matches:
            if not m["played"]:
                continue
            for g in m["games"]:
                for s in (1, 2):
                    if g["sides"][s] == s_name:
                        ln += 1; lw += (g["winner"] == s)
                if team in m["teams"]:
                    s = team_side(m, team)
                    if g["sides"][s] == s_name:
                        n += 1; w += (g["winner"] == s)
        sides[s_name] = {"n": n, "w": w, "wr": round(w / n * 100) if n else None,
                         "league_wr": round(lw / ln * 100) if ln else None}

    # ---- เจอทีมบน vs ทีมล่าง
    table = build_standings(matches)
    top = {r["team"] for r in table[:PLAYOFF_SLOTS + 1] if r["team"] != team}
    tiers = {"top": [0, 0, 0, 0], "bottom": [0, 0, 0, 0]}   # matchW, matchL, gameW, gameL
    for m in mine:
        side = team_side(m, team)
        opp = m["teams"][1] if side == 1 else m["teams"][0]
        gw = sum(1 for g in m["games"] if g["winner"] == side)
        gl = len(m["games"]) - gw
        key = "top" if opp in top else "bottom"
        tiers[key][0] += (gw > gl); tiers[key][1] += (gw < gl)
        tiers[key][2] += gw; tiers[key][3] += gl

    return {
        "series": series,
        "by_game_no": [{"game": n, "n": v[0], "w": v[1],
                        "wr": round(v[1] / v[0] * 100) if v[0] else None,
                        "league_wr": round(lg_by_game_no[n][1] / lg_by_game_no[n][0] * 100)
                        if lg_by_game_no[n][0] else None}
                       for n, v in sorted(by_game_no.items())],
        "by_length": by_length,
        "sides": sides,
        "closeout": {"n": closeout[0], "w": closeout[1],
                     "wr": round(closeout[1] / closeout[0] * 100) if closeout[0] else None},
        "deciders": {"n": deciders[0], "w": deciders[1]},
        "trailing": {"n": trailing[0], "w": trailing[1],
                     "wr": round(trailing[1] / trailing[0] * 100) if trailing[0] else None},
        "leading": {"n": leading[0], "w": leading[1],
                    "wr": round(leading[1] / leading[0] * 100) if leading[0] else None},
        "tiers": {
            "top": {"mw": tiers["top"][0], "ml": tiers["top"][1],
                    "gw": tiers["top"][2], "gl": tiers["top"][3],
                    "wr": round(tiers["top"][2] / max(tiers["top"][2] + tiers["top"][3], 1) * 100)},
            "bottom": {"mw": tiers["bottom"][0], "ml": tiers["bottom"][1],
                       "gw": tiers["bottom"][2], "gl": tiers["bottom"][3],
                       "wr": round(tiers["bottom"][2] / max(tiers["bottom"][2] + tiers["bottom"][3], 1) * 100)},
            "top_teams": sorted(top),
        },
    }


# ---------------------------------------------------------------- heroes
def hero_stats(matches: list[dict], team: str) -> dict:
    team_pick = defaultdict(lambda: [0, 0])
    league_pick = defaultdict(lambda: [0, 0])
    presence = Counter()
    team_ban = Counter()
    opp_ban_vs_team = Counter()
    league_ban = Counter()
    conceded = defaultdict(lambda: [0, 0])
    lengths = defaultdict(list)
    total_games = 0
    team_games = 0

    for m in matches:
        if not m["played"]:
            continue
        for g in m["games"]:
            total_games += 1
            for s in (1, 2):
                won = g["winner"] == s
                for h in g["picks"][s]:
                    league_pick[h][0] += 1; league_pick[h][1] += won
                    if g["length"]:
                        lengths[h].append(g["length"])
                for h in set(g["picks"][s] + g["bans"][s]):
                    presence[h] += 1
                for h in g["bans"][s]:
                    league_ban[h] += 1
            if team in m["teams"]:
                team_games += 1
                mine = team_side(m, team)
                other = 2 if mine == 1 else 1
                for h in g["picks"][mine]:
                    team_pick[h][0] += 1; team_pick[h][1] += (g["winner"] == mine)
                for h in g["bans"][mine]:
                    team_ban[h] += 1
                for h in g["bans"][other]:
                    opp_ban_vs_team[h] += 1
                for h in g["picks"][other]:
                    conceded[h][0] += 1; conceded[h][1] += (g["winner"] == other)

    def league_wr(h):
        n, w = league_pick[h]
        return round(w / n * 100) if n else None

    pool = []
    for h, (n, w) in team_pick.items():
        if n < 3:
            continue
        pool.append({"hero": h, "n": n, "w": w, "wr": round(w / n * 100),
                     "league_wr": league_wr(h),
                     "edge": round(w / n * 100) - (league_wr(h) or 0)})
    pool.sort(key=lambda x: (-x["wr"], -x["n"]))

    # ฮีโร่ที่คู่แข่งแบนใส่เรามากกว่าค่าเฉลี่ยลีก
    targeted = []
    denom = max(total_games * 2, 1)
    for h, n in opp_ban_vs_team.items():
        base = league_ban[h] / denom
        rate = n / max(team_games, 1)
        if n >= 3:
            targeted.append({"hero": h, "n": n, "of": team_games,
                             "rate": round(rate * 100),
                             "league_rate": round(base * 100),
                             "gap": round((rate - base) * 100)})
    targeted.sort(key=lambda x: -x["gap"])

    punished = [{"hero": h, "n": v[0], "w": v[1], "wr": round(v[1] / v[0] * 100)}
                for h, v in conceded.items() if v[0] >= 4]
    punished.sort(key=lambda x: (-x["wr"], -x["n"]))

    untapped = []
    for h, (n, w) in league_pick.items():
        if n >= 10 and presence[h] / max(total_games, 1) < 0.45:
            untapped.append({"hero": h, "league_n": n, "league_wr": round(w / n * 100),
                             "presence": round(presence[h] / total_games * 100),
                             "team_n": team_pick[h][0]})
    untapped = [u for u in untapped if u["league_wr"] >= 52]
    untapped.sort(key=lambda x: (-x["league_wr"], x["team_n"]))

    tempo_index = {h: round(sum(v) / len(v) / 60, 1) for h, v in lengths.items() if len(v) >= 8}

    # ฮีโร่เกมเร็ว vs เกมยาว
    fast_slow = []
    for h in tempo_index:
        short = [0, 0]; long_ = [0, 0]
        for m in matches:
            if not m["played"]:
                continue
            for g in m["games"]:
                if not g["length"]:
                    continue
                for s in (1, 2):
                    if h in g["picks"][s]:
                        tgt = short if g["length"] < 960 else long_
                        tgt[0] += 1; tgt[1] += (g["winner"] == s)
        if short[0] >= 5 and long_[0] >= 5:
            fast_slow.append({
                "hero": h,
                "short_wr": round(short[1] / short[0] * 100), "short_n": short[0],
                "long_wr": round(long_[1] / long_[0] * 100), "long_n": long_[0],
                "swing": round(short[1] / short[0] * 100) - round(long_[1] / long_[0] * 100),
            })
    fast_slow.sort(key=lambda x: -x["swing"])

    return {
        "pool": pool,
        "targeted": targeted[:10],
        "punished": punished[:10],
        "untapped": untapped[:12],
        "team_bans": [{"hero": h, "n": n} for h, n in team_ban.most_common(10)],
        "tempo_index": tempo_index,
        "fast_heroes": fast_slow[:8],
        "slow_heroes": sorted(fast_slow, key=lambda x: x["swing"])[:8],
        "total_games": total_games,
        "team_games": team_games,
    }


def tempo_matchups(matches: list[dict], team: str, tempo_index: dict) -> dict:
    def comp_index(picks):
        vals = [tempo_index[h] for h in picks if h in tempo_index]
        return sum(vals) / len(vals) if vals else None

    buckets = {"faster": [0, 0], "even": [0, 0], "slower": [0, 0]}
    league = {"faster": [0, 0], "even": [0, 0], "slower": [0, 0]}
    per_team = defaultdict(lambda: [0, 0])
    detail = []

    for m in matches:
        if not m["played"]:
            continue
        for g in m["games"]:
            a, b = comp_index(g["picks"][1]), comp_index(g["picks"][2])
            if a is None or b is None:
                continue
            for s, mine_ci, other_ci in ((1, a, b), (2, b, a)):
                gap = mine_ci - other_ci
                key = "faster" if gap < -0.3 else ("slower" if gap > 0.3 else "even")
                league[key][0] += 1; league[key][1] += (g["winner"] == s)
                if key == "slower":
                    t = m["teams"][s - 1]
                    per_team[t][0] += 1; per_team[t][1] += (g["winner"] == s)
            if team in m["teams"]:
                s = team_side(m, team)
                o = 2 if s == 1 else 1
                mine_ci = a if s == 1 else b
                other_ci = b if s == 1 else a
                gap = mine_ci - other_ci
                key = "faster" if gap < -0.3 else ("slower" if gap > 0.3 else "even")
                buckets[key][0] += 1; buckets[key][1] += (g["winner"] == s)
                detail.append({
                    "opponent": m["teams"][o - 1],
                    "ours": round(mine_ci, 1), "theirs": round(other_ci, 1),
                    "kind": key,
                    "minutes": round(g["length"] / 60, 1) if g["length"] else None,
                    "won": g["winner"] == s,
                })

    def pack(d):
        return {k: {"n": v[0], "w": v[1], "wr": round(v[1] / v[0] * 100) if v[0] else None}
                for k, v in d.items()}

    return {
        "team": pack(buckets),
        "league": pack(league),
        "slow_comp_by_team": sorted(
            [{"team": t, "n": v[0], "w": v[1], "wr": round(v[1] / v[0] * 100)}
             for t, v in per_team.items() if v[0] >= 6],
            key=lambda x: -x["wr"]),
        "games": detail,
    }


# ---------------------------------------------------------------- meta shift
def meta_shift(prev: list[dict], cur: list[dict], team: str) -> dict:
    def presence(matches):
        pres = Counter(); picks = defaultdict(lambda: [0, 0]); tp = Counter(); n = 0
        for m in matches:
            if not m["played"]:
                continue
            for g in m["games"]:
                n += 1
                for s in (1, 2):
                    for h in set(g["picks"][s] + g["bans"][s]):
                        pres[h] += 1
                    for h in g["picks"][s]:
                        picks[h][0] += 1; picks[h][1] += (g["winner"] == s)
                if team in m["teams"]:
                    s = team_side(m, team)
                    for h in g["picks"][s]:
                        tp[h] += 1
        return pres, picks, tp, max(n, 1)

    p_pres, _, p_team, p_n = presence(prev)
    c_pres, c_picks, c_team, c_n = presence(cur)

    risers, fallers = [], []
    for h in set(list(p_pres) + list(c_pres)):
        a = p_pres[h] / p_n * 100
        b = c_pres[h] / c_n * 100
        row = {"hero": h, "prev": round(a), "cur": round(b), "delta": round(b - a),
               "team_prev": p_team[h], "team_cur": c_team[h]}
        if b - a >= 12: risers.append(row)
        if a - b >= 12: fallers.append(row)
    risers.sort(key=lambda x: -x["delta"])
    fallers.sort(key=lambda x: x["delta"])

    new_heroes = {r["hero"] for r in risers[:12]}
    tn = tw = ln = lw = 0
    for m in cur:
        if not m["played"]:
            continue
        for g in m["games"]:
            for s in (1, 2):
                hits = len(set(g["picks"][s]) & new_heroes)
                if not hits:
                    continue
                if m["teams"][s - 1] == team:
                    tn += hits; tw += hits * (g["winner"] == s)
                else:
                    ln += hits; lw += hits * (g["winner"] == s)

    lost_tools = sorted(
        [r for r in [{"hero": h, "prev": p_team[h], "cur": c_team[h]} for h in p_team]
         if r["prev"] >= 6 and r["cur"] <= r["prev"] / 2],
        key=lambda x: -(x["prev"] - x["cur"]))[:10]

    return {
        "risers": risers[:12], "fallers": fallers[:10],
        "adaptation": {"team_n": tn, "team_wr": round(tw / tn * 100) if tn else None,
                       "league_n": ln, "league_wr": round(lw / ln * 100) if ln else None},
        "lost_tools": lost_tools,
        "prev_label": PREVIOUS_LABEL, "cur_label": CURRENT_LABEL,
    }


# ---------------------------------------------------------------- odds
def fit_ratings(matches: list[dict], teams: list[str]) -> dict:
    """Bradley-Terry ระดับเกม ฟิตด้วย gradient ascent + L2"""
    idx = {t: i for i, t in enumerate(teams)}
    r = [0.0] * len(teams)
    data = []
    for m in matches:
        if not m["played"]:
            continue
        a, b = m["teams"]
        ga = sum(1 for g in m["games"] if g["winner"] == 1)
        gb = len(m["games"]) - ga
        data.append((idx[a], idx[b], ga, gb))
    for _ in range(4000):
        grad = [0.0] * len(teams)
        for ia, ib, ga, gb in data:
            p = 1 / (1 + math.exp(-(r[ia] - r[ib])))
            d = ga - (ga + gb) * p
            grad[ia] += d; grad[ib] -= d
        for i in range(len(teams)):
            grad[i] -= 0.6 * r[i]
            r[i] += 0.01 * grad[i]
    mean = sum(r) / len(r)
    return {t: round(r[idx[t]] - mean, 3) for t in teams}


def simulate(standings: list[dict], remaining: list[dict], ratings: dict,
             team: str, sims: int = SIMS) -> dict:
    rows = {r["team"]: r for r in standings}
    teams = list(rows)
    fixtures = [(m["teams"][0], m["teams"][1]) for m in remaining]
    probs = {(a, b): 1 / (1 + math.exp(-(ratings[a] - ratings[b]))) for a, b in set(fixtures)}
    rng = random.Random(20260928)

    top4 = 0
    place = Counter()
    winout = 0
    top4_if_winout = 0
    above = Counter()
    my_games = sum(1 for a, b in fixtures if team in (a, b))

    def run_season(forced=None):
        """เล่นแมตช์ที่เหลือหนึ่งรอบ คืนค่า (อันดับของทีมเรา, จำนวนนัดที่เราชนะ, ลำดับทั้งหมด)"""
        W = {t: rows[t]["points"] for t in teams}
        D = {t: rows[t]["diff"] for t in teams}
        mine = 0
        for x, y in fixtures:
            if forced and (x, y) == forced[0]:
                ga, gb = (3, 1) if forced[1] == x else (1, 3)
            else:
                p = probs[(x, y)]
                ga = gb = 0
                while ga < 3 and gb < 3:
                    if rng.random() < p: ga += 1
                    else: gb += 1
            D[x] += ga - gb; D[y] += gb - ga
            winner = x if ga > gb else y
            W[winner] += 1
            if winner == team:
                mine += 1
        order = sorted(teams, key=lambda t: (-W[t], -D[t], rng.random()))
        return order.index(team) + 1, mine, order

    for _ in range(sims):
        rank, mine, order = run_season()
        place[rank] += 1
        if rank <= PLAYOFF_SLOTS:
            top4 += 1
        for t in teams:
            if t != team and order.index(team) < order.index(t):
                above[t] += 1
        if mine == my_games:
            winout += 1
            if rank <= PLAYOFF_SLOTS:
                top4_if_winout += 1

    top4_pct = top4 / sims * 100
    # ถ้าลุ้นเข้ารอบไม่ได้แล้ว ให้วัดผลกระทบกับ "การจบเหนือคู่แข่งที่ใกล้ที่สุด" แทน
    my_rank = next(r["rank"] for r in standings if r["team"] == team)
    neighbours = [r["team"] for r in standings if r["team"] != team
                  and abs(r["rank"] - my_rank) == 1]
    rival = neighbours[0] if neighbours else None
    goal_mode = "top4" if top4_pct >= 1.0 else "rank"
    goal_label = (f"เข้าท็อป {PLAYOFF_SLOTS}" if goal_mode == "top4"
                  else f"จบเหนือ {rival}")

    def goal_hit(rank, order):
        if goal_mode == "top4":
            return rank <= PLAYOFF_SLOTS
        return rival is not None and order.index(team) < order.index(rival)

    swing_sims = max(sims // 5, 2500)
    swing = []
    for fixture in dict.fromkeys(f for f in fixtures if team not in f):
        a, b = fixture
        outcome = {}
        for forced_winner in (a, b):
            hits = 0
            for _ in range(swing_sims):
                rank, _, order = run_season(forced=(fixture, forced_winner))
                if goal_hit(rank, order):
                    hits += 1
            outcome[forced_winner] = hits / swing_sims * 100
        swing.append({"match": f"{a} vs {b}", "a": a, "b": b,
                      "root_for": a if outcome[a] >= outcome[b] else b,
                      "if_a": round(outcome[a], 1), "if_b": round(outcome[b], 1),
                      "gap": round(abs(outcome[a] - outcome[b]), 1)})
    swing.sort(key=lambda x: -x["gap"])

    return {
        "top4": round(top4_pct, 2),
        "win_out": round(winout / sims * 100, 2),
        "top4_if_win_out": round(top4_if_winout / max(winout, 1) * 100, 1),
        "placement": {str(k): round(v / sims * 100, 1) for k, v in sorted(place.items())},
        "finish_above": sorted(
            [{"team": t, "pct": round(above[t] / sims * 100, 1)} for t in teams if t != team],
            key=lambda x: -x["pct"]),
        "goal_mode": goal_mode,
        "goal_label": goal_label,
        "rival": rival,
        "swing": swing[:10],
        "sims": sims,
    }


# ---------------------------------------------------------------- opponent prep
def opponent_prep(matches: list[dict], team: str, remaining: list[dict]) -> list[dict]:
    upcoming = []
    for m in remaining:
        if team not in m["teams"]:
            continue
        opp = m["teams"][1] if m["teams"][0] == team else m["teams"][0]
        picks = defaultdict(lambda: [0, 0])
        games = 0
        for x in matches:
            if not x["played"] or opp not in x["teams"]:
                continue
            s = 1 if x["teams"][0] == opp else 2
            for g in x["games"]:
                games += 1
                for h in g["picks"][s]:
                    picks[h][0] += 1; picks[h][1] += (g["winner"] == s)
        threats = sorted(
            [{"hero": h, "n": v[0], "w": v[1], "wr": round(v[1] / v[0] * 100)}
             for h, v in picks.items() if v[0] >= 4],
            key=lambda x: (-x["wr"], -x["n"]))[:6]
        h2h = []
        for x in matches:
            if not x["played"] or opp not in x["teams"] or team not in x["teams"]:
                continue
            s = team_side(x, team)
            gw = sum(1 for g in x["games"] if g["winner"] == s)
            h2h.append({"date": x["date"].split(" - ")[0],
                        "score": f"{gw}-{len(x['games']) - gw}",
                        "won": gw > len(x["games"]) - gw})
        upcoming.append({"opponent": opp, "date": m["date"], "threats": threats,
                         "head_to_head": h2h})
    return upcoming


# ---------------------------------------------------------------- main
def build_standalone(payload: dict) -> None:
    """รวม HTML + CSS + JS + ข้อมูล เป็นไฟล์เดียว เปิดด้วยการดับเบิลคลิกได้เลย"""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(here, "assets", "styles.css"), encoding="utf-8") as fh:
            css = fh.read()
        with open(os.path.join(here, "assets", "app.js"), encoding="utf-8") as fh:
            js = fh.read()
    except FileNotFoundError as exc:
        print(f"  ข้ามการสร้างไฟล์เดี่ยว: {exc}")
        return

    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('<link rel="stylesheet" href="assets/styles.css">',
                        f"<style>\n{css}\n</style>")
    html = html.replace('<script src="assets/app.js"></script>',
                        f"<script>window.__STATS__ = {blob};</script>\n<script>\n{js}\n</script>")
    out = os.path.join(here, "standalone.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"เขียนไฟล์ {out} ({os.path.getsize(out) / 1024:.0f} KB) — เปิดได้โดยไม่ต้องรันเซิร์ฟเวอร์")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default=DEFAULT_TEAM)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data", "stats.json"))
    ap.add_argument("--sims", type=int, default=SIMS)
    args = ap.parse_args()
    team = args.team

    print(f"ดึงข้อมูล {CURRENT_PAGE} ...")
    cur_matches = parse_matches(fetch_wikitext(CURRENT_PAGE))
    print(f"  ได้ {len(cur_matches)} แมตช์ "
          f"({sum(1 for m in cur_matches if m['played'])} แข่งแล้ว)")

    prev_matches = []
    try:
        print(f"ดึงข้อมูล {PREVIOUS_PAGE} (สำหรับเทียบเมต้า) ...")
        prev_matches = parse_matches(fetch_wikitext(PREVIOUS_PAGE))
        print(f"  ได้ {len(prev_matches)} แมตช์")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  ข้ามส่วนเทียบเมต้า: {exc}")

    standings = build_standings(cur_matches)
    all_teams = [r["team"] for r in standings]
    if team not in all_teams:
        print(f"ไม่พบทีม '{team}' — ทีมที่มีในลีก: {', '.join(all_teams)}")
        return 1

    remaining = [m for m in cur_matches if not m["played"]]
    heroes = hero_stats(cur_matches, team)
    ratings = fit_ratings(cur_matches, all_teams)

    print(f"จำลองผล {args.sims:,} รอบ ...")
    odds = simulate(standings, remaining, ratings, team, args.sims)

    mvps = Counter()
    for m in cur_matches:
        if not m["played"] or team not in m["teams"]:
            continue
        s = team_side(m, team)
        for i, g in enumerate(m["games"]):
            if i < len(m["mvps"]) and g["winner"] == s:
                mvps[m["mvps"][i]] += 1

    payload = {
        "meta": {
            "team": team,
            "tournament": CURRENT_LABEL,
            "source": "Liquipedia (CC-BY-SA)",
            "source_url": "https://liquipedia.net/honorofkings/"
                           + CURRENT_PAGE.replace(" ", "_"),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "played": sum(1 for m in cur_matches if m["played"]),
            "total": len(cur_matches),
            "playoff_slots": PLAYOFF_SLOTS,
        },
        "standings": standings,
        "ratings": ratings,
        "diagnostics": diagnostics(cur_matches, team),
        "heroes": heroes,
        "tempo": tempo_matchups(cur_matches, team, heroes["tempo_index"]),
        "meta_shift": meta_shift(prev_matches, cur_matches, team) if prev_matches else None,
        "odds": odds,
        "schedule": [{"date": m["date"], "a": m["teams"][0], "b": m["teams"][1],
                      "involves_team": team in m["teams"]} for m in remaining],
        "prep": opponent_prep(cur_matches, team, remaining),
        "mvps": [{"player": p, "n": n} for p, n in mvps.most_common()],
        "recent": [{"date": m["date"].split(" - ")[0],
                    "a": m["teams"][0], "b": m["teams"][1],
                    "score": f"{sum(1 for g in m['games'] if g['winner'] == 1)}-"
                             f"{sum(1 for g in m['games'] if g['winner'] == 2)}"}
                   for m in cur_matches if m["played"]][-12:],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    size = os.path.getsize(args.out) / 1024
    print(f"เขียนไฟล์ {args.out} ({size:.0f} KB)")
    build_standalone(payload)
    print(f"  {team}: อันดับ {next(r['rank'] for r in standings if r['team'] == team)} | "
          f"โอกาสเข้าท็อป {PLAYOFF_SLOTS} = {odds['top4']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
