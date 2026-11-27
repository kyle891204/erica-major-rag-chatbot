# AWS 환경 실행 및 운영

## 3주차 MVP 배포

기존 서울 리전 EC2와 프로젝트 버킷 및 벡터 인덱스를 재사용한다. 아래 명령은 2주차 자원 상태 파일이 있는 AWS CloudShell을 기준으로 한다. 해당 프로젝트 자원만 사용한다.

```sh
export AWS_REGION=ap-northeast-2
state=~/erica-week2-state.json
instance=$(jq -er .instance_id "$state")
bucket=$(jq -er .bucket "$state")
aws ec2 start-instances --instance-ids "$instance" --query 'StartingInstances[0].CurrentState.Name' --output text
aws ec2 wait instance-running --instance-ids "$instance"
aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$instance" --query 'InstanceInformationList[0].PingStatus' --output text
```

SSM 상태가 `Online`이면 CloudShell에서 아래 명령을 실행한다. GitHub에 게시된 3주차 브랜치의 커밋을 설치하며 기존 권한과 포트를 사용한다.

```sh
repo=/opt/erica-major-rag-chatbot
branch=refs/heads/week3/rag-mvp
params=$(jq -n --arg repo "$repo" --arg branch "$branch" --arg bucket "$bucket" '{
  executionTimeout: ["1200"],
  commands: [
    "set -e",
    ("git -C " + $repo + " fetch origin " + $branch),
    ("commit=$(git -C " + $repo + " rev-parse FETCH_HEAD)"),
    "release=$(mktemp)",
    "trap \"rm -f $release\" EXIT",
    ("git -C " + $repo + " show \"$commit:deploy/update_mvp.sh\" > \"$release\""),
    ("bash \"$release\" \"$commit\" " + ($bucket | @sh))
  ]}')
command_id=$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
  --parameters "$params" --query Command.CommandId --output text)
aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" \
  --query '{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}'
```

`Success`가 되면 아래에서 공인 IPv4를 확인한다. `curl` 및 브라우저의 주소에서 메인 화면과 대표 질문의 답변·출처를 확인한다. 기존 인스턴스의 공인 IP는 재시작 후 변경될 수 있다.

```sh
ip=$(aws ec2 describe-instances --instance-ids "$instance" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "http://$ip:8000/"
curl --fail "http://$ip:8000/health"
```

MVP 적재 경로는 S3의 `handbook/<version>/source.json`과 `chunks.json`이다. 벡터 적재 후 같은 경로에 `ready.json`을 기록한다. 적재는 결정적인 버전과 키를 사용해 같은 편람으로 재시도할 수 있다. 연동 확인에서 실패하면 배포 스크립트가 이전 EC2 서비스 설정과 커밋을 복구한다.

## 2주차 환경 기록

이 단계는 EC2에서 기본 API가 유지되고 AWS 자원에 역할로 접근할 수 있는지 확인한다. 학사 편람 검색과 답변을 수행하는 RAG 전체 기능은 후속 구현 범위다. 실제 생성 여부와 검증 결과는 환경 구성 보고서를 따른다.

## 개발 환경

Python 3.12를 사용한다. 가상환경에 설치한 의존성은 `requirements.lock.txt`로 고정한다.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
curl -i http://127.0.0.1:8000/health
```

응답은 `{"status":"ok","service":"erica-major-rag-chatbot"}`이다. 이 응답은 웹 서버 실행만 확인하며, AWS 의존 서비스나 RAG 파이프라인 상태를 검사하지 않는다.

## 배포 구성

- 리전은 서울 `ap-northeast-2`다.
- EC2는 Amazon Linux 2023 arm64, t4g.micro, 암호화된 gp3 8GiB를 사용한다. CPU 크레딧은 Standard로 설정해 초과 크레딧 요금을 피한다.
- 관리 접속은 Systems Manager를 사용한다. SSH 포트와 키 페어는 사용하지 않는다.
- 보안 그룹은 확인 API용 TCP 8000만 외부에 허용한다. 현재 공개되는 기능은 `/health`뿐이다. 실제 사용자 질문을 다루기 전에는 HTTPS와 접근 제어를 검토한다.
- 문서 S3 버킷은 퍼블릭 액세스 차단 4개 항목과 SSE-S3 암호화를 사용한다.
- 벡터 인덱스는 Titan Text Embeddings V2, 1024차원, 정규화, float32, cosine을 기준으로 구성한다.
- Nova Micro는 서울 Bedrock Runtime 엔드포인트에서 `apac.amazon.nova-micro-v1:0` 추론 프로파일로 호출한다. 고정된 단일 처리 리전을 주장하지 않는다.
- 모든 장기 비밀정보는 소스에 저장하지 않는다. EC2는 인스턴스 역할을 사용한다. 초기 환경 생성은 현재 콘솔의 승인된 로그인 주체로 수행하며, 루트 계정 작업을 일상 운영 절차로 삼지 않는다.

## 설치 절차

현재 프로젝트용으로 승인된 계정에서 `provision.py`를 실행한다. 이 프로그램은 현재 콘솔 로그인 주체를 결과에 기록하고, 생성 결과를 CloudShell 홈의 `erica-week2-state.json`에 저장한다. 이미 생성된 자원은 상태를 확인하여 이어서 처리한다. 중간 실패 시 해당 상태와 실제 AWS 자원을 먼저 비교한다.

```sh
python3 deploy/provision.py
```

EC2 사용자 데이터는 GitHub의 특정 커밋을 가져와 `deploy/install.sh`를 실행한다. CloudWatch Agent는 `/var/log/erica-api/api.log`를 `/erica-major-rag-chatbot/api` 로그 그룹으로 보낸다. 로그 보존 기간은 7일이다.

## 서버 시작과 재시작

AWS 콘솔의 EC2 인스턴스에서 연결 → Session Manager로 접속하거나, 허가된 관리자 역할로 SSM Run Command를 실행한다.

```sh
sudo systemctl start erica-api
sudo systemctl restart erica-api
sudo systemctl status erica-api --no-pager
sudo systemctl is-enabled erica-api
sudo tail -n 30 /var/log/erica-api/api.log
sudo systemctl status amazon-cloudwatch-agent --no-pager
```

관리자는 프로젝트 인스턴스에 대한 SSM Run Command 권한이 필요하다. 대화형 Session Manager 사용에는 관리자의 StartSession 권한이 필요하다. EC2 실행 역할에 연결된 AmazonSSMManagedInstanceCore는 인스턴스 등록·관리 통신을 위한 권한이다.

## 역할 기반 연동 확인

EC2 내부에서 실행한다. 이 프로그램은 EC2 인스턴스 역할을 확인하고 S3 쓰기·읽기, Titan 1024차원 생성, 별도 테스트 벡터 적재·검색, Nova 교차 리전 생성 호출을 수행한다.

```sh
/opt/erica-major-rag-chatbot/.venv/bin/python /opt/erica-major-rag-chatbot/deploy/verify_runtime.py
```

시험용 자료는 `tests/week2/`, 벡터 키는 `test-only/week2/`, 데이터셋 값은 `week2-test` 또는 `week2-ec2-test`를 사용한다. 실제 편람 적재 시에는 `dataset=handbook`처럼 별도 값을 부여하고 운영 검색에서 해당 값으로 필터링해야 한다. 시험 자료를 학사 근거로 사용하지 않는다.

## 로그와 데이터 설계

API 로그는 서버가 새로 만든 요청 ID, 정규화된 경로 구분, HTTP 메서드, 상태 코드, 처리 시간과 오류 여부를 기록한다. 원문 질문, 쿼리 문자열, IP 주소, 헤더와 인증정보는 기록하지 않는다.

후속 편람 적재 시 `text`는 비필터 메타데이터에 저장하고 `item_name`, `source_url`, `revision_date`, `dataset`을 함께 보존한다. 본문에는 표 제목·적용 대상·예외 조건을 붙여 문맥이 유지되도록 분할한다. 인덱스의 실제 모드별 메타데이터 제한을 적용하며, 우선 전체 UTF-8 직렬화 메타데이터를 32KiB 이하, 필터 메타데이터를 2KiB 이하로 제한하는 보수적인 분할 기준을 적용한다. 큰 조각은 나누고 원본은 S3에 보존한다. 문서와 질문은 같은 Titan 모델·1024차원·정규화 설정을 사용한다.

## 비용 관리

EC2 가동, EBS 저장, 공인 IPv4, S3 및 S3 Vectors 저장·요청, CloudWatch Logs, Bedrock 호출에 비용이 발생할 수 있다. 크레딧과 무료 적용 여부는 계정의 청구 화면에서 별도로 확인한다. 서버를 중지하면 EC2 컴퓨팅은 중지되지만 EBS와 저장소 등은 유지된다. 공인 IP는 중지·재시작 시 달라질 수 있다. 자원 삭제는 별도 결정 후 수행한다.

## 검증 후 중지와 다시 시작

2026년 11월 22일 외부 API 응답과 EC2 역할 연동을 검증한 뒤 비용 절감을 위해 인스턴스를 중지했다. 중지 상태에서는 API에 접속되지 않는다. 실제 검증 당시 주소와 설정값은 제출용 보고서에서 확인한다.

서울 EC2 콘솔에서 프로젝트 이름이 붙은 인스턴스를 선택한 뒤 인스턴스 상태 → 인스턴스 시작을 선택한다. 실행 상태가 된 뒤 새 공인 IPv4 주소를 확인하고 `http://새주소:8000/health`로 접속한다. systemd가 API를 자동으로 시작한다. 검증을 마치면 같은 메뉴에서 인스턴스 중지를 선택한다. 인스턴스 종료는 자원 삭제 동작이므로 중지와 구분한다.

조회한 서울 온디맨드 요금은 t4g.micro 시간당 US$0.0104, 공인 IPv4 시간당 US$0.005, gp3 월 GB당 US$0.0912다. 730시간 상시 가동과 디스크 8GiB 기준 기본 합계는 약 US$11.97이며 저장소·로그·모델 사용량과 세금은 별도다. 중지한 동안 8GiB 디스크의 월 환산 비용은 약 US$0.73이다.
