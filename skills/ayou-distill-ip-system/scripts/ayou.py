"""Unified CLI. Semantic distillation remains the hosting AI's job."""
import json
import subprocess
import sys
from pathlib import Path

from bundle_tool import output_strategy, read

ROUTES = {
    "ip-plan": ("ip_system.py", "plan"),
    "ip-check": ("ip_system.py", "check"),
    "doctor": ("source_tools.py", "doctor"),
    "ingest": ("source_tools.py", "ingest"),
    "collection": ("source_tools.py", "collection"),
    "query": ("source_tools.py", "query"),
    "validate": ("bundle_tool.py", "validate"),
    "compile": ("bundle_tool.py", "compile"),
    "output-score": ("bundle_tool.py", "score"),
    "prepare-eval": ("eval_tools.py", "prepare"),
    "trigger-score": ("eval_tools.py", "trigger-score"),
    "benchmark": ("eval_tools.py", "benchmark"),
    "export-prompts": ("eval_tools.py", "export-prompts"),
    "update": ("lifecycle.py", "update"),
    "repair": ("lifecycle.py", "repair"),
    "patch": ("lifecycle.py", "patch"),
    "snapshot": ("lifecycle.py", "snapshot"),
    "rollback": ("lifecycle.py", "restore"),
    "verify-build": ("lifecycle.py", "verify-build"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in {"--help", "-h"}:
        print("ayou-distill 1.2.0\nCommands: " + ", ".join(ROUTES) + ", replan")
        print("Run a command with --help for parameters. No raw-source-to-skill automatic model execution.")
        return 0
    if sys.argv[1] == "replan":
        import argparse
        parser=argparse.ArgumentParser()
        parser.add_argument("bundle")
        parser.add_argument("--purpose",choices=["learning","reference","workflow","distribution"],default="reference")
        args=parser.parse_args(sys.argv[2:])
        print(json.dumps(output_strategy(read(args.bundle),"auto",args.purpose),ensure_ascii=False,indent=2))
        return 0
    if sys.argv[1] not in ROUTES:
        print("Unknown command")
        return 2
    script, command = ROUTES[sys.argv[1]]
    return subprocess.call([sys.executable,"-X","utf8",str(Path(__file__).parent/script),command,*sys.argv[2:]])


if __name__ == "__main__":
    raise SystemExit(main())
