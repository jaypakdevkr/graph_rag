import json
import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# =========================
# 1. 경로 설정
# =========================

BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "outputs" / "parsed_docs.jsonl"
OUTPUT_PATH = BASE_DIR / "outputs" / "chunks.jsonl"


# =========================
# 2. JSONL 로드
# =========================

def load_parsed_documents(input_path: Path) -> list[Document]:
    """
    01_load_pdfplumber.py에서 저장한 parsed_docs.jsonl을
    LangChain Document 리스트로 다시 불러오기
    """
    if not input_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")

    docs = []

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)

            metadata = dict(row.get("metadata", {}))
            metadata["parent_doc_id"] = row.get("doc_id")

            docs.append(
                Document(
                    page_content=row["page_content"],
                    metadata=metadata,
                )
            )

    return docs


# =========================
# 3. chunk_id 생성
# =========================

def make_chunk_id(doc: Document, chunk_index: int) -> str:
    """
    같은 문서를 같은 방식으로 청킹하면 같은 id가 나오도록
    source, page, chunk_index, text 일부를 기반으로 hash 생성
    """
    source = doc.metadata.get("source", "unknown")
    page = doc.metadata.get("page_number", doc.metadata.get("page", "unknown"))
    text = doc.page_content[:100]

    raw = f"{source}:{page}:{chunk_index}:{text}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    return f"chunk-{digest}"


# =========================
# 4. 청킹
# =========================

def chunk_documents(docs: list[Document]) -> list[Document]:
    """
    약관 문서 구조를 고려해 청킹

    chunk_size:
      - 한 청크의 최대 문자 수

    chunk_overlap:
      - 청크 사이에 겹쳐서 넣을 문자 수
      - 검색 시 앞뒤 문맥이 끊기지 않도록 설정
    """

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=80,
        add_start_index=True,
        keep_separator=True,
        separators=[
            "\n제",      # 제1조, 제2조 같은 조항
            "\n①",
            "\n②",
            "\n③",
            "\n④",
            "\n⑤",
            "\n1.",
            "\n2.",
            "\n3.",
            "\n가.",
            "\n나.",
            "\n다.",
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    chunks = text_splitter.split_documents(docs)

    cleaned_chunks = []

    for i, chunk in enumerate(chunks):
        text = chunk.page_content.strip()

        if not text:
            continue

        # 너무 짧은 청크는 제거
        if len(text) < 20:
            continue

        chunk.metadata["chunk_index"] = len(cleaned_chunks)
        chunk.metadata["chunk_id"] = make_chunk_id(chunk, len(cleaned_chunks))
        chunk.metadata["char_count"] = len(text)

        chunk.page_content = text

        cleaned_chunks.append(chunk)

    return cleaned_chunks


# =========================
# 5. JSONL 저장
# =========================

def save_chunks_to_jsonl(chunks: list[Document], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            row = {
                "chunk_id": chunk.metadata["chunk_id"],
                "chunk_index": chunk.metadata["chunk_index"],
                "page_content": chunk.page_content,
                "metadata": chunk.metadata,
            }

            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# =========================
# 6. 실행
# =========================

def main() -> None:
    docs = load_parsed_documents(INPUT_PATH)
    print("불러온 문서 수:", len(docs))

    chunks = chunk_documents(docs)
    print("생성된 청크 수:", len(chunks))

    save_chunks_to_jsonl(chunks, OUTPUT_PATH)
    print("저장 완료:", OUTPUT_PATH)

    print("\n미리보기")
    print("=" * 80)

    for chunk in chunks[:3]:
        print("chunk_id:", chunk.metadata["chunk_id"])
        print("page:", chunk.metadata.get("page_number", chunk.metadata.get("page")))
        print("start_index:", chunk.metadata.get("start_index"))
        print("char_count:", chunk.metadata["char_count"])
        print(chunk.page_content[:500])
        print("-" * 80)


if __name__ == "__main__":
    main()