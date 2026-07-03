# LangChain + Neo4j GraphRAG Final PJT

이 폴더는 `data/kb.pdf` 약관 문서를 대상으로 GraphRAG 파이프라인을 단계별로 구축하는 실습 코드입니다.

```text
PDF 문서
  -> pdfplumber로 page 단위 로드/정제
  -> LangChain Document chunking
  -> Neo4j에 Document/Page/Chunk 원문 그래프 저장
  -> LLM으로 Chunk에서 보험 약관 Knowledge Graph 추출
  -> Neo4j에 KGEntity와 관계 저장
  -> GraphCypherQAChain으로 그래프 질의
  -> Neo4jVector로 Vector + Keyword hybrid index 생성
  -> Hybrid GraphRAG 질의응답
```

## 실습 데이터

```text
data/kb.pdf
```

현재 예제 PDF는 KB 반려행복펫보험 약관입니다. 파이프라인을 실행하면 아래 JSONL 파일들이 생성됩니다.

```text
outputs/parsed_docs.jsonl
outputs/chunks.jsonl
outputs/extracted_kg.jsonl
```

현재 폴더에는 `outputs/` 폴더가 없을 수 있습니다. `2_load_pdfplumber.py`, `3_split.py`, `5_build_kg_from_chunks.py`를 순서대로 실행하면 필요한 결과 파일이 생성됩니다.

## 설치

가상환경을 만든 뒤 패키지를 설치합니다.

```bash
python -m venv .venv
source .venv/bin/activate

pip install -U langchain langchain-openai langchain-neo4j python-dotenv langchain-community pdfplumber
```

macOS 환경에서 고정된 패키지 목록을 그대로 맞추고 싶다면 다음 명령을 사용할 수도 있습니다.

```bash
pip install -r requirements_macos.txt
```

## Neo4j 준비

Neo4j Desktop을 실행합니다.

브라우저 확인 주소:

```text
http://localhost:7474
```

DB 초기화

```cypher
MATCH (n)
DETACH DELETE n;
```

## 환경변수

프로젝트 루트에 `.env` 파일을 만들고 값을 채웁니다.

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j

PDF_PATH=data/kb.pdf
```

참고:
- 현재 `2_load_pdfplumber.py`는 기본적으로 `data/kb.pdf`를 사용합니다.
- `OPENAI_EMBEDDING_MODEL`을 지정하지 않으면 코드에서 `text-embedding-3-small`을 기본값으로 사용합니다.
- `NEO4J_DATABASE`는 코드에 따라 기본값이 `neo4j`로 되어 있으므로, `.env`에 명시해두는 편이 좋습니다.

## 파일 구성

| 파일 | 역할 | 필수 여부 |
| --- | --- | --- |
| `1_test_connection.py` | Neo4j 접속 확인 | 필수 |
| `2_load_pdfplumber.py` | `pdfplumber` 기반 PDF 로드, 한국어 약관 텍스트 정제, `parsed_docs.jsonl` 저장 | 필수 |
| `3_split.py` | LangChain splitter로 약관 구조를 고려한 chunk 생성, `chunks.jsonl` 저장 | 필수 |
| `4_ingest_chunks_to_neo4j.py` | `KBDocument`, `Page`, `Chunk` 노드와 관계를 Neo4j에 저장 | 필수 |
| `5_build_kg_from_chunks.py` | LLM structured output으로 Chunk에서 보험 약관 KG 추출 후 Neo4j 저장 | 필수 |
| `6_1_query.py` | 간단한 GraphCypherQAChain 실험 파일 | 보조 |
| `6_ask_graphrag.py` | `GraphCypherQAChain`으로 KG를 직접 질의 | 선택 |
| `7_build_vector_index.py` | `Chunk.text`를 embedding하고 Neo4j vector/full-text hybrid index 생성 | 필수 |
| `8_ask_hybrid_graphrag.py` | Vector+Keyword 검색 결과와 GraphCypherQAChain 결과를 함께 사용해 최종 답변 | 선택 |
| `9_ask_hybrid_graphrag.py` | `retrieval_query`로 Hybrid search 결과에 KGEntity context를 붙여 답변 | 선택 |

그 밖의 보조 파일은 다음과 같습니다.

| 파일 | 역할 |
| --- | --- |
| `.env_example` | 환경변수 예시 파일 |
| `.gitignore` | Git 제외 파일 설정 |
| `requirements_macos.txt` | macOS 환경용 고정 패키지 목록 |
| `data/kb.pdf` | 실습용 PDF 문서 |

## 실행 순서

### 1. Neo4j 연결 확인

```bash
python 1_test_connection.py
```

정상 연결되면 아래 메시지가 출력됩니다.

```text
Neo4j 연결 성공!
```

### 2. PDF 로드 및 전처리

```bash
python 2_load_pdfplumber.py
```

하는 일:
- `data/kb.pdf`를 page 단위로 로드
- 한국어 PDF 줄바꿈, 목차 점선, 페이지 번호 등 정리
- `outputs/parsed_docs.jsonl` 저장

### 3. 문서 Chunk 생성

```bash
python 3_split.py
```

하는 일:
- `outputs/parsed_docs.jsonl`을 LangChain `Document`로 다시 로드
- 약관의 `제1조`, `①`, `1.`, `가.` 같은 구조를 고려해 chunk 분할
- 각 chunk에 `chunk_id`, `chunk_index`, `page_number`, `char_count` 메타데이터 추가
- `outputs/chunks.jsonl` 저장

### 4. 원문 Chunk 그래프를 Neo4j에 저장

```bash
python 4_ingest_chunks_to_neo4j.py
```

생성되는 기본 구조:

```text
(:KBDocument)-[:HAS_PAGE]->(:Page)-[:HAS_CHUNK]->(:Chunk)
(:Chunk)-[:NEXT_CHUNK]->(:Chunk)
```

이 단계는 아직 LLM이 만든 Knowledge Graph가 아니라, 원문 검색과 출처 추적을 위한 문서 그래프입니다.

### 5. Chunk에서 Knowledge Graph 추출

```bash
python 5_build_kg_from_chunks.py
```

하는 일:
- 각 chunk를 LLM에 전달
- Pydantic schema(`KGNode`, `KGRelationship`, `KGGraph`)에 맞춰 노드/관계 추출
- 관계의 source/target이 실제 nodes에 있는지 검증
- Neo4j에 `KGEntity` 노드와 관계 저장
- `outputs/extracted_kg.jsonl` 저장

생성되는 대표 구조:

```text
(:Chunk)-[:MENTIONS]->(:KGEntity)
(:KGEntity)-[:SUPPORTED_BY]->(:Chunk)

(:Product)-[:HAS_CLAUSE]->(:SpecialClause)
(:SpecialClause)-[:HAS_ARTICLE]->(:Article)
(:Article)-[:COVERS]->(:Coverage)
(:Article)-[:EXCLUDES]->(:Exclusion)
(:Article)-[:REQUIRES_DOCUMENT]->(:RequiredDocument)
(:Article)-[:HAS_PAYMENT_RULE]->(:PaymentRule)
```

### 6. GraphCypherQAChain으로 그래프 질의

```bash
python 6_ask_graphrag.py
```

이 파일은 `GraphCypherQAChain`을 사용합니다.

흐름:

```text
사용자 질문
  -> LLM이 Neo4j schema를 보고 Cypher 생성
  -> Neo4j 조회
  -> 조회 결과를 자연어 답변으로 정리
```

예시 질문:

```text
보험금 청구할 때 어떤 서류가 필요해?
보험금은 언제 지급돼?
```

### 7. Hybrid Index 생성

```bash
python 7_build_vector_index.py
```

하는 일:
- `Chunk.text`를 OpenAI embedding으로 변환
- `Chunk.embedding` 속성에 저장
- Neo4j vector index 생성
- `Chunk.text` full-text keyword index 생성

생성되는 인덱스 이름:

```text
chunk_vector_index
chunk_keyword_index
```

이 단계 이후부터 `Neo4jVector(..., search_type="hybrid")`를 사용할 수 있습니다.

### 8. Vector/Keyword + GraphCypherQAChain 결합 질의

```bash
python 8_ask_hybrid_graphrag.py
```

이 파일은 두 가지 검색 결과를 모두 사용합니다.

```text
1. Vector + Keyword 검색 결과
2. GraphCypherQAChain 그래프 조회 결과
```

흐름:

```text
질문
  -> Neo4jVector Hybrid Search로 관련 Chunk 검색
  -> GraphCypherQAChain으로 KG 구조 조회
  -> 두 결과를 최종 LLM 프롬프트에 함께 전달
  -> 최종 답변
```

이 방식은 원문 기반 검색 결과와 그래프 구조 기반 검색 결과를 나란히 제공해 LLM이 종합하게 만드는 예제입니다.

### 9. `retrieval_query` 기반 Hybrid GraphRAG 질의

```bash
python 9_ask_hybrid_graphrag.py
```

이 파일은 `Neo4jVector.from_existing_index(...)`로 기존 hybrid index를 불러오되, `retrieval_query`를 함께 사용합니다.

검색 흐름:

```text
질문
  -> Vector Search
  -> Keyword Search
  -> 검색된 Chunk가 node 변수로 retrieval_query에 전달됨
  -> (node)-[:MENTIONS]->(:KGEntity) 관계를 따라 entity context 확장
  -> Chunk 원문 + KGEntity 목록을 LLM에게 전달
  -> 최종 답변
```

이 방식은 retriever 단계에서 바로 graph context를 붙이는 패턴입니다. `retrieval_query`는 LangChain 규칙상 반드시 `text`, `score`, `metadata` 세 컬럼을 반환해야 합니다.

## 핵심 개념 정리

| 개념 | 의미 |
| --- | --- |
| 일반 RAG | 질문과 비슷한 chunk를 찾아 LLM에 넣고 답변 |
| GraphRAG | chunk 검색에 더해, chunk가 연결된 엔티티와 관계를 활용 |
| `Chunk` | PDF 원문을 검색 가능한 크기로 나눈 단위 |
| `KGEntity` | LLM이 추출한 약관 엔티티 |
| `MENTIONS` | 특정 chunk가 어떤 KGEntity를 언급한다는 연결 |
| `SUPPORTED_BY` | KGEntity가 어떤 chunk를 근거로 추출됐는지 나타내는 연결 |
| `Neo4jGraph` | LangChain에서 Cypher를 실행하고 schema를 읽는 래퍼 |
| `GraphCypherQAChain` | 자연어 질문을 Cypher로 바꿔 Neo4j에 질의하는 체인 |
| `Neo4jVector` | Neo4j vector/full-text index를 LangChain retriever처럼 사용하는 도구 |
