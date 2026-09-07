"""Summarise observed control transitions and accounting without grading prose."""
import json
from collections import Counter
from pathlib import Path
p=Path(__file__).parent/'evidence'
b=json.loads((p/'baseline.json').read_text());s=json.loads((p/'workspace/state.json').read_text())
ev=[json.loads(x) for x in (p/'events.jsonl').read_text().splitlines()]
rows=[json.loads(x) for x in (p/'results.jsonl').read_text().splitlines()]
old=set(b['ledger']['entries']); entries=[v for k,v in s['ledger']['entries'].items() if k not in old]
report={'events':dict(Counter(x['kind'] for x in ev)),
 'steps':[{k:r.get(k) for k in ['status','invitation','mode','occurrence']} for r in rows],
 'additional_charged':sum(x['charged_tokens'] for x in entries),
 'observed_input':sum((x.get('usage') or {}).get('input_tokens') or 0 for x in entries),
 'observed_output':sum((x.get('usage') or {}).get('output_tokens') or 0 for x in entries),
 'unknown_calls':sum(bool(x.get('unknown')) for x in entries),
 'accounts':[{'before':{k:a.get(k) for k in ['method_revision','focus_revision','uses','phase']},'after':{k:c.get(k) for k in ['method_revision','focus_revision','uses','phase']}} for a,c in zip(b['accounts'],s['accounts'])],
 'bindings':len(s['bindings']),'dependency_queue':s['dependency_queue'],'notices':s['notices'][len(b['notices']):]}
(p/'analysis.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
