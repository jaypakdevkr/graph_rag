# Neo4j Cypher 실습 정리

이 문서는 Neo4j Cypher 기초 실습에서 사용한 주요 명령어를 정리한 문서입니다.

실습 주제는 다음 문장들을 그래프로 표현하고, 조회·수정·삭제하는 것입니다.

```text
문서 A: 김민수는 결제 시스템 리팩터링을 담당했다.
문서 B: 결제 시스템 리팩터링은 장애율 개선 프로젝트와 연결된다.
문서 C: 장애율 개선 프로젝트는 보안팀과 플랫폼팀이 공동으로 진행했다.
```

## 준비 사항

- Python 3.10 이상 권장
- OpenAI API 키
- Neo4j Desktop 앱

## 패키지 설치

가상환경을 만든 뒤 필요한 패키지를 설치합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U langchain langchain-openai langchain-neo4j python-dotenv
```

이미 `requirements.txt` 기준으로 동일한 환경을 맞추고 싶다면 다음 명령을 사용할 수도 있습니다.

```bash
pip install -r requirements.txt
```

macOS의 경우
```bash
pip install -r requirements_macos.txt
```

## 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 아래 값을 채웁니다.

```env
OPENAI_API_KEY=your_openai_api_key
NEO4J_URI=neo4j+s://your-neo4j-host
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

필요하면 모델명과 데이터베이스 이름도 추가할 수 있습니다.

```env
OPENAI_MODEL=gpt-5.5
NEO4J_DATABASE=neo4j
```

`OPENAI_MODEL`을 지정하지 않으면 코드에서는 기본값으로 `gpt-5.5`를 사용합니다.

## 1. 기본 개념

### 초기화

```cypher
MATCH (n)
DETACH DELETE n;
```

### 노드 생성

```cypher
CREATE
  (kim:Person {name: "김민수", age: 34})
RETURN kim;
```

```cypher
CREATE
    (kim:Person {이름: "김민수", 나이: 34}),
    (park:Person {이름: "박상호", 나이: 27}),
    (lee:Person {이름: "이상희", 나이: 32})
RETURN kim, park, lee
```

### 관계 생성

```cypher
CREATE
  (kim:Person {name: "김민수", age: 34})
  -[r:RESPONSIBLE_FOR]->
  (refactor:Project {name: "결제 시스템 리팩터링", status: "진행중"})
RETURN kim, r, refactor;
```

또는 경로 전체를 반환할 수도 있음.

```cypher
CREATE path =
  (kim:Person {name: "김민수", age: 34})
  -[:RESPONSIBLE_FOR]->
  (refactor:Project {name: "결제 시스템 리팩터링", status: "진행중"})
RETURN path;
```

## 2. 조회

### 전체 그래프 조회

```cypher
MATCH p = ()-->()
RETURN p;
```

### 특정 라벨의 노드 조회

```cypher
MATCH (p:Person)
RETURN p;
```

```cypher
MATCH (p:Person)
RETURN p.나이, p.이름;
```

### 필터링

```cypher
MATCH (p:Person {이름 : "이상희"})
RETURN p;
```

```cypher
MATCH (p:Person)
WHERE p.나이 > 30
RETURN p;
```

```cypher
MATCH (p:Person)
WHERE p.이름 CONTAINS "이상희"
RETURN p;
```

### with 논리 연산자

```cypher
MATCH (p:Person)
WHERE (p.나이 > 30) AND (p.이름 CONTAINS "이상희")
RETURN p;
```

## 3. 복잡한 그래프 생성 및 조회

### 노드 생성

```cypher
CREATE
  (kim:Person {이름: "김민수", 나이: 34}),
  (refactor:Project {이름: "결제 시스템 리팩터링", 상태: "진행중"}),
  (improve:Project {이름: "장애율 개선 프로젝트", 상태: "진행중"}),
  (security:Team {이름: "보안팀", 역할: "공동 진행팀"}),
  (platform:Team {이름: "플랫폼팀", 역할: "공동 진행팀"})
RETURN kim, refactor, improve, security, platform;
```

### 관계 생성
```cypher
MATCH 
    (kim:Person {이름: "김민수"}),
    (refactor:Project {이름: "결제 시스템 리팩터링"}),
    (improve:Project {이름: "장애율 개선 프로젝트"}),
    (security:Team {이름: "보안팀"}),
    (platform:Team {이름: "플랫폼팀"})

CREATE
    (kim)-[r:RESPONSIBLE_FOR]->(refactor),
    (refactor)-[atr:AIMS_TO_REDUCE]->(improve),
    (security)-[co1:COLLABORATES_ON]->(improve),
    (platform)-[co2:COLLABORATES_ON]->(improve)

RETURN kim, refactor, improve, security, platform, r, atr, co1, co2;
```

### 다단계 경로 조회

```cypher
MATCH (start:Person {이름: "김민수"})
MATCH (end:Team {이름: "보안팀"})
MATCH p = (start)-[*1..5]-(end)
RETURN p;
```

```cypher
MATCH (start:Person {이름: "김민수"})
MATCH (end:Team {이름: "보안팀"})
MATCH p = shortestPath((start)-[*1..5]-(end))
RETURN p;
```

* shortestPath : https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/

```cypher
MATCH p =
  (kim:Person {이름: "김민수"})
  -[:RESPONSIBLE_FOR]->
  (:Project {이름: "결제 시스템 리팩터링"})
  -[:AIMS_TO_REDUCE]->
  (:Project {이름: "장애율 개선 프로젝트"})
  <-[:COLLABORATES_ON]-
  (team:Team {이름: "보안팀"})
RETURN p;
```

* LangChain neo4j_graph.py : https://github.com/langchain-ai/langchain-neo4j/blob/main/libs/neo4j/langchain_neo4j/graphs/neo4j_graph.py
* LangChain cypher.py : https://github.com/langchain-ai/langchain-neo4j/blob/main/libs/neo4j/langchain_neo4j/chains/graph_qa/cypher.py

## 4. Update

### 노드 속성 Update

```cypher
MATCH (n:Person)
WHERE n.id CONTAINS "김민수"
SET n.이름 = n.id
RETURN n;
```

```cypher
MATCH (n:Entity)
WHERE n.id IN ["김민수", "보안팀", "플랫폼팀"]
SET n.이름 = n.id
RETURN n;
```

### 관계 속성 Update

```cypher
MATCH 
    (kim:Person {id: "김민수"})
    -[r:RESPONSIBLE_FOR]->
    (pay:Project {id: "결제 시스템 리팩터링"})
SET r.source = "문서 A"
RETURN kim, r, pay;
```

### MERGE

```cypher
MERGE (improve:Entity {id: "장애율 개선 프로젝트"}) 
SET improve.type = "Project", 
    improve.이름 = "장애율 개선 프로젝트" 
SET improve:Project 
RETURN improve;
```

```cypher
MATCH (refactor:Project {id: "결제 시스템 리팩터링"})
MATCH (improve:Project {id: "장애율 개선 프로젝트"})
MERGE (refactor)-[ct:CONTRIBUTES_TO]->(improve)
RETURN refactor, improve, ct;
```

```cypher
MATCH (improve:Project {id: "장애율 개선 프로젝트"})
MATCH (team:Team)
WHERE team.id IN ["보안팀", "플랫폼팀"]

MERGE (team)-[:COLLABORATES_ON]->(improve)
```

## 5. Delete

```cypher
MATCH (refactor:Project {id: "결제 시스템 리팩터링"})
MATCH (team:Team)
WHERE team.id IN ["보안팀", "플랫폼팀"]

MATCH (team)-[old]->(refactor)
DELETE old
```

```cypher
MATCH 
    (:Project {id: "결제 시스템 리팩터링"})
    -[r:AIMS_TO_REDUCE]->
    (m:Metric {id: "장애율"})
DELETE r, m;
```

```cypher
MATCH (m:Metric {id: "장애율"})
DELETE m;
```

```cypher
MATCH (m:Metric {id: "장애율"})
DETACH DELETE m;
```

```cypher
MATCH (n)
DETACH DELETE n;
```