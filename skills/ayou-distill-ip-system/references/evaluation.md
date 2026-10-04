# 任务评测与交付

## 先定标准，再跑任务

围绕能力实际输入输出定义代表任务，至少覆盖正常任务、缺输入、边界负例；涉及数字/单位/条件分支时增加相应样例。保存 suite.json 后再执行。用例应检验任务结果，不只比对措辞。

每个用例：`id`、`kind`（positive/missing_input/negative）、`prompt`、`criteria`（供语义评审）、`assertions`（可选机械断言）。断言支持：contains/not_contains（value字符串）；json_equals（field支持点分嵌套键、value期望值）；json_number（数字value、非负tolerance）；json_unit（field单位字段、value期望单位）；file_exists（path相对本用例输出目录）。数值不接受NaN/Infinity或布尔值；文件交付随报告登记哈希，无断言时仍需可解释语义评审。

suite 顶层包含 `bundle`（相对suite的Bundle路径）、`bundle_sha256`、`card_sha256`（卡片相对路径到哈希映射）、`resource_sha256`（可选，所有声明资源的路径哈希）、`cases`。固定被测版本，来源/卡片/触发声明变更后重建用例版本并重跑。没有资源的v1.0旧suite无需增加空字段。

AI在读取能力卡后逐条完成真实请求，输出落文件；不要用预期答案替代运行结果。results.json 顶层为 `reviewer`、`independent`（true/false）、`suite_sha256`、`cases`。每项：`id`、`output`（工作目录内路径，如 ../evals/outputs/p1.md 相对 results）、`semantic_pass`（布尔）、`reason`（说明是否满足标准）。

语义复核检查：方法选择/拒绝是否正确、结论是否受输入支持、分组/公式/分支是否正确、是否编造事实、输出能否直接用于任务。实际结果可得时再验证效果；合成案例不可声称获客提升或用户真实反馈。

## 计分与独立性

`bundle_tool.py score` 核验版本哈希、每个实际输出及断言；缺运行、重复/未知 ID、空输出或未填写语义理由均失败。每个用例都在分母里，不能只报完成的成功样例。

工具只核验语义评审记录存在，不证明评审正确。自运行自评时 `independent: false`，报告为功能自测；独立代理/人工盲测需真实执行再登记。没有子代理授权时正常串行测试，不为独立性虚构评审者。

输出报告分别显示机械与语义结果、评审独立性；不得把自测称作盲测、跨 AI 验证或现实效果验证。

## 编译门槛

来源哈希匹配，来源核查 verified，卡片路径可读，评测报告 passed；本能力登记的所有用例通过并至少覆盖三类，测试绑定当前 bundle/card/source 内容。任何不满足即停止编译并保留草稿。

v1.1输出single总入口或pack总入口＋晋级入口，只有明确声明的卡片和文本资源进入产物；底本全文、任务记录、个人和客户资料不打包。安装不代表用户批准公开发布。

## 触发、盲任务准备与版本比较

```text
python scripts/ayou.py prepare-eval suite.json --out blind-tasks-v1 --mode output
python scripts/ayou.py prepare-eval trigger-suite.json --out trigger-tasks-v1 --mode trigger
python scripts/ayou.py trigger-score trigger-suite.json trigger-results.json --out trigger-report.json
python scripts/ayou.py benchmark without-report.json old-report.json new-report.json --out comparison.json
```

prepare-eval按稳定种子分train/validation，tasks.json只给prompt和候选description，不含期望/评分标准。private-key和原suite留给组织评测者，不能一起喂给执行者；调参不看验证集。工具准备任务不等于独立盲测已执行。

trigger-suite与output suite一样绑定bundle/card/resource哈希，增加`candidates`（name/description列表）；每case有id、prompt、expected_skill（候选name或none）。trigger-results登记reviewer、independent、suite_sha256、cases（id、output）；实际输出文件为JSON `selected_skill`。缺运行、误触发、兄弟混淆计失败，报告precision/recall/F1、accuracy和逐例结果，分母为全部用例。pack晋级能力要求通过绑定当前版本的正例与负例触发报告。

benchmark只比较同一批case ID的实际报告，逐例列出旧/新/无技能的通过与失败，不推断统计显著性、速度、token成本或业务收益。语义标准/原始输入应由评审者确认一致；真实测量缺失就标未知。格式工具测试的合成数据不能称为技能独立性能验证。

可用 `python scripts/ayou.py export-prompts suite.json --skill <技能名> --out test-prompts.json` 导出仓颉使用的should_trigger/should_not_trigger/edge_case测试提示格式。只是格式转换，未接通或实测darwin运行时，不声称已经自动进化；没有真实来源的预期也不会因导出变可靠。

局部试点写清覆盖几个能力、对应哪些原条目，其余去向是未纳入本轮；不能把一个成功试点称为全书完成。
