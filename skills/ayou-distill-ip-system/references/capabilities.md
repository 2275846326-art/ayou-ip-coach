# 能力与来源契约

## 挑选与去向

每个关键任务列入 coverage.md；去向为能力、参考、待核查或淘汰，并说明理由。可执行候选需同时满足：来源足以支持限定范围的做法；新输入下可以产出并核验结果；对任务有实际帮助。知识验证通过不意味着值得独立成技能。

有独立意图、输入输出、执行流程，并值得复用或独立评测时才考虑单独成技能。第一版默认总入口内的能力卡，不为单个概念制造安装项。

v1.1编译支持single/pack/auto：学习或查阅默认single；工作流或分发且有晋级能力时推荐pack。推荐是输出形态，不等于来源/评测已通过。晋级字段`promotion`中 independent_intent、independent_contract、independent_run 全为true，independent_reuse或independent_eval至少一项true；需实际理由记录在卡片。晋级还需`trigger`与`trigger_evaluation`报告，具备正例及近邻负例；pack的`router_description`独立描述未晋级及整份来源意图。总可发现入口默认预算8，可在Bundle显式调整promotion_budget，不为凑数晋级。

编译生成destinations.json、CHEATSHEET、关联能力链接和显式资源。pack所有同级技能目录一起安装；晋级入口会引用来源入口内同一份能力卡，不能只安装一个晋级目录。不得同时装同来源的single和pack。独立能力ID保持稳定，正文修订加revision；真正拆分/合并才换ID并保存替代映射。

## 能力卡七项

1. **书本原意**：有原文定位的忠实转述，保留前提；短引文适量，不用合成例子作为来源证据。
2. **来源证据**：源文件 ID/哈希、章/节、阅读器页序、核查范围；明确是直接原文还是历史蒸馏。
3. **应用扩展**：迁移到什么任务、改变了哪些条件、哪些步骤为我们新增、为什么可能成立。没有扩展也明确写无。
4. **触发与边界**：用户语言、适用场景、负例、与邻近能力的区别。
5. **输入输出**：必需与可选字段，缺失时问什么/停在哪；格式、单位、证据与完成条件。
6. **执行**：操作顺序、条件分支、失败处理；每步可以判定是否完成。
7. **案例、测试与假设**：书中案例/合成演练分开；功能表现、现实效果和未验证假设分开记录。

## 可编译数据

bundle.json 使用 `schema_version: 1`、`name`、`description`、`revision`、`sources`、`capabilities`。
源条目：`id`、`path`（相对工作目录或明确绝对路径）、`sha256`。
能力条目：`id`、`title`、`card`（工作目录内相对路径）、`source_status`（verified/needs_review）、`evidence`、`extension_status`（none/proposed/functional_tested）、`test_status`（not_run/failed/passed）、`evaluation`（工作目录内评测报告）、`case_ids`（本能力测试 ID）。
证据条目：`source_id`、`location`、`checked_on`、`scope`。location 必须实际可定位，不用“整本书”替代；source_status 为 verified 是人工完成来源核查后的声明，哈希校验不证明语义忠实。

能力正文是内容事实源，bundle 是路由与状态事实源；冲突时先修正，不编译。编译产物只读，变更回到原卡和 bundle，输出到新目录保留旧版。

可选Bundle字段：router_description、promotion_budget、book_resources（相对文本路径）。可选能力字段：revision、also_read（其他能力ID）、one_liner、trigger、promotion、trigger_evaluation（相对报告路径）、resources（相对文本路径）。所有随包资源需要被测试版本resource_sha256绑定，修改资源后旧报告失效。

## 状态不能压成一个分数

- 已蒸馏：材料完整阅读、六层齐全；历史声明与本轮阅读区分。
- 已核对：声明范围内来源核查通过；旧标准的用户抽考另外记录。
- 已验证能力：限定范围内来源核查＋实际功能测试通过。
- 应用扩展功能测试通过：演练可完成任务；现实效果仍待业务数据验证。

任一来源或执行变化均使相关测试需要重跑，不能继承旧通过。新增实战结果进候选记录，不自动升为普遍规律。
