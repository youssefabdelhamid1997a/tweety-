"""Evidence-based coaching rules. Missing observations are never treated as zero."""

import math
import re
from datetime import datetime, timezone
from statistics import mean
from urllib.parse import urlparse

STEAM_BASE = 76561197960265728
ROLES = {"auto": "Cautious automatic", "carry": "Carry · position 1", "mid": "Mid · position 2",
         "offlane": "Offlane · position 3", "support": "Support · position 4", "hard_support": "Hard support · position 5"}
CORE = {"carry", "mid", "offlane"}
ITEMS = {"blink": "Blink Dagger", "black_king_bar": "Black King Bar", "manta": "Manta Style",
         "bfury": "Battle Fury", "maelstrom": "Maelstrom", "radiance": "Radiance",
         "force_staff": "Force Staff", "glimmer_cape": "Glimmer Cape", "guardian_greaves": "Guardian Greaves",
         "orchid": "Orchid Malevolence", "hand_of_midas": "Hand of Midas", "desolator": "Desolator",
         "ultimate_scepter": "Aghanim's Scepter", "aghanims_shard": "Aghanim's Shard",
         "travel_boots": "Boots of Travel", "power_treads": "Power Treads", "phase_boots": "Phase Boots",
         "arcane_boots": "Arcane Boots", "mekansm": "Mekansm", "pipe": "Pipe of Insight"}


class InputError(ValueError):
    pass


def account_id(value):
    text = str(value or "").strip()
    if "://" in text:
        url = urlparse(text)
        if url.scheme != "https" or url.hostname not in {"steamcommunity.com", "www.steamcommunity.com", "www.opendota.com", "opendota.com"}:
            raise InputError("Use your numeric Dota friend ID or an HTTPS Steam /profiles/ URL.")
        parts = url.path.strip("/").split("/")
        expected = "profiles" if "steamcommunity" in url.hostname else "players"
        if len(parts) != 2 or parts[0] != expected:
            raise InputError("Vanity /id/ links are not supported. In Dota, open Friends → Add Friend and copy your friend ID.")
        text = parts[1]
    if not re.fullmatch(r"[0-9]{1,17}", text):
        raise InputError("Enter a numeric Dota friend ID, Steam64 ID, or Steam /profiles/ URL.")
    number = int(text)
    if number >= STEAM_BASE:
        number -= STEAM_BASE
    if not 0 < number <= 4294967295:
        raise InputError("That is outside the valid Dota account ID range.")
    return number


def match_id(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"[0-9]{1,12}", text) or int(text) <= 0:
        raise InputError("Enter a numeric match ID, found in Dota's match history.")
    return int(text)


def role_value(value):
    if not isinstance(value, str) or value not in ROLES:
        raise InputError("Choose a role from the list.")
    return value


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def avg(values):
    usable = [v for v in values if num(v) is not None]
    return round(mean(usable), 1) if usable else None


def at_minute(player, field, minute):
    times, values = player.get("times"), player.get(field)
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    for t, v in zip(times, values):
        if num(t) is not None and t == minute * 60:
            return num(v)
    return None


def is_ranked(row):
    return row.get("lobby_type") == 7 and (num(row.get("duration")) or 0) >= 600 and row.get("leaver_status", 0) in (None, 0, 1)


def get_player(detail, account):
    players = detail.get("players")
    if not isinstance(players, list):
        return None
    return next((p for p in players if isinstance(p, dict) and p.get("account_id") == account), None)


def has_replay(player):
    return any(isinstance(player.get(k), list) and len(player[k]) > 0 for k in ("times", "purchase_log", "kills_log", "buyback_log"))


def normalize(row, account, detail=None, heroes=None, role="auto"):
    player = get_player(detail or {}, account)
    merged = dict(row)
    if player:
        merged.update(player)
        for key in ("duration", "radiant_win", "start_time", "lobby_type", "match_id"):
            if key in detail:
                merged[key] = detail[key]
    slot = num(merged.get("player_slot"))
    radiant_win = merged.get("radiant_win")
    won = (radiant_win == (slot < 128)) if slot is not None and isinstance(radiant_win, bool) else None
    duration = num(merged.get("duration")) or 0
    # lane_role is a lane, not a farm position. Only mid can be inferred cautiously.
    inferred = "mid" if merged.get("lane_role") == 2 and not merged.get("is_roaming") else "unknown"
    effective = role if role != "auto" else inferred
    kp = None
    if player and slot is not None:
        allies = [p for p in detail["players"] if num(p.get("player_slot")) is not None and (p["player_slot"] < 128) == (slot < 128)]
        kills = [num(p.get("kills")) for p in allies]
        if len(allies) == 5 and all(v is not None for v in kills) and sum(kills) > 0:
            own_kills, assists = num(player.get("kills")), num(player.get("assists"))
            if own_kills is not None and assists is not None:
                kp = round(100 * (own_kills + assists) / sum(kills), 1)
    purchases = []
    events = (player or {}).get("purchase_log")
    for event in events if isinstance(events, list) else []:
        if isinstance(event, dict) and event.get("key") in ITEMS and num(event.get("time")) is not None and event["time"] >= 0:
            purchases.append({"time": event["time"], "item": ITEMS[event["key"]], "key": event["key"]})
    purchases.sort(key=lambda e: e["time"])
    hero = (heroes or {}).get(str(merged.get("hero_id")), {})
    result = {"match_id": merged.get("match_id"), "hero_id": merged.get("hero_id"),
              "hero": hero.get("localized_name", f"Hero {merged.get('hero_id', '?')}"),
              "start_time": merged.get("start_time"), "duration": duration, "won": won,
              "role": effective, "parsed": bool(player and has_replay(player)),
              "detailed": player is not None, "purchases": purchases[:35], "kill_participation": kp,
              "last_hits_10": at_minute(player or {}, "lh_t", 10),
              "gold_10": at_minute(player or {}, "gold_t", 10)}
    for field in ("kills", "deaths", "assists", "gold_per_min", "xp_per_min", "last_hits", "tower_damage", "obs_placed", "sen_placed"):
        result[field] = num(merged.get(field))
    deaths = result["deaths"]
    result["deaths_per_10"] = round(deaths * 600 / duration, 2) if deaths is not None and duration > 0 else None
    times, gold = (player or {}).get("times"), (player or {}).get("gold_t")
    times = times if isinstance(times, list) else []
    gold = gold if isinstance(gold, list) else []
    result["economy"] = [{"minute": t / 60, "gold": g} for t, g in zip(times, gold)
                         if num(t) is not None and num(g) is not None and 0 <= t <= duration][:180]
    return result


def recommendations(matches):
    cards = []

    def add(key, title, rows, affected, evidence, action, target, question):
        if len(rows) >= 3 and len(affected) >= 2:
            cards.append({"key": key, "title": title, "sample": len(rows), "affected": len(affected),
                          "confidence": "Repeated signal" if len(rows) >= 8 else "Early signal",
                          "evidence": evidence, "action": action, "target": target, "question": question,
                          "match_ids": [m["match_id"] for m in affected[:3]]})

    rows = [m for m in matches if m["deaths_per_10"] is not None]
    bad = [m for m in rows if m["deaths_per_10"] > 2]
    add("survival", "Make each death earn its cost", rows, bad,
        f"{len(bad)} of {len(rows)} matches exceeded 2 deaths per 10 minutes. Sample average: {avg([m['deaths_per_10'] for m in rows])}.",
        "Before crossing the river, name the missing enemy heroes and your escape route. After a death, record the objective it bought; support sacrifices can be correct.",
        "For the next 5 games, review your first 3 deaths and remove one avoidable repeat per game.",
        "Was this death necessary for a tower, Roshan, a save, or safe farm elsewhere?")
    rows = [m for m in matches if m["role"] in CORE and m["last_hits_10"] is not None]
    targets = {"carry": 50, "mid": 50, "offlane": 40}
    bad = [m for m in rows if m["last_hits_10"] < targets[m["role"]]]
    add("lane", "Stabilize your first ten minutes", rows, bad,
        f"{len(bad)} of {len(rows)} core-role replay samples were below a starter practice target (carry/mid: 50 LH at 10; offlane: 40). Average: {avg([m['last_hits_10'] for m in rows])} LH.",
        "Warm up with 10 minutes of last-hitting. In a difficult lane, prioritize experience, ask for a pull or rotation, and identify your safe recovery camp.",
        "Track last hits at 10 for 5 games. Improve your own median by 5 before raising the target.",
        "Did I lose creeps to missed attacks, trading, lane equilibrium, or a matchup I should have left?")
    rows = [m for m in matches if m["role"] in {"support", "hard_support"} and m["obs_placed"] is not None]
    bad = [m for m in rows if m["obs_placed"] * 600 / m["duration"] < 0.8]
    add("vision", "Put vision where the next play happens", rows, bad,
        f"{len(bad)} of {len(rows)} support-role samples had fewer than 0.8 observer wards placed per 10 minutes. Ward quality is not measured.",
        "Carry detection and place vision with a teammate before your next objective. Check ward stock and avoid walking into darkness alone to ward.",
        "Before each major objective, say where your team needs vision. Review one ward's usefulness after each game.",
        "Did this ward protect the farming area or enable the next tower or Roshan play?")
    rows = [m for m in matches if m["role"] in CORE and m["tower_damage"] is not None and m["duration"] >= 1800]
    bad = [m for m in rows if m["tower_damage"] < 1000]
    add("objectives", "Turn a won fight into map progress", rows, bad,
        f"{len(bad)} of {len(rows)} core-role matches lasting at least 30 minutes had under 1,000 personal tower damage. Hero and team duties affect this.",
        "After a won fight, check waves, enemy buybacks, and your health. Call a safe tower, Roshan, or lane shove before chasing another kill.",
        "For 5 games, write down one fight you converted into an objective and one missed opportunity.",
        "Could we safely take a tower or Roshan, or was resetting the correct choice?")
    if not cards:
        cards.append({"key": "baseline", "title": "Build a trustworthy baseline", "sample": len(matches), "affected": 0,
                      "confidence": "More context needed", "evidence": "No repeated signal met the review rules with the available fields. This does not mean there were no mistakes.",
                      "action": "Review the first three deaths and the 10-minute lane state in your next three ranked games. Choose your actual role to unlock role-specific checks.",
                      "target": "Collect 5 games on one role and a small hero pool, then compare your own results.",
                      "question": "What decision could I change next game without needing my teammates to play differently?", "match_ids": []})
    cards.sort(key=lambda c: (c["affected"] / max(c["sample"], 1), c["sample"]), reverse=True)
    return cards[:3]


def build_report(account, profile, rows, details=None, heroes=None, role="auto", source="live", warnings=None):
    role_value(role)
    usable, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not is_ranked(row) or row.get("match_id") in seen:
            continue
        seen.add(row.get("match_id"))
        usable.append(row)
    usable.sort(key=lambda r: r.get("start_time") or 0, reverse=True)
    matches = [normalize(r, account, (details or {}).get(r["match_id"]), heroes, role) for r in usable]
    known = [m for m in matches if m["won"] is not None]
    wins = sum(m["won"] for m in known)
    parsed = sum(m["parsed"] for m in matches)
    tier = num(profile.get("rank_tier"))
    medals = {1: "Herald", 2: "Guardian", 3: "Crusader", 4: "Archon", 5: "Legend", 6: "Ancient", 7: "Divine", 8: "Immortal"}
    medal = medals.get(int(tier) // 10, "Uncalibrated / unavailable") if tier else "Uncalibrated / unavailable"
    notes = list(warnings or [])
    if not matches:
        notes.append("No eligible ranked matches were returned. Enable Expose Public Match Data in Dota → Settings → Social, sign in to OpenDota, and play new ranked matches. Older hidden history may remain unavailable.")
    if parsed < len(matches):
        notes.append(f"Replay event data is available for {parsed}/{len(matches)} matches in this report. Missing replay fields are excluded from their respective checks.")
    if role == "auto":
        notes.append("Automatic role mode only infers mid from lane data; other lanes do not identify carry versus support. Choose the role you played for a more specific review.")
    if len(matches) < 10:
        notes.append("This is a small sample. Use the suggestions as review prompts, not a verdict on your skill.")
    if source == "demo":
        notes.insert(0, "SAMPLE DATA: these invented matches are a demonstration, not your match history or a live OpenDota result.")
    summary = {"matches": len(matches), "wins": wins, "losses": len(known) - wins, "known_results": len(known),
               "win_rate": round(wins * 100 / len(known), 1) if known else None,
               "gold_per_min": avg([m["gold_per_min"] for m in matches]),
               "gold_samples": sum(m["gold_per_min"] is not None for m in matches),
               "deaths_per_10": avg([m["deaths_per_10"] for m in matches]),
               "death_samples": sum(m["deaths_per_10"] is not None for m in matches), "parsed": parsed,
               "last_hits_10": avg([m["last_hits_10"] for m in matches]),
               "last_hit_samples": sum(m["last_hits_10"] is not None for m in matches)}
    identity = profile.get("profile") if isinstance(profile.get("profile"), dict) else {}
    return {"account_id": account, "name": identity.get("personaname") or f"Player {account}",
            "rank": medal, "rank_stars": int(tier) % 10 if tier and int(tier) // 10 < 8 else None,
            "role": role, "role_label": ROLES[role], "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "matches": matches,
            "priorities": recommendations(matches), "warnings": notes,
            "method": "Explainable coaching rules, not a trained model or Divine-player benchmark. Statistics flag review opportunities; they cannot prove decision quality, blame, positioning, or why you lost. Practice targets are starter goals, not rank requirements."}
