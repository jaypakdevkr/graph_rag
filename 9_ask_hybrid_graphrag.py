import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_neo4j import Neo4jGraph, Neo4jVector
from langchain_core.prompts import ChatPromptTemplate


# ============================================================
# 1. 환경 변수 로드
# ============================================================

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL",
    "text-embedding-3-small",
)


# ============================================================
# 2. 7_build_hybrid_index.py에서 만든 인덱스 이름
# ------------------------------------------------------------#
# chunk_vector_index:
#   Chunk.embedding 속성을 대상으로 하는 vector index
#
# chunk_keyword_index:
#   Chunk.text 속성을 대상으로 하는 full-text keyword index
# ============================================================

VECTOR_INDEX_NAME = "chunk_vector_index"
KEYWORD_INDEX_NAME = "chunk_keyword_index"


# ============================================================
# 3. Neo4j 연결
# ------------------------------------------------------------
# Neo4jGraph는 여기서 상태 확인용으로 사용합니다.
# 실제 Hybrid Search는 Neo4jVector가 수행합니다.
# ============================================================

graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,
)

# ============================================================
# 4. Embedding / LLM 준비
# ------------------------------------------------------------
# embeddings:
#   질문을 embedding으로 바꾸는 데 사용합니다.
#   7_build_hybrid_index.py에서 Chunk.embedding을 만들 때 사용한
#   embedding 모델과 같은 모델 사용
#
# llm:
#   검색된 context를 바탕으로 최종 답변을 생성합니다.
# ============================================================

embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL,
)

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)

# ============================================================
# 5. Graph Expansion Query
# ------------------------------------------------------------
# [Hybrid GraphRAG 핵심]
#
# Neo4jVector가 먼저 Hybrid Search를 수행합니다.
#
# 1차 검색:
#   - Vector Search: Chunk.embedding 검색
#   - Keyword Search: Chunk.text 검색
#
# 그 결과로 검색된 Chunk가 retrieval_query 안에서
# node 변수로 전달됩니다.
#
# 이후 아래 Cypher가 node에서 출발해 그래프를 확장합니다.
#
# 2차 그래프 확장:
#   - 이전 Chunk
#   - 다음 Chunk
#   - Chunk가 언급한 KGEntity
#   - KGEntity 주변 관계
#
# 반환 규칙:
#   LangChain Neo4jVector의 retrieval_query는 반드시
#   text, score, metadata 세 컬럼을 반환해야 합니다.
# ============================================================

retrieval_query = """
OPTIONAL MATCH (node)-[:MENTIONS]->(entity:KGEntity)

WITH
    node,
    score,
    collect(DISTINCT {
        name: entity.name,
        type: entity.type
    }) AS entities

RETURN
    {
        chunk_text: node.text,
        entities: entities
    } AS text,
    score,
    {
        chunk_id: node.id,
        page_number: node.page_number,
        source: node.source
    } AS metadata
"""


# ============================================================
# 6. Hybrid GraphRAG VectorStore 불러오기
# ------------------------------------------------------------
# from_existing_index:
#   이미 만들어진 vector index를 불러옵니다.
#   새 embedding을 다시 저장하지 않습니다.
#
# search_type="hybrid":
#   vector search + keyword search를 함께 사용합니다.
#
# retrieval_query:
#   hybrid search로 찾은 Chunk 주변의 graph context를 확장합니다.
# ============================================================

vector_store = Neo4jVector.from_existing_index(
    embedding=embeddings,
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,

    index_name=VECTOR_INDEX_NAME,
    keyword_index_name=KEYWORD_INDEX_NAME,

    search_type="hybrid",
    retrieval_query=retrieval_query,
)


# ============================================================
# 7. Hybrid GraphRAG 검색 함수
# ------------------------------------------------------------
# similarity_search_with_score()를 직접 호출합니다.
#
# 내부 동작:
# 1. 질문 embedding 생성
# 2. vector index 검색
# 3. keyword index 검색
# 4. 결과 병합
# 5. 검색된 Chunk를 node로 하여 retrieval_query 실행
# 6. graph-expanded context 반환
# ============================================================

def search_hybrid_graphrag(question: str, k: int = 5):
    results = vector_store.similarity_search_with_score(
        question,
        k=k,
    )

    return results


# ============================================================
# 8. 검색 결과를 LLM context로 변환
# ------------------------------------------------------------
# similarity_search_with_score() 반환 형태:
#
# [
#   (Document, score),
#   (Document, score),
#   ...
# ]
#
# retrieval_query에서 RETURN한 text가 Document.page_content가 됩니다.
# metadata는 Document.metadata에 들어갑니다.
# ============================================================

def format_context(results) -> str:
    if not results:
        return "검색된 문맥이 없습니다."

    formatted = []

    for i, (doc, score) in enumerate(results, start=1):
        formatted.append(
            f"""
[검색 결과 {i}]
검색 점수:
{score}

metadata:
{doc.metadata}

검색된 Chunk 및 Graph Context:
{doc.page_content}
"""
        )

    return "\n\n".join(formatted)


# ============================================================
# 9. 답변 생성 프롬프트
# ============================================================

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
너는 보험 약관 기반 Hybrid GraphRAG assistant다.

너는 다음 세 가지 검색 결과를 바탕으로 답변한다.
1. Vector Search로 찾은 의미적으로 유사한 Chunk
2. Keyword Search로 찾은 키워드 일치 Chunk
3. 검색된 Chunk 주변의 Knowledge Graph 관계

답변 규칙:
- 반드시 제공된 context에 근거해서 답변하라.
- context에 없는 내용은 추측하지 말고 모른다고 말하라.
"""
    ),
    (
        "human",
        """
질문:
{question}

검색된 context:
{context}
"""
    )
])


# ============================================================
# 10. 최종 질의응답 함수
# ------------------------------------------------------------#
# 1. Hybrid GraphRAG 검색
# 2. 검색 결과를 context로 변환
# 3. Prompt 생성
# 4. LLM 답변 생성
# ============================================================

def answer_question(question: str, k: int = 5, show_context: bool = False) -> str:
    # 1. Vector Search + Keyword Search + Graph Expansion
    search_results = search_hybrid_graphrag(question, k=k)

    # 2. 검색 결과를 LLM용 context로 변환
    context = format_context(search_results)

    # 3. Prompt에 question과 context를 채움
    messages = prompt.format_messages(
        question=question,
        context=context,
    )

    # 4. LLM 호출
    response = llm.invoke(messages)

    return response.content


# ============================================================
# 12. 테스트 질문
# ============================================================

questions = [
    "우리집 댕댕이가 의자를 파손해 보험금 청구하려 하는데 필요한 서류와 지급 절차는 어떻게 돼?",
    "우리집 강아지가 너무 짖어 시끄럽다고 보상하라는데 이 보험으로 커버 가능해?",
]


for question in questions:
    print("=" * 80)
    print("질문:", question)

    answer = answer_question(
        question,
        k=5,
        show_context=False,
    )

    print("\n답변:")
    print(answer)