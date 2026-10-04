"""Blind task preparation, trigger scoring and paired report comparison."""
import argparse
import hashlib
import json
from pathlib import Path

from bundle_tool import bundle_check, digest, local, read, require, resource_hashes, save


def prepare(suite_path, out, mode="output"):
    suite_path=Path(suite_path).resolve()
    suite=read(suite_path)
    require(not Path(out).exists(),"Use a new preparation directory")
    cases=suite["cases"]
    ids=[case["id"] for case in cases]
    require(ids and len(ids)==len(set(ids)),"Duplicate/empty test cases")
    # Stable hash ranking gives a deterministic split; no expected labels enter blind tasks.
    ranked=sorted(ids,key=lambda value:hashlib.sha256(("ayou-v1:"+value).encode()).hexdigest())
    count=max(1,min(len(ids)-1,round(len(ids)*0.6))) if len(ids)>1 else 1
    train=set(ranked[:count])
    tasks=[{"id":case["id"],"prompt":case["prompt"],"set":"train" if case["id"] in train else "validation","candidates":suite.get("candidates",[])} for case in cases]
    save(Path(out)/"tasks.json",{"mode":mode,"suite_sha256":digest(suite_path),"tasks":tasks})
    save(Path(out)/"private-key.json",{"suite":str(suite_path),"train":sorted(train),"validation":sorted(set(ids)-train)})
    return {"tasks":len(tasks),"train":len(train),"validation":len(ids)-len(train),"note":"Keep private-key and original suite from the evaluator; validation runs remain separate from tuning"}


def trigger_score(suite_path, results_path, out):
    suite_path,results_path=Path(suite_path).resolve(),Path(results_path).resolve()
    suite,results=read(suite_path),read(results_path)
    bundle_path=(suite_path.parent/suite["bundle"]).resolve()
    data,cards,sources=bundle_check(bundle_path)
    require(suite["bundle_sha256"]==digest(bundle_path) and suite["card_sha256"]==cards,"Trigger suite version changed")
    resources=resource_hashes(data,bundle_path.parent)
    require(resources==suite.get("resource_sha256",{}),"Trigger resources changed")
    require(results.get("suite_sha256")==digest(suite_path),"Results belong to another suite")
    require(isinstance(results.get("independent"),bool) and results.get("reviewer"),"Declare trigger review scope")
    cases=suite["cases"]
    ids=[case["id"] for case in cases]
    require(ids and len(ids)==len(set(ids)),"Duplicate/empty trigger IDs")
    rows=results.get("cases",[])
    actual_ids=[row["id"] for row in rows]
    require(len(actual_ids)==len(set(actual_ids)) and set(actual_ids)<=set(ids),"Duplicate/unknown trigger result")
    allowed={candidate["name"] for candidate in suite["candidates"]}|{"none"}
    by_id={row["id"]:row for row in rows}
    records,artifacts=[],{}
    tp=fp=fn=correct=missing=0
    for case in cases:
        expected=case["expected_skill"]
        require(expected in allowed and case.get("prompt"),"Invalid trigger contract")
        row=by_id.get(case["id"])
        selected=None
        if row:
            path=local(bundle_path.parent,str((results_path.parent/row["output"]).resolve()))
            if path.is_file():
                response=read(path)
                selected=response.get("selected_skill")
                require(selected in allowed,"Unknown selected skill")
                artifacts[str(path)]=digest(path)
        match=selected is not None and selected==expected
        correct+=match
        if selected is None: missing+=1
        if match and expected!="none": tp+=1
        if selected is not None and selected!="none" and not match: fp+=1
        if expected!="none" and not match: fn+=1
        records.append({"id":case["id"],"expected":expected,"selected":selected,"passed":match})
    report={"passed":correct==len(cases),"passed_count":correct,"total":len(cases),"missing":missing,"precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn) if tp+fn else None,"f1":2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,"accuracy":correct/len(cases),"cases":records,"artifacts":artifacts,"reviewer":results["reviewer"],"independent":results["independent"],"bundle_sha256":digest(bundle_path),"card_sha256":cards,"source_sha256":sources,"resource_sha256":resources,"suite":str(suite_path),"suite_sha256":digest(suite_path),"results":str(results_path),"results_sha256":digest(results_path)}
    save(out,report)
    return report


def benchmark(report_paths,out):
    reports=[read(path) for path in report_paths]
    require(len(reports)>=2,"Provide at least two variant reports")
    first_ids={row["id"] for row in reports[0]["cases"]}
    require(all({row["id"] for row in report["cases"]}==first_ids for report in reports),"Benchmarks need the same case IDs")
    rows=[]
    for path,report in zip(report_paths,reports):
        require(report["total"]==len(first_ids),"Inconsistent report denominator")
        rows.append({"variant":Path(path).stem,"passed":report["passed_count"],"total":report["total"],"rate":report["passed_count"]/report["total"],"independent":report["independent"],"sha256":digest(path)})
    compared={"variants":rows,"paired_changes":[{"id":cid,"passed":[next(row["passed"] for row in report["cases"] if row["id"]==cid) for report in reports]} for cid in sorted(first_ids)],"claim":"Descriptive comparison only. Case difficulty, true input equivalence, timing and token usage require actual measurement; no statistical or business superiority asserted."}
    save(out,compared)
    return compared


def export_prompts(suite_path, skill, out):
    suite=read(suite_path)
    cases=[]
    for case in suite["cases"]:
        if "expected_skill" in case:
            kind="should_trigger" if case["expected_skill"]==skill else "should_not_trigger"
            expectation="Select " + case["expected_skill"]
        else:
            kind={"positive":"should_trigger","negative":"should_not_trigger","missing_input":"edge_case"}[case["kind"]]
            expectation="; ".join(case["criteria"])
        cases.append({"id":case["id"],"type":kind,"prompt":case["prompt"],"expected_behavior":expectation,"notes":"Exported from ayou source suite; semantic thresholds remain its evaluator's responsibility"})
    result={"skill":skill,"version":"1.1.0","test_cases":cases,"minimum_pass_rate":1.0,"format":"cangjie test-prompts style","notes":"Format export only; not tested against an installed darwin runtime"}
    save(out,result)
    return {"exported":len(cases),"darwin_runtime_verified":False}


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("prepare");p.add_argument("suite");p.add_argument("--out",required=True);p.add_argument("--mode",choices=["trigger","output"],default="output")
    p=sub.add_parser("trigger-score");p.add_argument("suite");p.add_argument("results");p.add_argument("--out",required=True)
    p=sub.add_parser("benchmark");p.add_argument("reports",nargs="+");p.add_argument("--out",required=True)
    p=sub.add_parser("export-prompts");p.add_argument("suite");p.add_argument("--skill",required=True);p.add_argument("--out",required=True)
    args=parser.parse_args()
    try:
        if args.command=="prepare": result=prepare(args.suite,args.out,args.mode)
        elif args.command=="trigger-score": result=trigger_score(args.suite,args.results,args.out)
        elif args.command=="benchmark": result=benchmark(args.reports,args.out)
        else: result=export_prompts(args.suite,args.skill,args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get("passed",True) else 1
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(f"FAIL: {error}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
