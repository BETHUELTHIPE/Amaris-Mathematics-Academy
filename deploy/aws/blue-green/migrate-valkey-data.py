import json
import os
import sys
import time
import tempfile
from redis import Redis

def main():
    values = json.load(sys.stdin)
    copied = []
    old = [Redis(host="127.0.0.1",port=6379,db=db,socket_timeout=5) for db in range(4)]
    with tempfile.NamedTemporaryFile(mode="w") as ca:
        ca.write(values["ca"]); ca.flush()
        new = [Redis(host=values["ip"],port=6379,db=db,password=values["password"],ssl=True,
                     ssl_ca_certs=ca.name,ssl_cert_reqs="required",ssl_check_hostname=True,
                     socket_connect_timeout=3,socket_timeout=5) for db in range(4)]
        try:
            if any(c.dbsize() for c in new):
                raise RuntimeError("Destination must be empty; refusing overwrite")
            # Source producers and worker are frozen from the host PID namespace.
            if old[2].hlen("unacked") or old[2].zcard("unacked_index"):
                raise RuntimeError("Unacknowledged jobs remain")
            old[0].save()
            inventory = []
            for db,(src,dst) in enumerate(zip(old,new)):
                keys = list(src.scan_iter())
                if len(keys)>10000:
                    raise RuntimeError("Unexpectedly large keyspace")
                copied_count=0
                queue_items=0
                for key in keys:
                    payload=src.dump(key)
                    ttl=src.pttl(key)
                    if payload is None or ttl == -2:
                        continue
                    if db==2 and src.type(key)==b"list":
                        queue_items+=src.llen(key)
                    dst.restore(key, max(1,ttl) if ttl>=0 else 0,payload,replace=False)
                    copied.append((dst,key))
                    if dst.dump(key)!=payload:
                        raise RuntimeError("Restored serialization mismatch")
                    copied_count+=1
                if db==2:
                    destination_items=sum(dst.llen(k) for k in dst.scan_iter() if dst.type(k)==b"list")
                    if destination_items!=queue_items:
                        raise RuntimeError("Broker queued-list reconciliation failed")
                inventory.append({"db":db,"copied_keys":copied_count,"queue_items":queue_items if db==2 else 0})
            # Persist both stores before resuming any source process.
            new[0].save()
            # Prevent old writers/consumers from mutating the source during ECS shutdown.
            old[0].execute_command("CLIENT","PAUSE",600000,"WRITE")
            print("Migration snapshot verified: "+json.dumps(inventory),flush=True)
        except Exception:
            for dst,key in reversed(copied):
                dst.delete(key)
            raise

try:
    main()
except Exception as exc:
    print("Queue migration refused: "+type(exc).__name__,file=sys.stderr,flush=True)
    sys.exit(1)
