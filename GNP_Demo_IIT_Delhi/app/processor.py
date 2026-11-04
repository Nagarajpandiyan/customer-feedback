import os, json, time, logging
from kafka import KafkaConsumer, KafkaProducer
import psycopg
from psycopg.types.json import Jsonb
from .common import clean_text, digest, now

logging.basicConfig(level=logging.INFO)
BOOTSTRAP=os.getenv("KAFKA_BOOTSTRAP","kafka:9092")
DB=os.getenv("DATABASE_URL","postgresql://feedback_app:local_dev_change_me@postgres:5432/feedback")

def ensure_columns():
    with psycopg.connect(DB) as conn:
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'unknown'")
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS trust_score INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS verification_details JSONB NOT NULL DEFAULT '{}'::jsonb")

def main():
    while True:
        try:
            ensure_columns()
            consumer=KafkaConsumer("feedback.raw",bootstrap_servers=BOOTSTRAP,
              value_deserializer=lambda b:json.loads(b.decode()),group_id="feedback-cleaners-v1",
              auto_offset_reset="earliest",enable_auto_commit=False)
            producer=KafkaProducer(bootstrap_servers=BOOTSTRAP,
              value_serializer=lambda v:json.dumps(v).encode(),acks="all")
            logging.info("Processor connected")
            for msg in consumer:
                r=msg.value
                r["text"]=clean_text(r.get("text"))
                if not r["text"]:
                    consumer.commit(); continue
                r["text_hash"]=digest(r["text"]); r["processed_at"]=now()
                producer.send("feedback.cleaned",r).get(timeout=30)
                with psycopg.connect(DB) as conn:
                    conn.execute("""INSERT INTO feedback
                      (source,source_id,product_query,text,text_hash,url,created_at,engagement,author_hash,collected_at,verification_status,trust_score,verification_details)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT (source,source_id) DO NOTHING""",
                      (r["source"],r["source_id"],r["product_query"],r["text"],r["text_hash"],r.get("url"),
                       r.get("created_at"),r.get("engagement",0),r.get("author_hash"),r.get("collected_at",now()),
                       r.get("verification_status","unknown"),int(r.get("trust_score",0)),
                       Jsonb(r.get("verification_details",{}))))
                consumer.commit()
        except Exception:
            logging.exception("Processor reconnecting"); time.sleep(5)

if __name__=="__main__": main()
