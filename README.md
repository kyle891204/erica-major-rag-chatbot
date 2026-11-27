# 한양대학교 ERICA 전공 제도 안내 RAG 챗봇
한양대학교 ERICA 2026 Cloud Architecture(HY24307)

한양대학교 ERICA 학부생이 전공제도를 질문하면 학사 안내 편람을 근거로 답변하고 출처를 제공하는 RAG기반 챗봇
> 현 진행 단계: 3주차 RAG MVP 및 로컬 동작 검증

## 1. 프로젝트 개요
- **대상 사용자:** 전공·다전공 제도에 대한 정보를 알고 싶은 한양대학교 ERICA 학부생
- **해결하려는 문제:** 여러 전공 제도의 신청 조건과 이수 기준을 직접 찾아 비교해야 하는 불편함
- **서비스 목표:** 자연어 질문을 통해 필요한 제도 정보를 확인하고, 답변의 출처까지 확인할 수 있도록 지원

## 2. 안내 범위
- 다전공 제도 안내
- 마이크로전공
- 부전공
- 일반다중전공
- 융합다중전공
- 복수전공
개인별 성적, 학적 조회나 실제 전공 신청 처리 기능은 제공하지 않음.

## 3. 핵심 기능
- **제도 질문·답변:** 안내 범위에 해당하는 질문에 문서 근거로 답변
- **출처 제공:** 답변에 사용한 문서의 출처 URL과 편람 수정일 표시
- **근거 부족 안내:** 자료에서 답변 근거를 찾기 어려운 경우 확인할 수 없음을 안내

## 4. 활용 데이터
- **자료:** ERICA 통합 학사 안내 편람의 전공·다전공 관련 6개 항목
- **링크:** https://yoorhi816.github.io/erica-academic-handbook/
- **수집 방식:** 편람 페이지의 문서 데이터에서 전공 제도 6개를 추출
- **처리 방식:** 문단, 목록 항목, 표 행, FAQ 질의응답 단위로 분할하고 출처와 편람 수정일을 보존

## 5. 시스템 구성
| 구성 요소 | 서비스 또는 기술 | 역할 |
|---|---|---|
| 웹 프런트엔드 | HTML, CSS, JavaScript | 질문 입력 및 답변·출처 표시 |
| 백엔드 API | Python, FastAPI | 검색과 모델 호출, 응답 처리 |
| 실행 환경 | Amazon EC2 | 웹 및 백엔드 실행 |
| 문서 저장소 | Amazon S3 | 수집한 원본·정리 자료 저장 |
| 문서 전처리 | Python | 텍스트 추출·분할 및 벡터 적재 |
| 임베딩 모델 | Amazon Bedrock — Titan Text Embeddings V2 | 문서와 질문을 벡터로 변환 |
| 벡터 검색 저장소 | Amazon S3 Vectors | 문서 벡터와 근거 정보 저장·검색 |
| 생성 모델 | Amazon Bedrock — Nova Micro | 검색된 문서에 근거한 답변 생성 |
| 접근 관리 | AWS IAM | 처리 역할에 필요한 권한 부여 |
| 로그 수집 | CloudWatch Agent, CloudWatch Logs | 처리 결과·지연 시간·오류 기록 |
기본 배포 리전은 서울(ap-northeast-2), Nova Micro는 교차 리전 추론 사용

## 6. 처리 흐름

### 데이터 준비
1. 전처리 프로그램이 학사 안내 편람의 대상 항목과 표시된 편람 수정일을 수집
2. 원본·정리 자료를 Amazon S3에 저장
3. 전처리 프로그램이 본문과 표를 조건별로 분할
4. Titan 임베딩 모델로 각 문서 조각을 벡터로 변환
5. 벡터와 원문, 항목명, 출처 URL, 편람 수정일 및 자료 버전을 S3 Vectors에 저장

### 질문·답변
1. 사용자가 웹 화면에 질문을 입력
2. 백엔드가 Titan 임베딩 모델로 질문을 벡터로 변환
3. S3 Vectors에서 질문과 관련된 문서 조각을 검색
4. 근거가 충분하면 질문과 검색된 원문을 Nova Micro에 전달
5. 백엔드가 생성된 답변과 검색 결과의 출처 정보를 웹 화면에 반환
6. 근거가 부족하면 답변할 수 없음을 안내
데이터 준비와 질문 및 답변에는 동일한 임베딩 모델과 벡터 검색 저장소를 사용함

## 7. 요청과 응답

웹 화면은 `/`에서 열립니다. `POST /api/ask`에 `{"question":"부전공은 몇 개까지 신청할 수 있나요?"}`를 전송하면 답변, 인용한 출처, 실행 모드를 받습니다. 출처마다 항목명, 절, 원문 링크, 편람 수정일, 근거 발췌를 표시합니다.

| 상태 | 의미 |
|---|---|
| `answered` | 검색 자료와 유효한 인용 번호가 있는 답변 |
| `insufficient_evidence` | 관련 근거가 부족해 안내 문구 표시 |
| HTTP 422 | 질문 누락 또는 길이 제한 초과 |
| HTTP 429 | 요청이 동시 처리 한도 2건 또는 AWS 모드의 분당 12건 한도에 도달 |
| HTTP 503 | 문서 또는 모델 서비스 연결 오류 |

`/health`는 FastAPI 프로세스 응답 여부를 반환합니다. 종단 간 확인은 대표 질문을 `/api/ask`로 보내 확인합니다.

## 8. 로컬 실행

Python 3.12에서 의존성을 설치하고 편람을 전처리합니다.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m deploy.ingest_handbook
```

이미 내려받은 편람 HTML을 사용하려면 전처리에 `--html /path/to/index.html`을 추가합니다. 자료는 `reports/private/handbook.json`에 저장됩니다.

Apple Intelligence 사용이 가능한 macOS에서는 한국어를 지원하는 온디바이스 모델과 로컬 검색으로 UI와 답변을 확인할 수 있습니다. Apple Intelligence가 활성화되어 있어야 합니다.

```sh
swiftc deploy/local_generator.swift -o /tmp/erica-local-generator
RAG_MODE=local RAG_LOCAL_GENERATOR=/tmp/erica-local-generator \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

브라우저에서 [로컬 테스트 화면](http://127.0.0.1:8000/)을 엽니다. 운영 모드는 `RAG_MODE=aws`이며 AWS 배포는 [운영 문서](deploy/OPERATIONS.md)를 따릅니다.

## 9. 대표 검증 질문

- 마이크로전공은 몇 학점을 이수해야 하나요?
- 부전공은 몇 개까지 신청할 수 있나요?
- 복수전공은 언제 신청할 수 있나요?
- 일반다중전공은 휴학 중에 신청할 수 있나요?
- 오늘 안산 날씨는 어때요?
- 2026년 2학기 복수전공 원서 마감일은 며칠인가요?

## 10. 2주차 환경 구성
- 기본 리전: 서울 `ap-northeast-2`
- EC2: Amazon Linux 2023 ARM64, `t4g.micro` 1대, 암호화 gp3 8GiB
- 최종 상태: 비용 절감을 위해 검증 후 EC2 중지
- API 확인 형식: `http://EC2_PUBLIC_IP:8000/health` (현재 중지 상태에서는 접속 불가, 재시작 시 새 공인 IP 확인 필요)
- 관리 접속: AWS Systems Manager, SSH 포트와 키 페어 미사용
- 보안 그룹: 외부 TCP 8000만 허용
- S3: 프로젝트 문서 버킷, 퍼블릭 액세스 차단, SSE-S3 암호화
- S3 Vectors: `handbook-titan-v2-1024`, 1024차원, float32, cosine, 원문 text를 비필터 메타데이터로 보존
- 임베딩: `amazon.titan-embed-text-v2:0`, dimensions=1024, normalize=true
- 생성: 서울 Bedrock Runtime에서 `apac.amazon.nova-micro-v1:0` 교차 리전 추론 프로파일 호출
- 실행 권한: EC2 인스턴스 역할에 프로젝트 저장소·지정 모델·로그 권한과 AmazonSSMManagedInstanceCore 연결
- 프로세스: systemd `erica-api`, 부팅 시 자동 시작
- 로그: CloudWatch Agent → `/erica-major-rag-chatbot/api`, 7일 보존

EC2 역할에서 S3 쓰기·읽기, Titan 1024차원 생성, 별도 시험 벡터 쓰기·검색, Nova Micro 생성 호출을 확인했습니다. 시험용 벡터는 `test-only/week2/` 키와 별도 dataset 값을 사용합니다. 실제 학사 편람 자료는 아직 적재하지 않았습니다.

운영·재시작·로그 확인과 비용 관리 방법은 [운영 문서](deploy/OPERATIONS.md)를 참고하세요. 원문 질문과 인증정보는 API 로그에 기록하지 않습니다.

## 11. 3주차 배포 경로

전처리 프로그램은 버전별로 S3에 대상 원본과 검색 자료를 저장하고 S3 Vectors에 1024차원 임베딩을 적재합니다. 운영 API는 `dataset=handbook`과 배포 버전으로 필터링해 2주차 시험용 벡터를 검색에서 제외합니다. EC2 배포 스크립트는 적재를 마친 뒤 systemd를 재시작하고 대표 질문과 근거 부족 응답을 검사합니다.

편람 수정일은 문서 안내에 표시된 날짜를 사용합니다. 제도별 학점과 자격은 조건 및 예외와 함께 확인하고, 학기별 정확한 신청 일자는 공지에서 확인하세요.
