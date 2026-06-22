# 我的技能说明书

生成时间：2026-06-18 11:20
技能总数：6
健康概览：正常 5 个，需完善 0 个，风险 1 个

## 1. 我现在有哪些技能

### 写作内容
- **khazix-writer / 公众号写作助手**
  - 用途：面向公众号文章、报告和长文写作，帮助用户形成清晰、有传播感的内容。
  - 唤起方式：/khazix-writer
  - 健康分：100；建议：保持版本说明和触发词更新

### 地图出行
- **TencentMap_map-assistant / 腾讯地图助手**
  - 用途：地点搜索、路线规划、天气查询和旅游行程地图渲染。
  - 唤起方式：/TencentMap_map-assistant
  - 健康分：100；建议：保持版本说明和触发词更新

### 技能创建
- **skill-creator-optimized-pro / 高级技能创建器**
  - 用途：创建、优化、审计和打包 AI Skill 技能包，修复 YAML front matter 和 SkillHub 上传结构。
  - 唤起方式：/skill-creator-optimized-pro
  - 健康分：100；建议：保持版本说明和触发词更新

### 技能导航
- **skill-navigation-assistant-sl / 技能导航助手**
  - 用途：扫描本地技能库，解释技能用途和唤起方式，根据用户任务推荐最合适的前 3 个技能，并在本地无合适技能时给出 SkillHub 补齐建议。
  - 唤起方式：/skill-navigation-assistant-sl
  - 健康分：100；建议：保持版本说明和触发词更新

### 未分类
- **legacy-skill / 旧技能**
  - 用途：该技能缺少清晰说明，需要补充 description。
  - 唤起方式：/legacy-skill
  - 健康分：55；建议：修复 YAML front matter，确保可解析; 补充 description 或中文用途说明

### 通用办公
- **hv-analysis / 横纵分析法研究**
  - 用途：系统性调研产品、公司、概念和技术，输出纵向发展脉络、横向竞品对比和洞察报告。
  - 唤起方式：/hv-analysis
  - 健康分：100；建议：保持版本说明和触发词更新

## 2. 推荐置顶与高频入口
统计模式：usage_data。基于使用记录统计。
建议置顶：skill-navigation-assistant-sl、skill-creator-optimized-pro、TencentMap_map-assistant
最近使用：skill-navigation-assistant-sl、skill-creator-optimized-pro、TencentMap_map-assistant

## 3. 当前任务推荐工作流
任务：我想调研一个产品并写成报告，再沉淀成 SkillHub 技能
1. **资料收集**：hv-analysis（/hv-analysis）
   - 任务包含“资料收集”相关意图，该技能在名称、类别或说明中命中相关关键词。
2. **内容生产**：khazix-writer（/khazix-writer）
   - 任务包含“内容生产”相关意图，该技能在名称、类别或说明中命中相关关键词。
3. **交付打包**：skill-creator-optimized-pro（/skill-creator-optimized-pro）
   - 任务包含“交付打包”相关意图，该技能在名称、类别或说明中命中相关关键词。

## 4. 技能库强项与缺口
强项类别：暂无明显强项
缺口类别：数据分析、知识管理、协作沟通、专家顾问、系统运维
建议去 SkillHub 搜索：数据分析 技能、知识管理 技能、协作沟通 技能、专家顾问 技能、系统运维 技能

## 5. 需要维护的技能
- **legacy-skill**：健康分 55
  - 问题：YAML 状态异常：missing_front_matter; 缺少清晰中文用途说明; 缺少版本号; 无法自动分类
  - 建议：修复 YAML front matter，确保可解析; 补充 description 或中文用途说明; 在 YAML 中补充 version; 补充更明确的触发词和适用场景

## 6. 下一步建议
1. 优先修复健康分低于 70 的技能。
2. 将高频技能置顶或记入常用入口。
3. 对缺口类别优先去 SkillHub 查找 Prompt 安装或 ZIP 包安装入口。
4. 如果某类任务经常出现但没有合适技能，建议沉淀为新的 SkillHub 技能。
