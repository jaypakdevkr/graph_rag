import re
import json
import unicodedata
from pathlib import Path

from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.documents import Document


# =========================
# 1. 경로 설정
# =========================

BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = BASE_DIR / "data" / "kb.pdf"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_PATH = OUTPUT_DIR / "parsed_docs.jsonl"


# =========================
# 2. 전처리용 정규표현식
# =========================

# 페이지 번호: - 3 -, 3, -3- 등
PAGE_NUMBER_RE = re.compile(r"^-?\s*\d+\s*-?$")

# 목차 점선: "특약명 .......... 255"
DOT_LEADER_RE = re.compile(r"[·.]{5,}\s*\d+$")

# 유니코드 private use 영역: \uf000 같은 깨진 bullet
PRIVATE_USE_RE = re.compile(r"[\uf000-\uf8ff]")

# 눈에 안 보이는 제어 문자
INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e]")

# 약관 조항 제목: 제1조(보상하는 손해)
ARTICLE_TITLE_RE = re.compile(r"^제\d+조\(.+\)")

# 번호 항목: ①, ②, 1., 2., 가., 나. 등
LIST_ITEM_RE = re.compile(
    r"^("
    r"[①②③④⑤⑥⑦⑧⑨⑩]"
    r"|\d+\."
    r"|[가-하]\."
    r"|【.+】"
    r"|<부표>"
    r")"
)


def is_new_paragraph(line: str) -> bool:
    """
    새 줄로 유지해야 하는 문장인지 판단
    약관의 조항 제목, 항 번호, 목록 번호는 새 줄로 유지
    """
    if ARTICLE_TITLE_RE.match(line):
        return True

    if LIST_ITEM_RE.match(line):
        return True

    if line.endswith("특별약관") or "특별약관(" in line:
        return True

    return False


def join_wrapped_lines(lines):
    """
    PDF에서 줄 단위로 끊긴 문장을 자연스럽게 연결
    조항 제목, bullet, 번호 항목은 새 줄로 유지
    """
    merged = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # 페이지 번호 제거
        if PAGE_NUMBER_RE.fullmatch(line):
            continue

        # 목차/색인: "특약명 .......... 255" 제거
        if DOT_LEADER_RE.search(line):
            continue

        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]

        # 현재 줄이 조항 제목/번호 항목이면 새 줄 유지
        if is_new_paragraph(line):
            merged.append(line)
            continue

        # 이전 줄이 문장 종결이면 다음 줄은 새 문장/문단으로 유지
        if re.search(r"(다\.|요\.|함\.|됨\.|음\.|[.!?])$", prev):
            merged.append(line)
            continue

        # 한글 줄바꿈은 보통 PDF 줄바꿈이므로 붙임
        # 예: 있습니 + 다. => 있습니다.
        if re.search(r"[가-힣]$", prev) and re.match(r"^[가-힣]", line):
            merged[-1] = prev + line
        else:
            merged[-1] = prev + " " + line

    return "\n".join(merged)


def clean_korean_pdf_text(text: str) -> str:
    """
    한국어 PDF 약관 텍스트 정제 함수
    """
    if not text:
        return ""

    # 약관 번호 ①, ② 등을 최대한 유지하기 위해 NFC 사용
    text = unicodedata.normalize("NFC", text)

    # 눈에 안 보이는 문자 제거
    text = INVISIBLE_RE.sub("", text)

    # \uf000 같은 깨진 bullet을 일반 bullet로 변환
    text = PRIVATE_USE_RE.sub("\n- ", text)

    # 자주 나오는 bullet 문자 통일
    text = text.replace("ㆍ", "- ")
    text = text.replace("·", "- ")

    # 줄바꿈 정규화
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 탭, 여러 공백 정리
    text = re.sub(r"[ \t]+", " ", text)

    # 줄 단위 strip
    lines = [line.strip() for line in text.split("\n")]

    # PDF 줄바꿈 병합
    text = join_wrapped_lines(lines)

    # 과도한 공백 정리
    text = re.sub(r"[ \t]+", " ", text)

    # 과도한 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 문장부호 앞 공백 제거
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)

    return text.strip()


def is_noise_document(doc: Document) -> bool:
    """
    RAG에 넣기 애매한 노이즈 페이지 제거용
    """
    text = doc.page_content.strip()

    if not text:
        return True

    if len(text) < 10:
        return True

    if PAGE_NUMBER_RE.fullmatch(text):
        return True

    if DOT_LEADER_RE.search(text) and len(text) < 100:
        return True

    return False


def preprocess_documents(docs, drop_noise=True):
    """
    Document 리스트 전체 전처리
    """
    cleaned_docs = []

    for doc in docs:
        cleaned_text = clean_korean_pdf_text(doc.page_content)

        metadata = dict(doc.metadata)

        # PDFPlumberLoader의 page는 보통 0부터 시작할 수 있어서,
        # 사람이 보기 편한 page_number를 따로 추가합니다.
        if "page" in metadata:
            metadata["page_number"] = metadata["page"] + 1

        new_doc = Document(
            page_content=cleaned_text,
            metadata=metadata,
        )

        if drop_noise and is_noise_document(new_doc):
            continue

        cleaned_docs.append(new_doc)

    return cleaned_docs


def save_documents_to_jsonl(docs, output_path: Path):
    """
    다음 단계에서 다시 읽기 쉽도록 JSONL로 저장
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for i, doc in enumerate(docs):
            row = {
                "doc_id": f"page-{i}",
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_pdf_with_pdfplumber(pdf_path: Path):
    """
    PDFPlumberLoader로 PDF를 페이지 단위 Document로 로드합니다.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    loader = PDFPlumberLoader(str(pdf_path))
    docs = loader.load()

    return docs


def main():
    print("PDF 경로:", PDF_PATH)

    docs = load_pdf_with_pdfplumber(PDF_PATH)
    print("원본 Document 수:", len(docs))

    cleaned_docs = preprocess_documents(docs)
    print("전처리 후 Document 수:", len(cleaned_docs))

    save_documents_to_jsonl(cleaned_docs, OUTPUT_PATH)
    print("저장 완료:", OUTPUT_PATH)

    print("\n미리보기")
    print("=" * 80)
    print(cleaned_docs[-1].metadata)
    print(cleaned_docs[-1].page_content[:1000])


if __name__ == "__main__":
    main()