# Skill Navigation Assistant SL / 技能导航助手

Skill Navigation Assistant SL 是一个面向办公小浣熊 SkillHub 的技能导航中枢，用于帮助用户全盘扫描本地技能、理解技能用途、根据任务推荐最合适的技能组合，并在本地没有合适技能时引导去 SkillHub 补齐能力。

## 核心能力

1. **本地技能全盘扫描**
   - 扫描用户技能目录和内置技能目录。
   - 读取技能英文名称、中文名称、版本、描述、路径、唤起方式和健康状态。

2. **技能中文说明**
   - 用中文解释技能做什么、适合什么场景、如何唤起。
   - 对缺少中文说明的技能生成保守中文解释，并标注“推断”。

3. **任务匹配推荐**
   - 用户提出任务后，从本地技能库中推荐最合适的前 3 个技能。
   - 给出单独使用或组合使用建议。

4. **SkillHub 补齐建议**
   - 本地没有合适技能时，生成 SkillHub 搜索关键词和候选评估清单。
   - 支持识别 SkillHub 页面常见的两种安装入口：复制 Prompt 安装、下载 ZIP 包安装。
   - 安装前必须获得用户确认。

5. **友好使用引导**
   - 用户直接启用技能时，主动展示可选用法和示例。

6. **技能健康评分**
   - 为每个技能输出 0-100 健康分、扣分原因和修复建议。

7. **最近使用 / 高频推荐**
   - 支持读取可选 usage JSON；无使用记录时基于健康分和通用性降级推荐。

8. **技能组合工作流**
   - 按任务阶段生成主技能、辅助技能、执行顺序和组合理由。

9. **技能缺口分析**
   - 统计技能类别覆盖，识别强项、缺口、风险技能，并给出 SkillHub 搜索关键词。

10. **我的技能说明书**
   - 一键生成 Markdown 说明书，包含总览、清单、健康、置顶、工作流、缺口和下一步建议。

## 推荐唤起方式

```text
/skill-navigation-assistant-sl
/skill-navigation-assistant-sl 列出全部技能
/skill-navigation-assistant-sl 我想做一个客户体验旅程地图，推荐哪个技能？
/skill-navigation-assistant-sl 检查我的技能健康度
/skill-navigation-assistant-sl 分析我的技能库强项和缺口
/skill-navigation-assistant-sl 生成我的技能说明书
```

也可以用自然语言：

```text
我有哪些技能？
帮我匹配一个适合做 SkillHub 技能包优化的技能。
本地没有合适技能的话，帮我去 SkillHub 找。
```

## 文件结构

```text
skill-navigation-assistant-sl/
├── SKILL.md
├── README.md
├── references/
│   ├── advanced-capabilities.md
│   ├── health-check.md
│   ├── matching-rules.md
│   ├── skillhub-policy.md
│   └── usage-guide.md
├── scripts/
│   ├── analyze_library.py
│   ├── generate_handbook.py
│   ├── health_check.py
│   ├── match_skills.py
│   └── scan_skills.py
├── templates/
│   ├── gap-analysis.md
│   ├── handbook.md
│   ├── recommendation.md
│   ├── skill-list.md
│   ├── skillhub-install-options.md
│   ├── skillhub-result.md
│   └── workflow.md
└── tests/
    ├── sample-handbook.md
    ├── sample-library-report.json
    ├── sample-library-report.md
    ├── sample-skills.json
    └── sample-usage.json
```

## 安全原则

- 不自动安装第三方技能。
- 不自动覆盖本地同名技能。
- 下载、安装、覆盖、启动外部技能前必须获得用户确认。
- SkillHub 推荐必须提供链接、理由和风险提示。

## 维护说明

更新技能时，请确保：

- 根目录包含包级 `SKILL.md`。
- `SKILL.md` 包含 YAML front matter。
- YAML front matter 可被标准 YAML 解析。
- description 中如包含英文冒号和空格，必须加引号。
