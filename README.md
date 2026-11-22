# 한양대학교 ERICA 전공 제도 안내 RAG 챗봇
한양대학교 ERICA 2026 Cloud Architecture(HY24307)

한양대학교 ERICA 학부생이 전공제도를 질문하면 학사 안내 편람을 근거로 답변하고 출처를 제공하는 RAG기반 챗봇
> 현 진행 단계: 2주차 AWS 환경 구성 및 기본 API 배포

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
- **출처 제공:** 답변에 사용한 문서의 출처 URL과 수정 기준일 표시
- **근거 부족 안내:** 자료에서 답변 근거를 찾기 어려운 경우 확인할 수 없음을 안내

## 4. 활용 데이터
- **자료:** ERICA 통합 학사 안내 편람의 전공·다전공 관련 6개 항목
- **링크:** https://yoorhi816.github.io/erica-academic-handbook/
- **수집 방식:** 담당자가 해당 항목의 본문과 표를 수집·정리
- **처리 방식:** 문서를 조건별로 분할하고, 출처 정보와 함께 검색용 데이터로 저장

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
1. 담당자가 학사 안내 편람의 대상 항목을 수집
2. 원본·정리 자료를 Amazon S3에 저장
3. 전처리 프로그램이 본문과 표를 조건별로 분할
4. Titan 임베딩 모델로 각 문서 조각을 벡터로 변환
5. 벡터와 원문, 항목명, 출처 URL, 수정 기준일을 S3 Vectors에 저장

### 질문·답변
1. 사용자가 웹 화면에 질문을 입력
2. 백엔드가 Titan 임베딩 모델로 질문을 벡터로 변환
3. S3 Vectors에서 질문과 관련된 문서 조각을 검색
4. 근거가 충분하면 질문과 검색된 원문을 Nova Micro에 전달
5. 백엔드가 생성된 답변과 검색 결과의 출처 정보를 웹 화면에 반환
6. 근거가 부족하면 답변할 수 없음을 안내
데이터 준비와 질문 및 답변에는 동일한 임베딩 모델과 벡터 검색 저장소를 사용함

## 7. AWS Architecture
### 데이터 준비 구성도
반영예정
<!-- 데이터 준비 구성도를 업로드한 뒤 이미지 경로를 추가합니다. -->

### 서비스 구성도
반영 예정
<!-- 질문·답변 구성도를 업로드한 뒤 이미지 경로를 추가합니다. -->

## 8. 진행 현황
- [x] 서비스 주제 및 안내 범위 정의
- [x] 활용 데이터 선정
- [x] 데이터 준비 및 서비스 흐름 설계
- [x] AWS 아키텍처 설계
- [ ] 문서 수집 및 전처리 구현
- [ ] 임베딩 생성 및 벡터 저장소 구축
- [ ] 검색·답변 API 구현
- [ ] 웹 화면 구현 및 연동
- [ ] 답변 정확성·출처·근거 부족 처리 검증
- [x] 2주차 기본 API의 EC2 배포 및 실행 확인
- [ ] RAG 전체 서비스의 AWS 배포 및 동작 확인

## 9. 기본 API 실행 방법
Python 3.12를 사용합니다.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
curl http://127.0.0.1:8000/health
```

```json
{"status":"ok","service":"erica-major-rag-chatbot"}
```

`/health`는 서버 실행 확인용입니다. RAG 전체 연결 성공이나 학사 질문에 대한 답변 기능을 의미하지 않습니다.

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

## 11. 남은 구현
편람 대상 6개 항목 수집, 표와 조건을 보존하는 분할, 실제 문서 벡터 적재, 검색 근거에 따른 답변 API, 검색 결과 출처 표시, 웹 화면과 정확성 검증은 후속 구현 범위입니다. 기존 데이터 준비 구성도와 질문·답변 구성도는 확보 후 위 7절에 반영합니다.
