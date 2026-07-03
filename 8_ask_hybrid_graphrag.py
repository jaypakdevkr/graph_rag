import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_neo4j import Neo4jGraph, Neo4jVector, GraphCypherQAChain
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate


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
# ------------------------------------------------------------
# 반드시 7번 파일에서 생성한 이름과 같아야 합니다.
# ============================================================

VECTOR_INDEX_NAME = "chunk_vector_index"
KEYWORD_INDEX_NAME = "chunk_keyword_index"


# ============================================================
# 3. Neo4j 연결
# ============================================================

graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,
)


# ============================================================
# 4. Embedding / LLM 준비
# ============================================================

embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL,
)

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)

# ============================================================
# 5. Vector + Keyword Retriever 준비
# ------------------------------------------------------------
#
# 역할:
# - Chunk.embedding 기반 Vector Search
# - Chunk.text 기반 Keyword Search
# - 두 결과를 합쳐 관련 Chunk 반환
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
)


def search_vector_keyword(question: str, k: int = 5):
    """
    Vector Search + Keyword Search로 관련 Chunk 조회
    """

    result = vector_store.similarity_search_with_score(
        question,
        k=k,
    )
    
    print("result : " , result)
    return result


def format_vector_keyword_context(results) -> str:
    """
    Vector + Keyword 검색 결과를 LLM에게 전달할 문자열 context로 변환
    """

    if not results:
        return "Vector + Keyword 검색 결과가 없습니다."

    formatted = []

    for i, (doc, score) in enumerate(results, start=1):
        formatted.append(
            f"""
[Hybrid 검색 결과 {i}]
score:
{score}

metadata:
{doc.metadata}

chunk_text:
{doc.page_content}
"""
        )

    return "\n\n".join(formatted)


# ============================================================
# 6. GraphCypherQAChain 준비
# ------------------------------------------------------------
#
# 역할:
# - 사용자 질문을 Cypher로 변환
# - Neo4j 그래프 구조를 직접 조회
# - KGEntity, 관계, evidence, 연결 Chunk 등을 검색
# ============================================================

CYPHER_GENERATION_TEMPLATE = """
당신은 Neo4j Cypher 전문가입니다.
사용자의 질문에 답하기 위한 Cypher만 생성하세요.

규칙:
- 읽기 전용 쿼리만 생성하세요.
- CREATE, MERGE, DELETE, SET, REMOVE, DROP 사용 금지.
- 반환 결과는 최대 10개로 제한하세요.
- 긴 Chunk.text 전체를 너무 많이 반환하지 마세요.
- 필요한 경우 name, type, evidence, page_number, chunk_id, source 정도만 반환하세요.
- 백틱(`)을 사용하지 마세요.
- Cypher 코드만 출력하세요. 설명하지 마세요.

스키마:
{schema}

질문:
{question}
"""

cypher_prompt = PromptTemplate(
    input_variables=["schema", "question"],
    template=CYPHER_GENERATION_TEMPLATE,
)

graph_chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    cypher_prompt=cypher_prompt,
    verbose=True,
    validate_cypher=True,
    allow_dangerous_requests=True,
    top_k=10,
)


def search_graph_cypher(question: str) -> dict:
    """
    GraphCypherQAChain으로 그래프 구조 기반 검색 수행

    반환값에는 보통 다음이 들어감
    - result: GraphCypherQAChain의 1차 자연어 답변
    - intermediate_steps: 생성된 Cypher와 DB 조회 결과
    """
    result = graph_chain.invoke({"query": question})

    print("graphrag_result : ", result)

    return result


def format_graph_context(graph_search_result: dict) -> str:
    """
    GraphCypherQAChain 결과를 LLM에게 전달할 문자열 context로 변환합니다.
    """

    graph_answer = graph_search_result.get("result", "")

    formatted = []
    formatted.append(graph_answer)

    return "\n".join(formatted)


# ============================================================
# 7. 최종 답변 생성 프롬프트
# ------------------------------------------------------------
# 두 독립 검색 결과를 모두 LLM에게 전달합니다.
#
# 1. Vector + Keyword 검색 결과
# 2. GraphCypherQAChain 검색 결과
#
# LLM은 두 결과를 비교/종합해서 최종 답변합니다.
# ============================================================

final_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
너는 보험 약관 기반 Hybrid GraphRAG assistant다.

너에게는 두 종류의 검색 결과가 제공된다.

1. Vector + Keyword 검색 결과
   - 질문과 의미적으로 유사하거나 키워드가 일치하는 Chunk
   - 원문 근거를 확인하는 데 유용하다.

2. GraphCypherQAChain 검색 결과
   - Neo4j Knowledge Graph 구조를 기반으로 조회한 결과
   - 조항, 필요서류, 지급절차, 보상 제외 조건 등 관계를 확인하는 데 유용하다.

답변 규칙:
- 반드시 제공된 검색 결과에 근거해서 답변하라.
- 검색 결과에 없는 내용은 추측하지 말고 모른다고 말하라.
"""
    ),
    (
        "human",
        """
질문:
{question}

[1] Vector + Keyword 검색 context:
{vector_keyword_context}

[2] GraphCypherQAChain 검색 context:
{graph_context}
"""
    )
])


# ============================================================
# 8. 최종 Hybrid GraphRAG 질의응답 함수
# ------------------------------------------------------------
# 이 함수가 전체 구조를 실행합니다.
#
# 1. Vector + Keyword Retriever 실행
# 2. GraphCypherQAChain 실행
# 3. 두 결과를 문자열 context로 변환
# 4. LLM 최종 답변 생성
# ============================================================

def answer_question(
    question: str,
    hybrid_k: int = 5,
    show_context: bool = False,
) -> str:
    # ------------------------------------------------------------
    # 검색 1: Vector + Keyword Retriever
    # ------------------------------------------------------------
    vector_keyword_results = search_vector_keyword(
        question,
        k=hybrid_k,
    )

    vector_keyword_context = format_vector_keyword_context(
        vector_keyword_results,
    )

    # ------------------------------------------------------------
    # 검색 2: GraphCypherQAChain
    # ------------------------------------------------------------
    graph_search_result = search_graph_cypher(question)

    graph_context = format_graph_context(graph_search_result)

    # ------------------------------------------------------------
    # 두 검색 결과 확인용 출력
    # ------------------------------------------------------------
    if show_context:
        print("\n" + "-" * 80)
        print("[Vector + Keyword 검색 context]")
        print("-" * 80)
        print(vector_keyword_context)

        print("\n" + "-" * 80)
        print("[GraphCypherQAChain 검색 context]")
        print("-" * 80)
        print(graph_context)

    # ------------------------------------------------------------
    # 최종 답변 생성
    # ------------------------------------------------------------
    messages = final_prompt.format_messages(
        question=question,
        vector_keyword_context=vector_keyword_context,
        graph_context=graph_context,
    )

    response = llm.invoke(messages)

    return response.content


# ============================================================
# 9. 테스트 질문
# ============================================================

questions = [
    "우리집 댕댕이가 의자를 파손해 보험금 청구하려 하는데 필요한 서류와 지급 절차는 어떻게 돼?",
    "우리집 강아지가 너무 짖어서 윗집에서 피해보상을 하라는데, 가입한 보험으로 처리 될까?",
]


for question in questions:
    print("=" * 80)
    print("질문:", question)


    answer = answer_question(
        question,
        hybrid_k=5,
        show_context=False,
    )

    print("\n최종 답변:")
    print(answer)