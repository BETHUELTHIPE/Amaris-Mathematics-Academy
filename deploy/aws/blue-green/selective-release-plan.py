"""Conservative changed-path release planner; never deploys or grants access."""
import json
import sys

COMPONENTS = {"frontend", "backend", "worker", "scheduler", "gateway"}

def plan(paths):
    result = set()
    review = False
    for path in paths:
        if path.startswith("frontend/"):
            result.add("frontend")
        elif path.startswith("backend/"):
            result.update(("backend", "worker", "scheduler"))
            if "/migrations/" in path or path.endswith("Dockerfile"):
                review = True
        elif path.startswith("deploy/aws/blue-green/proxy/"):
            result.add("gateway")
        elif path.startswith("docs/") or path in ("README.md", ".gitignore"):
            continue
        else:
            # Shared configuration, CI, unknown paths: fail conservative.
            result.update(COMPONENTS)
            review = True
    return {"build_components": sorted(result), "manual_review": review,
            "deployment": "native-ecs-blue-green", "deploy_allowed": False}

if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        assert plan(["frontend/app/page.tsx"])["build_components"] == ["frontend"]
        assert plan(["backend/content/tasks.py"])["build_components"] == ["backend","scheduler","worker"]
        assert plan(["backend/content/migrations/001.py"])["manual_review"]
        assert plan(["deploy/aws/blue-green/proxy/Dockerfile"])["build_components"] == ["gateway"]
        assert plan([".github/workflows/release.yml"])["build_components"] == sorted(COMPONENTS)
        assert not plan(["README.md"])["build_components"]
        assert not plan(["frontend/app/page.tsx"])["deploy_allowed"]
        print("PASS: seven selective release plan assertions")
    else:
        print(json.dumps(plan(sys.stdin.read().split("\0")[:-1]), indent=2))
