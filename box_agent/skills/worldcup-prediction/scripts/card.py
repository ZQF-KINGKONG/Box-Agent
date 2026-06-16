#!/usr/bin/env python3
"""Generate a TEXT-TO-IMAGE prompt for a '巨星对决图' from a prediction.

This skill does NOT render images itself. It turns the predicted matchup into a
ready-to-use prompt (EN + ZH + negative + caption) describing a dramatic
two-star face-off poster with the scoreline. The host client (and the image
model it integrates) renders the actual picture from this prompt.

Usage:
  python3 card.py FRA SEN --stage "I组·小组赛"
  python3 card.py BRA HAI --overrides rt.json --stage "C组·第2轮"
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predict  # noqa: E402

# code -> (flag, English name, kit_en, kit_zh)
TEAM_INFO = {
    "FRA": ("🇫🇷", "France", "blue home kit", "蓝色主场球衣"),
    "SEN": ("🇸🇳", "Senegal", "white-and-green kit", "白绿球衣"),
    "ARG": ("🇦🇷", "Argentina", "sky-blue and white striped kit", "天蓝白间条衫"),
    "BRA": ("🇧🇷", "Brazil", "iconic yellow-and-green kit", "标志性黄绿球衣"),
    "ESP": ("🇪🇸", "Spain", "red kit", "红色球衣"),
    "ENG": ("🏴", "England", "white kit", "白色球衣"),
    "POR": ("🇵🇹", "Portugal", "dark red kit", "深红球衣"),
    "NED": ("🇳🇱", "Netherlands", "bright orange kit", "橙色球衣"),
    "GER": ("🇩🇪", "Germany", "white kit with black trim", "白色黑边球衣"),
    "BEL": ("🇧🇪", "Belgium", "red kit", "红色球衣"),
    "CRO": ("🇭🇷", "Croatia", "red-and-white checkerboard kit", "红白格子衫"),
    "URU": ("🇺🇾", "Uruguay", "sky-blue kit", "天蓝球衣"),
    "COL": ("🇨🇴", "Colombia", "bright yellow kit", "亮黄球衣"),
    "MEX": ("🇲🇽", "Mexico", "green kit", "绿色球衣"),
    "USA": ("🇺🇸", "USA", "white-and-navy kit", "白藏青球衣"),
    "JPN": ("🇯🇵", "Japan", "deep blue kit", "深蓝球衣"),
    "MAR": ("🇲🇦", "Morocco", "red kit with green trim", "红色绿边球衣"),
    "SUI": ("🇨🇭", "Switzerland", "red kit", "红色球衣"),
    "KOR": ("🇰🇷", "South Korea", "red kit", "红色球衣"),
    "NOR": ("🇳🇴", "Norway", "red kit", "红色球衣"),
    "SWE": ("🇸🇪", "Sweden", "yellow-and-blue kit", "黄蓝球衣"),
    "TUN": ("🇹🇳", "Tunisia", "red-and-white kit", "红白球衣"),
    "HAI": ("🇭🇹", "Haiti", "blue-and-red kit", "蓝红球衣"),
    "GHA": ("🇬🇭", "Ghana", "white kit", "白色球衣"),
    "ECU": ("🇪🇨", "Ecuador", "yellow kit", "黄色球衣"),
    "CIV": ("🇨🇮", "Ivory Coast", "orange kit", "橙色球衣"),
    "IRN": ("🇮🇷", "Iran", "white kit", "白色球衣"),
    "EGY": ("🇪🇬", "Egypt", "red kit", "红色球衣"),
    "SCO": ("🏴", "Scotland", "dark blue kit", "深蓝球衣"),
    "CAN": ("🇨🇦", "Canada", "red kit", "红色球衣"),
    "TUR": ("🇹🇷", "Turkiye", "red kit", "红色球衣"),
    "ALG": ("🇩🇿", "Algeria", "green-and-white kit", "绿白球衣"),
    "AUT": ("🇦🇹", "Austria", "red kit", "红色球衣"),
    "COD": ("🇨🇩", "DR Congo", "blue kit", "蓝色球衣"),
}
DEFAULT_INFO = ("⚽", "", "national-team kit", "主场球衣")

# short Chinese colour word per team, for the "图方向" one-liner
COLOR_ZH = {
    "FRA": "蓝", "SEN": "绿", "ARG": "蓝白", "BRA": "黄", "ESP": "红", "ENG": "白",
    "POR": "红", "NED": "橙", "GER": "白", "BEL": "红", "CRO": "红白", "URU": "天蓝",
    "COL": "黄", "MEX": "绿", "USA": "蓝", "JPN": "蓝", "MAR": "红", "SUI": "红",
    "KOR": "红", "NOR": "红", "SWE": "黄蓝", "TUN": "红", "HAI": "蓝", "GHA": "白",
    "ECU": "黄", "CIV": "橙", "IRN": "白", "EGY": "红", "SCO": "蓝", "CAN": "红",
    "TUR": "红", "ALG": "绿", "AUT": "红", "COD": "蓝",
}

# Chinese player name (as in team YAML) -> internationally recognised romanized name.
# Used so the (strong) image model renders the REAL player's likeness. Unmapped
# names fall back to the Chinese string.
STAR_EN = {
    # France
    "姆巴佩": "Kylian Mbappé", "登贝莱": "Ousmane Dembélé", "格列兹曼": "Antoine Griezmann",
    "巴尔科拉": "Bradley Barcola", "祖阿梅尼": "Aurélien Tchouaméni",
    # Senegal
    "萨迪奥·马内": "Sadio Mané", "尼古拉斯·杰克逊": "Nicolas Jackson", "伊斯梅拉·萨尔": "Ismaïla Sarr",
    "伊利曼·恩迪亚耶": "Iliman Ndiaye", "帕普·马塔尔·萨尔": "Pape Matar Sarr",
    # Argentina
    "梅西": "Lionel Messi", "劳塔罗·马丁内斯": "Lautaro Martínez", "胡利安·阿尔瓦雷斯": "Julián Álvarez",
    "恩佐·费尔南德斯": "Enzo Fernández", "麦卡利斯特": "Alexis Mac Allister",
    # Brazil
    "维尼修斯": "Vinícius Júnior", "罗德里戈": "Rodrygo", "恩德里克": "Endrick",
    "拉菲尼亚": "Raphinha", "布鲁诺·吉马良斯": "Bruno Guimarães",
    # Portugal / Spain / England / Germany / Belgium / Netherlands / Croatia / Uruguay / Colombia
    "C罗": "Cristiano Ronaldo", "B费": "Bruno Fernandes", "B席": "Bernardo Silva", "莱昂": "Rafael Leão",
    "亚马尔": "Lamine Yamal", "佩德里": "Pedri", "罗德里": "Rodri", "莫拉塔": "Álvaro Morata", "尼科·威廉姆斯": "Nico Williams",
    "贝林厄姆": "Jude Bellingham", "凯恩": "Harry Kane", "福登": "Phil Foden", "萨卡": "Bukayo Saka", "帕尔默": "Cole Palmer",
    "维尔茨": "Florian Wirtz", "穆夏拉": "Jamal Musiala", "哈弗茨": "Kai Havertz", "京多安": "İlkay Gündoğan", "萨内": "Leroy Sané",
    "德布劳内": "Kevin De Bruyne", "卢卡库": "Romelu Lukaku", "多库": "Jérémy Doku",
    "德佩": "Memphis Depay", "加克波": "Cody Gakpo", "弗伦基·德容": "Frenkie de Jong", "哈维·西蒙斯": "Xavi Simons", "范迪克": "Virgil van Dijk", "雷因德斯": "Tijjani Reijnders",
    "莫德里奇": "Luka Modrić", "克拉马里奇": "Andrej Kramarić", "科瓦契奇": "Mateo Kovačić",
    "努涅斯": "Darwin Núñez", "巴尔韦德": "Federico Valverde", "阿劳霍": "Ronald Araújo",
    "哈梅斯·罗德里格斯": "James Rodríguez", "路易斯·迪亚斯": "Luis Díaz",
    # Japan / Korea / Mexico / USA
    "三笘薰": "Kaoru Mitoma", "久保建英": "Takefusa Kubo", "镰田大地": "Daichi Kamada", "堂安律": "Ritsu Dōan", "上田绮世": "Ayase Ueda",
    "孙兴慜": "Son Heung-min", "李刚仁": "Lee Kang-in", "黄喜灿": "Hwang Hee-chan", "金玟哉": "Kim Min-jae",
    "劳尔·希门尼斯": "Raúl Jiménez", "洛萨诺": "Hirving Lozano",
    "普利西奇": "Christian Pulisic", "韦阿": "Timothy Weah",
    # Norway / Sweden / Morocco / Switzerland / Turkiye / Ecuador
    "哈兰德": "Erling Haaland", "厄德高": "Martin Ødegaard", "索尔洛特": "Alexander Sørloth", "努萨": "Antonio Nusa", "博布": "Oscar Bobb",
    "伊萨克": "Alexander Isak", "约克雷斯": "Viktor Gyökeres", "库卢塞夫斯基": "Dejan Kulusevski", "埃兰加": "Anthony Elanga",
    "哈基米": "Achraf Hakimi", "布拉欣·迪亚斯": "Brahim Díaz", "恩内斯里": "Youssef En-Nesyri",
    "扎卡": "Granit Xhaka", "恩博洛": "Breel Embolo",
    "阿尔达·居莱尔": "Arda Güler", "恰尔汗奥卢": "Hakan Çalhanoğlu", "肯南·耶尔德兹": "Kenan Yıldız",
    "凯塞多": "Moisés Caicedo", "恩内尔·瓦伦西亚": "Enner Valencia", "肯德里·派斯": "Kendry Páez",
    # Africa / others
    "萨拉赫": "Mohamed Salah", "马尔穆什": "Omar Marmoush",
    "库杜斯": "Mohammed Kudus", "伊尼亚基·威廉姆斯": "Iñaki Williams", "塞门约": "Antoine Semenyo", "乔丹·阿尤": "Jordan Ayew",
    "哈勒尔": "Sébastien Haller", "凯西": "Franck Kessié", "阿丁格拉": "Simon Adingra", "佩佩": "Nicolas Pépé",
    "塔雷米": "Mehdi Taremi", "阿兹蒙": "Sardar Azmoun",
    "麦克托米奈": "Scott McTominay", "麦金": "John McGinn", "切·亚当斯": "Ché Adams",
    "乔纳森·戴维": "Jonathan David", "阿方索·戴维斯": "Alphonso Davies",
    "希克": "Patrik Schick", "哲科": "Edin Džeko", "道萨里": "Salem Al-Dawsari", "珀西·陶": "Percy Tau",
    "阿克拉姆·阿菲夫": "Akram Afif", "克里斯·伍德": "Chris Wood", "塔伊特·钟": "Tahith Chong",
    "约阿内·维萨": "Yoane Wissa", "塞德里克·巴坎布": "Cédric Bakambu",
    "里亚德·马赫雷斯": "Riyad Mahrez", "穆萨·塔马里": "Mousa Al-Taamari",
}

_ROLE_EN = {"W": "winger", "AM": "attacking midfielder", "ST": "striker", "F": "forward"}
_ROLE_ZH = {"W": "边锋", "AM": "前腰", "ST": "前锋", "F": "前锋"}


def _star(r, team_name):
    lst = r["likely_scorers"].get(team_name, [])
    return lst[0] if lst else {}


def _role_key(star):
    pos = (star.get("position") or "").upper()
    if any(t in pos for t in ("LW", "RW")) or pos.endswith("W"):
        return "W"
    if "AM" in pos:
        return "AM"
    if any(t in pos for t in ("ST", "CF", "SS")):
        return "ST"
    return "F"


def _desc_en(star):
    left = "left-footed " if "左脚" in str(star.get("traits", "")) else ""
    return left + _ROLE_EN[_role_key(star)]


def _desc_zh(star):
    left = "左脚" if "左脚" in str(star.get("traits", "")) else ""
    return left + _ROLE_ZH[_role_key(star)]


def build_prompts(r, stage=""):
    a, b = r["team_a"], r["team_b"]
    fa, ena, kita_en, kita_zh = TEAM_INFO.get(str(a["code"]).upper(), DEFAULT_INFO)
    fb, enb, kitb_en, kitb_zh = TEAM_INFO.get(str(b["code"]).upper(), DEFAULT_INFO)
    sa, sb = _star(r, a["name"]), _star(r, b["name"])
    na, nb = sa.get("name", a["name"]), sb.get("name", b["name"])
    na_en = STAR_EN.get(na, na)  # real romanized name for likeness
    nb_en = STAR_EN.get(nb, nb)
    s1, s2 = r["predicted_score"].split("-")
    score_line = "%s %s - %s %s" % (a["name"], s1, s2, b["name"])

    # 图方向 one-liner: top-2 scorers per side + team colours + stage
    top2a = "/".join(p.get("name", "") for p in r["likely_scorers"].get(a["name"], [])[:2])
    top2b = "/".join(p.get("name", "") for p in r["likely_scorers"].get(b["name"], [])[:2])
    cola = COLOR_ZH.get(str(a["code"]).upper(), "主色")
    colb = COLOR_ZH.get(str(b["code"]).upper(), "主色")
    direction = "%s｜%s vs %s｜%s%s对抗风｜%s预测卡" % (
        score_line, top2a or na, top2b or nb, cola, colb, stage or "世界杯")

    en = (
        "Epic cinematic football showdown poster, vertical 3:4, sports-magazine cover style. "
        "Dramatic split-screen face-off between two REAL superstars, photorealistic recognisable likenesses. "
        "LEFT: %s, the real %s national-team star (%s), wearing %s, fierce determined stare, dynamic heroic pose. "
        "RIGHT: %s, the real %s national-team star (%s), wearing %s, intense glare, facing the opponent. "
        "CENTER: large glowing golden 'VS' emblem with sparks. "
        "Background: packed night stadium, blazing floodlights, lens flare, drifting smoke and confetti, "
        "electric blue-to-magenta rim lighting, hyper-detailed, photorealistic, accurate facial likeness, high contrast, 8k. "
        "Reserve a bold banner area at the BOTTOM for large scoreline text: \"%s\". "
        "%sWorld Cup 2026."
    ) % (na_en, ena, _desc_en(sa), kita_en, nb_en, enb, _desc_en(sb), kitb_en,
         score_line, ("(%s) " % stage) if stage else "")

    zh = (
        "电影感足球巨星对决海报,竖版3:4,杂志封面级,写实还原真实球星本人。左右分屏对峙两位巨星。"
        "左:%s(%s,真实球星本人,%s),身穿%s,眼神凶狠坚定,动态英雄姿势;"
        "右:%s(%s,真实球星本人,%s),身穿%s,与对手对视。"
        "中央:巨大发光金色「VS」带火花。背景:满座夜晚球场、强烈泛光灯、镜头光晕、烟雾与彩纸、"
        "蓝到品红的轮廓光,超精细、写实、面部高度还原、高对比、8k。"
        "底部预留醒目横幅放大字比分:「%s」。世界杯2026%s。"
    ) % (na_en, a["name"], _desc_zh(sa), kita_zh, nb_en, b["name"], _desc_zh(sb), kitb_zh,
         score_line, ("·" + stage) if stage else "")

    neg = "no extra limbs, no distorted or unrecognisable faces, no garbled text, no watermark, not blurry, no fictional players"

    rp = r["result_probability"]
    caption = (
        "🔥%s vs %s｜模型预测 %s\n"
        "巨星对决:%s vs %s\n"
        "%s胜%.0f%% / 平%.0f%% / %s胜%.0f%%(置信度%s)\n"
        "#世界杯 #%s #足球预测"
    ) % (a["name"], b["name"], r["predicted_score"], na, nb,
         a["name"], rp["%s胜" % a["name"]] * 100, rp["平"] * 100,
         b["name"], rp["%s胜" % b["name"]] * 100, r["confidence"]["tier"],
         (a["name"] + "vs" + b["name"]))

    return {"en": en, "zh": zh, "negative": neg, "caption": caption,
            "score_line": score_line, "stars": [na, nb], "direction": direction}


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate a text-to-image prompt for a 巨星对决图")
    p.add_argument("team_a")
    p.add_argument("team_b")
    p.add_argument("--home", default=None)
    p.add_argument("--overrides", default=None)
    p.add_argument("--stage", default="", help="如 'I组·小组赛'")
    p.add_argument("--json", action="store_true", help="输出 JSON 而非文本")
    args = p.parse_args(argv)

    overrides = predict.load_overrides(args.overrides)

    def _team(code):
        t = predict.load_team(code)
        return predict.apply_overrides(t, overrides.get(str(t.get("code", "")).upper()))

    try:
        a, b = _team(args.team_a), _team(args.team_b)
    except ValueError as e:
        raise SystemExit(str(e))
    r = predict.predict_match(a, b, home=args.home)
    out = build_prompts(r, stage=args.stage)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print("========== 巨星对决图 · 生图 Prompt ==========")
    print("【比分】%s   【双星】%s vs %s" % (out["score_line"], out["stars"][0], out["stars"][1]))
    print("【图方向】%s\n" % out["direction"])
    print("--- 英文 prompt(推荐,多数模型更准)---\n%s\n" % out["en"])
    print("--- 中文 prompt ---\n%s\n" % out["zh"])
    print("--- negative(SD/MJ 可选)---\n%s\n" % out["negative"])
    print("--- 配套文案(发帖用)---\n%s" % out["caption"])
    print("\n提示:把上面的 prompt 交给客户端接入的生图模型渲染。"
          "支持文字的模型(nano-banana / Gemini 类)可直接出比分;否则比分作为叠加层。")


if __name__ == "__main__":
    main()
