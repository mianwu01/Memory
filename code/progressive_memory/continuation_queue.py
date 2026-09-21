"""Run the pre-registered, bounded development checks once the fixed data finish."""
import json
from pathlib import Path
import subprocess
import sys
import time

base=Path('results/development/progressive_search');dev=base/'dev_v2'
while not (dev/'reader_gate.json').exists():time.sleep(10)
print('actor_gate_ready',flush=True)
fit=base/'discovery_dev'
if not (fit/'fit.json').exists():
    subprocess.run([sys.executable,'-u','-B','-m','progressive_memory.discovery','--dev',str(dev),'--training',str(dev),'--scope','development_in_sample','--out',str(fit)],check=True)
from .discovery import load_projection,trajectories
from .selection import selections
from .runtime import save
projection=load_projection(fit/'projection.pkl');graph=json.loads((fit/'fit.json').read_text())['primary']['adjacency']
plans=[selections(tr,projection,graph) for tr in trajectories(dev,0,10)]
identical={control:sum(p['methods']['discovered']['prompt_sha256']==p['methods'][control]['prompt_sha256'] for p in plans) for control in ['complete','topic_only']}
gate=json.loads((dev/'reader_gate.json').read_text())
stop=any(n==10 for n in identical.values())
save(base/'development_structure_gate.json',dict(actor_passed=gate['passed'],identical_inputs=identical,stop_structure_claim=stop,expand_to_train_test=gate['passed'] and not stop))
print('structure_gate',json.dumps(dict(actor=gate['passed'],identical=identical,stop=stop)),flush=True)
# Both branches finish the fixed dev diagnostics. Formal train/test still requires
# review of the observable-state validity and the predeclared structural gate.
subprocess.run([sys.executable,'-u','-B','-m','progressive_memory.evaluate','--trajectories',str(dev),'--discovery',str(fit),'--out',str(base/'evaluation_dev')],check=True)
subprocess.run([sys.executable,'-u','-B','-m','progressive_memory.audit','--trajectories',str(dev),'--evaluation',str(base/'evaluation_dev'),'--out',str(base/'audit_dev'),'--index','/tmp/hm3-progressive-search-20260922.sqlite'],check=True)
print('development_discovery_and_audit_done',flush=True)
