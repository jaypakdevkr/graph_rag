import os
import json
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")


class KGNode(BaseModel):
    id: str = Field(description="노드 이름. 예: 김민수, 결제 시스템 리팩터링")
    type: Literal["Person", "Project", "Team", "Metric", "System", "Unknown"]


class KGRelationship(BaseModel):
    source: str = Field(description="출발 노드 id")
    target: str = Field(description="도착 노드 id")
    kind: Literal[
        "RESPONSIBLE_FOR",
        "AIMS_TO_REDUCE",
        "COLLABORATED_ON",
        "RELATED_TO",
    ]


class KGGraph(BaseModel):
    nodes: list[KGNode]
    relationships: list[KGRelationship]


def validate_kg(kg: KGGraph) -> KGGraph:
    """
    Graph Pruning:
    LLM이 추출한 관계 중에서 source와 target이 실제 nodes 목록에
    모두 존재하는 관계만 남깁니다.
    """

    node_ids = {node.id for node in kg.nodes}

    valid_relationships = []

    for rel in kg.relationships:
        source_exists = rel.source in node_ids
        target_exists = rel.target in node_ids

        if source_exists and target_exists:
            valid_relationships.append(rel)

    return KGGraph(
        nodes=kg.nodes,
        relationships=valid_relationships,
    )


graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE
)

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)

structured_llm = llm.with_structured_output(
    KGGraph,
    method="json_schema",
)

text = """
김민수는 결제 시스템 리팩터링을 담당했다.
결제 시스템 리팩터링은 장애율을 낮추기 위한 프로젝트였다.
결제 시스템 리팩터링은 보안팀과 플랫폼팀이 공동으로 진행했다.
"""

prompt = f"""
다음 한국어 문장에서 지식 그래프를 추출하세요.

규칙:
- 문장에 명시된 정보만 사용하세요.
- 노드는 중요한 사람, 프로젝트, 팀, 지표, 시스템을 추출하세요.
- 같은 의미의 노드는 하나로 합치세요.
- relationship의 source와 target은 반드시 nodes의 id 중 하나여야 합니다.
- 관계 방향은 반드시 아래 규칙을 따르세요.

관계 타입:
- RESPONSIBLE_FOR:
  - 의미: 사람이 프로젝트나 업무를 담당함
  - 방향: Person -> Project/System
  - 예: 김민수 -> 결제 시스템 리팩터링

- AIMS_TO_REDUCE:
  - 의미: 프로젝트가 어떤 지표를 낮추는 목적을 가짐
  - 방향: Project -> Metric
  - 예: 결제 시스템 리팩터링 -> 장애율

- COLLABORATED_ON:
  - 의미: 팀이 프로젝트를 공동 진행함
  - 방향: Team -> Project
  - 예: 보안팀 -> 결제 시스템 리팩터링

- RELATED_TO:
  - 의미: 위 관계로 표현하기 어려운 일반 관계
  - 방향: 문장의 주체 -> 대상

문장:
{text}
"""

kg = structured_llm.invoke(prompt)

print("최초 LLM의 답변:", kg)
"""
nodes=[KGNode(id='김민수', type='Person'), 
    KGNode(id='결제 시스템 리팩터링', type='Project'), 
    KGNode(id='장애율', type='Metric'), 
    KGNode(id='보안팀', type='Team'), 
    KGNode(id='플랫폼팀', type='Team')
] 
relationships=[KGRelationship(source='김민수', target='결제 시스템 리팩터링', kind='RESPONSIBLE_FOR'), 
    KGRelationship(source='결제 시스템 리팩터링', target='장애율', kind='AIMS_TO_REDUCE'), 
    KGRelationship(source='보안팀', target='결제 시스템 리팩터링', kind='COLLABORATED_ON'), 
    KGRelationship(source='플랫폼팀', target='결제 시스템 리팩터링', kind='COLLABORATED_ON')
]
"""

kg = validate_kg(kg)

# 중복 방지: Entity.id가 중복되지 않도록 유니크 제약조건 생성
## entity_id_unique라는 이름의 제약조건을 생성하라. 단, 이미 같은 제약조건이 있으면 새로 만들지 마라.
## 이 제약조건은 Entity 라벨을 가진 노드 e에 적용된다.
## Entity 노드의 id 속성은 반드시 유일해야 한다.
graph.query("""
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity)
REQUIRE e.id IS UNIQUE
""")

# .model_dump()  : BaseModel 객체를 Python dict로 바꾸는 메서드 (Pydantic v2)
nodes = [node.model_dump() for node in kg.nodes]
relationships = [rel.model_dump() for rel in kg.relationships]

print("nodes : " ,nodes)
print("relationships : " ,relationships)
"""
[
    {'id': '김민수', 'type': 'Person'}, 
    {'id': '결제 시스템 리팩터링', 'type': 'Project'}, 
    {'id': '장애율', 'type': 'Metric'}, 
    {'id': '보안팀', 'type': 'Team'}, 
    {'id': '플랫폼팀', 'type': 'Team'}
]
"""
"""
[
    {'source': '김민수', 'target': '결제 시스템 리팩터링', 'kind': 'RESPONSIBLE_FOR'}, 
    {'source': '결제 시스템 리팩터링', 'target': '장애율', 'kind': 'AIMS_TO_REDUCE'}, 
    {'source': '보안팀', 'target': '결제 시스템 리팩터링', 'kind': 'COLLABORATED_ON'}, 
    {'source': '플랫폼팀', 'target': '결제 시스템 리팩터링', 'kind': 'COLLABORATED_ON'}
]
"""

# 노드 저장
graph.query(
    """
    UNWIND $nodes AS node
    MERGE (e:Entity {id: node.id})
    SET e.name = node.id,
        e.type = node.type
    """,
    params={"nodes": nodes},
)


# type별 라벨 추가
for node_type in ["Person", "Project", "Team", "Metric", "System", "Unknown"]:
    graph.query(
        f"""
        MATCH (e:Entity {{type: $node_type}})
        SET e:{node_type}
        """,
        params={"node_type": node_type},
    )


# 관계 저장
# Cypher의 관계 타입(:RESPONSIBLE_FOR 등)은 파라미터로 넣을 수 없어, 관계 타입을 하나씩 순회하며 저장.
for kind in [
    "RESPONSIBLE_FOR",
    "AIMS_TO_REDUCE",
    "COLLABORATED_ON",
    "RELATED_TO",
]:
    graph.query(
        f"""
        UNWIND $relationships AS rel
        WITH rel
        WHERE rel.kind = $kind

        MATCH (source:Entity {{id: rel.source}})
        MATCH (target:Entity {{id: rel.target}})

        MERGE (source)-[r:{kind}]->(target)
        """,
        params={
            "relationships": relationships,
            "kind": kind,
        },
    )


graph.refresh_schema()

print("그래프 생성 완료!")
print(graph.schema)