import json
from pathlib import Path

from .analysis import InputError, account_id, build_report, get_player, is_ranked, match_id, role_value
from .client import APIError

HEROES = json.loads((Path(__file__).parent / "heroes.json").read_text(encoding="utf-8"))


class CoachService:
    def __init__(self, client):
        self.client = client

    def analyze(self, data):
        account = account_id(data.get("account"))
        role = role_value(data.get("role", "auto"))
        limit = data.get("limit", 20)
        if type(limit) is not int or limit not in (10, 20, 30):
            raise InputError("Choose 10, 20, or 30 recent ranked matches.")
        rows = self.client.matches(account, limit)
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise APIError("OpenDota returned an unexpected match list.")
        warnings, details = [], {}
        try:
            profile = self.client.profile(account)
            if not isinstance(profile, dict):
                raise APIError("OpenDota returned an unexpected profile.")
        except APIError as exc:
            profile = {}
            warnings.append(f"Profile unavailable: {exc}")
        eligible = sorted([r for r in rows if is_ranked(r)], key=lambda r: r.get("start_time") or 0, reverse=True)
        for row in eligible[:5]:
            try:
                detail = self.client.match(match_id(row.get("match_id")))
                if not isinstance(detail, dict) or not isinstance(detail.get("players"), list) or any(not isinstance(p, dict) for p in detail["players"]):
                    raise APIError("OpenDota returned an unexpected match response.")
                if detail.get("match_id") != row["match_id"] or detail.get("lobby_type") != 7:
                    raise APIError("OpenDota's detailed response did not match the requested ranked game.")
                if get_player(detail, account):
                    details[row["match_id"]] = detail
                else:
                    warnings.append(f"Match {row['match_id']}: your account is hidden or absent in its detailed response.")
            except APIError as exc:
                warnings.append(f"Detailed replay fetch stopped: {exc} Summary analysis is still available.")
                break
        warnings.append("To conserve the public API quota, only the 5 newest eligible matches receive detailed replay checks. Profile/history cache: 5 minutes; match details: 24 hours. Use Match review → Refresh to recheck a newly parsed replay.")
        return build_report(account, profile, rows, details, HEROES, role, warnings=warnings)

    def review(self, data, imported=None):
        account = account_id(data.get("account"))
        role = role_value(data.get("role", "auto"))
        if imported is None:
            requested = match_id(data.get("match_id"))
            detail = self.client.refresh_match(requested) if data.get("refresh") is True else self.client.match(requested)
        else:
            detail = imported
        if not isinstance(detail, dict) or not isinstance(detail.get("players"), list) or any(not isinstance(p, dict) for p in detail["players"]):
            raise InputError("Upload the complete OpenDota match JSON object, including its players array. Raw .dem files are not supported.")
        actual = match_id(detail.get("match_id"))
        if imported is None and actual != requested:
            raise APIError("OpenDota returned a different match than requested.")
        player = get_player(detail, account)
        if not player:
            raise InputError("Your account is not identified in this match. Check both IDs; anonymous players cannot be attributed to you.")
        row = {**player, **{k: detail.get(k) for k in ("match_id", "duration", "start_time", "radiant_win", "lobby_type")}}
        if not is_ranked(row):
            raise InputError("This coach reviews ranked matches (lobby type 7), at least 10 minutes long, without an abandon by this account.")
        return build_report(account, {}, [row], {actual: detail}, HEROES, role, source="import" if imported is not None else "live",
                            warnings=["Single-match review: repeated-pattern recommendations require at least 3 eligible observations. Use the timeline and replay prompts to investigate this game."])
