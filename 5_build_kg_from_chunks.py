import os
import json
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph


# =========================
# 1. 환경 변수 / 경로 설정
# =========================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

CHUNKS_PATH = BASE_DIR / "outputs" / "chunks.jsonl"
OUTPUT_PATH = BASE_DIR / "outputs" / "extracted_kg.jsonl"

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

DOC_TITLE = "KB 반려행복펫보험"

# =========================
# 2. KG 스키마 정의
# =========================

NodeType = Literal[
    "Product",
    "SpecialClause",
    "Article",
    "Coverage",
    "Exclusion",
    "RequiredDocument",
    "Procedure",
    "PaymentRule",
    "Condition",
    "Definition",
    "Party",
    "Limit",
    "Unknown",
]

RelationshipType = Literal[
    "HAS_CLAUSE",
    "HAS_ARTICLE",
    "COVERS",
    "EXCLUDES",
    "REQUIRES_DOCUMENT",
    "HAS_PROCEDURE",
    "HAS_PAYMENT_RULE",
    "HAS_CONDITION",
    "DEFINES",
    "APPLIES_TO",
    "HAS_LIMIT",
    "RELATED_TO",
]


class KGNode(BaseModel):
    """
    [Build KG 단계: Node Schema]

    LLM이 추출해야 하는 노드의 형식을 정의

    예:
    {
        "id": "Article:제7조(보험금의 청구)",
        "name": "제7조(보험금의 청구)",
        "type": "Article"
    }
    """

    id: str = Field(
        description='고유 노드 id. 반드시 "타입:이름" 형식. 예: "Article:제7조(보험금의 청구)"'
    )
    name: str = Field(
        description="노드 이름. 예: 제7조(보험금의 청구), 보험금 청구서"
    )
    type: NodeType


class KGRelationship(BaseModel):
    """
    [Build KG 단계: Relationship Schema]

    LLM이 추출해야 하는 관계의 형식을 정의

    예:
    {
        "source": "Article:제7조(보험금의 청구)",
        "target": "RequiredDocument:보험금 청구서",
        "kind": "REQUIRES_DOCUMENT",
        "evidence": "보험금 청구 시 보험금 청구서를 제출해야 합니다."
    }
    """

    source: str = Field(description="출발 노드 id. 반드시 nodes 안에 존재해야 함")
    target: str = Field(description="도착 노드 id. 반드시 nodes 안에 존재해야 함")
    kind: RelationshipType
    evidence: str = Field(description="관계의 근거가 되는 원문 문장")


class KGGraph(BaseModel):
    """
    [Build KG 단계: Graph Output Schema]

    하나의 chunk에서 추출된 KG 결과 전체 구조

    nodes:
        chunk에서 추출된 엔티티 목록

    relationships:
        엔티티 사이의 관계 목록
    """

    nodes: list[KGNode]
    relationships: list[KGRelationship]



# =========================
# 3. chunks.jsonl 로드
# =========================

def load_chunks(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"chunks.jsonl 파일을 찾을 수 없습니다: {path}")

    chunks = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            metadata = row.get("metadata", {})

            chunks.append({
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "text": row["page_content"],
                "page": metadata.get("page"),
                "page_number": metadata.get("page_number"),
                "source": metadata.get("source"),
            })

    return chunks


# =========================
# 4. Neo4j 연결 / KG Writer Setup (제약조건)
# =========================

def get_graph() -> Neo4jGraph:
    return Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )


def create_constraints(graph: Neo4jGraph) -> None:
    """
    [KG Writer Setup]
    [기초 Entity Resolution 준비]

    KGEntity의 id가 중복되지 않도록 제약조건 생성

    예:
    Article:제7조(보험금의 청구)
    Article:제 7 조 보험금의 청구

    위 둘은 의미상 같아도 id 문자열이 다르면 다른 노드로 저장될 수 있음
    """

    graph.query("""
    CREATE CONSTRAINT kg_entity_id_unique IF NOT EXISTS
    FOR (e:KGEntity)
    REQUIRE e.id IS UNIQUE
    """)




# =========================
# 5. Entity / Relation Extract - 프롬프트 생성
# =========================

def build_prompt(chunk: dict) -> str:
    return f"""
다음은 보험 약관 PDF에서 추출한 청크입니다.
이 청크에서 지식 그래프를 추출하세요.

문서명:
{DOC_TITLE}

청크 메타데이터:
- chunk_id: {chunk["chunk_id"]}
- page_number: {chunk.get("page_number")}
- chunk_index: {chunk.get("chunk_index")}

추출 규칙:
- 원문에 명시된 정보만 추출하세요.
- 추측하지 마세요.
- 의미 없는 일반 안내문이면 nodes와 relationships를 빈 리스트로 반환하세요.
- 노드 id는 반드시 "타입:이름" 형식으로 작성하세요.
  예: "Product:KB 반려행복펫보험"
  예: "SpecialClause:반려동물 배상책임 특별약관(대인 및 대동물)"
  예: "Article:제7조(보험금의 청구)"
  예: "RequiredDocument:보험금 청구서"

노드 타입:
- Product: 보험 상품
- SpecialClause: 특별약관
- Article: 조항
- Coverage: 보상하는 손해
- Exclusion: 보상하지 않는 손해
- RequiredDocument: 보험금 청구 필요서류
- Procedure: 절차
- PaymentRule: 보험금 지급 규칙
- Condition: 조건
- Definition: 용어 정의
- Party: 계약자, 피보험자, 회사, 피해자 등
- Limit: 보상한도, 자기부담금 등
- Unknown: 분류가 어려운 경우

관계 방향:
- Product - HAS_CLAUSE -> SpecialClause
- SpecialClause - HAS_ARTICLE -> Article
- Article - COVERS -> Coverage
- Article - EXCLUDES -> Exclusion
- Article - REQUIRES_DOCUMENT -> RequiredDocument
- Article - HAS_PROCEDURE -> Procedure
- Article - HAS_PAYMENT_RULE -> PaymentRule
- Article - HAS_CONDITION -> Condition
- Article - DEFINES -> Definition
- Article - HAS_LIMIT -> Limit
- Coverage/Exclusion/Condition/Procedure/PaymentRule - APPLIES_TO -> Party
- 위 관계로 표현하기 어려우면 RELATED_TO 사용

중요:
- relationship.source와 relationship.target은 반드시 nodes의 id 중 하나여야 합니다.
- evidence에는 관계를 뒷받침하는 원문 일부를 짧게 넣으세요.
- 같은 의미의 노드는 하나로 합치세요.

원문:
{chunk["text"]}
"""


# =========================
# 6. LLM으로 KG 추출
# =========================

def extract_kg_from_chunk(structured_llm, chunk: dict) -> KGGraph:
    """
    [Entity / Relation Extraction]

    하나의 chunk에서 KG를 추출

    입력:
        chunk text

    출력:
        KGGraph(nodes, relationships)
    """
    prompt = build_prompt(chunk)
    return structured_llm.invoke(prompt)


def validate_kg(kg: KGGraph) -> KGGraph:
    """
    [Graph Pruning]

    LLM이 추출한 관계 중에서 source와 target 노드가 실제 nodes 목록에
    모두 존재하는 관계만 남김

    예를 들어 관계가 A -> B라고 되어 있는데,
    nodes 목록에 B가 없으면 Neo4j에서 B를 찾을 수 없으므로
    해당 관계는 저장할 수 없음

    따라서 이런 '존재하지 않는 노드를 가리키는 관계' 제거
    """

    # 1. set을 활용해 현재 KG 안에 실제로 존재하는 노드 id만 수집
    node_ids = set()

    for node in kg.nodes:
        node_ids.add(node.id)

    # 2. 유효한 관계만 담을 리스트를 만들기
    valid_relationships = []

    # 3. LLM이 추출한 관계를 하나씩 확인
    for rel in kg.relationships:
        source_exists = rel.source in node_ids
        target_exists = rel.target in node_ids

        # 4. source와 target이 모두 실제 nodes 안에 있을 때만 append
        if source_exists and target_exists:
            valid_relationships.append(rel)

    # 5. 노드는 그대로 두고, 관계만 정리해서 다시 KGGraph로 반환
    return KGGraph(
        nodes=kg.nodes,
        relationships=valid_relationships,
    )


# =========================
# 7. Neo4j 저장 - KG Writer
# =========================

def add_type_labels(graph: Neo4jGraph) -> None:
    """
    KGEntity 공통 라벨 외에 Product, Article 같은 타입 라벨 추가
    GraphCypherQAChain이 스키마를 더 잘 이해하도록 하기 위함
    """
    node_types = [
        "Product",
        "SpecialClause",
        "Article",
        "Coverage",
        "Exclusion",
        "RequiredDocument",
        "Procedure",
        "PaymentRule",
        "Condition",
        "Definition",
        "Party",
        "Limit",
        "Unknown",
    ]

    for node_type in node_types:
        graph.query(
            f"""
            MATCH (e:KGEntity {{type: $node_type}})
            SET e:{node_type}
            """,
            params={"node_type": node_type},
        )


def save_kg_to_neo4j(graph: Neo4jGraph, kg: KGGraph, chunk: dict) -> None:
    nodes = [node.model_dump() for node in kg.nodes]
    relationships = [rel.model_dump() for rel in kg.relationships]

    if not nodes:
        return

    # 1. KGEntity 노드 저장 + Chunk와 연결
    graph.query(
        """
        MATCH (c:Chunk {id: $chunk_id})

        WITH c
        UNWIND $nodes AS node

        MERGE (e:KGEntity {id: node.id})
        SET e.name = node.name,
            e.type = node.type

        MERGE (c)-[:MENTIONS]->(e)
        MERGE (e)-[:SUPPORTED_BY]->(c)
        """,
        params={
            "chunk_id": chunk["chunk_id"],
            "nodes": nodes,
        },
    )

    add_type_labels(graph)

    # 2. 관계 저장
    relationship_types = [
        "HAS_CLAUSE",
        "HAS_ARTICLE",
        "COVERS",
        "EXCLUDES",
        "REQUIRES_DOCUMENT",
        "HAS_PROCEDURE",
        "HAS_PAYMENT_RULE",
        "HAS_CONDITION",
        "DEFINES",
        "APPLIES_TO",
        "HAS_LIMIT",
        "RELATED_TO",
    ]

    for rel_type in relationship_types:
        graph.query(
            f"""
            UNWIND $relationships AS rel
            WITH rel
            WHERE rel.kind = $rel_type

            MATCH (source:KGEntity {{id: rel.source}})
            MATCH (target:KGEntity {{id: rel.target}})

            MERGE (source)-[r:{rel_type}]->(target)
            SET r.evidence = rel.evidence,
                r.last_chunk_id = $chunk_id,
                r.chunk_ids =
                    CASE
                        WHEN r.chunk_ids IS NULL THEN [$chunk_id]
                        WHEN NOT $chunk_id IN r.chunk_ids THEN r.chunk_ids + [$chunk_id]
                        ELSE r.chunk_ids
                    END
            """,
            params={
                "relationships": relationships,
                "rel_type": rel_type,
                "chunk_id": chunk["chunk_id"],
            },
        )


# =========================
# 8. 추출 결과 저장
# =========================

def append_result_to_jsonl(output_path: Path, chunk: dict, kg: KGGraph) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "chunk_id": chunk["chunk_id"],
        "chunk_index": chunk["chunk_index"],
        "page_number": chunk.get("page_number"),
        "kg": kg.model_dump(),
    }

    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# =========================
# 9. 실행
# =========================

def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)

    print("처리할 청크 수:", len(chunks))

    graph = get_graph()
    create_constraints(graph)

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0,
    )

    structured_llm = llm.with_structured_output(
        KGGraph,
        method="json_schema",
    )

    # 테스트 반복 시 결과 파일이 누적되지 않도록 초기화
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    total_nodes = 0
    total_relationships = 0

    for i, chunk in enumerate(chunks, start=1):
        print("=" * 80)
        print(f"[{i}/{len(chunks)}] chunk_index={chunk['chunk_index']} page={chunk.get('page_number')}")
        print(chunk["text"][:200].replace("\n", " "))

        kg = extract_kg_from_chunk(structured_llm, chunk)
        kg = validate_kg(kg)

        print("추출 노드 수:", len(kg.nodes))
        print("추출 관계 수:", len(kg.relationships))

        save_kg_to_neo4j(graph, kg, chunk)
        append_result_to_jsonl(OUTPUT_PATH, chunk, kg)

        total_nodes += len(kg.nodes)
        total_relationships += len(kg.relationships)

    graph.refresh_schema()

    print("\n완료")
    print("총 추출 노드 수:", total_nodes)
    print("총 추출 관계 수:", total_relationships)
    print("결과 저장:", OUTPUT_PATH)

    print("\nGraph schema:")
    print(graph.schema)


if __name__ == "__main__":
    main()