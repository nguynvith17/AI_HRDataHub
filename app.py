import os, io, csv, json, sqlite3, secrets, hashlib, hmac, random, re
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from contextlib import contextmanager
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import pandas as pd

ROOT=Path(__file__).parent
DB=Path(os.environ.get('HR_DB',str(ROOT/'hr_demo.sqlite3')))
app=FastAPI(title='AI HR Productivity Hub — Recruitment Pilot',version='0.2.0')
auth=HTTPBearer(auto_error=False)
SCHEMA={
 'requests':['requisition_id','position','department','headcount_requested','open_date','recruiter_id','status'],
 'applications':['application_id','candidate_id','requisition_id','application_date','source'],
 'stages':['application_id','stage_name','stage_status','stage_date'],
 'offers':['application_id','offer_date','offer_status'],
 'costs':['cost_id','cost_date','cost_amount','cost_category']}
IDS={'requests':'requisition_id','applications':'application_id','costs':'cost_id'}
DATES={'open_date','actual_close_date','application_date','stage_date','offer_date','offer_accept_date','joining_date','cost_date','termination_date'}
STATUS={'requests':{'Open','Closed','On Hold','Cancelled'},'offers':{'Sent','Accepted','Rejected','Withdrawn','Pending'},'stages':{'Pass','Fail','Pending','Withdrawn','Rejected'}}
ALIASES={'recruitment requests':'requests','candidates & applications':'applications','recruitment stages':'stages','offers & hiring':'offers','recruitment costs & quality':'costs'}

@contextmanager
def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try: yield c; c.commit()
 finally:c.close()

def now():return datetime.utcnow().isoformat(timespec='seconds')+'Z'
def pw_hash(p,s=None):
 s=s or secrets.token_hex(16)
 return s+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),220000).hex()
def verify(p,h):
 try:s,_=h.split(':');return hmac.compare_digest(pw_hash(p,s),h)
 except Exception:return False

def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT, active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER,expires TEXT);
  CREATE TABLE IF NOT EXISTS datasets(id INTEGER PRIMARY KEY,created_at TEXT,created_by TEXT,source TEXT,rows INTEGER);
  CREATE TABLE IF NOT EXISTS records(dataset_id INTEGER,kind TEXT,payload TEXT);
  CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY,created_at TEXT,actor TEXT,action TEXT,detail TEXT);
  CREATE TABLE IF NOT EXISTS kpis(id TEXT PRIMARY KEY,name TEXT,formula TEXT,version INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS kpi_versions(id TEXT,version INTEGER,formula TEXT,changed_at TEXT,changed_by TEXT,PRIMARY KEY(id,version));''')
  if not c.execute('SELECT 1 FROM users').fetchone():
   c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',('admin',pw_hash(os.environ.get('DEMO_ADMIN_PASSWORD','DemoAdmin!2026')),'hr_admin'))
   c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',('employee',pw_hash(os.environ.get('DEMO_EMPLOYEE_PASSWORD','DemoEmployee!2026')),'employee'))
  for id,name,formula in [('KPI01','Recruitment Demand','SUM(headcount_requested) by open_date'),('KPI02','Total Hires','COUNT(DISTINCT application_id) by joining_date'),('KPI03','Fulfillment Rate','Cohort hires / cohort demand * 100'),('KPI05','Time to Fill','actual_close_date - open_date (requisition proxy)'),('KPI06','Time to Hire','offer_accept_date - application_date'),('KPI07','Offer Acceptance Rate','Accepted / (Accepted + Rejected) * 100'),('KPI08','CV Pass Rate','CV Pass / (CV Pass + CV Fail) * 100'),('KPI09','Interview Pass Rate','Interview Pass / (Interview Pass + Interview Fail) * 100'),('KPI10','Source Conversion','source hires / source applications * 100'),('KPI11','Cost per Hire','period cost / period hires')]:
   c.execute('INSERT OR IGNORE INTO kpis(id,name,formula) VALUES(?,?,?)',(id,name,formula))
  for row in c.execute('SELECT id,version,formula FROM kpis').fetchall():
   c.execute('INSERT OR IGNORE INTO kpi_versions VALUES(?,?,?,?,?)',(row['id'],row['version'],row['formula'],now(),'system'))
init()

def log(actor,action,detail=''):
 with conn() as c:c.execute('INSERT INTO logs(created_at,actor,action,detail) VALUES(?,?,?,?)',(now(),actor,action,detail[:1000]))

def current(creds:HTTPAuthorizationCredentials=Depends(auth)):
 if not creds:raise HTTPException(401,'Yêu cầu đăng nhập')
 th=hashlib.sha256(creds.credentials.encode()).hexdigest()
 with conn() as c:
  u=c.execute('SELECT u.* FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.active=1',(th,now())).fetchone()
 if not u:raise HTTPException(401,'Phiên không hợp lệ hoặc hết hạn')
 return dict(u)
def admin(u=Depends(current)):
 if u['role']!='hr_admin':
  log(u['username'],'ACCESS_DENIED','HR Admin endpoint')
  raise HTTPException(403,'Không có quyền truy cập')
 return u
class Login(BaseModel):username:str;password:str
@app.post('/api/login')
def login(data:Login):
 with conn() as c:u=c.execute('SELECT * FROM users WHERE username=?',(data.username,)).fetchone()
 if not u or not u['active'] or not verify(data.password,u['password_hash']):
  log('anonymous','LOGIN_FAILED','redacted');raise HTTPException(401,'Thông tin đăng nhập không hợp lệ')
 token=secrets.token_urlsafe(36);expires=(datetime.utcnow()+timedelta(hours=8)).isoformat()+'Z'
 with conn() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],expires))
 log(u['username'],'LOGIN_SUCCESS')
 return {'token':token,'role':u['role'],'username':u['username'],'expires':expires}
@app.post('/api/logout')
def logout(creds:HTTPAuthorizationCredentials=Depends(auth),u=Depends(current)):
 with conn() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(creds.credentials.encode()).hexdigest(),))
 log(u['username'],'LOGOUT');return {'ok':True}
@app.get('/api/me')
def me(u=Depends(current)):return {'username':u['username'],'role':u['role']}
@app.get('/api/users')
def users(u=Depends(admin)):
 with conn() as c:return [dict(x) for x in c.execute('SELECT id,username,role,active FROM users')]
class UserChange(BaseModel):role:str|None=None;active:bool|None=None
@app.patch('/api/users/{uid}')
def change_user(uid:int,data:UserChange,u=Depends(admin)):
 if uid==u['id']:raise HTTPException(400,'Không được tự thay đổi tài khoản đang dùng')
 if data.role is not None and data.role not in ('employee','hr_admin'):raise HTTPException(400,'Vai trò không hợp lệ')
 with conn() as c:
  if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise HTTPException(404,'Không tìm thấy')
  if data.role is not None:c.execute('UPDATE users SET role=? WHERE id=?',(data.role,uid))
  if data.active is not None:c.execute('UPDATE users SET active=? WHERE id=?',(int(data.active),uid))
  c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
 log(u['username'],'USER_CHANGE',f'id={uid} role={data.role} active={data.active}')
 return {'ok':True}

def parse_date(v):
 if v is None or str(v).strip() in ('','nan','NaT','None'):return ''
 try:return pd.to_datetime(v,errors='raise').strftime('%Y-%m-%d')
 except Exception:return None

def extra_validation(grouped):
 """Cross-table DQ05/DQ06/DQ09/DQ10/DQ11/DQ12, no silent correction."""
 issues=[]
 def add(kind,i,field,rule,message,severity='Critical'):
  issues.append({'file':'(combined)','sheet':kind,'row':i+2,'field':field,'rule':rule,'severity':severity,'message':message})
 req={r.get('requisition_id'):r for r in grouped.get('requests',[])}
 apps={a.get('application_id'):a for a in grouped.get('applications',[])}
 for i,a in enumerate(grouped.get('applications',[])):
  if not a.get('candidate_id') or not a.get('requisition_id'):add('applications',i,'candidate_id/requisition_id','DQ09','Thiếu quan hệ ứng viên hoặc yêu cầu')
  r=req.get(a.get('requisition_id'))
  if r and a.get('recruiter_id') and r.get('recruiter_id') and a['recruiter_id']!=r['recruiter_id']:
   add('applications',i,'recruiter_id','DQ12','Recruiter không khớp yêu cầu; cần lịch sử bàn giao','Warning')
  if r and a.get('application_date') and r.get('open_date') and a['application_date']<r['open_date']:
   add('applications',i,'application_date','DQ05','Ứng tuyển trước ngày mở yêu cầu','Warning')
 for kind in ('stages','offers'):
  for i,r in enumerate(grouped.get(kind,[])):
   if r.get('application_id') not in apps:add(kind,i,'application_id','DQ06','Application tham chiếu không tồn tại')
 for i,o in enumerate(grouped.get('offers',[])):
  if o.get('joining_date') and o.get('offer_status')!='Accepted':add('offers',i,'joining_date','DQ11','Có ngày nhận việc nhưng offer chưa Accepted')
  if o.get('offer_status')=='Accepted' and not o.get('offer_accept_date'):add('offers',i,'offer_accept_date','DQ11','Offer Accepted thiếu ngày chấp nhận','Warning')
  if o.get('offer_accept_date') and o.get('offer_date') and o['offer_accept_date']<o['offer_date']:
   add('offers',i,'offer_accept_date','DQ05','Ngày chấp nhận trước ngày gửi offer')
  if o.get('joining_date') and o.get('offer_date') and o['joining_date']<o['offer_date']:
   add('offers',i,'joining_date','DQ05','Ngày nhận việc trước ngày gửi offer')
  if o.get('termination_date') and o.get('joining_date') and o['termination_date']<o['joining_date']:
   add('offers',i,'termination_date','DQ05','Ngày nghỉ trước ngày nhận việc')
 by_app=defaultdict(list)
 for i,st in enumerate(grouped.get('stages',[])):
  if st.get('stage_name','').strip().lower() not in ('cv','cv screening','interview'):
   add('stages',i,'stage_name','DQ10','Vòng tuyển dụng chưa được hỗ trợ trong workflow mặc định','Warning')
  by_app[st.get('application_id')].append((i,st))
 for aid,events in by_app.items():
  ordered=sorted(events,key=lambda x:x[1].get('stage_date') or '')
  last=None
  for i,st in ordered:
   stage=st.get('stage_name','').lower()
   if stage=='interview' and not any(x.get('stage_name','').lower() in ('cv','cv screening') and x.get('stage_status')=='Pass' for _,x in ordered if x.get('stage_date','')<=st.get('stage_date','')):
    add('stages',i,'stage_name','DQ10','Phỏng vấn chưa có vòng CV Pass trước đó','Warning')
   if last and st.get('stage_date','')<last:add('stages',i,'stage_date','DQ10','Ngày vòng tuyển dụng không theo thứ tự','Warning')
   last=st.get('stage_date','')
 return issues

def normalize(kind,df):
 df.columns=[str(x).strip().lower().replace(' ','_') for x in df.columns]
 rows=[];errors=[];seen=set()
 for idx,row in df.iterrows():
  r={k:('' if pd.isna(v) else str(v).strip()) for k,v in row.to_dict().items()}
  for f in SCHEMA[kind]:
   if not r.get(f):errors.append({'row':idx+2,'field':f,'rule':'DQ01','severity':'Critical','message':'Thiếu trường bắt buộc'})
  for f in DATES.intersection(r):
   d=parse_date(r[f]);
   if d is None:errors.append({'row':idx+2,'field':f,'rule':'DQ03','severity':'Critical','message':'Ngày không hợp lệ'})
   else:r[f]=d
  if kind in STATUS and r.get('status' if kind=='requests' else 'offer_status' if kind=='offers' else 'stage_status'):
   f='status' if kind=='requests' else 'offer_status' if kind=='offers' else 'stage_status'
   if r[f] not in STATUS[kind]:errors.append({'row':idx+2,'field':f,'rule':'DQ04','severity':'Critical','message':'Trạng thái không hợp lệ'})
  if kind in IDS:
   f=IDS[kind];v=r.get(f)
   if v and v in seen:errors.append({'row':idx+2,'field':f,'rule':'DQ02' if kind!='applications' else 'DQ08','severity':'Critical','message':'Mã trùng trong tệp'})
   seen.add(v)
  if kind=='requests':
   try:
    if float(r.get('headcount_requested',''))%1!=0 or int(float(r.get('headcount_requested','')))<=0:raise ValueError()
    r['headcount_requested']=int(float(r['headcount_requested']))
   except:errors.append({'row':idx+2,'field':'headcount_requested','rule':'DQ07','severity':'Critical','message':'Headcount phải là số nguyên dương'})
   if r.get('actual_close_date') and r.get('open_date') and r['actual_close_date']<r['open_date']:errors.append({'row':idx+2,'field':'actual_close_date','rule':'DQ05','severity':'Critical','message':'Ngày đóng trước ngày mở'})
  if kind=='costs':
   try:
    r['cost_amount']=float(r.get('cost_amount',''))
    if r['cost_amount']<0:raise ValueError()
   except:errors.append({'row':idx+2,'field':'cost_amount','rule':'DQ07','severity':'Critical','message':'Chi phí không hợp lệ'})
  if kind=='offers' and r.get('joining_date') and r.get('offer_accept_date') and r['joining_date']<r['offer_accept_date']:errors.append({'row':idx+2,'field':'joining_date','rule':'DQ05','severity':'Critical','message':'Ngày nhận việc trước ngày chấp nhận đề nghị'})
  rows.append(r)
 return rows,errors

PENDING={}
@app.post('/api/upload/preview')
async def preview(files:list[UploadFile]=File(...),u=Depends(admin)):
 if len(files)>10:raise HTTPException(400,'Tối đa 10 tệp mỗi lượt')
 grouped=defaultdict(list);issues=[];filelist=[]
 for f in files:
  raw=await f.read()
  if not f.filename.lower().endswith(('.xlsx','.csv')) or len(raw)>10*1024*1024:raise HTTPException(400,'Chỉ nhận .xlsx/.csv tối đa 10MB/tệp')
  try:
   if f.filename.lower().endswith('.xlsx'):
    wb=pd.read_excel(io.BytesIO(raw),sheet_name=None,dtype=str)
   else:
    wb={Path(f.filename).stem:pd.read_csv(io.BytesIO(raw),dtype=str)}
  except Exception:raise HTTPException(400,f'Không đọc được {f.filename}')
  for sheet,df in wb.items():
   kind=str(sheet).lower().strip().replace(' ','_')
   kind=ALIASES.get(str(sheet).lower().strip(),kind)
   if kind not in SCHEMA:
    kind=next((k for k in SCHEMA if set(SCHEMA[k]).issubset(set(str(x).strip().lower() for x in df.columns))),None)
   if not kind:
    issues.append({'file':f.filename,'sheet':sheet,'row':1,'field':'sheet','rule':'MAPPING','severity':'Critical','message':'Không nhận diện nhóm dữ liệu; đặt tên sheet requests/applications/stages/offers/costs'});continue
   missing=set(SCHEMA[kind])-set(str(x).strip().lower().replace(' ','_') for x in df.columns)
   if missing:
    issues.append({'file':f.filename,'sheet':sheet,'row':1,'field':','.join(sorted(missing)),'rule':'DQ01','severity':'Critical','message':'Thiếu cột bắt buộc'});continue
   rows,err=normalize(kind,df)
   for e in err:e.update(file=f.filename,sheet=sheet)
   issues+=err;grouped[kind]+=rows;filelist.append({'file':f.filename,'sheet':sheet,'kind':kind,'rows':len(rows),'preview':rows[:10]})
 with conn() as c:
  existing={k:[json.loads(r['payload']) for r in c.execute('SELECT payload FROM records WHERE kind=? AND dataset_id=(SELECT MAX(id) FROM datasets)',(k,))] for k in SCHEMA}
 issues+=extra_validation(grouped)
 for kind,field,refkind,refid in [('applications','requisition_id','requests','requisition_id'),('stages','application_id','applications','application_id'),('offers','application_id','applications','application_id')]:
  known={str(r.get(refid)) for r in grouped[refkind]+existing[refkind]}
  for i,r in enumerate(grouped[kind]):
   if str(r.get(field)) not in known:issues.append({'file':'(combined)','sheet':kind,'row':i+2,'field':field,'rule':'DQ06','severity':'Critical','message':'Khóa ngoại không tồn tại'})
 for kind,field in IDS.items():
  known={str(r.get(field)) for r in existing[kind]}
  for i,r in enumerate(grouped[kind]):
   if str(r.get(field)) in known and False:issues.append({'file':'(combined)','sheet':kind,'row':i+2,'field':field,'rule':'DQ02','severity':'Critical','message':'ID đã tồn tại trong dataset hiện tại'})
 token=secrets.token_urlsafe(24)
 PENDING[token]={'owner':u['id'],'grouped':dict(grouped),'issues':issues,'files':filelist,'created':datetime.utcnow()}
 log(u['username'],'UPLOAD_PREVIEW',f'files={len(files)} issues={len(issues)}')
 return {'preview_token':token,'files':filelist,'issues':issues,'valid':not any(x['severity']=='Critical' for x in issues),'total_rows':sum(map(len,grouped.values()))}
class Confirm(BaseModel):preview_token:str;mode:str='replace'
@app.post('/api/upload/confirm')
def confirm(data:Confirm,u=Depends(admin)):
 p=PENDING.get(data.preview_token)
 if not p or p['owner']!=u['id'] or datetime.utcnow()-p['created']>timedelta(minutes=30):raise HTTPException(400,'Bản xem trước không hợp lệ hoặc đã hết hạn')
 if any(x['severity']=='Critical' for x in p['issues']):raise HTTPException(400,'Còn lỗi nghiêm trọng, không thể nhập')
 if not sum(map(len,p['grouped'].values())):raise HTTPException(400,'Không có bản ghi hợp lệ để nhập')
 if data.mode!='replace':raise HTTPException(400,'Pilot chỉ hỗ trợ thay thế toàn bộ dataset sau xác nhận')
 with conn() as c:
  c.execute('INSERT INTO datasets(created_at,created_by,source,rows) VALUES(?,?,?,?)',(now(),u['username'],','.join(x['file'] for x in p['files']),sum(map(len,p['grouped'].values()))))
  did=c.execute('SELECT last_insert_rowid()').fetchone()[0]
  for kind,rows in p['grouped'].items():c.executemany('INSERT INTO records VALUES(?,?,?)',[(did,kind,json.dumps(r,ensure_ascii=False)) for r in rows])
 PENDING.pop(data.preview_token,None);log(u['username'],'IMPORT_CONFIRMED',f'dataset={did}')
 return {'dataset_version':did,'ok':True}

def get_data():
 with conn() as c:
  d=c.execute('SELECT * FROM datasets ORDER BY id DESC LIMIT 1').fetchone()
  if not d:return None,{k:[] for k in SCHEMA}
  rows=c.execute('SELECT kind,payload FROM records WHERE dataset_id=?',(d['id'],)).fetchall()
 data=defaultdict(list)
 for r in rows:data[r['kind']].append(json.loads(r['payload']))
 return dict(d),{k:data[k] for k in SCHEMA}
def inside(s,start,end):return bool(s) and start<=s<=end
def rate(a,b):return round(a/b*100,2) if b else None
@app.get('/api/analytics')
def analytics(start:str='2026-01-01',end:str='2026-12-31',department:str='',recruiter:str='',source:str='',u=Depends(admin)):
 try:
  date.fromisoformat(start);date.fromisoformat(end)
 except ValueError:raise HTTPException(400,'Ngày phải theo YYYY-MM-DD')
 if start>end:raise HTTPException(400,'Khoảng thời gian không hợp lệ')
 meta,d=get_data()
 if not meta:return {'dataset':None,'kpis':None,'funnel':[],'sources':[],'recruiters':[],'trend':[]}
 req={r['requisition_id']:r for r in d['requests'] if (not department or r.get('department')==department) and (not recruiter or r.get('recruiter_id')==recruiter)}
 apps={a['application_id']:a for a in d['applications'] if a.get('requisition_id') in req and (not source or a.get('source')==source)}
 offers={o['application_id']:o for o in d['offers'] if o.get('application_id') in apps}
 stages=[s for s in d['stages'] if s.get('application_id') in apps]
 costs=[c for c in d['costs'] if inside(c.get('cost_date'),start,end) and (not source or c.get('source')==source)]
 demand=sum(int(r['headcount_requested']) for r in req.values() if inside(r.get('open_date'),start,end))
 hires={a for a,o in offers.items() if inside(o.get('joining_date'),start,end)}
 cohortreq={r['requisition_id'] for r in req.values() if inside(r.get('open_date'),start,end)}
 cohort_hires=sum(1 for a in hires if apps[a]['requisition_id'] in cohortreq)
 sent=[o for o in offers.values() if inside(o.get('offer_date'),start,end)]
 accepted=sum(o.get('offer_status')=='Accepted' for o in sent);rejected=sum(o.get('offer_status')=='Rejected' for o in sent)
 cv={s['application_id'] for s in stages if s.get('stage_name','').lower() in ('cv screening','cv') and s.get('stage_status')=='Pass' and inside(s.get('stage_date'),start,end)}
 cvfail={s['application_id'] for s in stages if s.get('stage_name','').lower() in ('cv screening','cv') and s.get('stage_status')=='Fail' and inside(s.get('stage_date'),start,end)}
 iv={s['application_id'] for s in stages if s.get('stage_name','').lower()=='interview' and s.get('stage_status')=='Pass' and inside(s.get('stage_date'),start,end)}
 ivfail={s['application_id'] for s in stages if s.get('stage_name','').lower()=='interview' and s.get('stage_status')=='Fail' and inside(s.get('stage_date'),start,end)}
 app_period={a for a,r in apps.items() if inside(r.get('application_date'),start,end)}
 tth=[(date.fromisoformat(o['offer_accept_date'])-date.fromisoformat(apps[a]['application_date'])).days for a,o in offers.items() if o.get('offer_accept_date') and inside(o['offer_accept_date'],start,end) and apps[a].get('application_date') and o['offer_accept_date']>=apps[a]['application_date']]
 ttf=[(date.fromisoformat(r['actual_close_date'])-date.fromisoformat(r['open_date'])).days for r in req.values() if r.get('actual_close_date') and inside(r['actual_close_date'],start,end) and r.get('open_date')]
 funnel=[{'stage':n,'count':len(v)} for n,v in [('Applications',app_period),('CV evaluated',cv|cvfail),('CV passed',cv),('Interview evaluated',iv|ivfail),('Interview passed',iv),('Offer sent',{a for a,o in offers.items() if inside(o.get('offer_date'),start,end)}),('Offer accepted',{a for a,o in offers.items() if o.get('offer_status')=='Accepted' and inside(o.get('offer_date'),start,end)}),('Joined',hires)]]
 src=[]
 for s in sorted({apps[a].get('source') or 'Unknown' for a in app_period}|{apps[a].get('source') or 'Unknown' for a in hires}):
  aa=sum((apps[a].get('source') or 'Unknown')==s for a in app_period);hh=sum((apps[a].get('source') or 'Unknown')==s for a in hires)
  cost=sum(float(c.get('cost_amount',0)) for c in costs if c.get('source')==s)
  src.append({'source':s,'applications':aa,'hires':hh,'conversion':rate(hh,aa),'cost':cost,'cost_per_hire':round(cost/hh) if hh else None})
 rec=[]
 for rid in sorted({r.get('recruiter_id') for r in req.values()}):
  assigned=[r for r in req.values() if r.get('recruiter_id')==rid]
  hh=sum(apps[a]['requisition_id'] in {r['requisition_id'] for r in assigned} for a in hires)
  rec.append({'recruiter':rid,'assigned':len(assigned),'open':sum(r.get('status')=='Open' for r in assigned),'hires':hh})
 months=sorted({s[:7] for s in [start,end]+[a.get('application_date','') for a in apps.values()]+[o.get('joining_date','') for o in offers.values()] if s and start[:7]<=s[:7]<=end[:7]})
 trend=[{'month':m,'applications':sum(a.get('application_date','').startswith(m) for a in apps.values()),'hires':sum(o.get('joining_date','').startswith(m) for o in offers.values())} for m in months]
 kpis={'demand':demand,'hires':len(hires),'fulfillment':rate(cohort_hires,demand),'unfilled':max(0,demand-cohort_hires),'open_requisitions':sum(r.get('status')=='Open' and r.get('open_date','')<=end for r in req.values()),'time_to_fill_proxy':round(sum(ttf)/len(ttf),1) if ttf else None,'time_to_hire':round(sum(tth)/len(tth),1) if tth else None,'offer_acceptance':rate(accepted,accepted+rejected),'cv_pass':rate(len(cv),len(cv|cvfail)),'interview_pass':rate(len(iv),len(iv|ivfail)),'cost_per_hire':round(sum(float(c.get('cost_amount',0)) for c in costs)/len(hires)) if hires else None}
 return {'dataset':meta,'filters':{'start':start,'end':end,'department':department,'recruiter':recruiter,'source':source},'formula_version':1,'kpis':kpis,'funnel':funnel,'sources':src,'recruiters':rec,'trend':trend,'notes':['Fulfillment dùng cohort requisition mở trong kỳ; hires tính theo joining_date trong kỳ.','Time to Fill là proxy cấp requisition.','Source conversion dùng applications phát sinh trong kỳ và hires nhận việc trong kỳ; không phải cohort conversion.']}
@app.get('/api/kpis')
def kpis(u=Depends(admin)):
 with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM kpis ORDER BY id')]
@app.get('/api/logs')
def logs(u=Depends(admin)):
 with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 100')]
@app.get('/api/report.csv')
def report(start:str='2026-01-01',end:str='2026-12-31',u=Depends(admin)):
 result=analytics(start,end,u=u)
 out=io.StringIO();w=csv.writer(out);w.writerow(['dataset_version',result['dataset']['id'] if result['dataset'] else '','formula_version',1,'created_at',now()]);w.writerow(['period',start,end]);w.writerow(['KPI','value'])
 for k,v in (result['kpis'] or {}).items():w.writerow([k,'N/A' if v is None else v])
 log(u['username'],'REPORT_EXPORT',f'{start}..{end}')
 return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="recruitment_report.csv"'})
class Question(BaseModel):question:str;start:str='2026-01-01';end:str='2026-12-31'
@app.post('/api/assistant')
def assistant(q:Question,u=Depends(admin)):
 result=analytics(q.start,q.end,u=u);k=result['kpis']
 if not k:return {'answer':'Chưa có dataset đã xác nhận. Không thể trả lời bằng số liệu.','dataset':None}
 s=q.question.lower()
 if 'nguồn' in s or 'source' in s:
  vals=[x for x in result['sources'] if x['conversion'] is not None]
  if not vals:answer='Không đủ dữ liệu để so sánh nguồn tuyển dụng.'
  else:
   best=max(vals,key=lambda x:x['conversion']);answer=f"Nguồn {best['source']} có tỷ lệ chuyển đổi theo kỳ cao nhất: {best['conversion']}% ({best['hires']} hires / {best['applications']} applications). Đây là so sánh mô tả, không chứng minh nguyên nhân."
 elif 'offer' in s or 'đề nghị' in s:answer=f"Tỷ lệ chấp nhận đề nghị: {k['offer_acceptance'] if k['offer_acceptance'] is not None else 'N/A'}%. Mẫu số chỉ gồm Accepted + Rejected."
 elif 'hoàn thành' in s or 'chỉ tiêu' in s:answer=f"Tỷ lệ hoàn thành theo cohort requisition mở trong kỳ: {k['fulfillment'] if k['fulfillment'] is not None else 'N/A'}%. Chỉ tiêu: {k['demand']}; số nhận việc thuộc cohort trong kỳ được dùng làm tử số."
 elif 'tuyển' in s or 'hire' in s or 'nhận việc' in s:answer=f"Có {k['hires']} lượt ứng tuyển ghi nhận joining_date trong kỳ. Mỗi application được đếm một lần."
 elif 'chi phí' in s:answer=f"Chi phí trên mỗi lượt nhận việc: {k['cost_per_hire'] if k['cost_per_hire'] is not None else 'N/A'} VND; chỉ đáng tin khi dữ liệu chi phí đầy đủ và cùng phạm vi."
 else:answer='Câu hỏi chưa thuộc nhóm truy vấn hỗ trợ. Hãy hỏi về số người nhận việc, tỷ lệ hoàn thành, offer, nguồn tuyển dụng hoặc chi phí.'
 return {'answer':answer,'dataset_version':result['dataset']['id'],'formula_version':1,'period':f'{q.start} đến {q.end}','mode':'Trợ lý truy vấn theo quy tắc; chưa tích hợp mô hình ngôn ngữ'}

@app.post('/api/seed')
def seed(u=Depends(admin)):
 rng=random.Random(19);requests=[];apps=[];stages=[];offers=[];costs=[]
 depts=['Technology','Operations','Finance','Sales','Human Resources'];sources=['Job Site','Referral','Career Page','Social Media','Agency']
 for i in range(1,41):
  month=1+(i-1)%10;opened=date(2026,month,rng.randint(1,18));rid=f'REQ{i:03d}';recruiter=f'HR{1+i%4:02d}'
  requests.append({'requisition_id':rid,'position':['Analyst','Specialist','Manager'][i%3],'department':depts[i%5],'headcount_requested':rng.randint(1,3),'open_date':opened.isoformat(),'recruiter_id':recruiter,'status':'Closed' if i%3 else 'Open','actual_close_date':(opened+timedelta(days=45)).isoformat() if i%3 else ''})
  for j in range(rng.randint(4,9)):
   aid=f'APP{i:03d}{j:02d}';ad=opened+timedelta(days=rng.randint(0,12));source=rng.choice(sources)
   apps.append({'application_id':aid,'candidate_id':f'CAN{i:03d}{j:02d}','requisition_id':rid,'application_date':ad.isoformat(),'source':source,'recruiter_id':recruiter})
   cv=rng.random()<.65;iv=cv and rng.random()<.6;offer=iv and rng.random()<.55;accepted=offer and rng.random()<.75
   stages.append({'application_id':aid,'stage_name':'CV Screening','stage_status':'Pass' if cv else 'Fail','stage_date':(ad+timedelta(days=2)).isoformat()})
   if cv:stages.append({'application_id':aid,'stage_name':'Interview','stage_status':'Pass' if iv else 'Fail','stage_date':(ad+timedelta(days=7)).isoformat()})
   if offer:offers.append({'application_id':aid,'offer_date':(ad+timedelta(days=12)).isoformat(),'offer_status':'Accepted' if accepted else 'Rejected','offer_accept_date':(ad+timedelta(days=15)).isoformat() if accepted else '','joining_date':(ad+timedelta(days=25)).isoformat() if accepted else ''})
  costs.append({'cost_id':f'C{i:03d}','cost_date':opened.isoformat(),'cost_amount':rng.randint(2,12)*1000000,'cost_category':'Advertising','source':sources[i%5]})
 with conn() as c:
  c.execute('INSERT INTO datasets(created_at,created_by,source,rows) VALUES(?,?,?,?)',(now(),u['username'],'SYNTHETIC_SEED',sum(map(len,[requests,apps,stages,offers,costs]))))
  did=c.execute('SELECT last_insert_rowid()').fetchone()[0]
  for kind,rows in [('requests',requests),('applications',apps),('stages',stages),('offers',offers),('costs',costs)]:c.executemany('INSERT INTO records VALUES(?,?,?)',[(did,kind,json.dumps(r)) for r in rows])
 log(u['username'],'SYNTHETIC_SEED',f'dataset={did}')
 return {'dataset_version':did,'rows':sum(map(len,[requests,apps,stages,offers,costs]))}
@app.get('/',response_class=HTMLResponse)
def home():return (ROOT/'index.html').read_text(encoding='utf-8')


@app.get('/api/validation/report/{token}')
def validation_report(token:str,u=Depends(admin)):
 p=PENDING.get(token)
 if not p or p['owner']!=u['id']:raise HTTPException(404,'Không tìm thấy bản kiểm tra')
 output=io.StringIO();writer=csv.writer(output)
 cols=['file','sheet','row','field','rule','severity','message'];writer.writerow(cols)
 for issue in p['issues']:writer.writerow([issue.get(k,'') for k in cols])
 log(u['username'],'VALIDATION_EXPORT',f'issues={len(p["issues"])}')
 return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="validation_issues.csv"'})

@app.get('/api/datasets')
def dataset_history(u=Depends(admin)):
 with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM datasets ORDER BY id DESC LIMIT 100')]

@app.get('/api/kpis/{kpi_id}/versions')
def kpi_history(kpi_id:str,u=Depends(admin)):
 with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM kpi_versions WHERE id=? ORDER BY version DESC',(kpi_id,))]

class KPIUpdate(BaseModel):
 formula:str
@app.patch('/api/kpis/{kpi_id}')
def update_kpi(kpi_id:str,data:KPIUpdate,u=Depends(admin)):
 # Formula metadata only: no user-defined formula is executed as code or SQL.
 # Changes to the calculation engine require a reviewed code release.
 if not 5<=len(data.formula.strip())<=500:raise HTTPException(400,'Mô tả công thức phải dài 5–500 ký tự')
 with conn() as c:
  old=c.execute('SELECT * FROM kpis WHERE id=?',(kpi_id,)).fetchone()
  if not old:raise HTTPException(404,'Không tìm thấy KPI')
  version=old['version']+1
  c.execute('UPDATE kpis SET formula=?,version=? WHERE id=?',(data.formula,version,kpi_id))
  c.execute('INSERT INTO kpi_versions VALUES(?,?,?,?,?)',(kpi_id,version,data.formula,now(),u['username']))
 log(u['username'],'KPI_METADATA_VERSION',f'{kpi_id} version={version}')
 return {'id':kpi_id,'version':version,'formula':data.formula,'calculation_changed':False,'warning':'Chỉ cập nhật mô tả; thuật toán tính KPI không thay đổi'}

@app.get('/api/analytics/compare')
def compare_periods(start:str,end:str,previous_start:str,previous_end:str,u=Depends(admin)):
 current_result=analytics(start,end,u=u)
 previous_result=analytics(previous_start,previous_end,u=u)
 current_kpis=current_result['kpis'] or {};previous_kpis=previous_result['kpis'] or {}
 return {'current':current_result,'previous':previous_result,
         'delta':{k:(v-previous_kpis[k] if isinstance(v,(int,float)) and isinstance(previous_kpis.get(k),(int,float)) else None) for k,v in current_kpis.items()},
         'note':'Mỗi tỷ lệ được tính từ tử số và mẫu số của kỳ tương ứng, không lấy trung bình tỷ lệ tháng.'}
