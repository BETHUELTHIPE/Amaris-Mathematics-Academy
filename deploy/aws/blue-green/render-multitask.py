"""Split the current six-container staging task into stateless web and singleton jobs.

This renderer is offline and does not register ECS definitions or change traffic.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("web_renderer", root / "render-stateless-task.py")
web_renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_renderer)

def render(original):
    original = copy.deepcopy(original)
    names = {c["name"]: c for c in original["containerDefinitions"]}
    expected = {"backend", "frontend", "cms", "valkey", "celery-worker", "celery-beat"}
    if set(names) != expected or len(original["containerDefinitions"]) != len(expected):
        raise ValueError("Expected current six-container staging task")
    if {v["name"] for v in original["volumes"]} != {
        "valkey-data", "cms-proxy", "proxy-headers", "staging-celery-config"
    }:
        raise ValueError("Unexpected host volumes")
    original["containerDefinitions"] = [c for c in original["containerDefinitions"]
                                        if c["name"] not in {"celery-worker", "celery-beat"}]
    original["volumes"] = [v for v in original["volumes"] if v["name"] != "staging-celery-config"]
    web = web_renderer.render(original, names["backend"]["image"], names["frontend"]["image"], None)
    backend = next(c for c in web["containerDefinitions"] if c["name"] == "backend")
    module = (root.parent / "celery" / "staging_celery.py").read_text(encoding="utf-8")
    if "AMARIS_CELERY_CONFIG" in module.splitlines():
        raise ValueError("Unsafe module delimiter")
    wrapper = backend["entryPoint"][2]
    if wrapper.count('exec "$@"') != 1:
        raise ValueError("Unexpected runtime wrapper")
    wrapper = wrapper.replace('exec "$@"', "cat > /tmp/staging_celery.py <<'AMARIS_CELERY_CONFIG'\n"
                              + module.rstrip() + "\nAMARIS_CELERY_CONFIG\n"
                              + 'export PYTHONPATH="/tmp:/app"\nexec "$@"')
    jobs = copy.deepcopy(web)
    jobs["family"] = "amaris-ecs-staging-singleton-jobs"
    jobs.pop("placementConstraints", None)
    jobs.pop("cpu", None)
    jobs.pop("memory", None)
    jobs["containerDefinitions"] = []
    for name in ("celery-worker", "celery-beat"):
        c = copy.deepcopy(names[name])
        c["entryPoint"] = copy.deepcopy(backend["entryPoint"])
        c["entryPoint"][2] = wrapper
        c["secrets"] = copy.deepcopy(backend["secrets"])
        c["essential"] = True
        c.pop("mountPoints", None)
        c.pop("volumesFrom", None)
        c["dependsOn"] = [d for d in c.get("dependsOn", []) if d["containerName"] != "valkey"]
        if not c["dependsOn"]:
            c.pop("dependsOn", None)
        if c.get("links") or c.get("portMappings"):
            raise ValueError("Unexpected jobs network or local state")
        jobs["containerDefinitions"].append(c)
    return {"web": web, "jobs": jobs}

if __name__ == "__main__":
    json.dump(render(json.load(sys.stdin)), sys.stdout, indent=2)
    print()
