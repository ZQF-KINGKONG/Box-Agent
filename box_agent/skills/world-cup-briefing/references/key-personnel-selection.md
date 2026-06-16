# 关键人员自动识别规则

世界杯战况简报和焦点战内容中，不应等待用户点名球员；必须根据比赛事实自动筛选关键人员，并给出简短介绍。

## 适用范围

- 昨日战况简报
- 最近 3 天战况简报
- 焦点战预告或复盘
- 用户关注球队/球员相关内容

## 必须筛选的关键人员类型

按优先级自动识别：

1. **直接改变比分的人**
   - 进球者
   - 助攻者
   - 点球制造者或罚入/罚失者
   - 乌龙球相关球员

2. **改变比赛走势的人**
   - 红牌/重大犯规相关球员
   - 替补登场后直接制造进球或明显改变节奏的球员
   - 加时、补时、点球大战中的决定性人物

3. **守门员与防线核心**
   - 零封比赛中的门将
   - 多次关键扑救、扑点、点球大战表现突出的门将
   - 在弱队逼平/爆冷强队时，优先检查门将和中卫

4. **赛前/赛后被权威来源明确提及的核心人物**
   - 队长
   - 核心前锋/中场组织者
   - 主教练
   - 明确伤停、复出或轮换导致战术变化的人

5. **用户偏好相关人员**
   - 用户关注球队的核心球员、教练、伤停人员
   - 用户关注球员本人，如其所在队最近 3 天无比赛，也要明确说明“本期未检到直接相关战况”

## 每场比赛至少检查

- 进球与助攻
- 红黄牌、点球、乌龙、换人
- 门将表现，尤其是低比分、平局、爆冷、零封比赛
- 双方队长/主教练是否对比赛有明显影响
- 是否有伤停、复出、停赛、轮换信息

## 输出要求

“关键人员信息”不能只列名字，必须包含：

- 姓名
- 所属球队
- 角色/位置
- 为什么关键：用 1-2 句说明其对这场比赛的影响
- 信息确定性：已确认 / 待核 / 赛后需刷新

## 人数控制

- 昨日战况：默认 4-8 人
- 最近 3 天：默认 6-12 人
- 单场焦点战：默认双方各 2-4 人
- 如果数据不足，明确写“可确认关键人员不足”，不要编造

## 禁止事项

- 不要只写用户举例给出的名字。
- 不要靠名气选人；必须和本场/近 3 天事实相关。
- 不要把传闻、社媒讨论当作确认事实。
- 不要用“核心球员很多”代替具体介绍。


## 每场最低覆盖要求

For each completed match included in a briefing, include at least 2-3 of the following personnel dimensions when verifiable:

- Starting core or captain
- Goal scorer, assister, penalty taker, or chance creator
- Goalkeeper or defensive leader with key saves/blocks/clean-sheet impact
- Substitute who changed the match
- Injured, suspended, absent, or returning player who changed tactical setup
- Head coach's tactical or substitution adjustment
- Player likely to affect the next match through rotation, suspension, or form

If a match lacks enough verifiable personnel detail, explicitly mark “可确认关键人员不足 / 待刷新”, rather than inventing names or relying only on star reputation.
