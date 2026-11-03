"""Optional AI inference on top of deterministic engine results. Off by default.
No market-data computation relies on a model.
"""
from __future__ import annotations
import json
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from . import integrations as cfg

INSTRUCTIONS=('You are TWYS Research. Use only the numeric figures and original trade examples supplied. '
 'Do not manufacture sample sizes, live quotes, trader counts, source quotes, causal findings or investment advice. '
 'Mention missing values and distinguish observations from hypotheses. Reference the original trade ID for journal claims.')

def status():
    p=cfg.config().get('ai_provider','off')
    return {'provider':p,'model':cfg.config().get('ai_model',''),
            'configured':p=='ollama' or bool(cfg.secret('OPENAI_API_KEY' if p=='openai' else 'COMPATIBLE_API_KEY')),
            'privacy_notice':'Cloud providers receive only selected source evidence for the question when enabled. Off mode sends nothing.'}

def reply(question, evidence):
    c=cfg.config(); p=c.get('ai_provider','off');model=c.get('ai_model','').strip()
    if p=='off' or not model:return None
    messages=[{'role':'system','content':INSTRUCTIONS},
              {'role':'user','content':json.dumps({'question':question,'evidence':evidence},ensure_ascii=False,default=str)}]
    if p=='ollama':
        endpoint='http://127.0.0.1:11434/api/chat'
        payload={'model':model,'messages':messages,'stream':False,'options':{'temperature':0.2,'num_predict':900}}
        headers={'Content-Type':'application/json'}
    else:
        endpoint='https://api.openai.com/v1/chat/completions' if p=='openai' else c.get('ai_endpoint','')
        key=cfg.secret('OPENAI_API_KEY' if p=='openai' else 'COMPATIBLE_API_KEY')
        if not key:raise ValueError('API credential not configured')
        u=urlparse(endpoint)
        if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1')):
            raise ValueError('Cloud AI endpoints must use HTTPS')
        payload={'model':model,'messages':messages,'temperature':0.2,'max_tokens':900}
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key}
    req=Request(endpoint,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    with urlopen(req,timeout=75) as response:
        result=json.load(response)
    content=(result.get('message') or {}).get('content') if p=='ollama' else (result.get('choices') or [{}])[0].get('message',{}).get('content')
    if not content:raise ValueError('AI provider returned no response')
    return {'provider':p,'model':model,'answer':content}
