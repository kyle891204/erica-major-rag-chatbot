#!/bin/bash
set -euo pipefail
dnf install -y python3.12 python3.12-pip git amazon-cloudwatch-agent
id erica >/dev/null 2>&1 || useradd --system --home-dir /opt/erica-major-rag-chatbot --shell /sbin/nologin erica
install -d -m 0750 -o erica -g erica /var/log/erica-api
touch /var/log/erica-api/api.log
chown erica:erica /var/log/erica-api/api.log
chmod 0640 /var/log/erica-api/api.log
cd /opt/erica-major-rag-chatbot
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.lock.txt
chown -R root:erica /opt/erica-major-rag-chatbot
chmod -R g+rX /opt/erica-major-rag-chatbot
install -m 0644 deploy/erica-api.service /etc/systemd/system/erica-api.service
install -m 0644 deploy/cloudwatch-agent.json /opt/aws/amazon-cloudwatch-agent/etc/erica.json
cat > /etc/logrotate.d/erica-api <<'EOF'
/var/log/erica-api/api.log {
  daily
  rotate 7
  size 10M
  compress
  missingok
  notifempty
  copytruncate
  su erica erica
}
EOF
systemctl daemon-reload
systemctl enable --now erica-api
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/erica.json
curl --fail http://127.0.0.1:8000/health
