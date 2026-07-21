"""Create a conservative generic sequence plan from a concrete ASG JSON file."""
from __future__ import annotations
import argparse
from pathlib import Path
from qulab.sequence_generation.migration import write_sequence_plan_from_template

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template"); parser.add_argument("--resource",default="asg"); parser.add_argument("--plan-id",default="imported_sequence")
    parser.add_argument("--output",required=True); parser.add_argument("--project-root",default="."); parser.add_argument("--force",action="store_true")
    args=parser.parse_args(argv)
    path=write_sequence_plan_from_template(args.template,args.output,resource=args.resource,plan_id=args.plan_id,
                                           project_root=Path(args.project_root),force=args.force)
    print(path); return 0
if __name__ == "__main__": raise SystemExit(main())
