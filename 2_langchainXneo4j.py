import os

from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

graph = Neo4jGraph(
    url=URI,
    username=USERNAME,
    password=PASSWORD,
    database="neo4j",
)

graph.query(
    """
    CREATE
    (kim:Person {이름: "김민수", 나이: 34}),
    (refactor:Project {이름: "결제 시스템 리팩터링", 상태: "진행중"}),
    (improve:Project {이름: "장애율 개선 프로젝트", 상태: "진행중"}),
    (security:Team {이름: "보안팀", 역할: "공동 진행팀"}),
    (platform:Team {이름: "플랫폼팀", 역할: "공동 진행팀"})
    RETURN kim, refactor, improve, security, platform;
    """
)

graph.query(
    """
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
    """
)

# graph.query(
#     """
#     MATCH (n)
#     DETACH DELETE n;    
#     """
# )

# graph.query(
#     """
#     CREATE
#       (kim:Person {이름: $person_name, 나이: $person_age}),
#       (refactor:Project {이름: $refactor_name, 상태: $project_status}),
#       (improve:Project {이름: $improve_name, 상태: $project_status}),
#       (security:Team {이름: $security_team_name, 역할: $team_role}),
#       (platform:Team {이름: $platform_team_name, 역할: $team_role})
#     RETURN kim, refactor, improve, security, platform;
#     """,
#     params={
#         "person_name": "김민수",
#         "person_age": 34,
#         "refactor_name": "결제 시스템 리팩터링",
#         "improve_name": "장애율 개선 프로젝트",
#         "project_status": "진행중",
#         "security_team_name": "보안팀",
#         "platform_team_name": "플랫폼팀",
#         "team_role": "공동 진행팀",
#     }
# )
