"""Record/check an IP knowledge-system change baseline; never adopt or apply it."""
import argparse
import json
from pathlib import Path

from bundle_tool import digest, local, read, require, save


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f'Missing {label}')


def file_record(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), f'Not a file: {path}')
    return {'path': str(path), 'sha256': digest(path)}


def plan(request, root, out):
    root = Path(root).resolve(strict=True)
    require(root.is_dir(), 'System root must be a directory')
    require(not Path(out).exists(), 'Plan already exists; choose a new version')
    data = read(request)
    for field in ('delta_id', 'distillation_ref'):
        nonempty(data.get(field), field)
    require(Path(data['distillation_ref']).is_absolute(), 'Use absolute distillation_ref')
    distillation = file_record(data['distillation_ref'])
    sources = data.get('sources')
    changes = data.get('changes')
    require(isinstance(sources, list) and bool(sources), 'Sources are required')
    require(isinstance(changes, list) and bool(changes), 'Changes are required')
    source_records = []
    for source in sources:
        nonempty(source.get('path'), 'source.path')
        require(Path(source['path']).is_absolute(), 'Use absolute source paths')
        nonempty(source.get('location'), 'source.location')
        require(source.get('source_status') in {'verified', 'needs_review'}, 'Bad source_status')
        source_records.append({**source, **file_record(source['path'])})
    targets = {}
    for change in changes:
        for field in ('target', 'section', 'before', 'after'):
            nonempty(change.get(field), field)
        require(change.get('change_type') in {'add', 'boundary', 'execution', 'conflict'}, 'Bad change_type')
        require(change.get('evidence_kind') in {'original', 'application', 'hypothesis'}, 'Bad evidence_kind')
        indexes = change.get('source_indexes')
        require(isinstance(indexes, list) and bool(indexes), 'Each change needs source_indexes')
        require(all(type(i) is int and 0 <= i < len(sources) for i in indexes), 'Bad source_indexes')
        cases = change.get('regressions')
        require(isinstance(cases, list) and bool(cases), 'Regression tasks are required')
        for case in cases:
            nonempty(case, 'regression task')
        path = local(root, change['target'])
        # local() confines resolved paths; rejecting the absolute input also keeps
        # this manifest portable inside the specified authoritative root.
        require(not Path(change['target']).is_absolute(), 'Target must be relative')
        require(path.is_file(), f'Target missing: {path}')
        actual = path.read_text(encoding='utf-8-sig')
        require(change['before'] in actual, f'Before text is not in target: {path}')
        require(change['before'] != change['after'], 'No-op change')
        require(change['after'] not in actual, 'Proposed text already exists; review duplicates')
        targets[change['target']] = file_record(path)
    protected = {Path(item['path']) for item in [distillation, *source_records, *targets.values()]}
    require(Path(out).resolve() not in protected, 'Output would overwrite an input')
    result = {
        'schema_version': 1, 'delta_id': data['delta_id'], 'status': 'candidate',
        'system_root': str(root), 'distillation': distillation,
        'sources': source_records, 'targets': targets, 'changes': changes,
        'semantic_verified_by_tool': False, 'tests_passed_by_tool': False,
        'authorization_verified_by_tool': False, 'system_modified': False,
    }
    save(out, result)
    return result


def check(plan_path):
    data = read(plan_path)
    require(data.get('schema_version') == 1 and data.get('status') == 'candidate', 'Not a candidate baseline')
    root = Path(data['system_root']).resolve(strict=True)
    records = [data['distillation'], *data['sources']]
    for name, record in data['targets'].items():
        require(local(root, name) == Path(record['path']).resolve(), 'Target path changed')
        records.append(record)
    for record in records:
        require(Path(record['path']).is_file(), f'Missing file: {record["path"]}')
        require(digest(record['path']) == record['sha256'], f'Baseline drift: {record["path"]}')
    return {'baseline_unchanged': True, 'status': 'candidate', 'system_modified': False,
            'semantic_verified_by_tool': False, 'tests_passed_by_tool': False,
            'authorization_verified_by_tool': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('plan')
    p.add_argument('request'); p.add_argument('--root', required=True); p.add_argument('--out', required=True)
    p = commands.add_parser('check'); p.add_argument('plan')
    args = parser.parse_args()
    try:
        result = plan(args.request, args.root, args.out) if args.command == 'plan' else check(args.plan)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error), 'system_modified': False}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
