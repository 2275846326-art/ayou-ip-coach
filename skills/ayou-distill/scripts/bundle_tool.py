"""ayou-distill: deterministic checks, scoring and router compilation. Stdlib only."""
import argparse
import hashlib
import json
import math
import os
import posixpath
import re
import tempfile
import urllib.parse
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix=".ayou-json-",dir=path.parent)
    with os.fdopen(descriptor,"w",encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(filename,path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(base, name):
    require(isinstance(name, str) and name.strip(), "Empty path")
    path = (base / name).resolve()
    require(path.is_relative_to(base.resolve()), f"Path outside working directory: {name}")
    return path


def bundle_check(path):
    path = Path(path).resolve()
    data, root = read(path), path.parent
    require(data.get("schema_version") == 1, "Unsupported schema_version")
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", data.get("name", "")), "Invalid name")
    require(len(data["name"]) <= 64, "Skill name exceeds 64 characters")
    require(isinstance(data.get("revision"), int) and data["revision"] > 0, "Invalid revision")
    require(bool(data.get("description", "").strip()), "Missing description")
    sources = {}
    for source in data.get("sources", []):
        sid = source["id"]
        require(sid not in sources, "Duplicate source ID")
        source_path = (root / source["path"]).resolve()
        require(source_path.is_file() and digest(source_path) == source["sha256"], f"Source changed/missing: {sid}")
        sources[sid] = source["sha256"]
    require(sources, "No sources")
    ids, cards = set(), {}
    require(data.get("capabilities"), "No capabilities")
    for cap in data["capabilities"]:
        require(cap["id"] not in ids, "Duplicate capability ID")
        ids.add(cap["id"])
        require(bool(cap.get("title", "").strip()), "Missing title")
        card = local(root, cap["card"])
        require(card.is_file() and card.read_text(encoding="utf-8").strip(), "Missing/empty card")
        require(cap["card"] not in cards, "Duplicate card path")
        cards[cap["card"]] = digest(card)
        require(cap.get("source_status") in ("verified", "needs_review"), "Invalid source status")
        require(cap.get("extension_status") in ("none", "proposed", "functional_tested"), "Invalid extension status")
        require(cap.get("test_status") in ("not_run", "failed", "passed"), "Invalid test status")
        require(cap.get("evidence"), "No evidence")
        for evidence in cap["evidence"]:
            require(evidence.get("source_id") in sources, "Unknown evidence source")
            require(all(isinstance(evidence.get(k), str) and evidence[k].strip() for k in ("location", "checked_on", "scope")), "Incomplete evidence")
    for cap in data["capabilities"]:
        require(set(cap.get("also_read", [])) <= ids - {cap["id"]}, "Unknown/self capability link")
        for resource in cap.get("resources", []):
            resource_path = local(root, resource)
            require(resource_path.is_file() and resource_path.suffix.lower() in {".md", ".txt", ".json", ".csv", ".py", ".yaml", ".yml"}, "Invalid declared text resource")
            resource_path.read_text(encoding="utf-8")
    for resource in data.get("book_resources", []):
        local(root, resource).read_text(encoding="utf-8")
    return data, cards, sources


def resource_hashes(data, root):
    return {name: digest(local(root, name)) for name in sorted(set(data.get("book_resources", [])) | {name for cap in data["capabilities"] for name in cap.get("resources", [])})}


def assertion_check(assertion, body, output):
    kind, value = assertion["type"], assertion.get("value")
    if kind == "contains":
        return value in body
    if kind == "not_contains":
        return value not in body
    if kind == "file_exists":
        return local(output.parent, assertion["path"]).is_file()
    require(kind in {"json_equals", "json_number", "json_unit"}, f"Unsupported assertion: {kind}")
    try:
        current = json.loads(body)
        for key in assertion["field"].split("."):
            current = current[key]
        if kind in {"json_equals", "json_unit"}:
            return current == value
        require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), "Invalid numeric expected value")
        tolerance = assertion.get("tolerance", 0)
        require(isinstance(tolerance, (int,float)) and tolerance >= 0 and math.isfinite(tolerance), "Invalid numeric tolerance")
        return isinstance(current, (int,float)) and not isinstance(current,bool) and math.isfinite(current) and abs(current-value) <= tolerance
    except (ValueError, KeyError, TypeError):
        return False


def score(suite_path, results_path, out):
    suite_path, results_path = Path(suite_path).resolve(), Path(results_path).resolve()
    suite, results = read(suite_path), read(results_path)
    bundle_path = (suite_path.parent / suite["bundle"]).resolve()
    data, cards, sources = bundle_check(bundle_path)
    require(digest(bundle_path) == suite["bundle_sha256"], "Tested bundle changed")
    require(cards == suite["card_sha256"], "Tested cards changed")
    resources = resource_hashes(data, bundle_path.parent)
    require(resources == suite.get("resource_sha256", {}), "Tested resources changed")
    require(results.get("suite_sha256") == digest(suite_path), "Results belong to another suite")
    require(isinstance(results.get("independent"), bool), "Declare review independence")
    require(bool(results.get("reviewer", "").strip()), "Missing reviewer")
    cases = suite["cases"]
    expected = [case["id"] for case in cases]
    require(expected and len(expected) == len(set(expected)), "Empty/duplicate suite cases")
    rows = results.get("cases", [])
    actual = [row["id"] for row in rows]
    require(len(actual) == len(set(actual)) and set(actual) <= set(expected), "Duplicate/unknown result ID")
    records, artifacts = [], {}
    by_id = {row["id"]: row for row in rows}
    for case in cases:
        require(case["kind"] in ("positive", "missing_input", "negative"), "Invalid case kind")
        require(case.get("prompt") and case.get("criteria"), "Missing case contract")
        row = by_id.get(case["id"])
        mechanical, semantic, reason = False, False, "Missing run"
        if row:
            output = local(bundle_path.parent, str((results_path.parent / row["output"]).resolve()))
            if output.is_file():
                body = output.read_text(encoding="utf-8")
                artifacts[str(output)] = digest(output)
                mechanical = bool(body.strip())
                for assertion in case.get("assertions", []):
                    check = assertion_check(assertion, body, output)
                    if assertion["type"] == "file_exists":
                        artifact = local(output.parent, assertion["path"])
                        if artifact.is_file():
                            artifacts[str(artifact)] = digest(artifact)
                    mechanical = mechanical and check
                require(isinstance(row.get("semantic_pass"), bool), "Missing semantic verdict")
                require(bool(row.get("reason", "").strip()), "Missing semantic reason")
                semantic, reason = row["semantic_pass"], row["reason"]
        records.append(dict(id=case["id"], kind=case["kind"], mechanical=mechanical, semantic=semantic, passed=mechanical and semantic, reason=reason))
    report = dict(passed=all(r["passed"] for r in records), passed_count=sum(r["passed"] for r in records), total=len(records), reviewer=results["reviewer"], independent=results["independent"], bundle_sha256=digest(bundle_path), card_sha256=cards, source_sha256=sources, resource_sha256=resources, cases=records, artifacts=artifacts, suite=str(suite_path), suite_sha256=digest(suite_path), results=str(results_path), results_sha256=digest(results_path))
    save(out, report)
    return report


def output_strategy(data, requested="auto", purpose="reference"):
    eligible = []
    for cap in data["capabilities"]:
        gate = cap.get("promotion", {})
        if all(gate.get(k) is True for k in ("independent_intent", "independent_contract", "independent_run")) and any(gate.get(k) is True for k in ("independent_reuse", "independent_eval")):
            require(bool(cap.get("trigger", "").strip()), "Promoted capability needs a distinct trigger")
            eligible.append(cap["id"])
    mode = requested if requested != "auto" else ("pack" if eligible and purpose in {"workflow", "distribution"} else "single")
    require(mode != "pack" or len(eligible) + 1 <= data.get("promotion_budget", 8), "Promotion budget exceeded; review packaging")
    return {"selected":mode,"promoted":eligible if mode == "pack" else [],"purpose":purpose,"reason":"Explicit mode or purpose plus declared promotion gate; single-first otherwise"}


def publish_tree(tree, destination, metadata):
    for filename,body in tree.items():
        if filename.endswith(".md"):
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)",body):
                target=target.strip().strip("<>").split("#",1)[0]
                if not target or urllib.parse.urlparse(target).scheme in {"http","https","mailto"}:
                    continue
                target=urllib.parse.unquote(target)
                resolved=posixpath.normpath(posixpath.join(posixpath.dirname(filename),target))
                require(resolved in tree,f"Unresolved relative link in {filename}: {target}")
    destination = Path(destination).resolve()
    require(not destination.exists(), "Output exists; use a new version directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / ("." + destination.name + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        staging = Path(tempfile.mkdtemp(prefix=".ayou-stage-", dir=destination.parent)).resolve()
        require(staging.is_relative_to(destination.parent), "Staging outside parent")
        for relative, body in tree.items():
            path = local(staging, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        save(staging / "BUILD_INFO.json", {**metadata,"files":{name:digest(local(staging,name)) for name in tree}})
        require(not destination.exists(), "Concurrent output already exists")
        staging.rename(destination)
    finally:
        lock.unlink(missing_ok=True)


def compile_router(bundle_path, destination, output="single", purpose="reference"):
    bundle_path, destination = Path(bundle_path).resolve(), Path(destination).resolve()
    data, cards, sources = bundle_check(bundle_path)
    require(not destination.exists(), "Output exists; use a new version directory")
    for cap in data["capabilities"]:
        require(cap["source_status"] == "verified" and cap["test_status"] == "passed", "Source or test gate not passed")
        require(cap["extension_status"] != "proposed", "Extension untested")
        report = read(local(bundle_path.parent, cap["evaluation"]))
        require(report["passed"] is True, "Evaluation failed")
        require(report["bundle_sha256"] == digest(bundle_path) and report["card_sha256"] == cards and report["source_sha256"] == sources, "Stale evaluation version")
        require(report.get("resource_sha256", {}) == resource_hashes(data, bundle_path.parent), "Resources changed since evaluation")
        for key in ("suite", "results"):
            recorded = local(bundle_path.parent, report[key])
            require(recorded.is_file() and digest(recorded) == report[key + "_sha256"], "Evaluation record changed")
        require(report.get("artifacts"), "No actual outputs")
        for filename, sha in report["artifacts"].items():
            artifact = local(bundle_path.parent, filename)
            require(artifact.is_file() and digest(artifact) == sha, "Evaluated output changed")
        selected = [r for r in report["cases"] if r["id"] in cap["case_ids"]]
        require(cap["case_ids"] and len(set(cap["case_ids"])) == len(cap["case_ids"]) == len(selected), "Missing/duplicate capability cases")
        require(all(r["passed"] for r in selected), "Capability case failed")
        require({r["kind"] for r in selected} >= {"positive", "missing_input", "negative"}, "Missing coverage kind")
    tree = {}
    strategy = output_strategy(data, output, purpose)
    if strategy["promoted"]:
        require(bool(data.get("router_description", "").strip()), "Pack needs distinct router_description")
        for index, cap in enumerate(data["capabilities"], 1):
            if cap["id"] not in strategy["promoted"]:
                continue
            trigger = read(local(bundle_path.parent, cap.get("trigger_evaluation", "")))
            require(trigger.get("passed") is True and trigger.get("bundle_sha256") == digest(bundle_path), "Promoted trigger tests absent/stale/failed")
            require(trigger.get("card_sha256") == cards and trigger.get("source_sha256") == sources and trigger.get("resource_sha256",{}) == resource_hashes(data,bundle_path.parent), "Trigger evidence changed")
            slug = data["name"] + "-cap-" + str(index)
            require(len(slug)<=64,"Promoted skill name exceeds 64 characters")
            require(any(row["expected"] == slug and row["passed"] for row in trigger["cases"]) and any(row["expected"] != slug and row["passed"] for row in trigger["cases"]), "Promoted trigger positive/negative coverage missing")
            for key in ("suite","results"):
                require(digest(local(bundle_path.parent,trigger[key])) == trigger[key+"_sha256"], "Trigger record changed")
            require(trigger.get("artifacts"), "Trigger actual outputs missing")
            for filename, sha in trigger["artifacts"].items():
                require(digest(local(bundle_path.parent, filename)) == sha, "Trigger output changed")
    prefix = data["name"] + "/" if strategy["selected"] == "pack" else ""
    description=data["router_description"] if strategy["promoted"] else data["description"]
    lines = ["---", f"name: {data['name']}", "description: " + json.dumps(description, ensure_ascii=False), "---", "", f"# {data['name']}", "", "按用户任务选择下列能力，读取卡片后执行；缺必需输入先补问，不扩大来源和验证范围。", "", "这些能力经过来源核查与功能任务测试；不代表现实业务效果或独立盲测已验证。", ""]
    card_names = {cap["id"]:f"cards/capability-{i}.md" for i,cap in enumerate(data["capabilities"],1)}
    destinations = {}
    for index, cap in enumerate(data["capabilities"], 1):
        filename = f"cards/capability-{index}.md"
        body = local(bundle_path.parent, cap["card"]).read_text(encoding="utf-8")
        links = [f"- [{other}]({Path(card_names[other]).name})" for other in cap.get("also_read", [])]
        if links:
            body += "\n\n## 关联能力\n\n" + "\n".join(links) + "\n"
        for ri, resource in enumerate(cap.get("resources", []), 1):
            target = f"resources/cap-{index}-{ri}" + Path(resource).suffix
            tree[prefix+target] = local(bundle_path.parent,resource).read_text(encoding="utf-8")
            body += f"\n配套资源：[{Path(resource).name}](../{target})。仅随包复制，不自动执行。\n"
        tree[prefix+filename] = body
        if cap["id"] in strategy["promoted"]:
            slug = data["name"] + "-cap-" + str(index)
            description = json.dumps(cap["trigger"],ensure_ascii=False)
            tree[f"{slug}/SKILL.md"] = f"---\nname: {slug}\ndescription: {description}\n---\n\n# {cap['title']}\n\n" + f"读取[能力正文](../{prefix}{filename})执行。来源总入口为[这里](../{prefix}SKILL.md)。\n"
            lines.append(f"- [{cap['title']}](../{slug}/SKILL.md)：{cap['trigger']}")
            destinations[cap["id"]] = {"promoted_to":slug}
        else:
            lines.append(f"- [{cap['title']}]({filename})：{cap.get('trigger',cap['title'])}")
            destinations[cap["id"]] = {"served_by":data["name"]}
    for index, resource in enumerate(data.get("book_resources", []),1):
        target = f"references/book-{index}" + Path(resource).suffix
        tree[prefix+target] = local(bundle_path.parent,resource).read_text(encoding="utf-8")
        lines.append(f"- [共享参考：{Path(resource).name}]({target})")
    tree[prefix+"SKILL.md"] = "\n".join(lines) + "\n"
    tree[prefix+"CHEATSHEET.md"] = "# 能力速查\n\n" + "\n".join(f"- {cap['title']}：{cap.get('one_liner',cap.get('trigger',cap['title']))}" for cap in data["capabilities"]) + "\n"
    tree["destinations.json"] = json.dumps(destinations,ensure_ascii=False,indent=2)
    publish_tree(tree,destination,dict(revision=data["revision"],bundle_sha256=digest(bundle_path),strategy=strategy))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate")
    p.add_argument("bundle")
    p = sub.add_parser("score")
    p.add_argument("suite")
    p.add_argument("results")
    p.add_argument("--out", required=True)
    p = sub.add_parser("compile")
    p.add_argument("bundle")
    p.add_argument("--out", required=True)
    p.add_argument("--output", choices=["single","pack","auto"], default="single")
    p.add_argument("--purpose", choices=["learning","reference","workflow","distribution"], default="reference")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            bundle_check(args.bundle)
        elif args.command == "score":
            report = score(args.suite, args.results, args.out)
            print(f"{report['passed_count']}/{report['total']} cases passed; independent={report['independent']}")
            return 0 if report["passed"] else 1
        else:
            compile_router(args.bundle, args.out,args.output,args.purpose)
        print("PASS")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"FAIL: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
