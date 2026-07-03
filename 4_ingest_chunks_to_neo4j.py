import os
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph


# =========================
# 1. 환경 변수 / 경로 설정
# =========================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

CHUNKS_PATH = BASE_DIR / "outputs" / "chunks.jsonl"

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

DOC_ID = "kb_pet_insurance"
DOC_TITLE = "KB 반려행복펫보험"

# =========================
# 2. chunks.jsonl 로드
# =========================

def load_chunks(path: Path) -> list[dict]:
    """
    02_split.py에서 저장한 outputs/chunks.jsonl 불러오기
    """

    if not path.exists():
        raise FileNotFoundError(f"chunks.jsonl 파일을 찾을 수 없습니다: {path}")

    chunks = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)

            metadata = row.get("metadata", {})

            page = metadata.get("page")
            page_number = metadata.get("page_number")

            # page_number가 없으면 page를 기준으로 보정합
            if page_number is None:
                if isinstance(page, int):
                    page_number = page + 1
                else:
                    page_number = 0

            chunk = {
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "text": row["page_content"],
                "source": metadata.get("source"),
                "page": page,
                "page_number": page_number,
                "start_index": metadata.get("start_index"),
                "char_count": metadata.get("char_count"),
                "parent_doc_id": metadata.get("parent_doc_id"),
            }

            chunks.append(chunk)

    return chunks


# =========================
# 3. Neo4j 연결
# =========================

def get_graph() -> Neo4jGraph:
    return Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )


# =========================
# 4. 제약 조건 생성
# =========================

def create_constraints(graph: Neo4jGraph) -> None:
    """
    MERGE가 안정적으로 동작하도록 id 유니크 제약조건 생성
    """

    graph.query("""
    CREATE CONSTRAINT kb_document_id_unique IF NOT EXISTS
    FOR (d:KBDocument)
    REQUIRE d.id IS UNIQUE
    """)

    graph.query("""
    CREATE CONSTRAINT page_id_unique IF NOT EXISTS
    FOR (p:Page)
    REQUIRE p.id IS UNIQUE
    """)

    graph.query("""
    CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
    FOR (c:Chunk)
    REQUIRE c.id IS UNIQUE
    """)


# =========================
# 5. Document / Page / Chunk 저장
# =========================

def save_chunks(graph: Neo4jGraph, chunks: list[dict]) -> None:
    """
    chunks.jsonl의 청크들을 Neo4j에 저장

    생성되는 구조:
    (:KBDocument)-[:HAS_PAGE]->(:Page)-[:HAS_CHUNK]->(:Chunk)
    """

    graph.query(
        """
        MERGE (d:KBDocument {id: $doc_id})
        SET d.title = $doc_title

        WITH d
        UNWIND $chunks AS row

        MERGE (p:Page {id: $doc_id + ":page:" + toString(row.page_number)})
        SET p.page = row.page,
            p.page_number = row.page_number,
            p.source = row.source

        MERGE (c:Chunk {id: row.chunk_id})
        SET c.text = row.text,
            c.chunk_index = row.chunk_index,
            c.source = row.source,
            c.page = row.page,
            c.page_number = row.page_number,
            c.start_index = row.start_index,
            c.char_count = row.char_count,
            c.parent_doc_id = row.parent_doc_id

        MERGE (d)-[:HAS_PAGE]->(p)
        MERGE (p)-[:HAS_CHUNK]->(c)
        """,
        params={
            "doc_id": DOC_ID,
            "doc_title": DOC_TITLE,
            "chunks": chunks,
        },
    )


# =========================
# 6. 청크 순서 관계 생성
# =========================

def create_next_chunk_relationships(graph: Neo4jGraph) -> None:
    """
    같은 문서 안에서 청크 순서를 보존

    (:Chunk)-[:NEXT_CHUNK]->(:Chunk)
    """

    graph.query(
        """
        MATCH (c:Chunk)
        WHERE c.chunk_index IS NOT NULL
        WITH c
        ORDER BY c.chunk_index ASC
        WITH collect(c) AS chunks

        UNWIND range(0, size(chunks) - 2) AS i
        WITH chunks[i] AS current_chunk,
             chunks[i + 1] AS next_chunk

        MERGE (current_chunk)-[:NEXT_CHUNK]->(next_chunk)
        """
    )


# =========================
# 7. 확인용 출력
# =========================

def print_summary(graph: Neo4jGraph) -> None:
    doc_count = graph.query("""
    MATCH (d:KBDocument)
    RETURN count(d) AS count
    """)

    page_count = graph.query("""
    MATCH (p:Page)
    RETURN count(p) AS count
    """)

    chunk_count = graph.query("""
    MATCH (c:Chunk)
    RETURN count(c) AS count
    """)

    rel_count = graph.query("""
    MATCH ()-[r]->()
    RETURN count(r) AS count
    """)

    print("문서 수:", doc_count[0]["count"])
    print("페이지 수:", page_count[0]["count"])
    print("청크 수:", chunk_count[0]["count"])
    print("관계 수:", rel_count[0]["count"])


# =========================
# 8. 실행
# =========================

def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)

    print("불러온 청크 수:", len(chunks))

    graph = get_graph()

    create_constraints(graph)
    save_chunks(graph, chunks)
    create_next_chunk_relationships(graph)

    graph.refresh_schema()

    print("\n저장 완료")
    print_summary(graph)

    print("\nGraph schema:")
    print(graph.schema)


if __name__ == "__main__":
    main()