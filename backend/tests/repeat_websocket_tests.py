"""Bounded subprocess repetitions of the previously stalled reconnect tests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

TESTS = [
    'backend/tests/test_foundation.py::test_sync_privacy_multitab_disconnect_and_reconnect',
    'backend/tests/test_campaign.py::test_ten_crisis_multiplayer_campaign_with_ties_privacy_reconnect_and_once_only',
]


def repeat(output, runs, timeout):
    output.mkdir(exist_ok=False)
    results=[]
    for index in range(runs):
        command=[sys.executable,'-m','pytest',*TESTS,'-vv','-o','faulthandler_timeout=3']
        try:
            process=subprocess.run(command,cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
            log=process.stdout
            status='success' if process.returncode==0 else 'failure'
        except subprocess.TimeoutExpired as error:
            log=error.stdout or b''; status='timeout'
        (output/f'run-{index+1}.log').write_bytes(log)
        results.append({'run':index+1,'status':status,'tests':TESTS,'timeout_seconds':timeout})
        (output/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({status:sum(row['status']==status for row in results) for status in ['success','failure','timeout']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=10)
    parser.add_argument('--timeout',type=float,default=7)
    args=parser.parse_args()
    if args.runs<1 or args.timeout<=0:parser.error('Positive runs/timeout required')
    repeat(args.output,args.runs,args.timeout)
