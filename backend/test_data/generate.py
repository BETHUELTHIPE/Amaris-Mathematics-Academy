"""Stream reproducible NDJSON fixtures; refuse to overwrite an existing dataset."""

import argparse
import json
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from test_data.factories import ENTITIES, SCHEMA_VERSION, Factory


def encoded(row):
    return (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()


def generate(factory, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "synthetic_only": True,
        "factory": asdict(factory),
        "files": {},
    }
    with tempfile.TemporaryDirectory(prefix=".synthetic-", dir=output.parent) as temporary:
        directory = Path(temporary) / "dataset"
        directory.mkdir()
        for entity in ENTITIES:
            digest = sha256()
            with (directory / f"{entity}.ndjson").open("xb") as stream:
                for row in factory.rows(entity):
                    data = encoded(row)
                    stream.write(data)
                    digest.update(data)
            manifest["files"][entity] = {
                "count": factory.counts[entity],
                "sha256": digest.hexdigest(),
            }
        (directory / "manifest.json").write_bytes(encoded(manifest))
        # Keep partially generated data invisible until all eight files exist.
        if output.exists():
            raise ValueError("Output already exists; choose a new directory")
        directory.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    for field, value in asdict(Factory()).items():
        parser.add_argument("--" + field.replace("_", "-"), type=int, default=value)
    args = vars(parser.parse_args())
    output = args.pop("output")
    manifest = generate(Factory(**args), output)
    print(
        json.dumps(
            {entity: item["count"] for entity, item in manifest["files"].items()},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
