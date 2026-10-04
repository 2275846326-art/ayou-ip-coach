"""Reviewable source diffs, immutable snapshots, repair tasks and version previews."""
import argparse
import difflib
import json
import os
import shutil
import tempfile
from pathlib import Path

from bundle_tool import bundle_check, digest, local, read, require, save


def tree_hashes(root):
    root = Path(root).resolve()
    files = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Snapshot cannot follow symlinks")
        if path.is_file() and not any(part in {".git", "__pycache__"} for part in path.relative_to(root).parts):
            files[path.relative_to(root).as_posix()] = digest(path)
    require(files, "Empty snapshot target")
    return files


def snapshot(target, out):
    target, out = Path(target).resolve(), Path(out).resolve()
    require(target.is_dir() and not out.exists() and not out.is_relative_to(target), "Snapshot needs a new directory outside target")
    manifest = tree_hashes(target)
    require("SNAPSHOT.json" not in manifest, "Do not snapshot a snapshot container")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ayou-snapshot-", dir=out.parent)).resolve()
    require(staging.is_relative_to(out.parent), "Invalid staging parent")
    for filename, sha in manifest.items():
        src, dst = local(target,filename), local(staging,filename)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src,dst)
        require(digest(dst) == sha, "File changed during snapshot")
    require(tree_hashes(target) == manifest, "Target changed during snapshot")
    save(staging / "SNAPSHOT.json", {"origin":str(target),"files":manifest})
    require(not out.exists(), "Snapshot destination changed")
    staging.rename(out)
    return {"snapshot":str(out),"files":len(manifest)}


def restore(snap, out):
    snap, out = Path(snap).resolve(), Path(out).resolve()
    manifest = read(snap / "SNAPSHOT.json")
    require(not out.exists() and not out.is_relative_to(snap), "Restore into a new directory outside snapshot")
    actual = tree_hashes(snap)
    actual.pop("SNAPSHOT.json",None)
    require(actual == manifest["files"], "Snapshot edited or incomplete")
    out.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ayou-restore-",dir=out.parent)).resolve()
    require(staging.is_relative_to(out.parent),"Invalid restore staging")
    for filename, sha in manifest["files"].items():
        src,dst=local(snap,filename),local(staging,filename)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst)
        require(digest(dst) == sha,"Snapshot changed during restore")
    save(staging / "RESTORE_INFO.json",{"snapshot":str(snap),"content_status":"restored for review; source and evaluation paths must be rebound before compile"})
    require(not out.exists(),"Restore destination changed")
    staging.rename(out)
    return {"restored":str(out),"files":len(manifest["files"])}


def verify_build(target):
    target=Path(target).resolve()
    build=read(target/"BUILD_INFO.json")
    actual=tree_hashes(target)
    actual.pop("BUILD_INFO.json",None)
    return {"clean":actual==build["files"],"changed":[name for name in set(actual)|set(build["files"]) if actual.get(name)!=build["files"].get(name)]}


def update_plan(bundle, old_chunks, new_chunks, source_id, out):
    # Read the old bundle without asserting old source hash: detecting that change is this command's job.
    data,old,new=read(bundle),read(old_chunks),read(new_chunks)
    require(source_id in {source["id"] for source in data["sources"]},"Unknown Bundle source ID")
    old_hashes,new_hashes=[x["content_hash"] for x in old],[x["content_hash"] for x in new]
    changes=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(a=old_hashes,b=new_hashes,autojunk=False).get_opcodes():
        if tag != "equal":
            changes.append({"type":tag,"old":old[a:b],"new":new[c:d]})
    changed={x["chunk_id"] for change in changes for x in change["old"]}
    affected=set()
    for cap in data["capabilities"]:
        for ev in cap["evidence"]:
            if ev["source_id"] == source_id and changes:
                if not ev.get("chunk_ids") or changed & set(ev["chunk_ids"]):
                    affected.add(cap["id"])
    # Deletion/reordering/addition can change interpretation; broad source mapping is conservative.
    if changes:
        affected.update(cap["id"] for cap in data["capabilities"] if any(ev["source_id"]==source_id and not ev.get("chunk_ids") for ev in cap["evidence"]))
    neighbors=set(affected)
    while True:
        expanded=neighbors | {other for cap in data["capabilities"] if cap["id"] in neighbors for other in cap.get("also_read",[])} | {cap["id"] for cap in data["capabilities"] if neighbors & set(cap.get("also_read",[]))}
        if expanded==neighbors: break
        neighbors=expanded
    report={"source_id":source_id,"old_chunks_sha256":digest(old_chunks),"new_chunks_sha256":digest(new_chunks),"changed":bool(changes),"changes":changes,"directly_affected":sorted(affected),"regression_scope":sorted(neighbors),"semantic_tasks":["Classify addition/correction/contradiction; retain sources separately", "Recheck affected evidence and update statuses to needs_review/not_run", "Review glossary, source router and neighboring trigger cases", "Re-run relevant tests and compile to a new version"],"mutates_bundle":False}
    save(out,report)
    return report


def repair(bundle, failure, out):
    data,case=read(bundle),read(failure)
    require(case.get("capability_id") in {c["id"] for c in data["capabilities"]},"Unknown repair capability")
    require(all(isinstance(case.get(k),str) and case[k].strip() for k in ("prompt","actual","expected","severity")),"Incomplete failure case")
    require(case["severity"] in {"critical","major","minor"},"Invalid severity")
    root=Path(out).resolve()
    require(not root.exists(),"Repair run exists")
    root.mkdir(parents=True)
    # Bundle and cards are snapshotted without raw sources or model trace fabrication.
    files={Path(bundle).name:digest(bundle)}
    for cap in data["capabilities"]:
        files[cap["card"]]=digest(local(Path(bundle).resolve().parent,cap["card"]))
    for filename,sha in files.items():
        dst=local(root/"before",filename)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(local(Path(bundle).resolve().parent,filename),dst)
        require(digest(dst)==sha,"Repair snapshot changed")
    task={"failure":case,"before_sha256":files,"diagnosis_options":["activation_miss","false_activation","source_gap","execution_gap","boundary_gap","preprocessing_gap","eval_gap"],"steps":["Reproduce from actual inputs; unavailable trace remains unavailable", "Locate whether preprocessing, source, execution or evaluation failed", "Create minimal versioned patch; never replace source with invented facts", "Add a neighboring negative case and run failure, capability and neighbor regressions"],"status":"pending_agent_diagnosis"}
    save(root/"repair-task.json",task)
    return task


def patch_preview(target, patch_file, out):
    target,out=Path(target).resolve(),Path(out).resolve()
    patch=read(patch_file)
    require(not out.exists() and not out.is_relative_to(target),"Patch needs a new sibling directory")
    for filename,sha in patch["expected_sha256"].items():
        require(digest(local(target,filename))==sha,"Patch parent changed")
    require(patch["changes"] and set(patch["changes"]) <= set(patch["expected_sha256"]),"Every edited file needs its expected parent hash")
    tree_hashes(target) # Reject symlink traversal before copying.
    out.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=".ayou-patch-",dir=out.parent)).resolve()
    require(stage.is_relative_to(out.parent),"Patch staging escaped parent")
    shutil.copytree(target,stage,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.git'))
    for filename,body in patch["changes"].items():
        require(isinstance(body,str),"Patch body must be UTF-8 text")
        local(stage,filename).write_text(body,encoding="utf-8")
    # Structural/source validation only; changed-card eval is stale by design until rerun.
    bundle_check(stage/patch.get("bundle","bundle.json"))
    for filename,sha in patch["expected_sha256"].items():
        require(digest(local(target,filename))==sha,"Patch target changed during preview")
    save(stage/"PATCH_INFO.json",{"parent":str(target),"changed":list(patch["changes"]),"tests":"must rerun before compile"})
    require(not out.exists(),"Patch destination changed")
    stage.rename(out)
    return {"preview":str(out),"original_untouched":True}


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("snapshot","restore"):
        p=sub.add_parser(name);p.add_argument("target");p.add_argument("--out",required=True)
    p=sub.add_parser("verify-build");p.add_argument("target")
    p=sub.add_parser("update");p.add_argument("bundle");p.add_argument("old_chunks");p.add_argument("new_chunks");p.add_argument("--source-id",required=True);p.add_argument("--out",required=True)
    p=sub.add_parser("repair");p.add_argument("bundle");p.add_argument("failure");p.add_argument("--out",required=True)
    p=sub.add_parser("patch");p.add_argument("target");p.add_argument("patch");p.add_argument("--out",required=True)
    args=parser.parse_args()
    try:
        if args.command=="snapshot": result=snapshot(args.target,args.out)
        elif args.command=="restore": result=restore(args.target,args.out)
        elif args.command=="verify-build": result=verify_build(args.target)
        elif args.command=="update": result=update_plan(args.bundle,args.old_chunks,args.new_chunks,args.source_id,args.out)
        elif args.command=="repair": result=repair(args.bundle,args.failure,args.out)
        else: result=patch_preview(args.target,args.patch,args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get("clean",True) else 1
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(f"FAIL: {error}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
