# 增量、失败修复与可恢复版本

## 统一命令

```text
python scripts/ayou.py update bundle.json old/chunks.json new/chunks.json --source-id src-main --out update-plan.json
python scripts/ayou.py repair bundle.json failure-case.json --out repair-run-v2
python scripts/ayou.py patch <旧工作目录> patch.json --out <新版本工作目录>
python scripts/ayou.py snapshot <目标目录> --out <外部快照新目录>
python scripts/ayou.py rollback <快照目录> --out <恢复新目录>
python scripts/ayou.py verify-build <编译目录>
```

update只生成差异与影响计划，AI随后判断新增/修正/矛盾。`source_id`是Bundle证据ID；不要直接把预处理自动ID当成它，两者在source-register映射。旧源新版单独登记，不移除其他来源；没有精确chunk映射时按整份来源保守核查。`also_read`邻近能力进入回归范围。来源支持改变需重置source_status/test_status；没有改变则保留不受影响能力内容，但测试报告绑定整个Bundle，新编译仍需产生匹配版本的报告。

失败case格式：capability_id、prompt、actual、expected、severity（critical/major/minor），可附真实日志。拿不到执行轨迹时actual写unavailable，不能用猜测填充。repair保留卡片与Bundle快照并生成诊断任务，区分触发、来源、执行、边界、预处理、评测错误；不是自动模型修复。

patch.json：`expected_sha256`（相对路径→父文件哈希）、`changes`（同一相对路径→新UTF-8正文）、`bundle`（默认bundle.json）。输出到新的兄弟版本目录，旧目录不变；检查父版本、路径和新Bundle结构，失败保留未发布staging供诊断。新增文件先在候选版本建立，再登记预期哈希，不用该补丁命令偷偷扩展范围。

修复最小影响范围，补语义邻近负例，再跑失败案例、能力与相邻能力回归。禁止只把一个失败案例的专有名词塞进触发词过拟合。

## 快照与回滚

快照放目标目录外，逐文件哈希；拒绝符号链接，不复制.git与Python缓存。恢复仅输出新目录，不删除或覆盖当前版本。恢复是内容恢复，不等于评测继续有效：修正版本、来源/报告路径后重新校验和测试，才能再次编译。工作状态中记录恢复自哪个版本，不倒退版本号。

编译和补丁都先写独立staging，检查后再发布新目录。BUILD_INFO保存生成文件哈希；verify-build可以发现手改、新增、缺文件。手改应回到能力源，不直接改生成目录来绕过评测。

v1.1尚不支持原地自动热更新或自动修复模型；这两个行为不应出现在完成声明里。跨设备状态同步仍按当前项目协议执行。
