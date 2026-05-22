from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.shared.contracts import contract_schema_bundle

    output = ROOT / "schemas" / "cascade-contracts.schema.json"
    output.write_text(json.dumps(contract_schema_bundle(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
