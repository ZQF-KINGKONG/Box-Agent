#!/usr/bin/env python3
"""World Cup SINGLE-MATCH prediction model (high-precision matchup).

Reads two teams' YAML profiles and computes, for one fixture:
  - base expected goals (xG) per side
  - a high-precision matchup pass: attacker traits vs defender weaknesses
    (wing speed, 1v1 dribbling, counter/in-behind, aerial/set-piece) that
    actually adjusts each side's xG — defence & duels DRIVE the scoreline
  - optional real-time / motivation overrides (injuries, form, GD-chase)
  - full Poisson scoreline matrix, win/draw/loss, confidence, likely scorers

Stdlib only. Prints JSON to stdout (use --human for a readable card).

Usage:
  python3 predict.py FRA SEN                          # one neutral matchup
  python3 predict.py FRA SEN --human                  # readable matchup card
  python3 predict.py MEX KOR --home MEX               # host home advantage
  python3 predict.py BRA HAI --overrides rt.json --human   # + real-time layer
"""

import sys
import os
import json
import math
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
TEAMS_DIR = os.path.join(HERE, "..", "references", "teams")
MAX_GOALS = 6  # cap scoreline computation at 6 goals each side


# --------------------------------------------------------------------------- #
# Data loading (YAML). Prefer PyYAML; fall back to a tiny purpose-built parser.
# --------------------------------------------------------------------------- #
def load_yaml(path):
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return _mini_yaml(path)


def _scalar(v):
    v = v.strip()
    if v == "":
        return ""
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _mini_yaml(path):
    """Purpose-built parser for the schema used by team/schedule files.

    Supports: top-level scalars, one nested mapping (e.g. ratings), and one
    nested sequence of mappings (e.g. core_players / fixtures). Indentation is
    2 spaces per level. Sufficient and robust for this skill's data format.
    """
    root = {}
    section = None
    current_item = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.strip().startswith("#"):
                continue
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if indent == 0:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    section = key
                    root[key] = None
                    current_item = None
                else:
                    section = None
                    root[key] = _scalar(val)
            elif indent == 2:
                if section is None:
                    continue
                if root[section] is None:
                    root[section] = [] if stripped.startswith("- ") else {}
                container = root[section]
                if isinstance(container, list):
                    if stripped.startswith("- "):
                        current_item = {}
                        container.append(current_item)
                        rest = stripped[2:].strip()
                        if rest and ":" in rest:
                            k, _, v = rest.partition(":")
                            current_item[k.strip()] = _scalar(v)
                else:
                    k, _, v = stripped.partition(":")
                    container[k.strip()] = _scalar(v)
            elif indent >= 4:
                if section and isinstance(root.get(section), list) and current_item is not None:
                    s = stripped
                    if s.startswith("- "):
                        s = s[2:].strip()
                    k, _, v = s.partition(":")
                    current_item[k.strip()] = _scalar(v)
    return root


def load_team(code):
    code = code.upper()
    # match by code in any *.yaml under teams dir
    for name in sorted(os.listdir(TEAMS_DIR)):
        if not name.endswith((".yaml", ".yml")):
            continue
        data = load_yaml(os.path.join(TEAMS_DIR, name))
        if str(data.get("code", "")).upper() == code:
            return data
    raise ValueError("数据库无此球队代码(需先扩充 references/teams/): %s" % code)


# --------------------------------------------------------------------------- #
# Run-time overrides (real-time layer; baseline YAML stays untouched)
# --------------------------------------------------------------------------- #
def apply_overrides(team, ov):
    """Apply a real-time adjustment layer onto a baseline team dict.

    The team YAML is a *stable overall profile*. Match-day reality (form swings,
    injuries, suspensions, replacements) is layered here at run time so the
    baseline never goes stale. `ov` is the per-team object from the overrides
    file. Mutates and returns a copy; records what changed in `_adjustments`.

    Schema (all keys optional):
      note          : str — why (e.g. "首轮1-5惨败/三笘伤退")
      ratings       : {key: delta}  — DELTA added to baseline rating (+/-)
      drop_players  : [name, ...]   — remove (injury/suspension/not in squad)
      add_players   : [ {name, position, shooting, scoring_styles, traits...} ]
    """
    import copy
    team = copy.deepcopy(team)
    changes = []
    if not ov:
        return team

    for k, delta in (ov.get("ratings") or {}).items():
        base = float(team.get("ratings", {}).get(k, 75))
        new = max(0.0, min(100.0, base + float(delta)))
        team.setdefault("ratings", {})[k] = new
        changes.append("%s %g→%g(%+g)" % (k, base, new, float(delta)))

    drop = set(ov.get("drop_players") or [])
    if drop:
        kept = [p for p in (team.get("core_players") or []) if p.get("name") not in drop]
        removed = [p.get("name") for p in (team.get("core_players") or []) if p.get("name") in drop]
        team["core_players"] = kept
        if removed:
            changes.append("移除: " + ", ".join(removed))

    for p in (ov.get("add_players") or []):
        team.setdefault("core_players", []).append(p)
        changes.append("加入: %s" % p.get("name"))

    mult = ov.get("xg_mult")
    if mult is not None:
        team["_xg_mult"] = float(mult)
        changes.append("xG×%.2f(动机/策略)" % float(mult))

    note = ov.get("note")
    team["_adjustments"] = {"note": note, "changes": changes}
    return team


def load_overrides(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # allow {"teams": {...}} or a flat {CODE: {...}} mapping
    teams = data.get("teams", data)
    return {str(k).upper(): v for k, v in teams.items()}


# --------------------------------------------------------------------------- #
# Scoring model
# --------------------------------------------------------------------------- #
def _r(team, key, default=75):
    return float(team.get("ratings", {}).get(key, default))


def expected_goals(attacker, defender, home_advantage=False):
    """Estimate attacking xG from attack/defense ratio, midfield control,
    recent form, and the opponent's defensive-error probability."""
    base = 1.35
    ratio = _r(attacker, "attack") / max(_r(defender, "defense"), 1.0)
    mf_diff = _r(attacker, "midfield") - _r(defender, "midfield")
    midfield_factor = 1.0 + (mf_diff / 100.0) * 0.35
    form_factor = 0.85 + (_r(attacker, "form") - 70) / 100.0
    error_bonus = (_r(defender, "defensive_error_prob") / 100.0) * 0.6
    xg = base * ratio * midfield_factor * form_factor + error_bonus
    if home_advantage:
        xg *= 1.10
    return max(0.2, round(xg, 3))


def _poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def scoreline_matrix(xg_a, xg_b):
    """Return dict keyed by 'A-B' -> probability, plus W/D/L for team A."""
    matrix = {}
    p_win = p_draw = p_loss = 0.0
    for a in range(MAX_GOALS + 1):
        for b in range(MAX_GOALS + 1):
            p = _poisson(a, xg_a) * _poisson(b, xg_b)
            matrix["%d-%d" % (a, b)] = p
            if a > b:
                p_win += p
            elif a == b:
                p_draw += p
            else:
                p_loss += p
    return matrix, p_win, p_draw, p_loss


def _result_of(score):
    a, b = (int(x) for x in score.split("-"))
    return "win_A" if a > b else ("draw" if a == b else "loss_A")


def headline_scoreline(matrix, results):
    """The headline prediction.

    Independent Poisson makes the *joint mode* collapse to 1-1 whenever both
    xG land in ~1.2-1.8, which contradicts a clear favourite. So we (1) pick
    the most likely RESULT (win/draw/loss), then (2) return the most likely
    SCORELINE consistent with that result. We also surface the raw joint mode
    separately for transparency.

    Returns: (headline_score, most_likely_result_key, modal_score)
    """
    modal_score = max(matrix.items(), key=lambda kv: kv[1])[0]
    top_result = max(results, key=results.get)
    best_score, best_p = None, -1.0
    for score, p in matrix.items():
        if _result_of(score) == top_result and p > best_p:
            best_score, best_p = score, p
    return best_score, top_result, modal_score


def confidence(matrix, results):
    """Confidence from scoreline concentration + result decisiveness."""
    probs = [p for p in matrix.values() if p > 0]
    n = len(probs)
    entropy = -sum(p * math.log2(p) for p in probs)
    max_ent = math.log2(n) if n else 1.0
    concentration = 1.0 - (entropy / max_ent) if max_ent else 0.0
    top_result = max(results.values()) if results else 0.33
    conf = 35 + concentration * 45 + (top_result - 0.33) * 30
    conf = max(30.0, min(95.0, conf))
    return int(round(conf))


def confidence_tier(pct):
    if pct >= 70:
        return "高"
    if pct >= 55:
        return "中"
    return "低"


def likely_scorers(team, xg):
    players = team.get("core_players", []) or []
    if not players:
        return []
    total = sum(float(p.get("shooting", 50)) for p in players) or 1.0
    ranked = sorted(players, key=lambda p: float(p.get("shooting", 50)), reverse=True)
    out = []
    for p in ranked:
        share = float(p.get("shooting", 50)) / total
        out.append({
            "name": p.get("name"),
            "position": p.get("position"),
            "age": p.get("age"),
            "expected_goals_share": round(xg * share, 2),
            "scoring_styles": p.get("scoring_styles", ""),
            "traits": p.get("traits", ""),
        })
    return out


def _avg_age(team):
    ages = [float(p.get("age")) for p in (team.get("core_players") or []) if p.get("age") is not None]
    return round(sum(ages) / len(ages), 1) if ages else None


def matchup_compare(a, b):
    """Side-by-side basic strengths the narrative must surface: 前/中/后三线、
    速度、年龄结构、经验、状态、核心平均年龄。"""
    ra, rb = a.get("ratings", {}), b.get("ratings", {})

    def pair(k):
        return {"a": ra.get(k), "b": rb.get(k), "diff": (ra.get(k, 0) - rb.get(k, 0))}

    return {
        "lines": {"前场": pair("attack"), "中场": pair("midfield"),
                  "后场": pair("defense"), "速度": pair("pace")},
        "squad": {"年龄结构": pair("age_balance"), "经验": pair("experience"),
                  "青春": pair("youth"), "状态": pair("form"),
                  "核心平均年龄": {"a": _avg_age(a), "b": _avg_age(b)}},
        "defensive_error_prob": {"a": ra.get("defensive_error_prob"),
                                 "b": rb.get("defensive_error_prob")},
        # kept for back-compat with older template placeholders
        "midfield": {"a": ra.get("midfield"), "b": rb.get("midfield"),
                     "diff_a_minus_b": (ra.get("midfield", 0) - rb.get("midfield", 0))},
        "experience": {"a": ra.get("experience"), "b": rb.get("experience")},
        "age_balance": {"a": ra.get("age_balance"), "b": rb.get("age_balance")},
        "attack_vs_defense": {"a_attack": ra.get("attack"), "b_defense": rb.get("defense")},
        "b_attack_vs_defense": {"b_attack": rb.get("attack"), "a_defense": ra.get("defense")},
    }


# --------------------------------------------------------------------------- #
# High-precision matchup engine: attacker traits vs defender weaknesses.
# Derives concrete duels from existing player/team data and turns them into a
# bounded per-side xG multiplier + a transparent breakdown. No new data files.
# --------------------------------------------------------------------------- #
def _players(team):
    return team.get("core_players", []) or []


def _tags(p):
    return str(p.get("scoring_styles", "")) + " " + str(p.get("traits", ""))


def _is_winger(p):
    pos = str(p.get("position", "")).upper()
    return any(t in pos for t in ("LW", "RW", "RWB", "LWB")) or pos.endswith("W")


def _is_forward(p):
    pos = str(p.get("position", "")).upper()
    return _is_winger(p) or any(t in pos for t in ("ST", "SS", "CF", "AM"))


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def matchup_engine(attacker, defender):
    """Turn attacker-vs-defender duels into a bounded xG multiplier + breakdown.

    Each dimension compares a concrete attacking strength (from the attacker's
    core players) against the corresponding defensive weakness (from the
    defender's ratings), yielding a small signed xG effect. The product is the
    matchup multiplier applied to that side's base xG.
    """
    rd = defender.get("ratings", {}) or {}
    pa = _players(attacker)
    d_def = float(rd.get("defense", 75))
    d_pace = float(rd.get("pace", 75))
    d_err = float(rd.get("defensive_error_prob", 22))
    d_exp = float(rd.get("experience", 75))
    dims = []

    # 1) 边路速度冲击: 进攻方最快边锋 pace vs 防守方整体 pace(防线移动/回追)
    wing = max([float(p.get("pace", 70)) for p in pa if _is_winger(p)] or [0])
    if wing:
        edge = wing - d_pace
        eff = _clip(edge / 100.0 * 0.45, -0.06, 0.10)
        dims.append(("边路速度冲击", round(wing), round(d_pace), round(edge, 1), eff,
                     "边锋速度压制对方边路/回追" if edge > 0 else "对方防线速度足以限制边路"))

    # 2) 一对一/盘带: 进攻方最强 dribbling vs 防守方 defense
    drib = max([float(p.get("dribbling", 70)) for p in pa if _is_forward(p)] or [70])
    edge = drib - d_def
    eff = _clip(edge / 100.0 * 0.35, -0.05, 0.07)
    dims.append(("一对一/盘带", round(drib), round(d_def), round(edge, 1), eff,
                 "持球点能单吃防守球员" if edge > 0 else "防线一对一不吃亏"))

    # 3) 反击/打身后: 速度型 + 反击/单刀/反越位风格,打身后 + 利用对方失误
    cp = [p for p in pa if _is_forward(p) and any(k in _tags(p) for k in ("反击", "单刀", "反越位"))]
    cpace = max([float(p.get("pace", 70)) for p in cp] or [0])
    if cpace:
        edge = cpace - d_pace
        eff = _clip(edge / 100.0 * 0.35, -0.04, 0.06)
        eff = _clip(eff + _clip(max(0.0, d_err - 20) * 0.004, 0.0, 0.03), -0.04, 0.08)
        dims.append(("反击/打身后", round(cpace), round(d_pace), round(edge, 1), eff,
                     "速度型前锋打身后+利用对方失误" if eff > 0 else "对方防线沉稳、反击空间小"))

    # 4) 空中/定位球: 头球/定位球/抢点型射手 vs 防守方高空稳健(defense+experience)
    air = [p for p in pa if any(k in _tags(p) for k in ("头球", "定位球", "抢点"))]
    if air:
        a_idx = sum(float(p.get("shooting", 70)) for p in air) / len(air)
        d_air = d_def * 0.6 + d_exp * 0.4
        edge = a_idx - d_air
        eff = _clip(edge / 100.0 * 0.30, -0.03, 0.05)
        dims.append(("空中/定位球", round(a_idx), round(d_air), round(edge, 1), eff,
                     "定位球/头球是额外得分点" if edge > 0 else "对方高空与禁区防守稳固"))

    total = sum(d[4] for d in dims)
    mult = _clip(1.0 + total, 0.82, 1.22)
    return {
        "xg_mult": round(mult, 3),
        "total_effect": round(total, 3),
        "dimensions": [
            {"name": n, "attacker": av, "defender": dv, "edge": e,
             "xg_effect": round(eff, 3), "read": r}
            for (n, av, dv, e, eff, r) in dims
        ],
    }


def defense_report(opp_matchup):
    """Flip the opponent's attacking matchup into THIS team's defensive picture:
    which lines they get exposed on (sorted by severity) and which they hold."""
    dims = opp_matchup.get("dimensions", []) or []
    weak = sorted([d for d in dims if d["xg_effect"] > 0.005], key=lambda d: -d["xg_effect"])
    solid = [d["name"] for d in dims if d["xg_effect"] <= 0.005]
    return {
        "concede_xg_mult": opp_matchup.get("xg_mult", 1.0),
        "weaknesses": [{"dim": d["name"], "xg_effect": d["xg_effect"], "read": d["read"]} for d in weak],
        "solid": solid,
    }


def predict_match(team_a, team_b, home=None):
    home_adv_a = (home is not None and home.upper() == str(team_a.get("code", "")).upper())
    home_adv_b = (home is not None and home.upper() == str(team_b.get("code", "")).upper())
    base_a = expected_goals(team_a, team_b, home_advantage=home_adv_a)
    base_b = expected_goals(team_b, team_a, home_advantage=home_adv_b)
    # motivation/strategy lever (GD-chase vs already-qualified rotation)
    mot_a = float(team_a.get("_xg_mult", 1.0))
    mot_b = float(team_b.get("_xg_mult", 1.0))
    # high-precision matchup pass: attacker traits vs defender weaknesses
    mu_a = matchup_engine(team_a, team_b)
    mu_b = matchup_engine(team_b, team_a)
    xg_a = max(0.2, round(base_a * mot_a * mu_a["xg_mult"], 3))
    xg_b = max(0.2, round(base_b * mot_b * mu_b["xg_mult"], 3))
    matrix, p_win, p_draw, p_loss = scoreline_matrix(xg_a, xg_b)
    results = {"win_A": p_win, "draw": p_draw, "loss_A": p_loss}
    conf = confidence(matrix, results)
    top_scores = sorted(matrix.items(), key=lambda kv: kv[1], reverse=True)[:5]
    headline, top_result, modal_score = headline_scoreline(matrix, results)

    na, nb = team_a.get("name"), team_b.get("name")
    result_label = {"win_A": "%s胜" % na, "draw": "平局", "loss_A": "%s胜" % nb}[top_result]

    return {
        "team_a": {"code": team_a.get("code"), "name": na},
        "team_b": {"code": team_b.get("code"), "name": nb},
        "neutral": home is None,
        "adjustments": {k: v for k, v in {
            na: team_a.get("_adjustments"), nb: team_b.get("_adjustments")}.items() if v},
        "xg": {"a": xg_a, "b": xg_b},
        "xg_breakdown": {
            na: {"base": base_a, "motivation_mult": mot_a,
                 "matchup_mult": mu_a["xg_mult"], "final": xg_a},
            nb: {"base": base_b, "motivation_mult": mot_b,
                 "matchup_mult": mu_b["xg_mult"], "final": xg_b},
        },
        "matchup": {na: mu_a, nb: mu_b},
        "defense": {na: defense_report(mu_b), nb: defense_report(mu_a)},
        "predicted_score": headline,
        "most_likely_result": {"key": top_result, "label": result_label,
                               "prob": round(results[top_result], 4)},
        "modal_scoreline": modal_score,
        "top_scorelines": [{"score": s, "prob": round(p, 4)} for s, p in top_scores],
        "result_probability": {
            "%s胜" % na: round(p_win, 4),
            "平": round(p_draw, 4),
            "%s胜" % nb: round(p_loss, 4),
        },
        "confidence": {"percent": conf, "tier": confidence_tier(conf)},
        "likely_scorers": {
            na: likely_scorers(team_a, xg_a),
            nb: likely_scorers(team_b, xg_b),
        },
        "comparison": matchup_compare(team_a, team_b),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(description="World Cup single-match prediction (high-precision matchup)")
    p.add_argument("team_a", nargs="?", help="team code, e.g. FRA")
    p.add_argument("team_b", nargs="?", help="team code, e.g. SEN")
    p.add_argument("--home", default=None, help="team code that has home advantage (host nation only)")
    p.add_argument("--overrides", default=None,
                   help="path to a real-time overrides JSON (form/injuries/motivation)")
    p.add_argument("--human", action="store_true", help="print a readable matchup card instead of JSON")
    args = p.parse_args(argv)

    try:
        overrides = load_overrides(args.overrides)
    except Exception as e:  # noqa
        raise SystemExit("覆盖文件读取失败: %s" % e)

    if not args.team_a or not args.team_b:
        p.error("provide two team codes, e.g.  predict.py FRA SEN")

    def _team(code):
        t = load_team(code)
        return apply_overrides(t, overrides.get(str(t.get("code", "")).upper()))

    try:
        a = _team(args.team_a)
        b = _team(args.team_b)
    except ValueError as e:
        raise SystemExit(str(e))
    result = predict_match(a, b, home=args.home)

    if args.human:
        print_human(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def print_human(r):
    ta, tb = r["team_a"]["name"], r["team_b"]["name"]
    print("=== %s vs %s ===%s" % (ta, tb, "  [中性场]" if r.get("neutral") else ""))
    for side, adj in (r.get("adjustments") or {}).items():
        chg = "; ".join(adj.get("changes") or []) or "—"
        print("  ⚡实时校正 %s: %s | %s" % (side, adj.get("note") or "", chg))
    mlr = r["most_likely_result"]
    print("最可能结果: %s (%.0f%%) → 预测比分 %s   置信度: %s (%d%%)" % (
        mlr["label"], mlr["prob"] * 100, r["predicted_score"],
        r["confidence"]["tier"], r["confidence"]["percent"]))
    print("xG: %s %.2f - %.2f %s   (联合众数比分 %s)" % (
        ta, r["xg"]["a"], r["xg"]["b"], tb, r["modal_scoreline"]))
    rp = r["result_probability"]
    print("胜平负: %s胜 %.0f%% | 平 %.0f%% | %s胜 %.0f%%" % (
        ta, rp["%s胜" % ta] * 100, rp["平"] * 100, tb, rp["%s胜" % tb] * 100))
    print("最可能比分: " + " / ".join(
        "%s %.1f%%" % (s["score"], s["prob"] * 100) for s in r["top_scorelines"]))

    cmp = r.get("comparison", {})
    lines = cmp.get("lines", {})
    squad = cmp.get("squad", {})
    if lines:
        print("\n▼ 三线对比(%s / %s)" % (ta, tb))
        for k, v in lines.items():
            d = v.get("diff", 0)
            edge = ("%s占优 +%d" % (ta, d)) if d > 0 else (("%s占优 +%d" % (tb, -d)) if d < 0 else "持平")
            print("  %s: %s %s - %s %s  (%s)" % (k, ta, v.get("a"), v.get("b"), tb, edge))
    if squad:
        ab = squad.get("年龄结构", {}); ex = squad.get("经验", {})
        ca = squad.get("核心平均年龄", {}); fm = squad.get("状态", {})
        ep = cmp.get("defensive_error_prob", {})
        print("▼ 年龄/经验/状态")
        print("  核心平均年龄: %s %s - %s %s 岁" % (ta, ca.get("a"), ca.get("b"), tb))
        print("  年龄结构: %s %s - %s %s | 经验: %s %s - %s %s" % (
            ta, ab.get("a"), ab.get("b"), tb, ta, ex.get("a"), ex.get("b"), tb))
        print("  近期状态: %s %s - %s %s | 后防失误率: %s %s - %s %s" % (
            ta, fm.get("a"), fm.get("b"), tb, ta, ep.get("a"), ep.get("b"), tb))

    print("\n▼ 对位分析(高精度,已修正 xG)")
    bd = r["xg_breakdown"]
    for side in (ta, tb):
        b = bd[side]
        print("  %s 进攻 → 对方防线:  基线 %.2f × 动机 %.2f × 对位 %.2f = %.2f" % (
            side, b["base"], b["motivation_mult"], b["matchup_mult"], b["final"]))
        for d in r["matchup"][side]["dimensions"]:
            e = d["xg_effect"]
            sign = "＋" if e > 0 else ("－" if e < 0 else "＝")
            print("     · %s: %s vs %s (%+g) %s%.0f%% xG — %s" % (
                d["name"], d["attacker"], d["defender"], d["edge"], sign, abs(e) * 100, d["read"]))

    print("\n▼ 防守端(各自最吃哪条线)")
    for side in (ta, tb):
        dr = r["defense"][side]
        if dr["weaknesses"]:
            w = dr["weaknesses"][0]
            extra = ("; 另吃: " + ", ".join(x["dim"] for x in dr["weaknesses"][1:])) if len(dr["weaknesses"]) > 1 else ""
            print("  %s 防线: 被对手对位×%.2f;最吃【%s】%+.0f%% — %s%s" % (
                side, dr["concede_xg_mult"], w["dim"], w["xg_effect"] * 100, w["read"], extra))
        else:
            print("  %s 防线: 对位上不吃亏,各条线均能限制对手" % side)

    print("\n进球线索:")
    for side in (ta, tb):
        sc = r["likely_scorers"][side][:3]
        print("  %s: %s" % (side, ", ".join(
            "%s(%.2f|%s)" % (s["name"], s["expected_goals_share"], s["scoring_styles"]) for s in sc)))

    print("\n💡 想要对决图?生成生图prompt: python3 scripts/card.py %s %s --stage \"%s\"" % (
        r["team_a"]["code"], r["team_b"]["code"], "小组赛"))


if __name__ == "__main__":
    main()
