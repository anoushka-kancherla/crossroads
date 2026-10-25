"""The brand tokens: one source, identical copies in both apps, loaded by both, and no hard-coded look
values outside them (FR-001, FR-002, FR-016, SC-002). Reads the source files, like the separation tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "branding" / "tokens.css"
APPS = ("customer-app", "internal-app")


def test_both_apps_hold_an_identical_copy_of_the_token_source():
    source = SOURCE.read_bytes()
    for app in APPS:
        copy = ROOT / app / "src" / "styles" / "tokens.css"
        assert copy.read_bytes() == source, f"{app} copy differs: run scripts/sync-tokens.sh"


def test_both_apps_load_the_tokens_before_their_own_styles():
    for app in APPS:
        main = (ROOT / app / "src" / "main.tsx").read_text()
        assert "./styles/tokens.css" in main, app
        assert main.index("./styles/tokens.css") < main.index("./styles.css"), app


# --- the scan: no look value written outside the token file (FR-001, FR-002, FR-016) -------------------

import re  # noqa: E402

NAMED_COLORS = (
    "black|white|red|green|blue|gray|grey|orange|yellow|purple|pink|brown|navy|teal|maroon|silver|gold|"
    "crimson|tomato|coral|salmon|violet|indigo|cyan|magenta|lime|olive|aqua|fuchsia"
)
SPACE_PROPS = r"(font-size|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|gap|row-gap|column-gap|border-radius)"


def _sources():
    for app in APPS:
        for path in (ROOT / app / "src").rglob("*"):
            if path.suffix not in {".css", ".ts", ".tsx"} or not path.is_file():
                continue
            if path.name in {"tokens.css", "types.ts", "vite-env.d.ts"} or ".test." in path.name:
                continue
            yield path


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _findings(path: Path) -> list[str]:
    text = _strip_comments(path.read_text())
    where = str(path.relative_to(ROOT))
    out: list[str] = []
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", text):
        if path.suffix == ".css" or re.search(r"[\"'`]$", text[max(0, m.start() - 1) : m.start()]):
            out.append(f"{where}: hex colour {m.group(0)}")
    for m in re.finditer(r"\b(?:rgba?|hsla?)\(", text):
        out.append(f"{where}: colour function {m.group(0)}")
    for m in re.finditer(r"(?:\b(?:color|background|border[a-z-]*|fill|stroke|outline)\s*:\s*)([^;{}]+)", text):
        for word in re.findall(rf"(?<![-\w])({NAMED_COLORS})(?![-\w])", m.group(1)):
            if "var(" not in m.group(1):
                out.append(f"{where}: named colour {word}")
    for m in re.finditer(r"\b(?:stroke|fill)=(?:\{?[\"'])([^\"']+)[\"']", text):
        if not m.group(1).startswith("var(") and m.group(1) not in {"none", "currentColor"}:
            out.append(f"{where}: chart colour {m.group(1)}")
    for m in re.finditer(r"font-family\s*:\s*([^;}]+)", text):
        if not m.group(1).strip().startswith(("var(", "inherit")):
            out.append(f"{where}: font family {m.group(1).strip()}")
    for _ in re.finditer(r"fontFamily\s*[:=]", text):
        out.append(f"{where}: fontFamily in code")
    if path.suffix == ".css":
        for m in re.finditer(rf"(?<![-\w]){SPACE_PROPS}\s*:\s*([^;}}]+)", text):
            value = re.sub(r"var\([^)]*\)", "", m.group(2))
            for num in re.findall(r"(?<![\w.-])-?\d*\.?\d+(?:px|rem|em)\b", value):
                if num not in {"0px", "0"}:
                    out.append(f"{where}: raw length {num} on {m.group(1)}")
    for m in re.finditer(r"box-shadow|text-shadow|drop-shadow|[a-z-]*gradient\(", text):
        out.append(f"{where}: shadow or gradient {m.group(0)}")
    return out


def test_no_hard_coded_colour_font_size_spacing_radius_shadow_or_gradient_outside_the_tokens():
    files = list(_sources())
    assert len(files) > 20, "the scan should be looking at both apps"
    findings = [f for p in files for f in _findings(p)]
    assert not findings, "\n".join(findings)
