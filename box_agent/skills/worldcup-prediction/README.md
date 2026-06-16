# worldcup-prediction

世界杯**单场**比分预测技能。基于 48 强球队画像 + 评分模型 + **高精度对位引擎**(后防与
对位直接修正 xG),预测某场比分、胜平负、置信度,并细化到「谁进球、怎么进」与对位拆解。

## 用法

```bash
# 单场高精度(对位分析默认开启,已修正 xG)
python3 scripts/predict.py FRA SEN --human

# 东道主在本国享主场加成(默认中性场)
python3 scripts/predict.py MEX KOR --home MEX

# 叠加实时校正(伤停/状态/上轮结果/动机),基准 YAML 不动
python3 scripts/predict.py BRA HAI --overrides references/overrides.example.json --human
```

> 只做单场,不做「未来 24 小时」批量。用户只说「下一场」时,先 web 查/确认对手,再单场预测。

## 数据说明

- 真实 2026 世界杯为 **48 队 / 12 组**(美·加·墨主办)。**球队库已覆盖全部 48 队**;
  评分(ratings 0-100)与球员属性为**主观估计,非官方数据**,仅供玩具级预测。
- **基准 vs 实时**:`teams/*.yaml` 是球队**整体满状态画像**(稳定),**不写时点信息**;
  伤停、近期状态、上轮结果、动机等实时信息在跑预测时用 `--overrides` 运行时叠加,基准不改。
- `references/schedule.yaml` 仅作真实赛程参考(6/14–6/18 + F 组),脚本不再读取。

## 结构

| 文件 | 作用 |
|------|------|
| `SKILL.md` | 技能入口与工作流 |
| `scripts/predict.py` | 单场预测模型(纯标准库;基线 + 对位引擎 + 实时/动机层;JSON / `--human`) |
| `scripts/card.py` | 巨星对决图「生图 prompt」生成器(EN/ZH prompt + 文案;不渲染图,交用户的生图工具) |
| `references/scoring-model.md` | 评分逻辑、对位引擎、动机乘子、手算降级方案 |
| `references/output-template.md` | 中文单场报告模板(含对位拆解) |
| `references/schedule.yaml` | 真实赛程(参考用,脚本不读) |
| `references/overrides.example.json` | 实时校正层示例(伤停/状态/换人/动机,运行时叠加) |
| `references/teams/*.yaml` | 48 强球队整体画像数据库 |

## 模型要点

- xG:攻防比 × 中场控制 × 状态 + 后防失误加成,泊松分布展开比分矩阵。
- 头条比分 `predicted_score`:先定最可能结果(胜/平/负),再取该结果下最高比分,
  避免独立泊松把所有势均力敌的比赛都压成 1-1。
- 置信度:比分分布集中度 + 结果决断度,两强相遇 → 低置信度。
