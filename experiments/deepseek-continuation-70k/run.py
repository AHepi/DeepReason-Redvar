"""Continue a saved inquiry with 70,000 additional charged token units.

Usage: OLLAMA_API_KEY in environment; python run.py BASELINE NEW_OUTPUT
No policy changes except the additional expenditure envelope. Records actual
requests, replies and host events independently of participant-visible history.
"""
import json, sys, time, shutil
from pathlib import Path
from open_inquiry.engine import Engine
from open_inquiry.providers import OllamaProvider
from open_inquiry.persistence import workspace_lock

def main():
    baseline, output = map(Path, sys.argv[1:])
    output.mkdir(parents=True, exist_ok=False)
    workspace = output / 'workspace'
    workspace.mkdir()
    shutil.copyfile(baseline / 'state.json', workspace / 'state.json')
    engine = Engine.load(workspace)
    before = engine.ledger.report()
    (output / 'baseline.json').write_text(json.dumps(engine.state, indent=2))
    class RecordedProvider(OllamaProvider):
        def generate(self, messages, **kwargs):
            with (output / 'requests.jsonl').open('a') as f:
                f.write(json.dumps({'messages': messages, 'options': kwargs})+'\n')
            return super().generate(messages, **kwargs)
    provider = RecordedProvider('deepseek-v4-flash:0731', base_url='https://ollama.com', think=False)
    def event(e):
        with (output / 'events.jsonl').open('a') as f:
            f.write(json.dumps(e)+'\n')
    engine.recorder.observers.append(event)
    engine.update_policy({'run_token_volume': before['charged_tokens']+70000,
                          'run_model_calls': before['used_calls']+100})
    engine.save()
    start = time.time(); results=[]
    with workspace_lock(workspace):
        for i in range(100):
            result=engine.step(provider); results.append(result)
            with (output / 'results.jsonl').open('a') as f:
                f.write(json.dumps(result)+'\n')
            report=engine.ledger.report()
            print(json.dumps({'step':i+1,'status':result.get('status'),'invitation':result.get('invitation'),
                'mode':result.get('mode'),'chars':len(result.get('response','')),
                'additional_charged':report['charged_tokens']-before['charged_tokens'],
                'elapsed':round(time.time()-start,1)}),flush=True)
            if result['status'] in {'limit','paused','provider-error'}: break
    summary={'model':provider.model,'before':before,'after':engine.ledger.report(),
        'elapsed_seconds':time.time()-start,'status':engine.status(),
        'additional_budget':70000,'settings_changed':['run_token_volume','run_model_calls']}
    (output / 'summary.json').write_text(json.dumps(summary,indent=2))
if __name__=='__main__':main()
