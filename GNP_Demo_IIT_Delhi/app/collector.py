import os, json, time, random, logging, psycopg
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from psycopg.rows import dict_row
from .common import now, digest
from .sources import collect_live
from cryptography.fernet import Fernet

logging.basicConfig(level=logging.INFO)
BOOT=os.getenv('KAFKA_BOOTSTRAP','kafka:9092')
DB=os.getenv('DATABASE_URL','postgresql://feedback_app:local_dev_change_me@postgres:5432/feedback')
FERNET=Fernet(os.getenv('APP_ENCRYPTION_KEY','" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "').encode())

def load_platform_credentials():
    with psycopg.connect(DB,row_factory=dict_row) as conn:
        rows=conn.execute('SELECT platform,encrypted_values FROM platform_credentials').fetchall()
    for row in rows:
        for key,value in row['encrypted_values'].items():
            plain=FERNET.decrypt(value.encode()).decode()
            if row['platform']=='youtube' and key=='api_key': os.environ['YOUTUBE_API_KEY']=plain
            if row['platform']=='reddit' and key=='client_id': os.environ['REDDIT_CLIENT_ID']=plain
            if row['platform']=='reddit' and key=='client_secret': os.environ['REDDIT_CLIENT_SECRET']=plain
            if row['platform']=='reddit' and key=='user_agent': os.environ['REDDIT_USER_AGENT']=plain

def connect():
    while True:
        try:
            return KafkaProducer(bootstrap_servers=BOOT,value_serializer=lambda v:json.dumps(v).encode(),retries=5,acks='all')
        except NoBrokersAvailable:
            logging.info('Waiting for Kafka'); time.sleep(3)

def make_demo_records(task):
    samples=['Battery life is excellent and lasts all day!','Sound quality is great for the price.',
      'Bluetooth disconnects frequently during calls.','Comfortable for long listening sessions.',
      'Customer support did not resolve my issue.','Excellent value for money.',
      'The microphone quality needs improvement.','Setup was simple and pairing was fast.']
    for i in range(task['batch_size']):
        source=task['sources'][i%len(task['sources'])]
        sid=f"demo-task{task['id']}-{int(time.time())}-{i}"
        yield {'source':source,'source_id':sid,'product_query':task['keywords'][i%len(task['keywords'])],
          'text':random.choice(samples),'url':None,'created_at':now(),'engagement':0,
          'author_hash':None,'collected_at':now(),'verification_status':'demo_unverified',
          'trust_score':0,'verification_details':{'retrieval':'synthetic_demo','note':'Synthetic sample; not collected from the named platform.'}}

def main():
    producer=connect()
    while True:
        try:
            with psycopg.connect(DB,row_factory=dict_row) as conn:
                active=conn.execute("SELECT * FROM collection_tasks WHERE status='running' AND (last_run_at IS NULL OR last_run_at <= NOW()-make_interval(secs => interval_seconds))").fetchall()
            for task in active:
                try:
                    records=list(make_demo_records(task)) if task['mode']=='demo' else (load_platform_credentials() or collect_live(task))
                    for record in records:
                        producer.send('feedback.raw',record)
                    producer.flush()
                    with psycopg.connect(DB) as conn:
                        conn.execute('UPDATE collection_tasks SET last_run_at=NOW(),records_published=records_published+%s,updated_at=NOW() WHERE id=%s',(len(records),task['id']))
                    logging.info('Task %s (%s) published %s events',task['id'],task['mode'],len(records))
                except Exception:
                    logging.exception('Collection task %s failed; task remains available for retry',task['id'])
                    with psycopg.connect(DB) as conn:
                        conn.execute('UPDATE collection_tasks SET last_run_at=NOW(),updated_at=NOW() WHERE id=%s',(task['id'],))
        except Exception:
            logging.exception('Collector polling failed')
        time.sleep(5)

if __name__=='__main__': main()
