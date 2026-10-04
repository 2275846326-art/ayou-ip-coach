"""Build the IP-linked variant from the pure master without duplicating maintenance."""
import argparse
from pathlib import Path


LINK_SECTION = '''## IP 知识系统联动（默认收尾与反馈入口）

每次完成实质蒸馏、来源修订或能力修复，读取 [IP 知识系统联动](references/ip-system-integration.md)，对照现行方法与手册，交付 `ip-system-impact.md`：新增了什么、影响哪个模块、建议如何改、证据与测试、采用状态。尚在章节地图阶段只记录待分析；没有可用增量就说明原因，不凑系统更新。

蒸馏完成不等于系统已更新。先形成可审阅的增量与回归结果；沿用当前系统的负责人裁决、父版本校验和发布授权。来源原意、应用扩展、待验证假设分别进入相应状态，不因模型测试通过升级为经营规律。

系统使用中的失败、真实结果和边界反馈回到对应来源条目与能力：登记反例或候选 → 查原文及替代解释 → 修正适用条件/执行步骤 → 补回归 → 再提出系统增量。每个 IP 的私人事实与经验留在该 IP 档案，通用方法经裁决后进入共享底座。

'''


def build(pure, linked):
    pure, linked = Path(pure).resolve(), Path(linked).resolve()
    if pure == linked:
        raise ValueError('Two variants must have distinct roots')
    for rel in ('references/ip-system-integration.md', 'scripts/ip_system.py'):
        if not (linked/rel).is_file():
            raise ValueError(f'Linked overlay missing: {rel}')
    core = [p for p in pure.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    exceptions = {'SKILL.md', 'agents/openai.yaml', 'scripts/ayou.py'}
    for source in core:
        rel = source.relative_to(pure)
        if rel.as_posix() in exceptions:
            continue
        target = linked/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    text = (pure/'SKILL.md').read_text(encoding='utf-8')
    text = text.replace('name: ayou-distill\n', 'name: ayou-distill-ip-system\n', 1)
    start = text.index('description: ')
    end = text.index('\n', start)
    text = text[:start]+'description: 在六层蒸馏、来源核查和任务评测基础上，联动用户已有的 IP 知识系统：对照方法与手册提出可验证增量，按现行授权迭代，并把使用反馈带回蒸馏。用于“蒸馏后优化 IP 知识系统”“把新方法接入系统”“根据系统反馈修订蒸馏”；只需蒸馏材料时用 ayou-distill。'+text[end:]
    text = text.replace('# ayou 蒸馏', '# ayou 蒸馏 · IP 知识系统联动版', 1)
    text = text.replace('任务测试 → 交付。', '任务测试 → IP 知识系统增量 → 交付与反馈回流。')
    text = text.replace('本版本为纯蒸馏版，不默认启动 IP 知识系统迭代。用户要求联动系统时使用 `$ayou-distill-ip-system`；普通蒸馏沿用本入口。', '本版本默认衔接现有 IP 知识系统。共享 ayou-distill 的蒸馏核心，增加增量分析、正式采用与使用反馈回流；不会把蒸馏结论直接升级为系统规则。')
    text = text.replace('交付六层与审计记录即可。', '交付六层与审计记录，随后检查对 IP 知识系统的增量价值；无需为接入而强制生成独立技能。')
    text = text.replace('## 共同约束', LINK_SECTION+'## 共同约束')
    text = text.replace('  coverage.md ', '  ip-system-impact.md     # 系统影响、候选/无增量、采用状态与反馈入口\n  ip-system-plan.json     # 可选：来源与目标父文件的哈希基线\n  coverage.md ')
    text = text.replace('新产物不自动公开或传到云端。', '新产物不自动公开或传到云端；系统迭代沿用现行授权协议，已获本次完整流转授权时不重复询问推送。报告区分候选已生成、正式规则已写入、运行副本已同步、公开版已发布，各阶段须有实际文件或远端证据。')
    (linked/'SKILL.md').write_text(text, encoding='utf-8')
    text = (pure/'scripts/ayou.py').read_text(encoding='utf-8').replace('ROUTES = {', 'ROUTES = {\n    "ip-plan": ("ip_system.py", "plan"),\n    "ip-check": ("ip_system.py", "check"),')
    (linked/'scripts/ayou.py').write_text(text, encoding='utf-8')
    (linked/'agents/openai.yaml').write_text('''interface:
  display_name: "ayou 蒸馏 · IP 系统联动"
  short_description: "保留六层蒸馏与评测，并将知识增量衔接 IP 系统迭代和真实使用反馈"
  default_prompt: "使用 $ayou-distill-ip-system 蒸馏材料，对照现有 IP 知识系统提出可验证增量并按已有授权完成迭代。"
''', encoding='utf-8')
    for source in core:
        rel = source.relative_to(pure)
        if rel.as_posix() not in exceptions:
            if source.read_bytes() != (linked/rel).read_bytes():
                raise ValueError(f'Core mismatch: {rel}')
    print(f'Built both variants; {len(core)-len(exceptions)} shared files identical')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pure', type=Path, default=Path(__file__).resolve().parent.parent/'skills/ayou-distill')
    p.add_argument('--linked', type=Path, default=Path(__file__).resolve().parent.parent/'skills/ayou-distill-ip-system')
    a = p.parse_args(); build(a.pure, a.linked)
