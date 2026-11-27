"""Offline split-service candidate renderer; never deploys or prints runtime secrets."""
import copy
import re

PORTS = {"backend": 8000, "frontend": 3000, "cms": 8080}
ALIASES = {"backend": "amaris-backend", "frontend": "amaris-frontend", "cms": "amaris-gateway"}
ALLOWED = {"family", "networkMode", "requiresCompatibilities", "runtimePlatform",
           "executionRoleArn", "taskRoleArn", "cpu", "memory", "ephemeralStorage",
           "placementConstraints"}

def render(task):
    if task.get("networkMode") != "awsvpc" or task.get("volumes"):
        raise ValueError("Expected stateless awsvpc task")
    if task.get("runtimePlatform", {}).get("cpuArchitecture") != "ARM64":
        raise ValueError("Expected ARM64")
    containers = {c["name"]: copy.deepcopy(c) for c in task["containerDefinitions"]}
    if set(containers) != set(PORTS):
        raise ValueError("Unexpected containers")
    result = {}
    for name, c in containers.items():
        if not re.search(r"@sha256:[a-f0-9]{64}$", c["image"]):
            raise ValueError("Immutable image required")
        if c.get("mountPoints") or c.get("volumesFrom") or c.get("links"):
            raise ValueError("Local state not permitted")
        c.pop("dependsOn", None)
        mappings = c.setdefault("portMappings", [])
        if not mappings:
            mappings.append({"containerPort": PORTS[name], "protocol": "tcp"})
        if len(mappings) != 1 or mappings[0]["containerPort"] != PORTS[name]:
            raise ValueError("Unexpected port mapping")
        mappings[0].update(name=name+"-http", appProtocol="http")
        if name == "frontend":
            entry = c.get("entryPoint") or []
            if len(entry) < 3 or entry[:2] != ["/bin/sh","-ec"] or entry[2].count('exec "$@"') != 1:
                raise ValueError("Review frontend settings loader")
            if not any(s["name"]=="AMARIS_RUNTIME_ENV" for s in c.get("secrets",[])):
                raise ValueError("Expected protected runtime environment")
            entry[2] = entry[2].replace('exec "$@"', 'export CMS_API_URL=http://amaris-gateway:8080/api/v1/\nexec "$@"')
        if name == "cms":
            commands = c.get("command") or []
            if len(commands)!=1 or "127.0.0.1:8000" not in commands[0] or "127.0.0.1:3000" not in commands[0]:
                raise ValueError("Review embedded gateway configuration")
            commands[0]=commands[0].replace("127.0.0.1:8000","amaris-backend:8000").replace("127.0.0.1:3000","amaris-frontend:3000")
        doc = {k:copy.deepcopy(v) for k,v in task.items() if k in ALLOWED and v is not None}
        doc["family"]="amaris-ecs-staging-independent-"+("gateway" if name=="cms" else name)
        doc["containerDefinitions"]=[c]
        doc["volumes"]=[]
        result[name]=doc
    return result

def self_test():
    digest="repo@sha256:"+"a"*64
    task={"networkMode":"awsvpc","runtimePlatform":{"cpuArchitecture":"ARM64"},"volumes":[],
          "containerDefinitions":[
          {"name":"backend","image":digest,"secrets":[{"name":"DB","valueFrom":"test"}]},
          {"name":"frontend","image":digest,"entryPoint":["/bin/sh","-ec",'unset AMARIS_RUNTIME_ENV\nexec "$@"',"amaris-settings"],"secrets":[{"name":"AMARIS_RUNTIME_ENV","valueFrom":"test"}],"dependsOn":[{"containerName":"cms","condition":"START"}]},
          {"name":"cms","image":digest,"command":["proxy_pass http://127.0.0.1:8000; proxy_pass http://127.0.0.1:3000;"]}]}
    output=render(task)
    assert set(output)==set(PORTS)
    assert all(len(x["containerDefinitions"])==1 for x in output.values())
    assert "export CMS_API_URL=http://amaris-gateway:8080/api/v1/" in output["frontend"]["containerDefinitions"][0]["entryPoint"][2]
    assert "amaris-frontend:3000" in output["cms"]["containerDefinitions"][0]["command"][0]
    assert output["backend"]["containerDefinitions"][0]["secrets"]==task["containerDefinitions"][0]["secrets"]
    assert "CMS_API_URL" not in task["containerDefinitions"][1]["entryPoint"][2]
    assert "dependsOn" not in output["frontend"]["containerDefinitions"][0]
    assert all(x["containerDefinitions"][0]["portMappings"][0]["containerPort"]==PORTS[n] for n,x in output.items())
    task["volumes"]=[{"name":"unsafe"}]
    try:
        render(task)
    except ValueError:
        pass
    else:
        raise AssertionError("Host state accepted")
    print("PASS: nine split-task assertions")

if __name__=="__main__":
    self_test()
