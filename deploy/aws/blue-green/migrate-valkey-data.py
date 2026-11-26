"""Quiesced staging-only transfer; never deletes source keys or logs payloads."""
import json
import sys
import tempfile
import time
from redis import Redis
from redis.exceptions import ResponseError

STAGE = "startup"
ALLOWED_TYPES = {b"string", b"list", b"hash", b"set", b"zset"}

def snapshot(client):
    # BGSAVE may already be running due to the normal persistence schedule.
    deadline = time.monotonic() + 30
    if not client.info("persistence")["rdb_bgsave_in_progress"]:
        try:
            client.bgsave()
        except ResponseError:
            if not client.info("persistence")["rdb_bgsave_in_progress"]:
                raise
    while time.monotonic() < deadline:
        info = client.info("persistence")
        if not info["rdb_bgsave_in_progress"]:
            if info["rdb_last_bgsave_status"] != "ok":
                raise RuntimeError("RDB snapshot failed")
            return
        time.sleep(.25)
    raise TimeoutError("RDB snapshot did not finish")

def value(client, key, kind):
    if kind == b"string": return client.get(key)
    if kind == b"list": return client.lrange(key, 0, -1)
    if kind == b"hash": return client.hgetall(key)
    if kind == b"set": return client.smembers(key)
    if kind == b"zset": return client.zrange(key, 0, -1, withscores=True)
    raise RuntimeError("Unsupported key type")

def transfer(src, dst, key, kind, contents, ttl):
    if dst.exists(key):
        raise RuntimeError("Destination key already exists")
    with dst.pipeline(transaction=True) as tx:
        if kind == b"string": tx.set(key, contents)
        elif kind == b"list": tx.rpush(key, *contents)
        elif kind == b"hash": tx.hset(key, mapping=contents)
        elif kind == b"set": tx.sadd(key, *contents)
        elif kind == b"zset": tx.zadd(key, dict(contents))
        else: raise RuntimeError("Unsupported key type")
        if ttl >= 0:
            tx.pexpire(key, max(1, ttl))
        tx.execute()
    if value(dst, key, kind) != contents:
        raise RuntimeError("Logical data reconciliation failed")

def queue_count(client):
    return sum(client.llen(k) for k in client.scan_iter() if client.type(k) == b"list")

def main():
    global STAGE
    values = json.load(sys.stdin)
    copied = []
    old = [Redis(host="127.0.0.1",port=6379,db=db,socket_timeout=5) for db in range(4)]
    with tempfile.NamedTemporaryFile(mode="w") as ca:
        ca.write(values["ca"]); ca.flush()
        new = [Redis(host=values["ip"],port=6379,db=db,password=values["password"],ssl=True,
                     ssl_ca_certs=ca.name,ssl_cert_reqs="required",ssl_check_hostname=True,
                     socket_connect_timeout=3,socket_timeout=5) for db in range(4)]
        try:
            STAGE = "destination emptiness"
            if any(c.dbsize() for c in new):
                raise RuntimeError("Destination must be empty")
            STAGE = "unacknowledged job guard"
            if old[2].hlen("unacked") or old[2].zcard("unacked_index"):
                raise RuntimeError("Unacknowledged jobs remain")
            STAGE = "source RDB persistence"
            snapshot(old[0])
            inventory = []
            for db,(src,dst) in enumerate(zip(old,new)):
                STAGE = f"DB {db} enumeration"
                keys = list(dict.fromkeys(src.scan_iter()))
                if len(keys)>10000:
                    raise RuntimeError("Unexpectedly large keyspace")
                copied_count=0
                queue_items=0
                for key in keys:
                    kind=src.type(key)
                    if kind == b"none": continue
                    STAGE = f"DB {db} logical read ({kind.decode('ascii')})"
                    if kind not in ALLOWED_TYPES:
                        raise RuntimeError("Unsupported key type")
                    contents=value(src,key,kind)
                    ttl=src.pttl(key)
                    if contents is None or ttl == -2:
                        continue
                    if ttl >= 0 and ttl < 5000 and db in (0,1):
                        # Cache entries about to expire are reconstructable. Never skip broker/results.
                        continue
                    if db==2 and kind==b"list":
                        queue_items+=len(contents)
                    STAGE = f"DB {db} logical restore ({kind.decode('ascii')})"
                    # Destination was empty, and no application consumers are enabled.
                    copied.append((dst,key))
                    transfer(src,dst,key,kind,contents,ttl)
                    copied_count+=1
                if db==2:
                    STAGE = "broker queued-list reconciliation"
                    if queue_count(dst)!=queue_items or queue_count(src)!=queue_items:
                        raise RuntimeError("Broker queued-list reconciliation failed")
                inventory.append({"db":db,"copied_keys":copied_count,"queue_items":queue_items if db==2 else 0})
            STAGE = "destination RDB persistence"
            snapshot(new[0])
            STAGE = "source write pause"
            old[0].execute_command("CLIENT","PAUSE",600000,"WRITE")
            print("Migration snapshot verified: "+json.dumps(inventory),flush=True)
        except Exception:
            for dst,key in reversed(copied):
                dst.delete(key)
            raise

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Redis errors may include user data; expose only operation and exception class.
        reason = str(exc).lower()
        known = next((s for s in ("background save already in progress","wrongtype","unknown command","busykey","oom","readonly","noperm","loading","syntax error","disk") if s in reason), "unclassified")
        print(f"Queue migration refused at {STAGE}: {type(exc).__name__} ({known})",file=sys.stderr,flush=True)
        sys.exit(1)
