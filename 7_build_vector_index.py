import os
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_neo4j import Neo4jGraph, Neo4jVector


# ============================================================
# 1. 환경 변수 로드
# ------------------------------------------------------------#
# chunk_vector_index:
#   Chunk.embedding 속성을 대상으로 하는 vector index
#
# chunk_keyword_index:
#   Chunk.text 속성을 대상으로 하는 full-text keyword index
# ============================================================

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

VECTOR_INDEX_NAME = "chunk_vector_index"
KEYWORD_INDEX_NAME = "chunk_keyword_index"


# ============================================================
# 2. Neo4j 연결
# ============================================================

graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,
)

# ============================================================
# 3. Chunk 데이터 확인
# ============================================================

chunk_count = graph.query("""
MATCH (c:Chunk)
RETURN count(c) AS count
""")

print("Chunk 수:", chunk_count[0]["count"])

# ============================================================
# 4. Embedding 모델 준비
# ============================================================

embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL,
)

# ============================================================
# 5. 기존 Chunk graph에서 Hybrid Index 생성
# ------------------------------------------------------------
# [Hybrid RAG 구축 단계]
#
# 이 단계에서 하는 일:
# 1. Chunk.text를 읽음
# 2. Chunk.text의 embedding을 생성
# 3. Chunk.embedding 속성에 저장
# 4. Chunk.embedding에 vector index 생성
# 5. Chunk.text에 full-text keyword index 생성
#
# 결과:
# - semantic search 가능
# - keyword search 가능
# - search_type="hybrid"로 둘을 함께 사용 가능
# ============================================================

vector_store = Neo4jVector.from_existing_graph(
    embedding=embeddings,
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,

    index_name=VECTOR_INDEX_NAME,
    keyword_index_name=KEYWORD_INDEX_NAME,

    node_label="Chunk",
    text_node_properties=["text"],
    embedding_node_property="embedding",

    search_type="hybrid",
)


# ============================================================
# 6. Index 생성 완료 대기
# ============================================================

graph.query("CALL db.awaitIndexes(30)")


# ============================================================
# 7. 생성된 인덱스 확인
# ============================================================

indexes = graph.query("""
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties
WHERE name IN [$vector_index_name, $keyword_index_name]
RETURN name, type, labelsOrTypes, properties
ORDER BY name
""", params={
    "vector_index_name": VECTOR_INDEX_NAME,
    "keyword_index_name": KEYWORD_INDEX_NAME,
})

print("\n생성된 인덱스:")
for row in indexes:
    print(row)


# ============================================================
# 8. Embedding 저장 확인
# ============================================================

embedding_check = graph.query("""
MATCH (c:Chunk)
RETURN
    count(c) AS total_chunks,
    count(c.embedding) AS embedded_chunks
""")

print("\nEmbedding 저장 확인:")
print(embedding_check[0])


# ============================================================
# 9. 간단 Hybrid RAG 테스트
# ============================================================

query = "강아지가 다른 사람 물건을 망가뜨렸을 때 보험금 청구 서류"

results = vector_store.similarity_search_with_score(query, k=3)

print("\n검색 테스트:")
for doc, score in results:
    print("=" * 80)
    print("score:", score)
    print("metadata:", doc.metadata)
    print(doc.page_content[:500])