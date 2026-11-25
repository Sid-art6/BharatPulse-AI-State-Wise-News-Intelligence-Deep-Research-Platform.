"""Manual local release smoke test for the live BharatPulse server.

Usage: python scripts/verify_local.py --article-id <id>
No credentials are read, stored or printed. Uses ONLY the selected localhost
server and reports evidence/graph structure, not journalistic truth.
"""
from __future__ import annotations

import argparse
import re
import sys
import httpx

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from app.evidence_utils import quote_in_source

NODES = ('Planner', 'Discovery', 'Retriever', 'Synthesis', 'Quality Reviewer', 'Report Builder')


def main() -> int:
    parser=argparse.ArgumentParser(description='Run a structure and attribution smoke test against an existing BharatPulse server.')
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--article-id', default='')
    args=parser.parse_args()
    root=args.base.rstrip('/')
    if not re.fullmatch(r'https?://(?:127\.0\.0\.1|localhost)(?::\d{2,5})?',root):
        parser.error('For safety, local verification only accepts localhost or 127.0.0.1')
    with httpx.Client(base_url=root,timeout=120,trust_env=False) as client:
        def get(path,**params):
            response=client.get(path,params=params or None)
            response.raise_for_status()
            return response.json()
        def post(path, body):
            response=client.post(path,json=body)
            response.raise_for_status()
            return response.json()
        health=get('/api/health')
        meta=get('/api/meta')
        print('Health:',health.get('status'),'| Release:',health.get('version'))
        print('LLM provider:',meta.get('llm_provider'),'| Configured:',meta.get('llm_configured'))
        selected=args.article_id
        if not selected:
            feed=get('/api/news',region='All India',demo='false',limit='20')
            live=feed.get('items',[])
            if not live:
                print('No live RSS records are indexed. Use the dashboard refresh and rerun.')
                return 2
            selected=live[0]['id']
        story=get('/api/news/'+selected)
        if story.get('is_demo'):
            print('Select a live RSS article; demo articles are deliberately excluded.')
            return 2
        print('Selected headline:',story.get('title'))
        publisher=post('/api/chat',{'article_id':selected,'question':'Which news publisher published this report?','language':'English'})
        if publisher.get('generated_by')!='source_metadata' or story.get('publisher') not in publisher.get('answer',''):
            raise AssertionError('Publisher metadata routing failed')
        print('Publisher lookup: PASS')
        followup=post('/api/chat',{'article_id':selected,'question':'When did the reported event happen?','language':'English'})
        if followup.get('generated_by') in ('general_ai','mixed_ai'):
            raise AssertionError('Event-specific question entered unrestricted general AI')
        print('Event-date routing: PASS')
        question='Explain what the available reports establish, the reported dates and figures, and what remains unknown.'
        data=post('/api/research/'+selected,{'language':'English','question':question})
        trace=data.get('workflow',{}).get('trace',[])
        visited=tuple(step.get('agent') for step in trace)
        if visited!=NODES:
            raise AssertionError('Expected six actual LangGraph stages; got '+str(visited))
        print('Six-node trace: PASS')
        sources=data.get('sources',[])
        findings=data.get('report',{}).get('findings',[])
        hidden = 0
        for finding in findings:
            for evidence in finding.get('evidence',[]):
                index=evidence['source']
                if not isinstance(index,int) or not 1<=index<=len(sources):
                    raise AssertionError('Invalid source citation index')
                src=sources[index-1]
                if src.get('evidence_origin') == 'publisher_article':
                    hidden += 1
                    continue  # The private passage cache is unavailable to this client.
                if not quote_in_source(evidence['quote'],src.get('title',''),src.get('description','')):
                    raise AssertionError('Research finding contains non-existent RSS quote')
        print('Validated source indices and public RSS quotations. Private passage citations:',hidden)
        report=data.get('report',{})
        print('Question coverage:',len(report.get('research_focus',[])),
              '| additional same-story source highlights:',len(report.get('source_highlights',[])))
        print('Model review:',data.get('workflow',{}).get('review_status'),
              '| generation:',data.get('generated_by'))
        print('STRUCTURAL SMOKE TEST PASSED. This is not an independent fact-check or proof of zero hallucinations.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (httpx.HTTPError,AssertionError,KeyError,TypeError) as error:
        print('LOCAL QA FAILED:',error)
        raise SystemExit(1)
