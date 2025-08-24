import re
import warnings
warnings.filterwarnings("ignore")

def clean_text(text: str) -> str:
    """
    Làm sạch văn bản: loại bỏ ký tự xuống dòng, thừa khoảng trắng.
    """
    if not isinstance(text, str):
        return ""
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_cols(df, lst: list):
    for col in lst:
        df[col] = df[col].apply(lambda x: clean_text(x.lower()))

# Phat hien tieng anh hay viet. tao series df['language'] co gia tri la ngon ngu nhu vi-en.
# goi model phat hien ngon ngu
# model = fasttext.load_model("lid.176.bin")

# model dung numpy duoi 2.0 (version)
# print(model.predict("Lương thưởng hấp dẫn, môi trường năng động")) 
# -> ('__label__vi', 0.99)

# def detect_language(text: str) -> str:
    # if not isinstance(text, str) or not text.strip():
    #     return "unknown"
    # labels, probs = model.predict(text, k=1)
    # if probs[0] >= 0.8: 
    #     return labels[0].replace("__label__", "")  # type: ignore
    # else:
    #     return "unknown"
    
import re
from typing import List, Optional, Dict, Tuple

# ===== Helpers =====

NUM_VI = {
    'm': 1_000_000, 'tr': 1_000_000, 'triệu': 1_000_000,
    'k': 1_000, 'nghìn': 1_000, 'ngàn': 1_000,
    'tỷ': 1_000_000_000, 'ty': 1_000_000_000
}

CURRENCY_SYMS = {
    'vnd': ['vnd', 'vnđ', 'đ', 'đồng'],
    'usd': ['$', 'usd', 'us$'],
    'jpy': ['yên', 'yen', '¥', 'jpy']
}

def _to_int(s: str) -> Optional[int]:
    s = s.replace(',', '').replace('.', '')
    return int(s) if s.isdigit() else None

def _norm_amount(num_str: str, unit: Optional[str]) -> Optional[int]:
    """
    Chuẩn hoá các số như:
      - "30", "30m", "30tr", "30 triệu", "30000000", "300k", "300 nghìn"
    Trả về VND nếu đơn vị là m/tr/triệu/k/nghìn/ngàn/tỷ; nếu không rõ thì số tuyệt đối (đã bỏ , .)
    """
    num_str = num_str.strip().lower()
    # tách số & hậu tố dính liền (vd "30tr", "30m")
    m = re.match(r'(\d+(?:[.,]\d+)?)([a-zà-ỹ]*)', num_str)
    if not m:
        return None
    val, suf = m.groups()
    val = float(val.replace(',', '.'))
    suf = (suf or '').strip()

    # đơn vị rời (vd "30 triệu")
    if unit:
        suf = unit.strip().lower()

    if suf in NUM_VI:
        return int(val * NUM_VI[suf])
    # không có hậu tố → số “thô” (có thể là VND hoặc USD tuỳ ngữ cảnh)
    return int(val)

def _find_currency(text_lower: str) -> str:
    # ưu tiên theo dấu hiệu dễ thấy nhất
    if any(sym in text_lower for sym in CURRENCY_SYMS['usd']):
        return 'USD'
    if any(sym in text_lower for sym in CURRENCY_SYMS['jpy']):
        return 'JPY'
    if any(sym in text_lower for sym in CURRENCY_SYMS['vnd']):
        return 'VND'
    # fallback: nếu có “tr/triệu/k/nghìn” mà không có $ → VND
    if re.search(r'\b(\d+)\s*(m|tr|triệu|k|nghìn|ngàn|tỷ|ty)\b', text_lower):
        return 'VND'
    return 'UNKNOWN'

def _mid(a: float, b: float) -> float:
    return (a + b) / 2.0

# ===== 1) Kinh nghiệm =====

EXPERIENCE_PATTERNS = [
    # Ranges: "3-5 năm", "03–08 năm", "3 to 5 years"
    (re.compile(r'(\d+)\s*[-–]\s*(\d+)\s*(?:năm|years)\b', re.I), 'range'),
    (re.compile(r'(?:from|từ)\s*(\d+)\s*(?:to|đến|-|–)\s*(\d+)\s*(?:năm|years)\b', re.I), 'range'),
    # 5+ years, 3+ năm, more than 3 years
    (re.compile(r'(?:more than|over|>\s*)?(\d+)\s*\+\s*(?:years|năm)\b', re.I), 'atleast'),
    (re.compile(r'(?:more than|over)\s*(\d+)\s*(?:years|năm)\b', re.I), 'atleast'),
    # Ít nhất / Tối thiểu / At least
    (re.compile(r'(?:ít nhất|tối thiểu|at least)\s*(\d+)\s*(?:năm|years)\b', re.I), 'atleast'),
    # đơn lẻ: "5 years", "3 năm"
    (re.compile(r'\b(\d+)\s*(?:năm|years)\b', re.I), 'single'),
]

EXPERIENCE_PATTERNS += [
    # 1) "at least 1 year experience with/in/using ..."
    (re.compile(
        r'(?:at\s*least|ít\s*nhất|it\s*nhat|tối\s*thiểu|toi\s*thieu)\s*(\d+)\s*(?:year|years|năm)\s*(?:of\s+)?(?:experience|exp)(?:\s+(?:with|in|using)\b.*)?',
        re.I
    ), 'atleast'),

    # 2) "from 2 year of experience ..." (không có vế 'to ...')
    (re.compile(
        r'\bfrom\s*(\d+)\s*(?:year|years|năm)\s*(?:of\s+)?(?:experience|exp)(?:\s+(?:with|in|using)\b.*)?',
        re.I
    ), 'atleast'),
]

def extract_experience(text: str) -> Optional[float]:
    """
    Trả về số năm KN (float).
    - Range → trung bình (vd 3-5 năm → 4.0)
    - "X+" hoặc "ít nhất/at least" → X.0
    - Bắt được nhiều dạng xuất hiện trong file JSON (3–8 năm, 5+ years, etc.)
    """
    tl = text.lower()
    for pat, kind in EXPERIENCE_PATTERNS:
        m = pat.search(tl)
        if not m:
            continue
        if kind == 'range':
            a, b = map(int, m.groups())
            return _mid(a, b)
        if kind == 'atleast':
            return float(m.group(1))
        if kind == 'single':
            return float(m.group(1))
    return None

# ===== 2) Lương =====

# nắm bắt các mẫu trong JSON: "Upto $2500", "2500$ - $3500", "~$1200", "up to 30Tr/VNĐ"
SALARY_RANGE_PATS = [
    # $1200 - $1500 ; 2500$ - $3500 ; 30tr - 40tr
    re.compile(r'(\$?\s*\d[\d,\.]*\s*(?:m|tr|triệu|k|nghìn|ngàn)?)[\s]*[-–to]{1,3}[\s]*(\$?\s*\d[\d,\.]*\s*(?:m|tr|triệu|k|nghìn|ngàn)?)', re.I),
]

SALARY_UPTO_PATS = [
    re.compile(r'(?:up\s*to|upto|đến)\s*(\$?\s*\d[\d,\.]*\s*(?:m|tr|triệu|k|nghìn|ngàn)?)', re.I)
]

SALARY_SINGLE_PATS = [
    # "~$1200", "$1200", "1200$", "30tr", "30 triệu"
    re.compile(r'(?:~|≈)?\s*(\$?\s*\d[\d,\.]*\s*(?:m|tr|triệu|k|nghìn|ngàn)?)(?:\s*/\s*(?:tháng|month))?', re.I)
]


def extract_salary(text: str, vnd_per_usd: int = 25_000) -> Optional[int]:
    """
    Trả về mức lương cao nhất (USD/tháng) từ chuỗi:
      - USD: $2500 | 2500$ | 2500 usd | ~$1200 | 2500$ - $3500 | 1200-1500 usd
      - VND (triệu): 30m | 30 tr | 30 triệu | 15-20tr | up to 30tr
      - Up to / Upto: "upto $2500", "up to 30tr"
    """
    if not isinstance(text, str) or not text.strip():
        return None
    tl = text.lower()

    usd_vals = []

    # --- USD đơn lẻ ---
    usd_vals += [int(x) for x in re.findall(r"\$\s*(\d{2,5})\b", tl)]           # $3500
    usd_vals += [int(x) for x in re.findall(r"\b(\d{2,5})\s*\$", tl)]           # 2500$
    usd_vals += [int(x) for x in re.findall(r"\b(\d{2,5})\s*usd\b", tl)]        # 2500 usd
    usd_vals += [int(x) for x in re.findall(r"\busd\s*(\d{2,5})\b", tl)]        # usd 2500
    usd_vals += [int(x) for x in re.findall(r"~\s*\$?\s*(\d{2,5})\b", tl)]      # ~$1200

    # --- USD up to/upto ---
    usd_vals += [int(x) for x in re.findall(r"(?:up\s*to|upto|đến|len\s*den|lên\s*đến)\s*\$?\s*(\d{2,5})\s*(?:usd|\$)?", tl)]

    # --- USD range: "1200 - 1500 usd" (đơn vị chỉ ở cuối) -> lấy cả hai số ---
    for a, b in re.findall(r"\b(\d{2,5})\s*[-–]\s*(\d{2,5})\s*(?:usd|\$)\b", tl):
        usd_vals += [int(a), int(b)]

    # --- VND (triệu) ---
    vnd_millions = []
    # range: "15 - 20 tr"
    for a, b in re.findall(r"\b(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(?:m|tr|triệu|trieu)\b", tl):
        vnd_millions += [float(a.replace(",", ".")), float(b.replace(",", "."))]
    # up to: "up to 30tr"
    vnd_millions += [float(x.replace(",", ".")) for x in re.findall(r"(?:up\s*to|upto|đến|len\s*den|lên\s*đến)\s*(\d+(?:[.,]\d+)?)\s*(?:m|tr|triệu|trieu)\b", tl)]
    # single: "30 tr"
    vnd_millions += [float(x.replace(",", ".")) for x in re.findall(r"\b(\d+(?:[.,]\d+)?)\s*(?:m|tr|triệu|trieu)\b", tl)]

    vnd_to_usd = [int(round(mil * 1_000_000 / vnd_per_usd)) for mil in vnd_millions]

    all_usd = usd_vals + vnd_to_usd
    return max(all_usd) if all_usd else None
# ===== 3) Kỹ năng =====

# Tập kỹ năng rút trực tiếp từ JSON (mẫu tiêu biểu trong các JD)
SKILL_DICT = {
    # Ngôn ngữ & nền tảng
    'php','laravel','symfony','cake','java','spring','spring boot','python','django','flask','nodejs','node.js',
    'typescript','javascript','react','reactjs','next.js','vue','vuejs','.net','.net core','c#','c/c++','c++','kotlin','swift',
    'salesforce','apex','soql','lwc','apex trigger',
    # Mobile/Embedded/OS
    'android','ios','aosp','linux','kernel','hal','bootloader',
    # DevOps & Cloud
    'aws','azure','gcp','docker','kubernetes','k8s','terraform','ansible','gitlab ci','jenkins','argocd','cicd','ci/cd',
    # Data/Message/Cache
    'postgresql','mysql','mssql','oracle','redis','mongodb','kafka','rabbitmq','hdfs','spark',
    # Web/API/Protocol
    'rest','restful','graphql','grpc','websocket','oauth 2.0','openid connect','saml',
    # QA/Testing
    'selenium','cypress','robot framework','jest','junit','postman','rest assured','unit test',
    # Tools/Tracking
    'jira','svn','git','github','gitlab','datadog','prometheus','grafana',
    # Arch/Patterns
    'microservices','microservice','event-driven','eda','soa','ddd','clean architecture','solid',
    # BI/ML
    'power bi','pytorch','tensorflow',
    # Security
    'owasp','mitre att&ck','siem','soar','waf','xdr','edr'
}

def extract_skills(text: str) -> List[str]:
    tl = ' ' + text.lower() + ' '
    found = set()
    for kw in SKILL_DICT:
        # khớp nguyên cụm/từ (tránh match lệch)
        if re.search(rf'(?<![a-z0-9_]){re.escape(kw)}(?![a-z0-9_])', tl):
            found.add(kw)
    return sorted(found)

# ===== 4) Cấp độ/seniority =====

LEVEL_ORDER = ['fresher','junior','mid','senior','lead','architect','manager','director']
LEVEL_PATTERNS = [
    (re.compile(r'\bfresher\b', re.I), 'fresher'),
    (re.compile(r'\bjunior\b', re.I), 'junior'),
    (re.compile(r'\bmid(?:-level)?\b', re.I), 'mid'),
    (re.compile(r'\bsenior\b', re.I), 'senior'),
    (re.compile(r'\b(team\s*lead|tech\s*lead|lead)\b', re.I), 'lead'),
    (re.compile(r'\b(solution|technical|software)\s+architect\b', re.I), 'architect'),
    (re.compile(r'\b(manager|leader|project\s*manager)\b', re.I), 'manager'),
    (re.compile(r'\bdirector\b', re.I), 'director'),
]

def infer_level(text: str) -> str:
    tl = text.lower()
    for pat, lvl in LEVEL_PATTERNS:
        if pat.search(tl):
            return lvl
    # fallback theo số năm KN
    yoe = extract_experience(text)
    if yoe is not None:
        if yoe < 2: return 'junior'
        if yoe < 4: return 'mid'
        if yoe < 7: return 'senior'
        return 'lead'
    return 'unknown'

# ===== 5) Ngôn ngữ yêu cầu =====

LANG_PATTERNS = [
    (re.compile(r'\b(english|tiếng anh|en\b)\b', re.I), 'en'),
    (re.compile(r'\b(japanese|tiếng nhật|jp\b)\b', re.I), 'ja'),
    (re.compile(r'\b(n1|n2|n3)\b', re.I), 'ja'),  # JLPT
    (re.compile(r'\b(korean|tiếng hàn)\b', re.I), 'ko'),
    (re.compile(r'\b(chinese|mandarin|tiếng trung)\b', re.I), 'zh'),
]

def detect_language_required(text: str) -> str:
    tl = text.lower()
    langs = set()
    for pat, code in LANG_PATTERNS:
        if pat.search(tl):
            langs.add(code)
    if not langs:
        return 'vi'  # JD VN mặc định
    # Nếu có nhiều, trả về chuỗi ghép (vd "en,ja")
    return ','.join(sorted(langs))

