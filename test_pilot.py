import io, os, sys, importlib, tempfile
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def setup(tmp_path,monkeypatch):
 monkeypatch.setenv('HR_DB',str(tmp_path/'test.sqlite3'))
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 sys.modules.pop('app',None)
 module=importlib.import_module('app')
 client=TestClient(module.app)
 def login(name,password):
  response=client.post('/api/login',json={'username':name,'password':password})
  assert response.status_code==200
  return {'Authorization':'Bearer '+response.json()['token']}
 return module,client,login

def test_roles_and_revoked_sessions(setup):
 m,c,login=setup
 admin=login('admin','DemoAdmin!2026');employee=login('employee','DemoEmployee!2026')
 assert c.get('/api/analytics',headers=employee).status_code==403
 assert c.get('/api/logs',headers=employee).status_code==403
 assert c.get('/api/users',headers=employee).status_code==403
 assert c.get('/api/users',headers=admin).status_code==200
 assert c.post('/api/logout',headers=admin).status_code==200
 assert c.get('/api/users',headers=admin).status_code==401

def test_seed_and_metrics(setup):
 m,c,login=setup;h=login('admin','DemoAdmin!2026')
 assert c.get('/api/analytics',headers=h).json()['kpis'] is None
 assert c.post('/api/seed',headers=h).status_code==200
 result=c.get('/api/analytics',headers=h).json()
 assert result['kpis']['hires']>=0
 assert result['kpis']['offer_acceptance'] is None or 0<=result['kpis']['offer_acceptance']<=100
 assert result['dataset']['id']>=1
 assert c.get('/api/analytics/compare',params={'start':'2026-07-01','end':'2026-09-30','previous_start':'2026-04-01','previous_end':'2026-06-30'},headers=h).status_code==200
 assert c.get('/api/analytics',params={'start':'bad'},headers=h).status_code==400

def test_validation_and_confirmation(setup):
 m,c,login=setup;h=login('admin','DemoAdmin!2026')
 bad='requisition_id,position,department,headcount_requested,open_date,recruiter_id,status\nR1,Analyst,IT,-1,2026-01-01,HR1,Open\n'
 r=c.post('/api/upload/preview',files=[('files',('requests.csv',bad,'text/csv'))],headers=h)
 assert r.status_code==200
 payload=r.json();assert not payload['valid']
 assert any(x['rule']=='DQ07' for x in payload['issues'])
 assert c.post('/api/upload/confirm',json={'preview_token':payload['preview_token']},headers=h).status_code==400
 assert c.get('/api/validation/report/'+payload['preview_token'],headers=h).status_code==200
 assert c.get('/api/analytics',headers=h).json()['dataset'] is None
 good=bad.replace('-1','2')
 r=c.post('/api/upload/preview',files=[('files',('requests.csv',good,'text/csv'))],headers=h)
 assert r.json()['valid'],r.json()
 assert c.get('/api/analytics',headers=h).json()['dataset'] is None
 assert c.post('/api/upload/confirm',json={'preview_token':r.json()['preview_token']},headers=h).status_code==200
 assert c.get('/api/analytics',headers=h).json()['kpis']['demand']==2

def test_duplicate_and_kpi_versions(setup):
 m,c,login=setup;h=login('admin','DemoAdmin!2026')
 rows='requisition_id,position,department,headcount_requested,open_date,recruiter_id,status\nR1,Analyst,IT,1,2026-01-01,HR1,Open\nR1,Analyst,IT,1,2026-01-01,HR1,Open\n'
 p=c.post('/api/upload/preview',files=[('files',('requests.csv',rows,'text/csv'))],headers=h).json()
 assert any(i['rule']=='DQ02' for i in p['issues'])
 before=c.get('/api/kpis/KPI01/versions',headers=h).json()
 response=c.patch('/api/kpis/KPI01',json={'formula':'Documented demand formula v2'},headers=h)
 assert response.status_code==200
 assert response.json()['calculation_changed'] is False
 assert len(c.get('/api/kpis/KPI01/versions',headers=h).json())==len(before)+1
 employee=login('employee','DemoEmployee!2026')
 assert c.patch('/api/kpis/KPI01',json={'formula':'Override demand'},headers=employee).status_code==403

def test_rules_cross_table():
 from app import extra_validation
 rows={'requests':[{'requisition_id':'R1','recruiter_id':'HR1','open_date':'2026-01-01'}],
       'applications':[{'application_id':'A1','candidate_id':'C1','requisition_id':'R1','application_date':'2026-01-02','recruiter_id':'HR2'}],
       'stages':[{'application_id':'A1','stage_name':'Interview','stage_status':'Pass','stage_date':'2026-01-04'}],
       'offers':[{'application_id':'A1','offer_date':'2026-01-05','offer_status':'Rejected','joining_date':'2026-01-08'}]}
 rules={i['rule'] for i in extra_validation(rows)}
 assert {'DQ10','DQ11','DQ12'}<=rules
