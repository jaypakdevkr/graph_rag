# LangChain + Neo4j 통합 실습

이 레포지토리는 LangChain 공식 Neo4j 통합 문서를 바탕으로 만든 예제 레포지토리입니다.

공식 문서: [Neo4j integrations - LangChain Docs](https://docs.langchain.com/oss/python/integrations/providers/neo4j)


## 파일 구성

| 순서 | 파일 | 학습 목표 |
| --- | --- | --- |
| 1 | `1_test_connection.py` | Neo4j Python 드라이버로 DB 접속을 확인합니다. |
| 2 | `2_langchainXneo4j.py` | `Neo4jGraph`로 Cypher를 직접 실행해 노드와 관계를 만듭니다. |
| 3 | `3_build_graph.py` | OpenAI LLM이 한국어 문장에서 지식 그래프를 추출하고 Neo4j에 저장합니다. |
| 4 | `4_ask_graph.py` | `GraphCypherQAChain`으로 저장된 그래프에 자연어 질문을 합니다. |

실습 문장은 아래 내용을 그래프로 표현합니다.

```text
김민수는 결제 시스템 리팩터링을 담당했다.
결제 시스템 리팩터링은 장애율을 낮추기 위한 프로젝트였다.
결제 시스템 리팩터링은 보안팀과 플랫폼팀이 공동으로 진행했다.
```

## 준비 사항

- Python 3.10 이상
- Neo4j Desktop 또는 Docker로 실행 중인 Neo4j DB
- OpenAI API 키

DB를 초기화하고 실습하려면 아래 쿼리를 실행합니다. 모든 노드와 관계가 삭제되므로 실습용 DB에서만 사용하세요.

```cypher
MATCH (n)
DETACH DELETE n;
```

## 패키지 설치

가상환경을 만든 뒤 패키지를 설치합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

핵심 패키지는 다음과 같습니다.

```bash
pip install neo4j langchain langchain-neo4j langchain-openai python-dotenv pydantic
```

macOS에서 별도 고정 버전 파일을 사용하려면 다음 명령을 사용할 수 있습니다.

```bash
pip install -r requirements_macos.txt
```

## 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 아래 값을 채웁니다.

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.5

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
```

## 실행 순서

### 1. Neo4j 연결 확인

```bash
python 1_test_connection.py
```

정상 연결되면 아래 메시지가 출력됩니다.

```text
Neo4j 연결 성공!
```

이 단계는 LangChain을 쓰기 전에 DB 주소, 아이디, 비밀번호가 맞는지 확인하는 용도입니다.

### 2. LangChain `Neo4jGraph`로 그래프 직접 생성

```bash
python 2_langchainXneo4j.py
```

이 파일은 LLM을 사용하지 않습니다. 사람이 직접 작성한 Cypher를 `graph.query(...)`로 실행합니다.

### 3. LLM으로 문장에서 지식 그래프 추출

```bash
python 3_build_graph.py
```

이 단계에서는 OpenAI 모델이 한국어 문장을 읽고 다음 구조를 추출합니다.

```python
KGGraph(
    nodes=[...],
    relationships=[...],
)
```

코드에서 중요한 부분은 다음입니다.

| 코드 요소 | 의미 |
| --- | --- |
| `KGNode`, `KGRelationship`, `KGGraph` | LLM이 따라야 할 출력 형식입니다. |
| `with_structured_output(...)` | LLM 응답을 Pydantic 객체로 받습니다. |
| `validate_kg(...)` | 노드 목록에 없는 관계를 제거합니다. |
| `MERGE (e:Entity {id: node.id})` | 같은 노드가 중복 생성되지 않게 저장합니다. |
| `SET e:Person`, `SET e:Project` | 그래프 스키마를 읽기 쉽게 타입별 라벨을 추가합니다. |

이 단계가 끝나면 Neo4j에는 `Entity` 노드와 `RESPONSIBLE_FOR`, `AIMS_TO_REDUCE`, `COLLABORATED_ON` 같은 관계가 저장됩니다.

### 4. 자연어로 그래프 질문하기

```bash
python 4_ask_graph.py
```

이 파일은 `GraphCypherQAChain`을 사용합니다.

실행 흐름은 다음과 같습니다.

```text
자연어 질문
  -> LLM이 Neo4j 스키마를 참고해 Cypher 생성
  -> Neo4j에서 쿼리 실행
  -> 조회 결과를 다시 자연어 답변으로 요약
```

예시 질문:

```text
김민수와 보안팀은 어떤 관계야?
```

`verbose=True`가 켜져 있으므로 실행 중 생성된 Cypher도 터미널에서 확인할 수 있습니다. 학생들은 이 출력을 보면서 “LLM이 자연어 질문을 어떻게 Cypher로 바꾸는지” 관찰하면 됩니다.


## 참고 링크

- [LangChain Neo4j provider 문서](https://docs.langchain.com/oss/python/integrations/providers/neo4j)
- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [langchain-neo4j GitHub 저장소](https://github.com/langchain-ai/langchain-neo4j)
