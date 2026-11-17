"""Envoltorio mínimo de GitHub CLI (`gh`) para los scripts de releases.

En GitHub Actions `gh` está instalado y usa GH_TOKEN. Los tests lo reemplazan
por un `gh` falso en el PATH.
"""

from __future__ import annotations

import json
import subprocess


class ErrorGh(RuntimeError):
    pass


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ErrorGh(f"gh {' '.join(args)} falló ({r.returncode}): {r.stderr.strip()}")
    return r


def releases() -> list[dict]:
    """Releases del repo (incluye borradores), de la más nueva a la más vieja."""
    r = gh("release", "list", "--limit", "200", "--json", "tagName,isDraft,isLatest,isPrerelease,createdAt")
    return sorted(json.loads(r.stdout or "[]"), key=lambda x: x["createdAt"], reverse=True)


def existe_release(tag: str) -> bool:
    return gh("release", "view", tag, "--json", "tagName", check=False).returncode == 0


def assets(tag: str) -> list[str]:
    r = gh("release", "view", tag, "--json", "assets")
    return [a["name"] for a in json.loads(r.stdout)["assets"]]
