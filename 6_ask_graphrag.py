import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.prompts import PromptTemplate

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,
)
graph.refresh_schema()

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)

CYPHER_GENERATION_TEMPLATE = """
당신은 Neo4j Cypher 전문가입니다.
사용자의 질문에 답하기 위한 Cypher만 생성하세요.

규칙:
- 읽기 전용 쿼리만 생성하세요. CREATE, MERGE, DELETE, SET, REMOVE 사용 금지.
- 반환 결과는 최대 10개로 제한하세요.
- 긴 Chunk.text 전체를 많이 반환하지 마세요.
- 필요한 경우 evidence, name, type, page_number, chunk_id 정도만 반환하세요.
- 가변 길이 경로 `*0..3` 같은 넓은 탐색은 가능하면 피하세요.
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

chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    cypher_prompt=cypher_prompt,
    verbose=True,
    validate_cypher=True,
    allow_dangerous_requests=True,
    top_k=5,
)

questions = [
    "우리집 댕댕이가 너무 짖어서 윗집에서 피해보상을 하라는데, 가입한 보험으로 처리 될까?",
    "우리집 강아지 죽으면 위로금은 보상돼?",
    "보상하지 않는 경우는 뭐야?",
    "보험금 청구할 때 어떤 서류가 필요해?",
    "보험금은 언제 지급돼?",
]

for question in questions:
    print("=" * 80)
    print("질문:", question)

    try:
        result = chain.invoke({"query": question})

        print("\n답변:")
        print(result["result"])

    except Exception as e:
        print("\n에러 발생:")
        print(type(e).__name__)
        print(e)