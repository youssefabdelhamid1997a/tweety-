"""Deterministic synthetic data. Never a fallback for a failed live request."""

from .analysis import build_report
from .service import HEROES


def demo_report(role="carry"):
    account = 999999999
    rows, details = [], {}
    heroes = [8, 44, 54, 8, 44, 54, 8, 44, 54, 8, 44, 54]
    for i, hero in enumerate(heroes):
        duration = 2100 + (i % 4) * 180
        won = i % 5 in (0, 2)
        player = {"account_id": account, "hero_id": hero, "player_slot": 0, "kills": 4 + i % 8,
                  "deaths": 5 + i % 7, "assists": 5 + i % 6, "gold_per_min": 420 + i % 4 * 43,
                  "xp_per_min": 510 + i * 7, "last_hits": 180 + i * 7, "tower_damage": 600 if i % 3 else 3500,
                  "lane_role": 1, "leaver_status": 0}
        row = {**player, "match_id": 9000000001 + i, "duration": duration, "radiant_win": won,
               "start_time": 1793563200 - i * 86400, "lobby_type": 7}
        rows.append(row)
        if i < 5:
            times = list(range(0, duration + 1, 60))
            player.update({"times": times, "lh_t": [int(t / 60 * (3.2 + i * .3)) for t in times],
                           "gold_t": [int(600 + t / 60 * player["gold_per_min"]) for t in times],
                           "obs_placed": i % 3, "sen_placed": i + 1,
                           "purchase_log": [{"time": 420, "key": "power_treads"}, {"time": 1050 + i * 90, "key": "manta"},
                                            {"time": 1680 + i * 30, "key": "black_king_bar"}]})
            allies = [{"account_id": 100 + j, "player_slot": j, "kills": 5 + j} for j in range(1, 5)]
            details[row["match_id"]] = {**row, "players": [player] + allies}
    return build_report(account, {"profile": {"personaname": "Sample player"}, "rank_tier": 43}, rows, details, HEROES, role, source="demo")
