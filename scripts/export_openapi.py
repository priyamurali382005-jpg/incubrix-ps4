import pathlib

import yaml

from app.main import app

spec = app.openapi()
pathlib.Path("openapi.yaml").write_text(
    yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)
)
print("openapi", spec["openapi"], "- paths:", len(spec["paths"]))
