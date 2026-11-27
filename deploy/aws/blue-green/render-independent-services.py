"""Render independent candidate task definitions. Never registers or starts tasks.

The gateway and frontend must be Service Connect clients; backend/frontend
are servers. Private routing and health contracts must be reviewed and tested
before registering any candidate. Input and outputs can contain sensitive
runtime configuration; keep them in memory or a protected local directory.
"""
import copy
import re

ALIASES = {"backend": "amaris-backend", "frontend": "amaris-frontend"}
PORTS = {"backend": 8000, "frontend": 3000}
ALLOWED = {"family", "networkMode", "requiresCompatibilities", "runtimePlatform",
           "executionRoleArn", "taskRoleArn", "cpu", "memory", "ephemeralStorage",
           "placementConstraints"}

def render(task):
    if task.get("networkMode") != "awsvpc" or task.get("volumes"):
        raise ValueError("Expected stateless awsvpc task")
    if task.get("runtimePlatform", {}).get("cpuArchitecture") != "ARM64":
        raise ValueError("Expected ARM64")
    containers = {c["name"]: copy.deepcopy(c) for c in task["containerDefinitions"]}
    if set(containers) != {"backend", "frontend", "cms"}:
        raise ValueError("Unexpected containers")
    result = {}
    for name, c in containers.items():
        if not re.search(r"@sha256:[a-f0-9]{64}$", c["image"]):
            raise ValueError("Immutable image required")
        if c.get("mountPoints") or c.get("volumesFrom") or c.get("links"):
            raise ValueError("Local state not permitted")
        c.pop("dependsOn", None)
        if name in PORTS:
            mappings = c.get("portMappings", [])
            selected = [p for p in mappings if p["containerPort"] == PORTS[name]]
            if len(selected) != 1:
                raise ValueError("Unexpected port mapping for " + name)
            selected[0]["name"] = name + "-http"
            selected[0]["appProtocol"] = "http"
        if name == "frontend":
            settings = [x for x in c.get("environment", []) if x["name"] == "CMS_API_URL"]
            if len(settings) != 1:
                raise ValueError("Review actual frontend CMS configuration")
            old = settings[0]["value"]
            # Preserve API path and require the known local gateway endpoint.
            m = re.fullmatch(r"http://(?:localhost|127\.0\.0\.1):(?:8080|8000)(/api/v1/?)", old)
            if not m:
                raise ValueError("Unexpected CMS endpoint; manual review")
            settings[0]["value"] = "http://amaris-backend:8000" + m.group(1)
        if name == "cms":
            commands = c.get("command") or []
            if len(commands) != 1 or "127.0.0.1:8000" not in commands[0] or "127.0.0.1:3000" not in commands[0]:
                raise ValueError("Expected embedded Nginx proxy configuration")
            commands[0] = commands[0].replace("127.0.0.1:8000","amaris-backend:8000").replace("127.0.0.1:3000","amaris-frontend:3000")
        doc = {k: copy.deepcopy(v) for k,v in task.items() if k in ALLOWED and v is not None}
        # Preserve sizing if declared; new size optimization is a separate load test.
        doc["family"] = "amaris-ecs-staging-independent-" + ("gateway" if name=="cms" else name)
        doc["containerDefinitions"] = [c]
        doc["volumes"] = []
        result[name] = doc
    return result

def self_test():
    digest = "repo@sha256:" + "a"*64
    task = {"networkMode":"awsvpc","runtimePlatform":{"cpuArchitecture":"ARM64"},"volumes":[],
            "containerDefinitions":[
                {"name":"backend","image":digest,"portMappings":[{"containerPort":8000}],"secrets":[{"name":"DB","valueFrom":"test-secret"}]},
                {"name":"frontend","image":digest,"portMappings":[{"containerPort":3000}],"environment":[{"name":"CMS_API_URL","value":"http://127.0.0.1:8080/api/v1/"}],"dependsOn":[{"containerName":"cms","condition":"START"}]},
                {"name":"cms","image":digest,"command":["proxy_pass http://127.0.0.1:8000; proxy_pass http://127.0.0.1:3000;"]}]}
    output = render(task)
    assert set(output)=={"backend","frontend","cms"}
    assert all(len(x["containerDefinitions"])==1 for x in output.values())
    assert output["frontend"]["containerDefinitions"][0]["environment"][0]["value"]=="http://amaris-backend:8000/api/v1/"
    assert "amaris-frontend:3000" in output["cms"]["containerDefinitions"][0]["command"][0]
    assert output["backend"]["containerDefinitions"][0]["secrets"]==task["containerDefinitions"][0]["secrets"]
    assert task["containerDefinitions"][1]["environment"][0]["value"].startswith("http://127.")
    assert "dependsOn" not in output["frontend"]["containerDefinitions"][0]
    task["volumes"]=[{"name":"unsafe"}]
    try:
        render(task)
    except ValueError:
        pass
    else:
        raise AssertionError("Host state accepted")
    print("PASS: eight isolated split-task rendering assertions")

if __name__=="__main__":
    self_test()
