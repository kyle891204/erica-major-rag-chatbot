#!/bin/bash
# Run as root on the existing Week 2 EC2 instance through Systems Manager.
set -euo pipefail
commit=${1:?Provide the full Git commit SHA}
bucket=${2:?Provide the existing project bucket name}
[[ $commit =~ ^[a-f0-9]{40}$ && $bucket =~ ^erica-major-rag-chatbot-[0-9]{12}-ap-northeast-2$ ]]
repo=/opt/erica-major-rag-chatbot
service=/etc/systemd/system/erica-api.service
env_file=/etc/erica-api/mvp.env
python="$repo/.venv/bin/python"

exec 9>/run/lock/erica-mvp-deploy.lock
flock -n 9
work=$(mktemp -d)
old_commit=$(git -C "$repo" rev-parse HEAD)
switched=0
cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 && switched )); then
    echo "MVP smoke check failed. Restoring previous service files." >&2
    git -C "$repo" checkout --detach "$old_commit" || true
    install -m 0644 "$work/old.service" "$service" || true
    if [[ -f "$work/old.env" ]]; then
      install -m 0640 "$work/old.env" "$env_file" || true
    else
      rm -f "$env_file"
    fi
    systemctl daemon-reload && systemctl restart erica-api || true
  fi
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT

git -C "$repo" diff --quiet HEAD
install -m 0644 "$service" "$work/old.service"
if [[ -f "$env_file" ]]; then
  install -m 0640 "$env_file" "$work/old.env"
fi
mkdir "$work/release"
git -C "$repo" archive "$commit" | tar -x -C "$work/release"
(
  cd "$work/release"
  "$python" -m deploy.ingest_handbook --bucket "$bucket" --output "$work/handbook.json"
)
version=$("$python" -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$work/handbook.json")
[[ $version =~ ^[a-f0-9]{16}$ ]]

switched=1
git -C "$repo" checkout --detach "$commit"
install -d -m 0750 /etc/erica-api
printf 'RAG_MODE=aws\nRAG_VECTOR_BUCKET=%s\nRAG_CORPUS_VERSION=%s\n' "$bucket" "$version" >"$work/mvp.env"
install -m 0640 "$work/mvp.env" "$env_file"
install -m 0644 "$repo/deploy/erica-api.service" "$service"
systemctl daemon-reload
systemctl restart erica-api
curl --fail --silent --show-error --retry 8 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
"$python" - <<'PY'
import json
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8000"
with urlopen(base, timeout=10) as response:
    assert "ERICA".encode() in response.read()
for question, expected in [
    ("마이크로전공은 몇 학점을 이수해야 하나요?", "answered"),
    ("오늘 안산 날씨는 어때요?", "insufficient_evidence"),
]:
    request = Request(
        base + "/api/ask", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"question": question}).encode(),
    )
    with urlopen(request, timeout=105) as response:
        answer = json.load(response)
    assert answer["mode"] == "aws" and answer["status"] == expected, answer["status"]
    assert bool(answer["sources"]) == (expected == "answered")
    if expected == "answered":
        assert "12학점" in answer["answer"] and "9학점" in answer["answer"], "Credit values missing"
    print(json.dumps({"status": expected, "sources": len(answer["sources"])}))
PY
echo "Deployed commit $commit and corpus $version"
