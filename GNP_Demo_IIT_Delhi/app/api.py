import os, psycopg, hashlib, hmac, base64, json, time, secrets
from psycopg.rows import dict_row
from fastapi import FastAPI, Query, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from cryptography.fernet import Fernet
from starlette.responses import Response
from kafka import KafkaAdminClient
from kafka.errors import KafkaError, NoBrokersAvailable
DB=os.getenv('DATABASE_URL','postgresql://feedback_app:local_dev_change_me@postgres:5432/feedback')
app=FastAPI(title='GNP Demo API',version='2.0')
TOKEN_SECRET=os.getenv('APP_TOKEN_SECRET','local-demo-token-secret-change-before-deployment').encode()
DEFAULT_ADMIN=os.getenv('DEFAULT_ADMIN_USER','gnpadmin')
DEFAULT_ADMIN_PASSWORD=os.getenv('DEFAULT_ADMIN_PASSWORD','GNP-IITD-2026!')
FERNET=Fernet(os.getenv('APP_ENCRYPTION_KEY','" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "').encode())
def encrypt_secret(value):
    return FERNET.encrypt(value.encode()).decode() if value else ''
def decrypt_secret(value):
    return FERNET.decrypt(value.encode()).decode() if value else ''
ALL_PAGES=['Overview','Analytics & health','Create collection','Tasks','Feedback explorer','Admin controls']
def _b64(data): return base64.urlsafe_b64encode(data).decode().rstrip('=')
def _password_hash(password, salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()
    return salt+'$'+digest
def _verify_password(password, stored):
    try:
        salt,digest=stored.split('$',1)
        return hmac.compare_digest(_password_hash(password,salt).split('$',1)[1],digest)
    except Exception: return False
def _make_token(user):
    payload={'sub':user['username'],'role':user['role'],'permissions':user['permissions'],'exp':int(time.time())+43200}
    raw=json.dumps(payload,separators=(',',':')).encode(); body=_b64(raw)
    sig=_b64(hmac.new(TOKEN_SECRET,body.encode(),hashlib.sha256).digest())
    return body+'.'+sig
def _decode_token(token):
    try:
        body,sig=token.split('.',1); expected=_b64(hmac.new(TOKEN_SECRET,body.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(sig,expected): return None
        payload=json.loads(base64.urlsafe_b64decode(body+'='*((4-len(body)%4)%4)))
        if payload.get('exp',0)<time.time(): return None
        return payload
    except Exception: return None
@app.on_event('startup')
def seed_admin():
    with psycopg.connect(DB) as conn:
        # Upgrade databases created by earlier demo ZIPs without deleting user data.
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'unknown'")
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS trust_score INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS verification_details JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute('''CREATE TABLE IF NOT EXISTS platform_credentials (platform TEXT PRIMARY KEY, encrypted_values JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
        conn.execute('''CREATE TABLE IF NOT EXISTS app_users (id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')), permissions JSONB NOT NULL DEFAULT '[]'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
        exists=conn.execute('SELECT id FROM app_users WHERE username=%s',(DEFAULT_ADMIN,)).fetchone()
        if not exists:
            conn.execute('INSERT INTO app_users(username,password_hash,role,permissions) VALUES (%s,%s,\'admin\',%s)',(DEFAULT_ADMIN,_password_hash(DEFAULT_ADMIN_PASSWORD),json.dumps(ALL_PAGES)))
@app.middleware('http')
async def require_login(request: Request, call_next):
    public=('/api/auth/login','/health','/metrics','/docs','/openapi.json','/redoc')
    if request.url.path not in public:
        auth=request.headers.get('authorization','')
        token=auth[7:] if auth.lower().startswith('bearer ') else ''
        user=_decode_token(token) if token else None
        if not user: return Response(content='Authentication required or session expired',status_code=401,media_type='text/plain')
        request.state.user=user
        if user.get('role')!='admin':
            path=request.url.path
            required=None
            if path.startswith('/api/admin/'): required='Admin controls'
            elif path.startswith('/api/tasks/') and request.method=='POST': required='Tasks'
            elif path=='/api/tasks' and request.method=='POST': required='Create collection'
            elif path=='/api/tasks' and request.method=='GET': required='Tasks|Overview'
            elif path=='/api/feedback' and request.method=='GET': required='Feedback explorer|Overview'
            elif path=='/api/summary' and request.method=='GET': required='Overview|Analytics & health'
            if required and not any(x in user.get('permissions',[]) for x in required.split('|')):
                return Response(content='This account does not have permission to perform this action.',status_code=403,media_type='text/plain')
    return await call_next(request)
@app.post('/api/auth/login')
def login(body: dict):
    username=str(body.get('username','')).strip(); password=str(body.get('password',''))
    found=rows('SELECT username,password_hash,role,permissions FROM app_users WHERE username=%s',(username,))
    if not found or not _verify_password(password,found[0]['password_hash']): raise HTTPException(401,'Invalid username or password')
    user=found[0]; permissions=user['permissions'] if isinstance(user['permissions'],list) else json.loads(user['permissions'])
    return {'token':_make_token({'username':user['username'],'role':user['role'],'permissions':permissions}),'username':user['username'],'role':user['role'],'permissions':permissions}
def admin_only(request: Request):
    if getattr(request.state,'user',{}).get('role')!='admin': raise HTTPException(403,'Administrator permission required')
class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=32,pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')
    password:str=Field(min_length=10,max_length=128)
    role:str='user'
    permissions:list[str]=Field(default_factory=list)
@app.get('/api/admin/users')
def list_users(request: Request):
    admin_only(request)
    return rows('SELECT id,username,role,permissions,created_at FROM app_users ORDER BY created_at')
@app.post('/api/admin/users')
def create_user(body: UserCreate, request: Request):
    admin_only(request)
    if body.role not in ('admin','user'): raise HTTPException(400,'Role must be admin or user')
    if not set(body.permissions).issubset(set(ALL_PAGES)): raise HTTPException(400,'Unknown page permission')
    perms=ALL_PAGES if body.role=='admin' else [p for p in body.permissions if p!='Admin controls']
    try:
        with psycopg.connect(DB,row_factory=dict_row) as conn:
            return conn.execute('INSERT INTO app_users(username,password_hash,role,permissions) VALUES (%s,%s,%s,%s) RETURNING id,username,role,permissions,created_at',(body.username,_password_hash(body.password),body.role,json.dumps(perms))).fetchone()
    except psycopg.errors.UniqueViolation: raise HTTPException(409,'Username already exists')
@app.patch('/api/admin/users/{user_id}')
def update_user(user_id:int, body:dict, request:Request):
    admin_only(request)
    role=body.get('role','user'); perms=body.get('permissions',[])
    if role not in ('admin','user') or not isinstance(perms,list) or not set(perms).issubset(set(ALL_PAGES)): raise HTTPException(400,'Invalid role or permissions')
    if role=='admin': perms=ALL_PAGES
    else: perms=[p for p in perms if p!='Admin controls']
    with psycopg.connect(DB,row_factory=dict_row) as conn:
        row=conn.execute('UPDATE app_users SET role=%s,permissions=%s WHERE id=%s AND username<>%s RETURNING id,username,role,permissions,created_at',(role,json.dumps(perms),user_id,DEFAULT_ADMIN)).fetchone()
    if not row: raise HTTPException(404,'User not found or protected default admin')
    return row
@app.delete('/api/admin/users/{user_id}')
def delete_user(user_id:int, request:Request):
    admin_only(request)
    with psycopg.connect(DB) as conn:
        cur=conn.execute('DELETE FROM app_users WHERE id=%s AND username<>%s',(user_id,DEFAULT_ADMIN))
    if cur.rowcount==0: raise HTTPException(404,'User not found or protected default admin')
    return {'deleted':True}
class PlatformCredentials(BaseModel):
    youtube_api_key:str=''
    reddit_client_id:str=''
    reddit_client_secret:str=''
    reddit_user_agent:str='GNPFeedbackCollector/1.0 (academic project)'

@app.get('/api/admin/platform-credentials')
def get_platform_credentials(request:Request):
    admin_only(request)
    data={r['platform']:r['encrypted_values'] for r in rows('SELECT platform,encrypted_values FROM platform_credentials')}
    def has(platform,field):
        try: return bool(decrypt_secret(data.get(platform,{}).get(field,'')))
        except Exception: return False
    return {'youtube_configured':has('youtube','api_key'),
            'reddit_configured':has('reddit','client_id') and has('reddit','client_secret')}

@app.put('/api/admin/platform-credentials')
def save_platform_credentials(body:PlatformCredentials,request:Request):
    admin_only(request)
    # Empty inputs preserve existing values; credentials are encrypted at rest.
    supplied={'youtube':{'api_key':body.youtube_api_key},
              'reddit':{'client_id':body.reddit_client_id,'client_secret':body.reddit_client_secret,'user_agent':body.reddit_user_agent}}
    with psycopg.connect(DB,row_factory=dict_row) as conn:
        for platform,fields in supplied.items():
            old=conn.execute('SELECT encrypted_values FROM platform_credentials WHERE platform=%s',(platform,)).fetchone()
            values=old['encrypted_values'] if old else {}
            for key,value in fields.items():
                if value: values[key]=encrypt_secret(value)
            conn.execute('''INSERT INTO platform_credentials(platform,encrypted_values,updated_at)
                VALUES (%s,%s,NOW()) ON CONFLICT(platform) DO UPDATE SET encrypted_values=EXCLUDED.encrypted_values,updated_at=NOW()''',
                (platform,json.dumps(values)))
    return get_platform_credentials(request)

def live_platform_credentials():
    result={}
    for r in rows('SELECT platform,encrypted_values FROM platform_credentials'):
        for key,value in r['encrypted_values'].items():
            result[(r['platform'],key)]=decrypt_secret(value)
    return result

requests_total=Counter('feedback_api_requests_total','API requests',['endpoint'])
def rows(sql,params=()):
    with psycopg.connect(DB,row_factory=dict_row) as conn: return conn.execute(sql,params).fetchall()
class TaskCreate(BaseModel):
    name:str=Field(min_length=2,max_length=80)
    keywords:list[str]=Field(min_length=1,max_length=12)
    sources:list[str]=Field(min_length=1)
    mode:str='demo'
    interval_seconds:int=Field(default=60,ge=30,le=86400)
    batch_size:int=Field(default=20,ge=1,le=500)
    @field_validator('name')
    @classmethod
    def valid_name(cls,v):
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{1,79}',v.strip()): raise ValueError('Use 2–80 letters, numbers, spaces, dots, underscores or hyphens.')
        return v.strip()
    @field_validator('keywords')
    @classmethod
    def valid_keywords(cls,values):
        import re
        cleaned=[x.strip() for x in values]
        if not cleaned or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{1,49}',x) for x in cleaned): raise ValueError('Each keyword must be 2–50 characters and use letters, numbers, spaces, dots, underscores or hyphens.')
        if len(set(x.lower() for x in cleaned))!=len(cleaned): raise ValueError('Remove duplicate keywords.')
        return cleaned
@app.get('/health')
def health(): rows('SELECT 1'); return {'status':'ok','database':'connected'}
@app.get('/metrics')
def metrics(): return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@app.get('/api/health/services')
def services_health():
    result={'api':{'status':'healthy','detail':'FastAPI is responding'}}
    try:
        rows('SELECT 1')
        result['postgres']={'status':'healthy','detail':'Database query succeeded'}
    except Exception as exc:
        result['postgres']={'status':'unhealthy','detail':str(exc)[:160]}
    try:
        client=KafkaAdminClient(bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP','kafka:9092'),
                                request_timeout_ms=2500,api_version_auto_timeout_ms=2500)
        topics=client.list_topics(); client.close()
        result['kafka']={'status':'healthy','detail':f'Broker reachable · {len(topics)} topic(s)'}
    except Exception as exc:
        result['kafka']={'status':'unhealthy','detail':str(exc)[:160]}
    return result
@app.get('/api/summary')
def summary():
    requests_total.labels('summary').inc()
    total=rows('SELECT COUNT(*) AS n FROM feedback')[0]['n']
    sources=rows('SELECT source,COUNT(*) AS count FROM feedback GROUP BY source')
    daily=rows('SELECT DATE(collected_at) AS day,COUNT(*) AS count FROM feedback GROUP BY DATE(collected_at) ORDER BY day')
    return {'total':total,'sources':sources,'daily':daily}
@app.get('/api/feedback')
def feedback(limit:int=Query(200,ge=1,le=1000),source:str|None=None):
    if source: return rows('SELECT * FROM feedback WHERE source=%s ORDER BY collected_at DESC LIMIT %s',(source,limit))
    return rows('SELECT * FROM feedback ORDER BY collected_at DESC LIMIT %s',(limit,))
@app.get('/api/topics')
def topics(): return rows('SELECT product_query,COUNT(*) AS count FROM feedback GROUP BY product_query ORDER BY count DESC')
@app.get('/api/tasks')
def tasks(): return rows('SELECT * FROM collection_tasks ORDER BY created_at DESC')
@app.post('/api/tasks')
def create_task(task:TaskCreate):
    sources=sorted(set(task.sources))
    if not set(sources).issubset({'youtube','reddit','hackernews','stackoverflow'}):
        raise HTTPException(400,'Supported sources: youtube, reddit, hackernews and stackoverflow')
    if task.mode not in ('demo','live'):
        raise HTTPException(400,'Collection mode must be demo or live.')
    if task.mode=='live':
        creds=live_platform_credentials()
        missing=[]
        for source in sources:
            if source=='youtube' and not creds.get(('youtube','api_key')): missing.append('YouTube API key')
            if source=='reddit' and not (creds.get(('reddit','client_id')) and creds.get(('reddit','client_secret'))): missing.append('Reddit client ID and client secret')
        if missing: raise HTTPException(400,'Configure credentials in Admin controls first: '+', '.join(missing))
    keywords=[k.strip() for k in task.keywords if k.strip()]
    if not keywords: raise HTTPException(400,'Add a product keyword')
    with psycopg.connect(DB,row_factory=dict_row) as conn:
        return conn.execute("INSERT INTO collection_tasks(name,keywords,sources,mode,interval_seconds,batch_size,status) VALUES (%s,%s,%s,%s,%s,%s,'running') RETURNING *",(task.name,keywords,sources,task.mode,task.interval_seconds,task.batch_size)).fetchone()
@app.delete('/api/tasks/{task_id}')
def delete_task(task_id:int, request:Request):
    admin_only(request)
    with psycopg.connect(DB) as conn:
        cur=conn.execute('DELETE FROM collection_tasks WHERE id=%s',(task_id,))
    if cur.rowcount==0: raise HTTPException(404,'Task not found')
    return {'deleted':True,'task_id':task_id}
@app.post('/api/tasks/{task_id}/{action}')
def task_action(task_id:int,action:str):
    # Stop is terminal; pause/resume only operate on valid current states.
    transitions={
        'pause': ('running','paused'),
        'resume': ('paused','running'),
        'stop': (('running','paused'),'stopped'),
    }
    if action not in transitions:
        raise HTTPException(400,'Invalid action. Use pause, resume or stop.')
    allowed_current,new_status=transitions[action]
    with psycopg.connect(DB,row_factory=dict_row) as conn:
        if isinstance(allowed_current,tuple):
            row=conn.execute(
                'UPDATE collection_tasks SET status=%s,updated_at=NOW() WHERE id=%s AND status=ANY(%s) RETURNING *',
                (new_status,task_id,list(allowed_current))
            ).fetchone()
        else:
            row=conn.execute(
                'UPDATE collection_tasks SET status=%s,updated_at=NOW() WHERE id=%s AND status=%s RETURNING *',
                (new_status,task_id,allowed_current)
            ).fetchone()
        if not row:
            exists=conn.execute('SELECT status FROM collection_tasks WHERE id=%s',(task_id,)).fetchone()
            if not exists: raise HTTPException(404,'Task not found')
            raise HTTPException(409,f"Cannot {action} a task in '{exists['status']}' status.")
    return row
