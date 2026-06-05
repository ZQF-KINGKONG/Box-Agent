# writing-workflow SkillHub 发布审计

## 1. 审计对象与结论

- 审计对象：`writing-workflow`
- 当前结构：包含 `SKILL.md`、`AGENTS.md`、`README.md`、`LICENSE`、`CHANGELOG.md`、`skillhub.json`、`package.json`、`examples/`、`references/`、`tests/`、`docs/` 和 `reports/`。
- 综合判断：**可以作为 SkillHub 候选发布包继续验证**。当前版本已经具备写作分诊、结构化成文、风格参考、事实核查、风险降级、发布前质量门禁和失败恢复规则。
- 发布前仍需注意：确认目标 SkillHub schema 是否接受当前 `skillhub.json` 字段；若平台要求 UI 元数据，应另行补充 `agents/openai.yaml`。

## 2. 已修复项

| 项目 | 当前状态 |
|---|---|
| 入口元数据 | `SKILL.md` 已包含名称、描述、版本、许可、标签、触发词、兼容性和隐私字段。 |
| 参考资料导航 | `SKILL.md` 已说明何时读取 `references/roles.md`、`references/workflows.md`、`references/evidence-policy.md` 和 `references/quality-gates.md`。 |
| 通用化资料入口 | 证据政策与工作流已改为“授权知识库素材”和“授权阅读材料”，不绑定具体私有平台。 |
| 隐私边界 | 默认不读取私有材料；仅使用用户当前提供或明确授权的内容；私人原文只可概括、脱敏或短引。 |
| 发布元数据一致性 | `skillhub.json` 区分 `has_agent_instructions` 与 `has_ui_metadata`，不再暗示存在 UI metadata 文件。 |
| 打包边界 | 新增 `.skillignore`，排除本地状态、缓存、日志和系统临时文件。 |

## 3. 发布检查清单

- `SKILL.md` front matter 可被目标平台解析。
- `skillhub.json` 字段符合目标平台 schema。
- 打包流程遵守 `.skillignore`，不包含 `.omx/`、`.DS_Store`、缓存或日志。
- 示例、测试和参考文档不包含真实私人材料、密钥、内部账号、客户隐私或未授权内容。
- 高风险事实、第三方评价、法律医疗金融等内容会进入事实核查与风险降级流程。
- 外部发布前仍建议人工复核事实、合规、品牌语气和敏感信息。

## 4. 剩余风险

- 当前测试主要是结构化人工评测，不是可执行自动化测试。
- 若部署环境支持真实知识库、阅读平台或网络检索，需要由宿主环境单独提供权限、审计和数据最小化策略。
- 若平台强制要求 `agents/openai.yaml` 一类 UI 元数据，当前包需要补充该文件后再上架。
