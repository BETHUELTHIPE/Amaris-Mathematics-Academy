"""Put the existing Amaris application proxy behind the ALB target group."""

import json
import sys


def main():
    task = json.load(sys.stdin)
    if task.get("family") != "amaris-ecs-staging-private-web" or task.get("networkMode") != "awsvpc":
        raise SystemExit("The existing private ECS task template is required.")
    task["family"] = "amaris-ecs-staging-alb-web"
    for volume in task["volumes"]:
        volume["host"]["sourcePath"] = volume["host"]["sourcePath"].replace("/opt/amaris-staging/vpc/", "/opt/amaris-staging/alb/")
    task["volumes"].append({"name": "proxy-headers", "host": {"sourcePath": "/opt/amaris-staging/alb/backend.inc"}})
    for container in task["containerDefinitions"]:
        if container["name"] == "cms":
            container["portMappings"] = [{"containerPort": 8080, "protocol": "tcp"}]
            container["mountPoints"].append({
                "sourceVolume": "proxy-headers", "containerPath": "/etc/nginx/conf.d/backend.inc", "readOnly": True,
            })
        else:
            container.pop("portMappings", None)
    json.dump(task, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
