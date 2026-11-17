#!/usr/bin/env python3
"""Native dependency companion to cargo-deny; same allowlist/scoped exceptions."""
import hashlib
import json
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        import re
        class MiniToml:
            @staticmethod
            def loads(s):
                data = {"licenses": {"allow": [], "exceptions": []}}
                in_licenses, in_allow, in_exception = False, False, False
                cur_exc = {}
                for line in s.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line == "[licenses]":
                        in_licenses, in_exception = True, False
                    elif line == "[[licenses.exceptions]]":
                        in_licenses, in_exception = False, True
                        cur_exc = {}
                        data["licenses"]["exceptions"].append(cur_exc)
                    elif line.startswith("["):
                        in_licenses, in_exception = False, False
                    elif in_licenses:
                        if line.startswith("allow"):
                            in_allow = True
                        if in_allow:
                            data["licenses"]["allow"].extend(re.findall(r'"([^"]+)"', line))
                            if "]" in line:
                                in_allow = False
                    elif in_exception and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if v.startswith("["):
                            cur_exc[k] = re.findall(r'"([^"]+)"', v)
                        else:
                            cur_exc[k] = v.strip('"')
                return data
        tomllib = MiniToml()
import sys

def require(condition, message):
    if not condition:
        raise SystemExit(message)


here = Path(__file__).resolve().parent
policy = tomllib.loads((here.parent.parent / "deny.toml").read_text())["licenses"]
dep = json.loads((here / "dependencies.json").read_text())
allowed = set(policy["allow"])
for exception in policy.get("exceptions", []):
    if exception["name"] == dep["name"]:
        allowed.update(exception["allow"])
for filename, license in dep["licenses"].items():
    require(license["spdx"] in allowed, f"{dep['name']}: {license['spdx']} not allowed")
    require(hashlib.sha256((here / "licenses" / filename).read_bytes()).hexdigest() == license["sha256"], filename)
    downloaded = (Path(sys.argv[1]) if len(sys.argv) > 1 else here / "build") / "_deps" / "aspl-src" / filename
    if downloaded.exists():
        require(downloaded.read_bytes() == (here / "licenses" / filename).read_bytes(), filename)
cmake = (here / "CMakeLists.txt").read_text()
require(dep["revision"] in cmake and dep["archive_sha256"] in cmake, "CMake source pin mismatch")
print(f"{dep['name']} {dep['version']}: MIT + scoped Apple-MIT; checksums and notices verified")
