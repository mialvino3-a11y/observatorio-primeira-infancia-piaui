import os
import re
import json
import base64
import mimetypes
import shlex
import sqlite3
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
import altair as alt
from sqlalchemy import create_engine, text
from streamlit.components.v1 import html as st_html

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_OK = True
except Exception:
    px = None

    class _GoFallback:
        class Figure:
            pass

    go = _GoFallback()
    PLOTLY_OK = False


# ─── Caminhos ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR    = BASE_DIR / "assets"
CAPA_HTML     = ASSETS_DIR / "Capa Dashboard.html"
NAV_HTML      = ASSETS_DIR / "Navegacao Interna Paineis.html"
OBSERVATORIO_DIR = ASSETS_DIR
CAPA_LOGO     = ASSETS_DIR / "assets" / "pacto-logo.png"
CAPA_ARTE     = ASSETS_DIR / "assets" / "abraco-ilustracao.png"
SQLITE_DB     = BASE_DIR / "banco_primeira_infancia_piaui_oficial.sqlite"
PIAUI_GEOJSON = BASE_DIR / "geojs-22-mun.json"


# ─── Cores e paleta do projeto ───────────────────────────────────────────────

COR_RESULTADO   = "#e85c41"   # coral — resultados
COR_ESFORCO     = "#2a5abf"   # azul  — esforços
COR_PI          = "#f5c842"   # amarelo — Piauí
COR_BR          = "#b4b2a9"   # cinza  — Brasil
COR_BOM         = "#27ae60"
COR_ATENCAO     = "#e67e22"
COR_CRITICO     = "#c0392b"
COR_BOM_BG      = "#EAF3DE"
COR_ATENCAO_BG  = "#FAEEDA"
COR_CRITICO_BG  = "#FCEBEB"
COR_NEUTRO_BG   = "#f0f2f5"
COR_NEUTRO      = "#5a6478"


# ─── Catálogo de indicadores (spec v4.5) ─────────────────────────────────────
# Cada entrada: (regex_nome, ref_pi, ref_br, cls, fmt)
# cls: "pior" = menor é melhor · "melhor" = maior é melhor · None = sem semáforo

INDICADORES_CAT = [
    # ── Saúde — Rede Materno-Infantil — Resultados ──────────────────────────
    (r"mortalidade materna",                       44.5,   35.0, "pior",   "{:.1f}"),
    (r"mortalidade neonatal",                       9.4,    7.8, "pior",   "{:.1f}"),
    (r"mortalidade infantil",                      14.2,   12.1, "pior",   "{:.1f}"),
    (r"baixo peso",                                 9.8,    8.0, "pior",   "{:.1f}"),
    (r"s[íi]filis",                                 4.2,    2.8, "pior",   "{:.1f}"),
    # ── Saúde — Rede Materno-Infantil — Esforços ────────────────────────────
    (r"7.{0,15}consultas|consultas.*pré-natal",    78.4,   82.6, "melhor", "{:.1f}"),
    (r"6.{0,30}consultas.*12.*semana|12.*semana.*gesta[çc]",  68.2, 72.8, "melhor", "{:.1f}"),
    (r"cesariana",                                 52.4,   56.8,  None,    "{:.1f}"),
    (r"[áa]gua pot[áa]vel|cobertura de esgoto",    48.0,   71.0, "melhor", "{:.1f}"),
    (r"saneamento b[áa]sico",                      74.0,   89.0, "melhor", "{:.1f}"),
    # ── Saúde — Cobertura Vacinal — Esforços ────────────────────────────────
    (r"\bBCG\b",                                   94.1,   96.1, "melhor", "{:.1f}"),
    (r"Hepatite B.*1|HepB.*1",                     91.2,   93.2, "melhor", "{:.1f}"),
    (r"Pentavalente|Penta\b",                      87.6,   91.6, "melhor", "{:.1f}"),
    (r"Tr[íi]plice Viral.*1|SCR.*1ª",              82.4,   88.4, "melhor", "{:.1f}"),
    (r"Tr[íi]plice Viral.*2|SCRV|SCR.*2ª",        78.2,   84.6, "melhor", "{:.1f}"),
    (r"Pneumoc[óo]cica",                           85.3,   90.3, "melhor", "{:.1f}"),
    (r"VIP|Polio.*inativ",                         84.8,   89.7, "melhor", "{:.1f}"),
    # ── Nutrição — Resultados ────────────────────────────────────────────────
    (r"d[eé]ficit estatural|prevalência.*estatural",  8.4,  7.3, "pior",   "{:.1f}"),
    (r"d[eé]ficit ponderal|prevalência.*ponderal",    5.1,  4.2, "pior",   "{:.1f}"),
    (r"obesidade",                                 11.8,   14.6, "pior",   "{:.1f}"),
    (r"desnutri[çc][aã]o.*[óo]bito|[óo]bito.*desnutri", 28.0, 210.0, None, "{:.0f}"),
    # ── Nutrição — Esforços ──────────────────────────────────────────────────
    (r"acompanhamento nutricional",                52.4,   58.1, "melhor", "{:.1f}"),
    (r"aleitamento.*exclusivo",                    44.8,   45.7, "melhor", "{:.1f}"),
    (r"aleitamento.*continuado",                   30.6,   31.2, "melhor", "{:.1f}"),
    # ── Aprendizagem — Resultados ────────────────────────────────────────────
    (r"\bIDEB\b",                                   5.4,    5.8, "melhor", "{:.1f}"),
    (r"alfabetizadas|alfabetização",               64.2,   68.2, "melhor", "{:.1f}"),
    (r"abandono.*EF|taxa.*abandono",                1.4,    1.2, "pior",   "{:.2f}"),
    (r"distor[çc][aã]o idade",                    16.2,   14.6, "pior",   "{:.1f}"),
    # ── Aprendizagem — Esforços ──────────────────────────────────────────────
    (r"matr[íi]culas em creche",                   26.8,   34.1, "melhor", "{:.1f}"),
    (r"docentes em creches|docentes.*creches",      65.4,   74.8, "melhor", "{:.1f}"),
    (r"creche.*coleta de esgoto|creche.*esgot",    22.1,   14.2, "pior",   "{:.1f}"),
    (r"creche.*distribui[çc][aã]o de [áa]gua|creche.*[áa]gua pot", 14.8, 8.4, "pior", "{:.1f}"),
    (r"investimento.*educa|per.*capita.*edu",    2840.0, 3120.0, "melhor", "{:.0f}"),
    (r"matr[íi]culas.*pré-escola|pré-escola.*matr", 80.2, 84.3, "melhor", "{:.1f}"),
    (r"docentes na pré-escola|docentes.*pré-escola", 70.2, 78.2, "melhor", "{:.1f}"),
    (r"pré-escola.*esgot|esgotamento.*pré",        18.4,   10.2, "pior",   "{:.1f}"),
    (r"pré-escola.*[áa]gua pot|pré-escola.*oferecem [áa]gua", 12.4, 6.8, "pior", "{:.1f}"),
    # ── Segurança — Resultados ───────────────────────────────────────────────
    (r"viol[eê]ncia f[íi]sica",                   38.4,   38.3, "pior",   "{:.1f}"),
    (r"viol[eê]ncia sexual",                       24.2,   22.1, "pior",   "{:.1f}"),
    (r"neglig[eê]ncia|abandono.*crian",            30.1,   29.5, "pior",   "{:.1f}"),
    (r"homic[íi]dio.*crian|[óo]bitos.*homic",       1.9,    1.8, "pior",   "{:.2f}"),
    (r"trabalho infantil",                          5.4,    4.8, "pior",   "{:.1f}"),
    # ── Segurança — Esforços ─────────────────────────────────────────────────
    (r"\bPAIF\b",                                  52.4,   56.8, "melhor", "{:.1f}"),
    (r"\bPAEFI\b",                                 34.8,   38.2, "melhor", "{:.1f}"),
    (r"\bSCFV\b",                                  64.2,   68.4, "melhor", "{:.1f}"),
    (r"conselho tutelar",                          72.4,   78.1, "melhor", "{:.1f}"),
    # ── Cuidado — Resultados ─────────────────────────────────────────────────
    (r"registro de nascimento",                    95.8,   97.8, "melhor", "{:.1f}"),
    (r"registradas.*m[aã]e|s[oó].*nome.*m[aã]e",  15.2,   14.2, "pior",   "{:.1f}"),
    (r"casamentos infantis",                       14.8,   12.3, "pior",   "{:.1f}"),
    (r"extrema pobreza",                           12.0,    8.0, "pior",   "{:.1f}"),
    (r"(?<!extrema )pobreza(?!.*extrema)",         22.0,   18.0, "pior",   "{:.1f}"),
    # ── Cuidado — Esforços ───────────────────────────────────────────────────
    (r"fam[íi]lias vulner[áa]veis.*transfer[eê]ncia|bolsa fam[íi]lia.*cad[úu]nico", 74.2, 68.4, "melhor", "{:.1f}"),
    (r"crian[çc]a feliz|\bPCF\b",                 42.1,   48.2, "melhor", "{:.1f}"),
    (r"m[eé]dicos por mil",                         0.9,    2.1, "melhor", "{:.2f}"),
    (r"bolsa fam[íi]lia",                          72.4,   64.8, "melhor", "{:.1f}"),
    # ── Cuidado — Esforços (novos) ───────────────────────────────────────────
    (r"cobertura.*equipes.*sa[úu]de|equipes.*sa[úu]de da fam[íi]lia", 74.2, 68.4, "melhor", "{:.1f}"),
    # ── Saúde — Saneamento (SNIS) ────────────────────────────────────────────
    (r"esgotamento sanit[áa]rio.*domic[íi]|cobertura.*esgot.*SNIS", 48.0, 71.0, "melhor", "{:.1f}"),
    (r"[áa]gua pot[áa]vel.*domic[íi]|cobertura.*[áa]gua.*SNIS",     74.0, 89.0, "melhor", "{:.1f}"),
    # ── Segurança — Negligência (SINAN VIOL) ─────────────────────────────────
    (r"neglig[eê]ncia.*abandon|taxa.*neglig[eê]ncia",               30.1, 29.5, "pior",   "{:.1f}"),
    # ── Saúde / Nutrição — novos ─────────────────────────────────────────────
    (r"mortalidade na inf[aâ]ncia|mort.*<5|mort.*5 anos",           28.0, 22.0, "pior",   "{:.1f}"),
]


def _ind_cls(nome: str) -> str:
    """Retorna cls do indicador por pattern. Default 'pior'."""
    for pattern, _, _, cls, _ in INDICADORES_CAT:
        if cls and re.search(pattern, nome, flags=re.IGNORECASE):
            return cls
    return "pior"


def _ind_ref_pi(nome: str) -> float | None:
    """Retorna ref_pi do indicador por pattern."""
    for pattern, ref_pi, _, _, _ in INDICADORES_CAT:
        if re.search(pattern, nome, flags=re.IGNORECASE):
            return ref_pi
    return None


def _ind_ref_br(nome: str) -> float | None:
    """Mantido por compatibilidade; benchmark BR sintético não é usado."""
    return None


def _ind_fmt(nome: str) -> str:
    """Retorna formato de exibição do indicador por pattern."""
    for pattern, _, _, _, fmt in INDICADORES_CAT:
        if re.search(pattern, nome, flags=re.IGNORECASE):
            return fmt
    return "{:.1f}"


# ─── Mapeamento de dimensões ──────────────────────────────────────────────────

DIMENSAO_SUBTEMAS = {
    "Saúde e Bem-estar": [
        ("Rede Materno-Infantil",
         r"mortalidade materna|mortalidade neonatal|mortalidade infantil|baixo peso|s[íi]filis"),
        ("Cobertura Vacinal",
         r"vacina|vacinal|bcg|hepatite|penta|tr[íi]plice|pneumoc|vip|poliomielite"),
    ],
    "Alimentação": [
        ("Estado Nutricional",
         r"d[eé]ficit estatural|d[eé]ficit ponderal|obesidade|desnutri|nutricional|prevalência"),
        ("Amamentação",
         r"aleitamento|amamentação|leite materno"),
    ],
    "Aprendizagem": [
        ("Creche (0–3 anos)",
         r"creche|matr[íi]culas em creche|docentes em creche|docentes.*creche|\[Infraestrutura\].*creche"),
        ("Pré-escola (4–5 anos)",
         r"pré-escola|pré.escola|\[Infraestrutura\].*pré"),
    ],
    "Proteção": [
        ("Violência contra crianças",
         r"viol[eê]ncia f[íi]sica|viol[eê]ncia sexual|neglig[eê]ncia|homic[íi]dio"),
        ("Trabalho Infantil",
         r"trabalho infantil"),
    ],
    "Cuidado": [
        ("Transferência e Benefícios",
         r"bolsa fam[íi]lia|fam[íi]lias vulner[áa]veis.*transfer"),
        ("Vulnerabilidade Social",
         r"extrema pobreza|<5 anos em pobreza|pobreza"),
    ],
}

MENU_GROUPS = [
    ("CONTEXTO", [
        "Visão Geral",
        "Perfil do Município",
    ]),
    ("DIMENSÕES", [
        "Saúde e Bem-estar",
        "Alimentação",
        "Aprendizagem",
        "Proteção",
        "Cuidado",
    ]),
]

PAGE_FROM_MENU = {
    "Visão Geral": "VisaoGeral",
    "Perfil do Município": "Perfil",
    "Saúde e Bem-estar": "Saude",
    "Alimentação": "Alimentacao",
    "Aprendizagem": "Aprendizagem",
    "Proteção": "Protecao",
    "Cuidado": "Cuidado",
}

MENU_FROM_PAGE = {
    "VisaoGeral": "Visão Geral",
    "Perfil": "Perfil do Município",
    "Saude": "Saúde e Bem-estar",
    "Alimentacao": "Alimentação",
    "Aprendizagem": "Aprendizagem",
    "Protecao": "Proteção",
    "Cuidado": "Cuidado",
}


# ─── Config Streamlit ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="Observatório da Primeira Infância — Piauí",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Utilitários de asset ────────────────────────────────────────────────────

def _to_data_uri(asset_path: Path) -> str | None:
    if not asset_path.exists() or not asset_path.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(asset_path))
    if not mime:
        ext = asset_path.suffix.lower()
        mime = {".svg": "image/svg+xml", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp"}.get(ext)
        if not mime:
            return None
    b64 = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _embed_local_assets(html: str, base_dir: Path) -> str:
    src_re = re.compile(r"""src=(['"])(?!https?://|data:|//)([^'"]+)\1""", flags=re.IGNORECASE)
    def src_sub(m):
        p = (base_dir / m.group(2).strip()).resolve()
        d = _to_data_uri(p)
        return f"src={m.group(1)}{d}{m.group(1)}" if d else m.group(0)
    out = src_re.sub(src_sub, html)
    url_re = re.compile(r"""url\((['"]?)(?!https?://|data:|//)([^)'"]+)\1\)""", flags=re.IGNORECASE)
    def url_sub(m):
        p = (base_dir / m.group(2).strip()).resolve()
        d = _to_data_uri(p)
        q = m.group(1) or ""
        return f"url({q}{d}{q})" if d else m.group(0)
    return url_re.sub(url_sub, out)


# ─── Conexão com banco ───────────────────────────────────────────────────────

def get_dsn() -> str:
    dsn = os.getenv("PG_DSN", "").strip()
    if dsn:
        return dsn
    try:
        dsn = st.secrets.get("PG_DSN", "").strip()
        if dsn:
            return dsn
    except Exception:
        pass
    return ""


def normalize_dsn_for_sqlalchemy(dsn: str) -> str:
    txt = (dsn or "").strip()
    if not txt:
        return txt
    if txt.startswith(("postgresql://", "postgresql+psycopg://")):
        if txt.startswith("postgresql://"):
            return "postgresql+psycopg://" + txt[len("postgresql://"):]
        return txt
    if "host=" in txt and "dbname=" in txt and "user=" in txt:
        parts = {}
        for token in shlex.split(txt):
            if "=" in token:
                k, v = token.split("=", 1)
                parts[k.strip().lower()] = v.strip().strip('"').strip("'")
        host    = parts.get("host", "")
        port    = parts.get("port", "5432")
        dbname  = parts.get("dbname", "postgres")
        user    = quote_plus(parts.get("user", ""))
        pwd     = quote_plus(parts.get("password", ""))
        sslmode = parts.get("sslmode", "require")
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{dbname}?sslmode={sslmode}"
    return txt


@st.cache_resource(show_spinner=False)
def get_engine(dsn: str):
    return create_engine(normalize_dsn_for_sqlalchemy(dsn), pool_pre_ping=True)


# ─── Carregamento de dados ───────────────────────────────────────────────────

_SQL_FATO = """
    SELECT
        fi.cod_ibge,
        dm.municipio,
        fi.ano,
        di.eixo,
        di.indicador,
        di.fonte_principal,
        di.regra_resumo,
        fi.valor,
        fi.numerador,
        fi.denominador,
        fi.recorte
    FROM fato_indicador fi
    JOIN dim_indicador di ON di.indicador_id = fi.indicador_id
    JOIN dim_municipio dm ON dm.cod_ibge = fi.cod_ibge
"""

_SQL_DESAG = """
    SELECT
        fd.cod_ibge,
        dm.municipio,
        fd.ano,
        di.eixo,
        di.indicador,
        fd.nivel_desagregacao,
        fd.sexo,
        fd.raca_cor,
        fd.idade_mae_faixa,
        fd.valor,
        fd.numerador,
        fd.denominador,
        fd.recorte
    FROM fato_indicador_desagregado fd
    JOIN dim_indicador di ON di.indicador_id = fd.indicador_id
    JOIN dim_municipio dm ON dm.cod_ibge = fd.cod_ibge
"""

_SQL_MUN = "SELECT cod_ibge, municipio, uf, regiao FROM dim_municipio ORDER BY municipio"

_SQL_IND = "SELECT indicador_id, eixo, indicador, fonte_principal, regra_resumo FROM dim_indicador ORDER BY eixo, indicador"


@st.cache_data(ttl=600, show_spinner=False)
def load_fato(_engine, _cache_token: str = "") -> pd.DataFrame:
    if _engine is None:
        return load_fato_sqlite(_cache_token)
    with _engine.connect() as conn:
        return pd.read_sql(text(_SQL_FATO), conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_desag(_engine, _cache_token: str = "") -> pd.DataFrame:
    if _engine is None:
        return load_desag_sqlite(_cache_token)
    with _engine.connect() as conn:
        return pd.read_sql(text(_SQL_DESAG), conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_municipios(_engine) -> pd.DataFrame:
    if _engine is None:
        return load_municipios_sqlite()
    with _engine.connect() as conn:
        return pd.read_sql(text(_SQL_MUN), conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_indicadores(_engine) -> pd.DataFrame:
    if _engine is None:
        return load_indicadores_sqlite()
    with _engine.connect() as conn:
        return pd.read_sql(text(_SQL_IND), conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_fato_sqlite(_cache_token: str = "") -> pd.DataFrame:
    with sqlite3.connect(SQLITE_DB) as conn:
        return pd.read_sql_query(_SQL_FATO, conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_desag_sqlite(_cache_token: str = "") -> pd.DataFrame:
    with sqlite3.connect(SQLITE_DB) as conn:
        return pd.read_sql_query(_SQL_DESAG, conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_municipios_sqlite() -> pd.DataFrame:
    with sqlite3.connect(SQLITE_DB) as conn:
        return pd.read_sql_query(_SQL_MUN, conn)


@st.cache_data(ttl=600, show_spinner=False)
def load_indicadores_sqlite() -> pd.DataFrame:
    with sqlite3.connect(SQLITE_DB) as conn:
        return pd.read_sql_query(_SQL_IND, conn)


# ─── Formatação e helpers ────────────────────────────────────────────────────

def fmt_int(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def fmt_num(v, decimals: int = 1, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/d"
    return f"{v:.{decimals}f}".replace(".", ",") + suffix


def _normalize_display_value(indicador: str, valor: float | None) -> float | None:
    """Normaliza escalas conhecidas para exibição (sem inventar valores)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    v = float(valor)
    # Alguns carregamentos trazem IDHM em escala 0-1000.
    if "idhm" in indicador.lower() and v > 10:
        return v / 1000.0
    return v


def status_badge(mun_val, ref_val, sentido: str = "pior") -> tuple[str, str, str]:
    """Retorna (label, bg_color, text_color). Thresholds per spec v4.5."""
    if mun_val is None or ref_val is None or pd.isna(mun_val) or pd.isna(ref_val) or ref_val == 0:
        return "n/d", COR_NEUTRO_BG, COR_NEUTRO
    ratio = mun_val / ref_val
    if sentido == "pior":       # menor = melhor (mortalidade, violência…)
        if ratio <= 1.02:
            return "Bom", COR_BOM_BG, COR_BOM
        if ratio <= 1.10:
            return "Atenção", COR_ATENCAO_BG, COR_ATENCAO
        return "Crítico", COR_CRITICO_BG, COR_CRITICO
    else:                       # maior = melhor (cobertura, IDEB…)
        if ratio >= 0.97:
            return "Bom", COR_BOM_BG, COR_BOM
        if ratio >= 0.90:
            return "Atenção", COR_ATENCAO_BG, COR_ATENCAO
        return "Crítico", COR_CRITICO_BG, COR_CRITICO


def trend_badge(series: pd.Series, sentido: str = "pior") -> tuple[str, str]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) < 4:
        return "→ Estável", "td-fl"
    last2 = float(vals.iloc[-2:].mean())
    prev2 = float(vals.iloc[-4:-2].mean())
    if prev2 == 0:
        return "→ Estável", "td-fl"
    delta = ((last2 - prev2) / abs(prev2)) * 100.0
    if sentido == "pior":
        if delta < -1:
            return "↗ Melhorando", "td-up"
        if delta > 1:
            return "↘ Piorando", "td-dn"
    else:
        if delta > 1:
            return "↗ Melhorando", "td-up"
        if delta < -1:
            return "↘ Piorando", "td-dn"
    return "→ Estável", "td-fl"


def extract_mean(df: pd.DataFrame, pattern: str, col: str = "valor") -> float | None:
    if df.empty:
        return None
    mask = df["indicador"].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    vals = pd.to_numeric(df.loc[mask, col], errors="coerce").dropna()
    return float(vals.mean()) if not vals.empty else None


def extract_latest_mun_value(
    df: pd.DataFrame,
    cod_ibge: str,
    pattern: str,
    ano_ref: int | None = None,
    col: str = "valor",
) -> float | None:
    if df.empty:
        return None
    mask = (
        (df["cod_ibge"].astype(str) == str(cod_ibge))
        & df["indicador"].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    )
    dfx = df.loc[mask].copy()
    if dfx.empty:
        return None
    if ano_ref is not None:
        dfx = dfx[dfx["ano"] <= int(ano_ref)]
        if dfx.empty:
            return None
    ano_last = int(pd.to_numeric(dfx["ano"], errors="coerce").dropna().max())
    vals = pd.to_numeric(dfx.loc[dfx["ano"] == ano_last, col], errors="coerce").dropna()
    return float(vals.mean()) if not vals.empty else None


def kpi_card(label: str, value: str, ref: str = ""):
    st.markdown(
        f"""<div class="pi-kpi-card">
          <div class="pi-kpi-label">{label}</div>
          <div class="pi-kpi-value">{value}</div>
          <div class="pi-kpi-ref">{ref}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# ─── CSS global ──────────────────────────────────────────────────────────────

def apply_app_css():
    st.markdown("""
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;700&display=swap');

          :root {
            --pi-bg: #f0f2f5;
            --pi-card: #ffffff;
            --pi-card-border: #e0e4ea;
            --pi-text: #2c3e50;
            --pi-text-soft: #7a8496;
            --pi-accent: #2b57a8;
            --pi-radius: 10px;
          }

          html, body, [class*="css"] {
            font-family: "Inter", "Segoe UI", sans-serif !important;
            color: #2c3e50;
          }

          .stApp, [data-testid="stAppViewContainer"] { background: var(--pi-bg); }
          [data-testid="stHeader"] { background: transparent; }
          [data-testid="stSidebar"] { background: #ffffff; }
          .main .block-container {
            max-width: 100% !important;
            padding-top: 0.35rem !important;
            padding-left: 1.05rem !important;
            padding-right: 1.05rem !important;
            padding-bottom: 0.75rem !important;
          }

          .stButton > button {
            height: 33px; border-radius: 999px;
            border: 1px solid #d0d5dd; color: #2a5abf;
            background: #ffffff; font-weight: 600;
            font-size: 0.72rem; padding: 0.2rem 0.78rem;
          }
          .stButton > button:hover {
            border-color: #2a5abf; color: #2a5abf; background: #eef2fc;
          }

          h2, h3 { font-family: "Playfair Display", serif !important; color: #1a3a6b !important; letter-spacing: -0.01em; font-weight: 700 !important; }

          /* KPI card */
          .pi-kpi-card {
            min-height: 72px; border-radius: 8px;
            border: 1px solid var(--pi-card-border);
            background: var(--pi-card); padding: 8px 10px;
            display: flex; flex-direction: column; justify-content: center;
          }
          .pi-kpi-label {
            color: #aab0bb; font-size: 0.5rem;
            font-weight: 700; letter-spacing: 0.08em;
            text-transform: uppercase; margin-bottom: 5px;
          }
          .pi-kpi-value {
            color: var(--pi-text); font-size: 1.05rem;
            font-weight: 800; line-height: 1.05; font-variant-numeric: tabular-nums;
          }
          .pi-kpi-ref {
            font-size: 0.48rem; color: #aab0bb;
            margin-top: 4px; font-weight: 600;
          }

          /* Cabeçalho de seção */
          .pi-section-header {
            display: flex; align-items: center; gap: 8px;
            padding: 5px 0 4px 0; margin-bottom: 2px;
          }
          .pi-section-bar {
            width: 4px; height: 18px; border-radius: 3px; flex-shrink: 0;
          }
          .pi-section-title {
            font-size: 0.68rem; font-weight: 800; color: #5a6478;
            text-transform: uppercase; letter-spacing: 0.06em;
          }
          .pi-section-sub {
            font-size: 0.56rem; color: #aab0bb; font-weight: 600; margin-left: 4px;
          }

          /* Painel de contexto (barra azul escura) */
          .pi-ctx-bar {
            background: #1a3a6b; border-radius: 8px;
            padding: 9px 16px; margin-bottom: 10px;
            display: flex; gap: 0; overflow: hidden;
          }
          .pi-ctx-item {
            flex: 1; display: flex; flex-direction: column; gap: 1px;
            padding: 0 12px;
            border-right: 1px solid rgba(255,255,255,.15);
          }
          .pi-ctx-item:first-child { padding-left: 0; }
          .pi-ctx-item:last-child  { border-right: none; padding-right: 0; }
          .pi-ctx-lbl { font-size: 0.58rem; font-weight: 700; color: rgba(255,255,255,.5); text-transform: uppercase; letter-spacing: .5px; }
          .pi-ctx-val { font-size: 1.05rem; font-weight: 800; line-height: 1.2; color: rgba(255,255,255,.92); }
          .pi-ctx-ref { font-size: 0.58rem; color: rgba(255,255,255,.4); }

          /* Badges */
          .pi-badge {
            display: inline-block; padding: 2px 9px; border-radius: 6px;
            font-size: 0.68rem; font-weight: 800; white-space: nowrap;
          }
          .td-up { background: #EAF3DE; color: #27ae60; }
          .td-dn { background: #FCEBEB; color: #c0392b; }
          .td-fl { background: #f0f2f5; color: #5a6478; }

          /* Tabela de indicadores */
          .pi-ind-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
          .pi-ind-table th {
            font-size: 0.62rem; font-weight: 700; color: #aab0bb;
            text-transform: uppercase; letter-spacing: .5px;
            padding: 5px 10px; text-align: right; background: #fafbfc;
            border-bottom: 1px solid #eef0f3;
          }
          .pi-ind-table th:first-child { text-align: left; }
          .pi-ind-table td {
            padding: 6px 10px; border-top: 1px solid #f0f2f5;
            color: #2c3e50; vertical-align: middle;
          }
          .pi-ind-table td:first-child { color: #3a4558; max-width: 260px; }
          .pi-ind-table td:not(:first-child) { text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }
          .pi-ind-table tr:hover td { background: #f8f9fb; }

          /* Barras horizontais de comparação */
          .pi-bar-row { margin-bottom: 10px; }
          .pi-bar-label {
            display: flex; justify-content: space-between;
            font-size: 0.72rem; color: #2c3e50; margin-bottom: 3px;
          }
          .pi-bar-track {
            position: relative; height: 8px;
            background: #f0f2f5; border-radius: 4px;
          }

          /* Card de painel */
          .pi-panel {
            background: #ffffff; border: 1px solid #e0e4ea;
            border-radius: 8px; padding: 8px 10px;
          }
          .pi-panel-title {
            font-size: 0.58rem; font-weight: 800; color: #5a6478;
            text-transform: uppercase; letter-spacing: 0.06em;
            margin-bottom: 8px;
          }
          .contexto-nav-label {
            font-size: 0.56rem; color: #6c757d;
            text-transform: uppercase; letter-spacing: 0.14em;
            font-weight: 800; margin-bottom: 5px;
          }
          .contexto-nav {
            display: flex; flex-wrap: wrap; gap: 8px;
            margin: 0 0 12px 0;
          }
          .contexto-nav-item {
            display: inline-flex; align-items: center;
            padding: 5px 10px; border-radius: 999px;
            border: 1px solid #dbe3f1; background: #ffffff;
            color: #355fbb !important; font-size: 0.68rem; font-weight: 700;
            text-decoration: none !important;
          }
          .contexto-nav-item:hover {
            background: #f2f6ff; border-color: #bfcff0;
          }
          .contexto-nav-item.active {
            background: #355fbb; color: #ffffff !important; border-color: #355fbb;
          }

          /* Sidebar */
          .sidebar-logo {
            margin: -1rem -1rem 16px -1rem;
            padding: 20px 16px 16px;
            border-bottom: 1px solid #e8edf5;
            background: #ffffff;
          }
          .sidebar-logo img {
            width: 160px; max-width: 100%; height: auto;
            display: block; margin: 0 auto;
          }
          .sidebar-group-title {
            font-size: 0.68rem; color: #6c757d;
            text-transform: uppercase; letter-spacing: 0.16em;
            margin: 0 0 6px 0; padding: 0 4px;
          }
          .sidebar-shell a,
          .sidebar-shell a:link,
          .sidebar-shell a:visited,
          .sidebar-shell a:hover,
          .sidebar-shell a:active,
          .sidebar-shell a:focus {
            text-decoration: none !important;
          }
          .sidebar-item {
            display: block; width: 100%; padding: 10px 12px;
            border-radius: 10px; color: #1f2a44;
            text-decoration: none !important; margin-bottom: 4px; font-weight: 700;
          }
          .sidebar-item:hover { background: #eef3ff; color: #1f2a44; }
          .sidebar-item.active { background: #355fbb; color: #ffffff; }
          .sidebar-home {
            display: block; width: 100%; padding: 8px 12px;
            border-radius: 10px; color: #5a6478;
            text-decoration: none !important; margin: 0 0 12px 0;
            font-weight: 600; font-size: 0.85rem;
          }
          .sidebar-home:hover { background: #eef3ff; color: #1f2a44; }
          .sidebar-divider { border: none; border-top: 1px solid #e8edf5; margin: 12px 0; }
          [data-testid="stSidebar"] > div:first-child { height: 100vh; }
          [data-testid="stSidebarContent"] { height: 100%; }
          .sidebar-shell {
            min-height: calc(100vh - 8px);
            display: flex;
            flex-direction: column;
          }
          .sidebar-menu { flex: 1; }
          .sidebar-footer {
            margin-top: auto;
            padding: 12px 4px 4px;
            border-top: 1px solid #e8edf5;
          }
          .gov-line {
            font-size: 0.52rem;
            font-weight: 800;
            color: #1a3a6b;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }
          .piaui-line {
            font-size: 1.3rem;
            font-weight: 900;
            color: #1a3a6b;
            line-height: 1;
            letter-spacing: -0.04em;
          }
          .tagline-gov {
            font-size: 0.55rem;
            color: #9aa3b1;
            margin-top: 2px;
          }
          .sidebar-rainbow {
            display: flex;
            height: 5px;
            border-radius: 99px;
            overflow: hidden;
            margin-top: 10px;
          }
          .sidebar-rainbow span:nth-child(1) { flex: 1; background: #e85c41; }
          .sidebar-rainbow span:nth-child(2) { flex: 1; background: #f5c842; }
          .sidebar-rainbow span:nth-child(3) { flex: 1; background: #5cb85c; }
          .sidebar-rainbow span:nth-child(4) { flex: 1; background: #2a5abf; }

          /* Capa */
          .capa-eyebrow {
            font-size: .72rem; text-transform: uppercase;
            letter-spacing: .12em; color: #e57d79; font-weight: 800;
            margin: 8px 0 8px 0;
          }
          .capa-title {
            color: #4a50d3; font-size: 3.45rem; line-height: 0.97;
            font-weight: 800; margin: 4px 0 6px 0; letter-spacing: -0.02em;
          }
          .capa-title .accent { color: #ea807f; }
          .capa-sub {
            color: #4f5660; font-size: 1.03rem; line-height: 1.42;
            max-width: 560px; margin: 10px 0 14px 0;
          }
          .capa-caption {
            color: #4e79c9; font-size: .74rem;
            text-transform: uppercase; letter-spacing: .14em;
            font-weight: 800; margin: 12px 0 4px 0;
          }
          .st-key-capa_left, .st-key-capa_right {
            background: #f6f7f9; border: 1px solid #e0e4ea;
            border-radius: 10px; padding: 14px 16px; min-height: 610px;
          }
          .st-key-capa_right { background: #ecdfce; }
          .st-key-capa_right [data-testid="stImage"] img {
            max-height: 560px; object-fit: contain;
          }
          .st-key-capa_panel_nav button {
            height: 30px !important; min-height: 30px !important;
            padding: 0.1rem .72rem !important; border-radius: 999px !important;
            border: 1px solid #d7dde8 !important; background: #ffffff !important;
            color: #4e79c9 !important; font-size: .70rem !important; font-weight: 800 !important;
          }
          .st-key-capa_panel_nav button:hover {
            border-color: #4a50d3 !important; color: #4a50d3 !important;
            background: #f3f5fb !important;
          }

          [data-baseweb="select"] > div { min-height: 34px; border-radius: 6px; font-size: 0.78rem; }
          [data-baseweb="select"] [role="combobox"] { font-size: 0.78rem; }
          label[data-testid="stWidgetLabel"] p { font-size: 0.72rem !important; font-weight: 600 !important; color: #5a6478 !important; }
          [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 8px; }
          [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def _normalize_menu_item(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).strip()
    menu_values = [item for _, group in MENU_GROUPS for item in group]
    return normalized if normalized in menu_values else None


def render_sidebar_menu() -> str:
    # Lê pagina_ativa do formato novo de query params (Streamlit atual)
    try:
        selected = st.query_params.get("pagina_ativa")
    except Exception:
        selected = None

    # Fallback para versões antigas
    if not selected and hasattr(st, "experimental_get_query_params"):
        try:
            params_legacy = st.experimental_get_query_params()
            selected = params_legacy.get("pagina_ativa", [None])[0]
        except Exception:
            selected = None

    if selected:
        normalized = _normalize_menu_item(selected)
        if normalized:
            st.session_state["pagina_ativa"] = normalized
            mapped_page = PAGE_FROM_MENU.get(normalized)
            if mapped_page:
                st.session_state["page"] = mapped_page

    if "pagina_ativa" not in st.session_state:
        st.session_state["pagina_ativa"] = MENU_GROUPS[0][1][0]
    active_page = st.session_state["pagina_ativa"]
    logo_uri = _to_data_uri(CAPA_LOGO) if CAPA_LOGO.exists() else ""

    menu_html = '<a class="sidebar-home" href="?page=Capa">Início</a>'
    for index, (group_label, items) in enumerate(MENU_GROUPS):
        menu_html += f'<div class="sidebar-group-title">{group_label}</div>'
        for item in items:
            active_class = " active" if item == active_page else ""
            target_page = PAGE_FROM_MENU.get(item, st.session_state.get("page", "Perfil"))
            href = f'?page={quote_plus(target_page)}&pagina_ativa={quote_plus(item)}'
            menu_html += f'<a class="sidebar-item{active_class}" href="{href}">{item}</a>'
        if index < len(MENU_GROUPS) - 1:
            menu_html += '<div class="sidebar-divider"></div>'

    logo_block = (
        f'<div class="sidebar-logo"><img src="{logo_uri}" alt="Logo do Pacto" /></div>'
        if logo_uri else ""
    )

    footer_block = """
    <div class="sidebar-footer">
      <div class="gov-line">GOVERNO DO</div>
      <div class="piaui-line">PIAUÍ</div>
      <div class="tagline-gov">AQUI TEM TRABALHO. AQUI TEM FUTURO.</div>
      <div class="sidebar-rainbow"><span></span><span></span><span></span><span></span></div>
    </div>
    """

    st.sidebar.markdown(
        f'<div class="sidebar-shell">{logo_block}<div class="sidebar-menu">{menu_html}</div>{footer_block}</div>',
        unsafe_allow_html=True,
    )
    return active_page


# ─── Capa ────────────────────────────────────────────────────────────────────

def render_capa_html_navegavel():
    logo_uri = _to_data_uri(CAPA_LOGO) or ""
    arte_uri = _to_data_uri(CAPA_ARTE) or ""
    gov_uri  = _to_data_uri(OBSERVATORIO_DIR / "assets" / "governo-piaui.svg") or ""
    st.markdown(
        f"""
<style>
  [data-testid="stAppViewContainer"] {{ background:#0b1d3f !important; }}
  [data-testid="stToolbar"], [data-testid="stStatusWidget"],
  #MainMenu, footer, header {{ display:none !important; visibility:hidden !important; }}
  .main .block-container {{ max-width:100vw !important; padding:0 !important; margin:0 !important; }}
  .capa-outer {{ width:100vw; min-height:100vh; background:#0b1d3f; display:flex; align-items:stretch; justify-content:center; }}
  .capa-card  {{ width:100vw; max-width:100vw; min-height:100vh; display:flex; background:transparent; }}
  .capa-left  {{ flex:1.2; background:#f7f7f8; padding:46px 56px 28px 56px; display:flex; flex-direction:column; }}
  .capa-right {{ flex:1; background:#e8dbc9; position:relative; display:flex; align-items:center; justify-content:center; overflow:hidden; }}
  .capa-arte  {{ width:88%; max-width:760px; height:auto; }}
  .capa-eyebrow {{ margin-top:8px; color:#ef817d; font-size:13px; font-weight:800; letter-spacing:.22em; text-transform:uppercase; }}
  .capa-title {{ margin:22px 0 0 0; color:#4147d5 !important; font-size:clamp(52px,5.5vw,96px); line-height:.98; font-weight:800; letter-spacing:-.02em; }}
  .capa-title .accent {{ color:#ef817d !important; }}
  .capa-line  {{ width:92px; height:5px; border-radius:999px; background:#ef817d; margin:26px 0 20px 0; }}
  .capa-sub   {{ color:#4c4c4f; font-size:clamp(20px,1.3vw,30px); line-height:1.45; max-width:760px; margin:0; }}
  .capa-caption {{ margin-top:24px; color:#5282c2; font-size:13px; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }}
  .capa-nav   {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:10px; }}
  .capa-pill  {{ display:inline-flex; align-items:center; border-radius:999px; border:1px solid #dfe3eb; background:#fff; color:#5282c2; font-size:16px; font-weight:700; padding:11px 16px; text-decoration:none !important; }}
  .capa-pill:hover {{ border-color:#5282c2; background:#eef3ff; }}
  .capa-pill.active {{ background:#5282c2; color:#fff; border-color:#5282c2; }}
  .capa-footer {{ margin-top:auto; padding-top:16px; border-top:1px solid #e0e4ea; display:flex; align-items:center; gap:14px; }}
  .capa-tagline {{ margin-left:auto; font-size:19px; color:#ef817d; font-style:italic; font-weight:600; }}
  .capa-bottom-ref {{ position:absolute; left:0; right:0; bottom:0; height:18px; background:#fff; }}
  .capa-bar {{ width:100%; height:8px; display:flex; }}
  .capa-bar > span:nth-child(1) {{ flex:1; background:#ef817d; }}
  .capa-bar > span:nth-child(2) {{ flex:1; background:#f4a94e; }}
  .capa-bar > span:nth-child(3) {{ flex:1; background:#adcc6b; }}
  .capa-bar > span:nth-child(4) {{ flex:1; background:#5282c2; }}
</style>
<div class="capa-outer"><div class="capa-card">
  <section class="capa-left">
    <img src="{logo_uri}" alt="Pacto pelas Crianças do Piauí" style="width:300px;height:auto;" />
    <div class="capa-eyebrow">Observatório da Primeira Infância</div>
    <h1 class="capa-title">Pacto pelas<br/>Crianças<br/><span class="accent">do Piauí</span></h1>
    <div class="capa-line"></div>
    <p class="capa-sub">Painel de acompanhamento para leitura integrada dos indicadores da primeira infância no território piauiense.</p>
    <div class="capa-caption">Explore os painéis</div>
    <div class="capa-nav">
      <a class="capa-pill active" href="?page=VisaoGeral&pagina_ativa=Vis%C3%A3o+Geral">Visão Geral</a>
      <a class="capa-pill" href="?page=Perfil&pagina_ativa=Perfil+do+Munic%C3%ADpio">Perfil do Município</a>
      <a class="capa-pill" href="?page=Saude&pagina_ativa=Sa%C3%BAde+e+Bem-estar">Saúde e Bem-estar</a>
      <a class="capa-pill" href="?page=Alimentacao&pagina_ativa=Alimenta%C3%A7%C3%A3o">Alimentação</a>
      <a class="capa-pill" href="?page=Aprendizagem&pagina_ativa=Aprendizagem">Aprendizagem</a>
      <a class="capa-pill" href="?page=Protecao&pagina_ativa=Prote%C3%A7%C3%A3o">Proteção</a>
      <a class="capa-pill" href="?page=Cuidado&pagina_ativa=Cuidado">Cuidado</a>
    </div>
    <div class="capa-footer">
      <img src="{gov_uri}" alt="Governo do Piauí" style="height:62px;width:auto;" />
      <div class="capa-tagline">Primeira infância é para a vida toda.</div>
    </div>
  </section>
  <section class="capa-right">
    <img class="capa-arte" src="{arte_uri}" alt="Ilustração" />
    <div class="capa-bottom-ref"><div class="capa-bar"><span></span><span></span><span></span><span></span></div></div>
  </section>
</div></div>
""",
        unsafe_allow_html=True,
    )


# ─── Componentes visuais reutilizáveis ───────────────────────────────────────────

def _section_header(title: str, subtitle: str, cor: str):
    st.markdown(
        f"""<div class="pi-section-header">
          <div class="pi-section-bar" style="background:{cor};"></div>
          <span class="pi-section-title">{title}</span>
          <span class="pi-section-sub">{subtitle}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _ctx_bar(municipio: str, pop_06: int | None, ano: int):
    """Barra de contexto azul no topo de cada dimensão."""
    pop_str = fmt_int(pop_06) if pop_06 else "n/d"
    st.markdown(
        f"""<div class="pi-ctx-bar">
          <div class="pi-ctx-item">
            <div class="pi-ctx-lbl">Município</div>
            <div class="pi-ctx-val">{municipio}</div>
          </div>
          <div class="pi-ctx-item">
            <div class="pi-ctx-lbl">Pop. 0–6 anos</div>
            <div class="pi-ctx-val">{pop_str}</div>
            <div class="pi-ctx-ref">estimativa</div>
          </div>
          <div class="pi-ctx-item">
            <div class="pi-ctx-lbl">Ano de referência</div>
            <div class="pi-ctx-val">{ano}</div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _plotly_defaults() -> dict:
    """Configurações padrão Plotly para o projeto."""
    if not PLOTLY_OK:
        return {}
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", size=10, color="#5a6478"),
        margin=dict(l=4, r=4, t=24, b=4),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )


def _chart_linha(
    df_mun: pd.DataFrame,
    df_pi: pd.DataFrame | None,
    df_br: pd.DataFrame | None,
    indicador: str,
    cor_mun: str,
    nome_mun: str,
    ylabel: str = "",
    meta: float | None = None,
    height: int = 240,
) -> go.Figure | None:
    """Gráfico de linha série histórica: município vs PI vs BR."""
    if not PLOTLY_OK:
        return None

    fig = go.Figure()

    def _prep_year(dfx: pd.DataFrame | None) -> pd.DataFrame | None:
        if dfx is None or dfx.empty:
            return dfx
        out = dfx.copy()
        out["ano"] = pd.to_numeric(out["ano"], errors="coerce")
        out = out.dropna(subset=["ano"]).copy()
        out["ano"] = out["ano"].astype(int)
        out["ano_label"] = out["ano"].astype(str)
        return out.sort_values("ano")

    df_mun = _prep_year(df_mun)
    df_pi = _prep_year(df_pi)
    df_br = _prep_year(df_br)

    if df_br is not None and not df_br.empty:
        fig.add_trace(go.Scatter(
            x=df_br["ano_label"], y=df_br["valor"], name="Brasil",
            line=dict(color=COR_BR, width=1.5, dash="dot"),
            marker=dict(size=3), mode="lines+markers",
        ))
    if df_pi is not None and not df_pi.empty:
        fig.add_trace(go.Scatter(
            x=df_pi["ano_label"], y=df_pi["valor"], name="Piauí",
            line=dict(color=COR_PI, width=2),
            marker=dict(size=4), mode="lines+markers",
        ))
    if df_mun is not None and not df_mun.empty:
        fig.add_trace(go.Scatter(
            x=df_mun["ano_label"], y=df_mun["valor"], name=nome_mun,
            line=dict(color=cor_mun, width=2.5),
            marker=dict(size=5), mode="lines+markers",
        ))
    if meta is not None:
        anos_range = df_mun["ano_label"].tolist() if df_mun is not None and not df_mun.empty else []
        if anos_range:
            fig.add_trace(go.Scatter(
                x=[anos_range[0], anos_range[-1]], y=[meta, meta],
                name=f"Meta {meta:.0f}", mode="lines",
                line=dict(color=cor_mun, width=1.5, dash="longdash"),
                opacity=0.45,
            ))

    defaults = _plotly_defaults()
    fig.update_layout(
        height=height,
        yaxis_title=ylabel,
        xaxis=dict(type="category", categoryorder="array", gridcolor="#f0f2f5"),
        yaxis=dict(gridcolor="#f0f2f5"),
        **defaults,
    )
    return fig


def _chart_barras_comparacao(
    indicadores: list[str],
    valores_mun: list[float],
    valores_pi: list[float],
    valores_br: list[float],
    cor_mun: str,
    meta: float | None = None,
    height: int = 260,
) -> go.Figure | None:
    """Barras horizontais sobrepostas para comparação Mun / PI / BR."""
    if not PLOTLY_OK:
        return None

    fig = go.Figure()

    if valores_br:
        fig.add_trace(go.Bar(
            y=indicadores, x=valores_br, name="Brasil",
            orientation="h", marker_color=COR_BR, opacity=0.4,
        ))
    if valores_pi:
        fig.add_trace(go.Bar(
            y=indicadores, x=valores_pi, name="Piauí",
            orientation="h", marker_color=COR_PI, opacity=0.7,
        ))
    fig.add_trace(go.Bar(
        y=indicadores, x=valores_mun, name="Município",
        orientation="h", marker_color=cor_mun,
    ))
    if meta is not None:
        fig.add_vline(
            x=meta, line_dash="longdash",
            line_color=cor_mun, opacity=0.4,
            annotation_text=f"Meta {meta:.0f}",
            annotation_position="top right",
            annotation_font_size=10,
        )

    defaults = _plotly_defaults()
    fig.update_layout(
        height=max(height, len(indicadores) * 44 + 60),
        barmode="overlay",
        xaxis=dict(gridcolor="#f0f2f5"),
        yaxis=dict(autorange="reversed"),
        **defaults,
    )
    return fig


def _render_line_fallback(
    df_mun: pd.DataFrame,
    df_pi: pd.DataFrame | None,
    df_br: pd.DataFrame | None,
    nome_mun: str,
):
    parts = []
    if df_br is not None and not df_br.empty:
        p = df_br[["ano", "valor"]].copy()
        p.columns = ["ano", "Brasil"]
        parts.append(p)
    if df_pi is not None and not df_pi.empty:
        p = df_pi[["ano", "valor"]].copy()
        p.columns = ["ano", "Piauí"]
        parts.append(p)
    if df_mun is not None and not df_mun.empty:
        p = df_mun[["ano", "valor"]].copy()
        p.columns = ["ano", nome_mun]
        parts.append(p)
    if not parts:
        st.info("Sem dados para série histórica.")
        return
    merged = parts[0]
    for p in parts[1:]:
        merged = merged.merge(p, on="ano", how="outer")
    merged = merged.sort_values("ano")
    value_cols = [c for c in merged.columns if c != "ano"]
    if not value_cols:
        st.info("Sem dados para série histórica.")
        return
    long_df = merged.melt(id_vars="ano", value_vars=value_cols, var_name="Série", value_name="Valor").dropna()
    if long_df.empty:
        st.info("Sem dados para série histórica.")
        return
    long_df["Ano"] = long_df["ano"].astype(int).astype(str)
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("Ano:N", title="Ano"),
            y=alt.Y("Valor:Q", title="Valor"),
            color=alt.Color("Série:N", legend=alt.Legend(orient="top")),
            tooltip=["Ano:N", "Série:N", alt.Tooltip("Valor:Q", format=".2f")],
        )
        .properties(height=240)
    )
    st.altair_chart(chart, use_container_width=True)


def _render_bar_compare_fallback(indicadores: list[str], valores_mun: list[float], valores_pi: list[float]):
    if not indicadores:
        st.info("Sem dados para comparação.")
        return
    data = pd.DataFrame({"Indicador": indicadores, "Município": valores_mun})
    if valores_pi:
        data["Piauí"] = valores_pi
    data = data.set_index("Indicador")
    st.bar_chart(data, use_container_width=True, height=max(260, len(indicadores) * 36))


def _tabela_indicadores(rows: list[dict], sentido_default: str = "pior"):
    """
    Renderiza tabela HTML de indicadores com colunas Mun / PI / BR / Status.
    rows: lista de dicts com chaves: nome, mun, pi, br, fmt, sentido
    """
    linhas_html = ""
    for r in rows:
        mun_val = r.get("mun")
        pi_val  = r.get("pi")
        br_val  = r.get("br")
        fmt     = r.get("fmt", "{:.1f}")
        sentido = r.get("sentido", sentido_default)
        label, bg, fg = status_badge(mun_val, pi_val, sentido)

        def fv(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "n/d"
            try:
                return fmt.format(v)
            except Exception:
                return str(v)

        linhas_html += f"""
        <tr>
          <td>{r["nome"]}</td>
          <td>{fv(mun_val)}</td>
          <td style="color:#888780">{fv(pi_val)}</td>
          <td style="color:#b4b2a9">{fv(br_val)}</td>
          <td><span class="pi-badge" style="background:{bg};color:{fg};">{label}</span></td>
        </tr>"""

    st.markdown(
        f"""<table class="pi-ind-table">
          <thead><tr>
            <th>Indicador</th>
            <th>Município</th>
            <th>Piauí</th>
            <th>Brasil</th>
            <th>Status</th>
          </tr></thead>
          <tbody>{linhas_html}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


def _tabela_comp_desvio(rows: list[dict]):
    """Tabela estilo v4.5 com desvio percentual vs Piauí."""
    linhas_html = ""
    for r in rows:
        mun = r.get("mun")
        pi = r.get("pi")
        br = r.get("br")
        fmt = r.get("fmt", "{:.1f}")
        sentido = r.get("sentido", "pior")

        def _fv(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "n/d"
            try:
                return fmt.format(v).replace(".", ",")
            except Exception:
                return str(v)

        if mun is None or pi is None or pi == 0 or pd.isna(mun) or pd.isna(pi):
            desvio_txt = "—"
            desvio_bg = COR_NEUTRO_BG
            desvio_fg = COR_NEUTRO
        else:
            delta = ((float(mun) / float(pi)) - 1.0) * 100.0
            if sentido == "pior":
                # para indicadores em que menor é melhor, delta positivo é ruim
                bad = delta > 0
            else:
                # para indicadores em que maior é melhor, delta negativo é ruim
                bad = delta < 0
            desvio_bg = COR_CRITICO_BG if bad else COR_BOM_BG
            desvio_fg = COR_CRITICO if bad else COR_BOM
            desvio_txt = f"{delta:+.1f}%".replace(".", ",")

        linhas_html += f"""
        <tr>
          <td>{r.get("nome", "")}</td>
          <td>{_fv(mun)}</td>
          <td>{_fv(pi)}</td>
          <td>{_fv(br)}</td>
          <td><span class="pi-badge" style="background:{desvio_bg};color:{desvio_fg};">{desvio_txt}</span></td>
        </tr>"""

    st.markdown(
        f"""<table class="pi-ind-table">
          <thead><tr>
            <th>Indicador</th>
            <th>Município</th>
            <th>Piauí</th>
            <th>Brasil</th>
            <th>Desvio vs PI</th>
          </tr></thead>
          <tbody>{linhas_html}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


# ─── Seletor de município / ano (barra top de cada painel) ───────────────────

def _seletores_mun_ano(df: pd.DataFrame, key_prefix: str = "global") -> tuple[str, str, int]:
    """Retorna (cod_ibge, nome_municipio, ano) selecionados."""
    if df.empty:
        return "", "", 0
    muns = (
        df[["cod_ibge", "municipio"]]
        .drop_duplicates()
        .sort_values("municipio")
    )
    anos_all = sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        nome_mun = st.selectbox(
            "Município",
            options=muns["municipio"].tolist(),
            key=f"sel_municipio_{key_prefix}",
        )
    cod_ibge = str(muns.loc[muns["municipio"] == nome_mun, "cod_ibge"].iloc[0])
    anos_mun = sorted(
        df.loc[df["cod_ibge"].astype(str) == cod_ibge, "ano"].dropna().astype(int).unique().tolist(),
        reverse=True,
    )
    anos = anos_mun if anos_mun else anos_all
    with c2:
        ano = st.selectbox(
            "Ano de referência",
            options=anos,
            key=f"sel_ano_{key_prefix}",
        )
    with c3:
        st.write("")  # espaço para alinhamento

    return str(cod_ibge), nome_mun, int(ano)


def _serie_mun(df: pd.DataFrame, cod_ibge: str, padrao: str) -> pd.DataFrame:
    mask = (
        (df["cod_ibge"] == cod_ibge) &
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False)
    )
    return (
        df[mask]
        .groupby("ano", as_index=False)["valor"]
        .mean()
        .sort_values("ano")
    )


def _serie_uf(df: pd.DataFrame, padrao: str, recorte: str = "estado") -> pd.DataFrame:
    mask = (
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False) &
        df["recorte"].astype(str).str.contains(recorte, case=False, regex=True, na=False)
    )
    return (
        df[mask]
        .groupby("ano", as_index=False)["valor"]
        .mean()
        .sort_values("ano")
    )


def _serie_br(df: pd.DataFrame, padrao: str) -> pd.DataFrame:
    mask = (
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False)
        & df["recorte"].astype(str).str.contains(r"brasil|nacional", case=False, regex=True, na=False)
    )
    return (
        df[mask]
        .groupby("ano", as_index=False)["valor"]
        .mean()
        .sort_values("ano")
    )


def _val_mun_ano(df: pd.DataFrame, cod_ibge: str, ano: int, padrao: str) -> float | None:
    mask = (
        (df["cod_ibge"] == cod_ibge) &
        (df["ano"] == ano) &
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False)
    )
    vals = pd.to_numeric(df.loc[mask, "valor"], errors="coerce").dropna()
    return float(vals.mean()) if not vals.empty else None


def _val_pi_ano(df: pd.DataFrame, ano: int, padrao: str) -> float | None:
    mask = (
        (df["ano"] == ano) &
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False) &
        df["recorte"].astype(str).str.contains("estado", case=False, regex=True, na=False)
    )
    vals = pd.to_numeric(df.loc[mask, "valor"], errors="coerce").dropna()
    if not vals.empty:
        return float(vals.mean())
    mask2 = (
        (df["ano"] == ano) &
        df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False)
    )
    vals2 = pd.to_numeric(df.loc[mask2, "valor"], errors="coerce").dropna()
    return float(vals2.mean()) if not vals2.empty else None


def _val_br_ano(df: pd.DataFrame, ano: int, padrao: str) -> float | None:
    mask = (
        (df["ano"] == ano)
        & df["indicador"].astype(str).str.contains(padrao, case=False, regex=True, na=False)
        & df["recorte"].astype(str).str.contains(r"brasil|nacional", case=False, regex=True, na=False)
    )
    vals = pd.to_numeric(df.loc[mask, "valor"], errors="coerce").dropna()
    return float(vals.mean()) if not vals.empty else None


def _render_dim_header(df_full: pd.DataFrame, cod_ibge: str, ano: int, titulo: str, fonte_txt: str):
    idhm = extract_latest_mun_value(df_full, cod_ibge, r"\bIDHM\b", ano_ref=ano)
    pob = extract_latest_mun_value(df_full, cod_ibge, r"Crian[çc]as <5 anos em pobreza", ano_ref=ano)
    ext = extract_latest_mun_value(df_full, cod_ibge, r"Crian[çc]as <5 anos em extrema pobreza", ano_ref=ano)
    urb = extract_latest_mun_value(df_full, cod_ibge, r"situa[çc][aã]o urbano-rural|[áa]rea urbana", ano_ref=ano)
    idhm = _normalize_display_value("IDHM", idhm)

    c_title, c_metrics = st.columns([3, 1.6], gap="small")
    with c_title:
        st.markdown(
            f'<div style="font-family:Playfair Display,serif;font-size:2.0rem;color:#e85c41;line-height:1.1;">{titulo}</div>'
            f'<div style="font-size:.64rem;color:#aab0bb;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-top:2px;">{fonte_txt}</div>',
            unsafe_allow_html=True,
        )
    with c_metrics:
        st.markdown(
            f"""
            <div style="display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;">
              <div class="pi-kpi-card" style="min-width:86px;min-height:52px;padding:6px 8px;"><div class="pi-kpi-label">IDHM</div><div class="pi-kpi-value" style="font-size:1rem;color:#27ae60">{fmt_num(idhm,3)}</div></div>
              <div class="pi-kpi-card" style="min-width:86px;min-height:52px;padding:6px 8px;"><div class="pi-kpi-label">Pobreza Inf.</div><div class="pi-kpi-value" style="font-size:1rem;color:#e67e22">{fmt_num(pob,0)}</div></div>
              <div class="pi-kpi-card" style="min-width:86px;min-height:52px;padding:6px 8px;"><div class="pi-kpi-label">Extrema Pob.</div><div class="pi-kpi-value" style="font-size:1rem;color:#e67e22">{fmt_num(ext,0)}</div></div>
              <div class="pi-kpi-card" style="min-width:86px;min-height:52px;padding:6px 8px;"><div class="pi-kpi-label">Área Urbana</div><div class="pi-kpi-value" style="font-size:1rem;color:#2a5abf">{fmt_num(urb,1,' %')}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_dimensao(
    df: pd.DataFrame,
    dimensao: str,
    cor_resultado: str,
    cor_esforco: str,
    subtemas_resultado: list[tuple],
    subtemas_esforco: list[tuple],
):
    df_full = df.copy()
    eixo_regex_by_dim = {
        "saude": r"sa[úu]de",
        "alimentacao": r"nutri[çc][aã]o|alimenta[çc][aã]o",
        "aprendizagem": r"educa[çc][aã]o|aprendizagem",
        "protecao": r"prote[çc][aã]o|seguran[çc]a",
        "cuidado": r"assist[eê]ncia|cuidado",
    }
    titulo_fonte = {
        "saude": ("Saúde e Bem-estar", "SIM · SINASC · SI-PNI · SINAN · SINISA"),
        "alimentacao": ("Nutrição", "SISVAN · SIM"),
        "aprendizagem": ("Oportunidades de Aprendizagem", "Censo Educacional · INEP · SAEB · SAEPI"),
        "protecao": ("Segurança e Proteção", "SINAN · PNAD Contínua · SIPIA-CT · SUAS"),
        "cuidado": ("Cuidado Responsivo", "Registro Civil · CadÚnico · CNES · SAGICAD"),
    }

    dfx = df.copy()
    dim_regex = eixo_regex_by_dim.get(dimensao)
    if dim_regex:
        mask_dim = dfx["eixo"].astype(str).str.contains(dim_regex, case=False, regex=True, na=False)
        if mask_dim.any():
            dfx = dfx.loc[mask_dim].copy()
        else:
            all_patterns = [p for _, p in subtemas_resultado] + [p for _, p in subtemas_esforco]
            pat_union = "|".join([f"(?:{p})" for p in all_patterns if p])
            if pat_union:
                dfx = dfx.loc[dfx["indicador"].astype(str).str.contains(pat_union, case=False, regex=True, na=False)].copy()

    if dfx.empty:
        st.warning("Sem dados disponíveis para esta dimensão no banco atual.")
        return

    cod_ibge, nome_mun, ano = _seletores_mun_ano(dfx, key_prefix=dimensao)
    pop_06 = extract_latest_mun_value(df_full, cod_ibge, r"Popula[çc][aã]o entre 0 a 6 anos|pop\.?\s*0.?6", ano_ref=ano)
    _ctx_bar(nome_mun, int(pop_06) if pop_06 is not None and pop_06 >= 1 else None, ano)
    ttl, fonte = titulo_fonte.get(dimensao, ("Painel", ""))
    _render_dim_header(df_full, cod_ibge, ano, ttl, fonte)
    st.caption(f"Série disponível nesta dimensão: {int(dfx['ano'].min())}–{int(dfx['ano'].max())}.")

    def _subtemas_com_dados(lista: list[tuple[str, str]]) -> list[tuple[str, str]]:
        validos = []
        for lbl, pat in lista:
            has_any = dfx["indicador"].astype(str).str.contains(pat, case=False, regex=True, na=False).any()
            if has_any:
                validos.append((lbl, pat))
        return validos if validos else lista

    subtemas_resultado_use = _subtemas_com_dados(subtemas_resultado)
    subtemas_esforco_use = _subtemas_com_dados(subtemas_esforco)

    def _inds_year_by_pattern(base: pd.DataFrame, pattern: str, ano_sel: int, limit: int) -> tuple[list[str], int]:
        mask = (base["ano"] == ano_sel) & base["indicador"].astype(str).str.contains(pattern, case=False, regex=True, na=False)
        inds = base.loc[mask, "indicador"].dropna().unique().tolist()[:limit]
        ano_use = ano_sel
        if not inds:
            base_pat = base[base["indicador"].astype(str).str.contains(pattern, case=False, regex=True, na=False)]
            if not base_pat.empty:
                ano_use = int(base_pat["ano"].max())
                inds = base_pat.loc[base_pat["ano"] == ano_use, "indicador"].dropna().unique().tolist()[:limit]
        return inds, ano_use

    def _render_situacao_table(inds: list[str], ano_use: int):
        rows = []
        for ind in inds:
            mun_v = _val_mun_ano(dfx, cod_ibge, ano_use, re.escape(ind))
            pi_v = _val_pi_ano(dfx, ano_use, re.escape(ind))
            br_v = _val_br_ano(dfx, ano_use, re.escape(ind))
            mun_v = _normalize_display_value(ind, mun_v)
            pi_v = _normalize_display_value(ind, pi_v)
            br_v = _normalize_display_value(ind, br_v)
            rows.append({
                "nome": ind,
                "mun": mun_v,
                "pi": pi_v,
                "br": br_v,
                "fmt": _ind_fmt(ind),
                "sentido": _ind_cls(ind),
            })
        if rows:
            _tabela_comp_desvio(rows)
        else:
            st.info("Sem dados para este subtema / ano.")

    # RESULTADOS
    st.markdown('<div class="pi-panel-title">Resultados — Situação Atual</div>', unsafe_allow_html=True)
    subtema_res = st.radio(
        "Subtema resultado",
        [s[0] for s in subtemas_resultado_use],
        horizontal=True,
        label_visibility="collapsed",
        key=f"radio_res_{dimensao}",
    )
    padrao_res = next(p for l, p in subtemas_resultado_use if l == subtema_res)
    inds_res, ano_res = _inds_year_by_pattern(dfx, padrao_res, ano, 12)

    c_res_l, c_res_r = st.columns([1, 1], gap="small")
    with c_res_l:
        with st.container(border=True):
            if ano_res != ano:
                st.caption(f"Sem dados em {ano}. Exibindo último ano disponível: {ano_res}.")
            _render_situacao_table(inds_res, ano_res)
    with c_res_r:
        with st.container(border=True):
            st.markdown('<div class="pi-panel-title">Resultados — Série Histórica</div>', unsafe_allow_html=True)
            ind_res_sel = st.selectbox(
                "Indicador resultado",
                inds_res if inds_res else ["Sem dados"],
                key=f"sel_ind_res_{dimensao}",
                label_visibility="collapsed",
            )
            if ind_res_sel != "Sem dados":
                s_mun = _serie_mun(dfx, cod_ibge, re.escape(ind_res_sel))
                s_pi = _serie_uf(dfx, re.escape(ind_res_sel))
                s_br = _serie_br(dfx, re.escape(ind_res_sel))
                tbadge, tcss = trend_badge(s_mun["valor"] if not s_mun.empty else pd.Series([], dtype=float), sentido=_ind_cls(ind_res_sel))
                st.markdown(f'<span class="pi-badge {tcss}" style="margin-bottom:6px;display:inline-block;">{tbadge}</span>', unsafe_allow_html=True)
                fig = _chart_linha(s_mun, s_pi, s_br, ind_res_sel, cor_resultado, nome_mun)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                else:
                    _render_line_fallback(s_mun, s_pi, s_br, nome_mun)
            else:
                st.info("Sem dados para série histórica.")

    # ESFORÇOS
    st.markdown('<div class="pi-panel-title" style="margin-top:10px;">Esforços — Situação Atual</div>', unsafe_allow_html=True)
    subtema_esf = st.radio(
        "Subtema esforço",
        [s[0] for s in subtemas_esforco_use],
        horizontal=True,
        label_visibility="collapsed",
        key=f"radio_esf_{dimensao}",
    )
    padrao_esf = next(p for l, p in subtemas_esforco_use if l == subtema_esf)
    inds_esf, ano_esf = _inds_year_by_pattern(dfx, padrao_esf, ano, 12)

    c_esf_l, c_esf_r = st.columns([1, 1], gap="small")
    with c_esf_l:
        with st.container(border=True):
            if ano_esf != ano:
                st.caption(f"Sem dados em {ano}. Exibindo último ano disponível: {ano_esf}.")
            _render_situacao_table(inds_esf, ano_esf)
    with c_esf_r:
        with st.container(border=True):
            st.markdown('<div class="pi-panel-title">Esforços — Série Histórica</div>', unsafe_allow_html=True)
            ind_esf_sel = st.selectbox(
                "Indicador esforço",
                inds_esf if inds_esf else ["Sem dados"],
                key=f"sel_ind_esf_{dimensao}",
                label_visibility="collapsed",
            )
            if ind_esf_sel != "Sem dados":
                s_mun = _serie_mun(dfx, cod_ibge, re.escape(ind_esf_sel))
                s_pi = _serie_uf(dfx, re.escape(ind_esf_sel))
                s_br = _serie_br(dfx, re.escape(ind_esf_sel))
                tbadge, tcss = trend_badge(s_mun["valor"] if not s_mun.empty else pd.Series([], dtype=float), sentido=_ind_cls(ind_esf_sel))
                st.markdown(f'<span class="pi-badge {tcss}" style="margin-bottom:6px;display:inline-block;">{tbadge}</span>', unsafe_allow_html=True)
                fig = _chart_linha(s_mun, s_pi, s_br, ind_esf_sel, cor_esforco, nome_mun)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                else:
                    _render_line_fallback(s_mun, s_pi, s_br, nome_mun)
            else:
                st.info("Sem dados para série histórica.")


def render_saude(df: pd.DataFrame):
    render_dimensao(
        df=df,
        dimensao="saude",
        cor_resultado=COR_RESULTADO,
        cor_esforco=COR_ESFORCO,
        subtemas_resultado=DIMENSAO_SUBTEMAS["Saúde e Bem-estar"],
        subtemas_esforco=[
            ("Pré-natal e Saneamento",
             r"7.{0,15}consultas|6.{0,30}consultas|cesariana|[áa]gua pot[áa]vel|saneamento"),
            ("Cobertura Vacinal",
             r"\bBCG\b|Hepatite B|Pentavalente|Penta\b|Tr[íi]plice Viral|Pneumoc[óo]cica|\bVIP\b|Polio"),
        ],
    )


def render_alimentacao(df: pd.DataFrame):
    render_dimensao(
        df=df,
        dimensao="alimentacao",
        cor_resultado="#9b59b6",
        cor_esforco="#16a085",
        subtemas_resultado=DIMENSAO_SUBTEMAS["Alimentação"],
        subtemas_esforco=[
            ("Acompanhamento Nutricional",
             r"acompanhamento nutricional|SISVAN|cobertura.*nutri"),
            ("Aleitamento Materno",
             r"aleitamento.*exclusivo|aleitamento.*continuado|leite materno"),
        ],
    )


def render_aprendizagem(df: pd.DataFrame):
    render_dimensao(
        df=df,
        dimensao="aprendizagem",
        cor_resultado="#f39c12",
        cor_esforco="#2980b9",
        subtemas_resultado=DIMENSAO_SUBTEMAS["Aprendizagem"],
        subtemas_esforco=[
            ("Creche (0–3 anos)",
             r"matr[íi]culas em creche|docentes em creche|docentes.*creches|creche.*esgot|creche.*[áa]gua|\[Infraestrutura\].*creche"),
            ("Pré-escola (4–5 anos)",
             r"docentes na pré-escola|docentes.*pré-escola|\[Infraestrutura\].*pré.escola|pré.escola.*esgot|pré.escola.*[áa]gua"),
        ],
    )


def render_protecao(df: pd.DataFrame):
    render_dimensao(
        df=df,
        dimensao="protecao",
        cor_resultado="#c0392b",
        cor_esforco="#8e44ad",
        subtemas_resultado=DIMENSAO_SUBTEMAS["Proteção"],
        subtemas_esforco=[
            ("Notificações",
             r"ass[ée]dio sexual|estupro|explora[çc][aã]o sexual|pornografia infantil|viol[eê]ncia psicol[oó]gica|viol[eê]ncia sexual|viol[eê]ncia f[íi]sica"),
            ("Letalidade",
             r"homic[íi]dio|armas de fogo"),
        ],
    )


def render_cuidado(df: pd.DataFrame):
    render_dimensao(
        df=df,
        dimensao="cuidado",
        cor_resultado="#27ae60",
        cor_esforco="#1a7a50",
        subtemas_resultado=DIMENSAO_SUBTEMAS["Cuidado"],
        subtemas_esforco=[
            ("Transferência de Renda",
             r"bolsa fam[íi]lia|fam[íi]lias vulner[áa]veis.*transfer"),
            ("Vulnerabilidade Social",
             r"extrema pobreza|<5 anos em pobreza|pobreza"),
        ],
    )


# Cada eixo: (label, cor, [(padrao, ref_pi, cls), ...])
# Indicadores usados no score conforme spec v4.5
EIXOS_VISAO_GERAL = [
    ("Saúde", COR_RESULTADO, [
        (r"mortalidade materna",   44.5, "pior"),
        (r"mortalidade neonatal",   9.4, "pior"),
        (r"mortalidade infantil",  14.2, "pior"),
        (r"baixo peso",             9.8, "pior"),
        (r"s[íi]filis",             4.2, "pior"),
    ]),
    ("Nutrição", COR_PI, [
        (r"d[eé]ficit estatural|prevalência.*estatural",  8.4, "pior"),
        (r"d[eé]ficit ponderal|prevalência.*ponderal",    5.1, "pior"),
        (r"obesidade",            11.8, "pior"),
    ]),
    ("Aprendizagem", "#5cb85c", [
        (r"\bIDEB\b",               5.4, "melhor"),
        (r"alfabetizadas",         64.2, "melhor"),
        (r"abandono.*EF",           1.4, "pior"),
        (r"distor[çc][aã]o idade", 16.2, "pior"),
    ]),
    ("Segurança", "#9b59b6", [
        (r"viol[eê]ncia f[íi]sica", 38.4, "pior"),
        (r"viol[eê]ncia sexual",    24.2, "pior"),
        (r"neglig[eê]ncia",         30.1, "pior"),
        (r"homic[íi]dio.*crian|[óo]bitos.*homic", 1.9, "pior"),
    ]),
    ("Cuidado", "#16a085", [
        (r"registro de nascimento", 95.8, "melhor"),
        (r"registradas.*m[aã]e",   15.2, "pior"),
        (r"casamentos infantis",   14.8, "pior"),
        (r"extrema pobreza",       12.0, "pior"),
    ]),
]


def _score_eixo(df: pd.DataFrame, cod_ibge: str, ano: int,
                indicadores: list) -> float | None:
    """Score 0–100 usando sistema 20/50/80 pontos por indicador (spec v4.5)."""
    pontos = []
    for padrao, ref_pi, cls in indicadores:
        val = _val_mun_ano(df, cod_ibge, ano, padrao)
        if val is None or ref_pi == 0:
            continue
        ratio = val / ref_pi
        if cls == "pior":
            p = 20 if ratio > 1.10 else (50 if ratio > 1.02 else 80)
        else:
            p = 20 if ratio < 0.90 else (50 if ratio < 0.97 else 80)
        pontos.append(p)
    return float(sum(pontos) / len(pontos)) if pontos else None


def _render_contexto_nav(active_page: str):
    itens = [
        ("Visão Geral", "VisaoGeral"),
        ("Perfil do Município", "Perfil"),
    ]
    links = []
    for label, page in itens:
        cls = "contexto-nav-item active" if page == active_page else "contexto-nav-item"
        links.append(f'<a class="{cls}" href="?page={quote_plus(page)}&pagina_ativa={quote_plus(label)}">{label}</a>')
    st.markdown(
        f'<div class="contexto-nav-label">Contexto</div><div class="contexto-nav">{"".join(links)}</div>',
        unsafe_allow_html=True,
    )


def _build_visao_geral_html(geo_js: str, mi_js: str, mc_js: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',system-ui,sans-serif;font-size:11px;background:#f4f6fa;overflow:hidden;height:760px;display:flex;flex-direction:column}}
  .comp-header{{display:flex;align-items:baseline;justify-content:space-between;padding:6px 16px;background:#fff;border-bottom:1px solid #e0e4ea;flex-shrink:0}}
  .ch-title{{font-size:14px;font-weight:700;color:#1a3a6b}}
  .ch-src{{font-size:9px;color:#aab0bb;margin-left:8px}}
  .ctx-strip{{font-size:9px;color:#5a6478}}
  .panel-hdr{{padding:7px 12px;border-bottom:1px solid #eef0f3;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
  .panel-ttl{{font-size:10px;font-weight:700;color:#2c3e50}}
  .footer{{font-size:8px;color:#aab0bb;text-align:center;padding:4px;border-top:1px solid #eef0f3;flex-shrink:0}}
  .rainbow-bar{{height:3px;background:linear-gradient(90deg,#e85c41,#f5c842,#5cb85c,#9b59b6,#16a085);flex-shrink:0}}
  table{{border-collapse:collapse;width:100%}}
  th{{font-size:8.5px;font-weight:600;color:#5a6478;padding:5px 8px;text-align:left;position:sticky;top:0;background:#fff;z-index:2;border-bottom:1px solid #eef0f3;white-space:nowrap}}
  td{{font-size:10px;color:#2c3e50;border-top:0.5px solid #f0f2f5}}
  .badge{{display:inline-block;min-width:32px;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;text-align:center}}
  #pacto-thermo{{display:flex;gap:6px;padding:7px 8px;background:#fff;border-bottom:1px solid #e0e4ea;flex-shrink:0;flex-wrap:wrap}}
  .thermo-card{{flex:1;min-width:120px;background:#fff;border-radius:7px;padding:8px 12px;cursor:pointer;transition:all .15s;user-select:none}}
  .main-body{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px;overflow:hidden;min-height:0}}
  .panel{{background:#fff;border-radius:8px;border:1px solid #e8ecf2;display:flex;flex-direction:column;overflow:hidden}}
  .right-col{{display:flex;flex-direction:column;gap:8px;overflow:hidden;min-height:0}}
  #map-container{{flex:1;position:relative;min-height:0}}
  .map-legend{{padding:5px 12px;border-top:1px solid #eef0f3;display:flex;gap:14px;align-items:center;flex-shrink:0}}
  .leg-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:3px}}
  .heatmap-wrap{{flex:1;overflow-y:auto;min-height:0}}
  .ranking-panel{{background:#fff;border-radius:8px;border:1px solid #e8ecf2;display:flex;flex-direction:column;overflow:hidden;flex:0 0 auto}}
  #ranking-table td{{padding:4px 8px}}
  #ranking-table th{{padding:5px 8px}}
</style>
</head>
<body>

<!-- CABEÇALHO -->
<div class="comp-header">
  <div style="display:flex;align-items:baseline;gap:8px">
    <span class="ch-title">Visão Geral</span>
    <span class="ch-src">Síntese do desempenho · 10 municípios monitorados</span>
  </div>
  <div id="ctx-pacto" class="ctx-strip"></div>
</div>

<!-- TERMÔMETROS -->
<div id="pacto-thermo"></div>

<!-- CORPO -->
<div class="main-body">

  <!-- MAPA -->
  <div class="panel">
    <div class="panel-hdr">
      <span class="panel-ttl">Distribuição territorial — desempenho geral</span>
      <span style="font-size:8px;color:#aab0bb">Hover p/ detalhes</span>
    </div>
    <div id="map-container">
      <svg id="pacto-map" style="width:100%;height:100%;display:block"></svg>
    </div>
    <div class="map-legend">
      <span style="font-size:8.5px;color:#5a6478;font-weight:600">Desempenho</span>
      <span><span class="leg-dot" style="background:#27ae60"></span><span style="font-size:8px;color:#5a6478">Bom ≥70</span></span>
      <span><span class="leg-dot" style="background:#e67e22"></span><span style="font-size:8px;color:#5a6478">Atenção 45–69</span></span>
      <span><span class="leg-dot" style="background:#c0392b"></span><span style="font-size:8px;color:#5a6478">Crítico &lt;45</span></span>
      <span style="font-size:8px;color:#aab0bb;margin-left:auto">Piauí — 10 municípios</span>
    </div>
  </div>

  <!-- COLUNA DIREITA -->
  <div class="right-col">

    <!-- HEATMAP -->
    <div class="panel" style="flex:1;min-height:0">
      <div class="panel-hdr">
        <span class="panel-ttl">Mapa de calor — municípios × eixos</span>
        <span style="font-size:8px;color:#aab0bb">Clique no eixo para ranking</span>
      </div>
      <div class="heatmap-wrap">
        <table id="heatmap-grid"></table>
      </div>
    </div>

    <!-- RANKING -->
    <div class="ranking-panel">
      <div class="panel-hdr">
        <span class="panel-ttl" id="ranking-title">Ranking — selecione um eixo</span>
      </div>
      <div style="overflow-x:auto">
        <table id="ranking-table"></table>
      </div>
    </div>

  </div>
</div>

<!-- RODAPÉ -->
<div class="footer">Observatório da Primeira Infância do Piauí · Dados: SIM, SINASC, SINAN, SISVAN · Scores 0–100</div>
<div class="rainbow-bar"></div>

<script>
const MUN_KEYS = ['teresina','parnaiba','picos','floriano','oeiras','srnona','piripiri','barras','campogr','guaribas'];

const IBGE_TO_KEY = {{
  '2211001':'teresina','2207702':'parnaiba','2208007':'picos',
  '2203909':'floriano','2207009':'oeiras','2209401':'srnona',
  '2208403':'piripiri','2201200':'barras','2202117':'campogr','2204550':'guaribas'
}};

const EIXOS = [
  {{key:'saude',    label:'Saúde',        cor:'#e85c41',
    ids:['mort_mat','mort_neo','mort_inf','bx_peso','sifilis'],
    refs:[44.5,9.4,14.2,9.8,4.2], cls:['pior','pior','pior','pior','pior']}},
  {{key:'nut',      label:'Nutrição',     cor:'#f5c842',
    ids:['def_est','def_pon','obesi'],
    refs:[8.4,5.1,11.8], cls:['pior','pior','pior']}},
  {{key:'edu',      label:'Aprendizagem', cor:'#5cb85c',
    ids:['ideb','alfab','aband','dist'],
    refs:[5.4,64.2,1.4,16.2], cls:['melhor','melhor','pior','pior']}},
  {{key:'seg',      label:'Segurança',    cor:'#9b59b6',
    ids:['v_fis','v_sex','neglig','o_hom'],
    refs:[38.4,24.2,30.1,1.9], cls:['pior','pior','pior','pior']}},
  {{key:'cuid',     label:'Cuidado',      cor:'#16a085',
    ids:['reg_nas','so_mae','cas_inf'],
    refs:[95.8,15.2,14.8], cls:['melhor','pior','pior']}}
];

const MI = {mi_js};
const MC = {mc_js};
let PIUI_GEO = {geo_js};
let activeEixo = null;

function scoreColor(s) {{
  if (s === null || s === undefined) return {{bg:'#f0f2f5', txt:'#aab0bb', label:'n/d'}};
  if (s >= 70) return {{bg:'#EAF3DE', txt:'#27ae60', label:'Bom'}};
  if (s >= 45) return {{bg:'#FAEEDA', txt:'#e67e22', label:'Atenção'}};
  return {{bg:'#FCEBEB', txt:'#c0392b', label:'Crítico'}};
}}

function munEixoScore(mun, eixo) {{
  const mi = MI[mun] || {{}};
  const pts = [];
  eixo.ids.forEach((id, i) => {{
    const v  = mi[id];
    const pi = eixo.refs[i];
    if (v == null || v === undefined || pi == null || pi === 0) return;
    const ratio = v / pi;
    const cls   = eixo.cls[i];
    let p;
    if (cls === 'pior')   p = ratio > 1.10 ? 20 : ratio > 1.02 ? 50 : 80;
    else if (cls === 'melhor') p = ratio < 0.90 ? 20 : ratio < 0.97 ? 50 : 80;
    else p = 50;
    pts.push(p);
  }});
  if (pts.length === 0) return null;
  return Math.round(pts.reduce((a,b)=>a+b,0)/pts.length);
}}

function munOverallScore(mun) {{
  const scores = EIXOS.map(e => munEixoScore(mun,e)).filter(s => s !== null);
  if (scores.length === 0) return null;
  return Math.round(scores.reduce((a,b)=>a+b,0)/scores.length);
}}

/* ── TERMÔMETROS ── */
function renderThermo() {{
  const el = document.getElementById('pacto-thermo');
  el.innerHTML = EIXOS.map(e => {{
    const scores = MUN_KEYS.map(m => munEixoScore(m,e)).filter(s => s !== null);
    const avg  = scores.length > 0 ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : null;
    const crit = scores.filter(s=>s<45).length;
    const sc   = scoreColor(avg);
    const trend = avg===null?'sem dados':avg>=70?'↗ Melhorando':avg>=45?'→ Estável':'↘ Piorando';
    const tColor= avg===null?'#aab0bb':avg>=70?'#27ae60':avg>=45?'#e67e22':'#c0392b';
    const isActive = activeEixo === e.key;
    return `<div onclick="selectEixo('${{e.key}}')" id="thermo-${{e.key}}" class="thermo-card"
      style="border:2px solid ${{isActive?e.cor:e.cor+'33'}};background:${{isActive?'#f8f9ff':'#fff'}}">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:10px;font-weight:700;color:${{e.cor}}">${{e.label}}</span>
        <span style="font-size:8px;color:${{tColor}}">${{trend}}</span>
      </div>
      <div style="display:flex;align-items:baseline;gap:4px;margin-bottom:5px">
        <span style="font-size:22px;font-weight:700;color:${{sc.txt}}">${{avg !== null ? avg : 'n/d'}}</span>
        <span style="font-size:9px;color:#aab0bb">${{avg !== null ? '/ 100' : ''}}</span>
      </div>
      <div style="height:5px;background:#eef0f3;border-radius:3px;overflow:hidden;margin-bottom:5px">
        <div style="height:100%;width:${{avg !== null ? avg : 0}}%;background:${{e.cor}};border-radius:3px;transition:width .4s"></div>
      </div>
      <div style="font-size:8.5px;color:${{crit>3?'#c0392b':'#aab0bb'}};font-weight:${{crit>3?700:400}}">
        ${{avg !== null ? crit+' município'+(crit!==1?'s':'')+' crítico'+(crit!==1?'s':'') : 'dados indisponíveis'}}
      </div>
    </div>`;
  }}).join('');
}}

function selectEixo(key) {{
  activeEixo = key;
  renderThermo();
  renderRanking(key);
}}

/* ── MAPA SVG ── */
function renderMap(selMun) {{
  const svgEl = document.getElementById('pacto-map');
  const cont  = document.getElementById('map-container');
  const W = cont.clientWidth  || 420;
  const H = cont.clientHeight || 400;
  svgEl.setAttribute('viewBox',`0 0 ${{W}} ${{H}}`);

  if (!PIUI_GEO) {{
    svgEl.innerHTML=`<text x="${{W/2}}" y="${{H/2}}" text-anchor="middle" font-size="12" font-family="Inter,sans-serif" fill="#aab0bb">GeoJSON não disponível</text>`;
    return;
  }}

  let minLon=Infinity,maxLon=-Infinity,minLat=Infinity,maxLat=-Infinity;
  PIUI_GEO.features.forEach(f=>{{
    const rings = f.geometry.type==='MultiPolygon'?f.geometry.coordinates.flat(1):f.geometry.coordinates;
    rings.forEach(ring=>ring.forEach(([lon,lat])=>{{
      if(lon<minLon)minLon=lon;if(lon>maxLon)maxLon=lon;
      if(lat<minLat)minLat=lat;if(lat>maxLat)maxLat=lat;
    }}));
  }});

  const PAD=16, mapW=W-PAD*2, mapH=H-PAD*2;
  const scX=mapW/(maxLon-minLon), scY=mapH/(maxLat-minLat), sc=Math.min(scX,scY);
  const offX=PAD+(mapW-(maxLon-minLon)*sc)/2;
  const offY=PAD+(mapH-(maxLat-minLat)*sc)/2;

  function proj(lon,lat){{return[offX+(lon-minLon)*sc, offY+(maxLat-lat)*sc];}}
  function ring2path(ring){{return'M'+ring.map(([lon,lat])=>proj(lon,lat).map(v=>v.toFixed(1)).join(',')).join('L')+'Z';}}
  function feat2path(f){{
    if(f.geometry.type==='Polygon') return f.geometry.coordinates.map(ring2path).join(' ');
    if(f.geometry.type==='MultiPolygon') return f.geometry.coordinates.map(p=>p.map(ring2path).join(' ')).join(' ');
    return '';
  }}
  function centroid(f){{
    const ring=f.geometry.type==='MultiPolygon'?f.geometry.coordinates[0][0]:f.geometry.coordinates[0];
    const pts=ring.map(([lon,lat])=>proj(lon,lat));
    return[pts.reduce((s,p)=>s+p[0],0)/pts.length, pts.reduce((s,p)=>s+p[1],0)/pts.length];
  }}

  let bg='',mon='',lbls='';
  PIUI_GEO.features.forEach(f=>{{
    const props=f.properties||{{}};
    const cod=String(props.id||props.codarea||'');
    const munKey=IBGE_TO_KEY[cod];
    const d=feat2path(f);
    if(!d) return;
    if(munKey){{
      const sc2=munOverallScore(munKey);
      const c=scoreColor(sc2);
      const isSel=munKey===selMun;
      const [cx,cy]=centroid(f);
      mon+=`<g class="mun-g" data-key="${{munKey}}" data-sc="${{sc2}}" style="cursor:pointer">
        <path d="${{d}}" fill="${{c.bg}}" stroke="${{isSel?'#1a3a6b':'#fff'}}" stroke-width="${{isSel?2:0.8}}" style="transition:all .12s"/>
      </g>`;
      lbls+=`<g pointer-events="none">
        <text x="${{cx.toFixed(1)}}" y="${{(cy-2).toFixed(1)}}" text-anchor="middle" font-size="7.5" font-family="Inter,sans-serif" font-weight="${{isSel?700:600}}" fill="${{isSel?'#1a3a6b':c.txt}}" style="text-shadow:0 1px 2px rgba(255,255,255,.9)">${{MC[munKey].nome.split(' ')[0]}}</text>
        <text x="${{cx.toFixed(1)}}" y="${{(cy+8).toFixed(1)}}" text-anchor="middle" font-size="7" font-family="Inter,sans-serif" font-weight="700" fill="${{isSel?'#1a3a6b':c.txt+'99'}}">${{sc2 !== null ? sc2 : 'n/d'}}</text>
      </g>`;
    }} else {{
      bg+=`<path d="${{d}}" fill="#e8edf2" stroke="#fff" stroke-width="0.4"/>`;
    }}
  }});

  svgEl.innerHTML=`<defs><filter id="ms"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#00000018"/></filter></defs>
    <g filter="url(#ms)">${{bg}}${{mon}}</g><g>${{lbls}}</g>`;

  let tt=document.getElementById('map-tt');
  if(!tt){{tt=document.createElement('div');tt.id='map-tt';
    Object.assign(tt.style,{{position:'absolute',background:'#1a3a6b',color:'#fff',borderRadius:'7px',padding:'9px 13px',fontSize:'10px',fontFamily:'Inter,sans-serif',pointerEvents:'none',display:'none',zIndex:'20',minWidth:'148px',lineHeight:'1.7',boxShadow:'0 4px 18px rgba(0,0,0,.22)'}});
    cont.appendChild(tt);
  }}

  svgEl.querySelectorAll('.mun-g').forEach(g=>{{
    const key=g.dataset.key;
    g.addEventListener('mouseenter',()=>{{
      g.querySelector('path').style.filter='brightness(0.86)';
      const sc2=munOverallScore(key), c=scoreColor(sc2);
      const rows=EIXOS.map(e=>{{const es=munEixoScore(key,e);const ec=scoreColor(es);
        return`<div style="display:flex;justify-content:space-between;gap:14px"><span style="color:rgba(255,255,255,.65)">${{e.label}}</span><span style="font-weight:700;color:${{ec.bg}}">${{es !== null ? es : 'n/d'}}</span></div>`;
      }}).join('');
      tt.innerHTML=`<div style="font-weight:700;font-size:11px;margin-bottom:4px;border-bottom:1px solid rgba(255,255,255,.2);padding-bottom:4px">${{MC[key].nome}}</div>${{rows}}<div style="margin-top:4px;border-top:1px solid rgba(255,255,255,.2);padding-top:4px;display:flex;justify-content:space-between"><span style="color:rgba(255,255,255,.6)">Geral</span><span style="font-weight:700;color:${{c.bg}}">${{sc2 !== null ? sc2 : 'n/d'}}</span></div>`;
      tt.style.display='block';
    }});
    g.addEventListener('mousemove',evt=>{{
      const r=cont.getBoundingClientRect();
      tt.style.left=Math.min(evt.clientX-r.left+14,W-165)+'px';
      tt.style.top=Math.max(4,evt.clientY-r.top-14)+'px';
    }});
    g.addEventListener('mouseleave',()=>{{g.querySelector('path').style.filter='';tt.style.display='none';}});
    g.addEventListener('click',()=>{{renderMap(key);renderHeatmap(key);}});
  }});
}}

/* ── HEATMAP ── */
function renderHeatmap(selMun) {{
  const t=document.getElementById('heatmap-grid');
  const hdr=`<thead><tr>
    <th style="text-align:left">Município</th>
    ${{EIXOS.map(e=>`<th onclick="selectEixo('${{e.key}}')" style="color:${{e.cor}};cursor:pointer;text-align:center">${{e.label}}</th>`).join('')}}
    <th style="text-align:center">Geral</th>
  </tr></thead>`;
  const rows=MUN_KEYS.map(mun=>{{
    const isSel=mun===selMun;
    const bg=isSel?'#eef2fc':'transparent';
    const fw=isSel?700:400;
    const ov=munOverallScore(mun), oc=scoreColor(ov);
    const cells=EIXOS.map(e=>{{const s=munEixoScore(mun,e);const c=scoreColor(s);
      return`<td style="padding:4px 6px;text-align:center"><span class="badge" style="background:${{c.bg}};color:${{c.txt}}">${{s !== null ? s : 'n/d'}}</span></td>`;
    }}).join('');
    return`<tr style="background:${{bg}};cursor:pointer" onclick="onHeatmapClick('${{mun}}')">
      <td style="padding:4px 10px;font-weight:${{fw}};white-space:nowrap">${{MC[mun].nome}}</td>
      ${{cells}}
      <td style="padding:4px 6px;text-align:center"><span class="badge" style="background:${{oc.bg}};color:${{oc.txt}}">${{ov !== null ? ov : 'n/d'}}</span></td>
    </tr>`;
  }}).join('');
  t.innerHTML=hdr+'<tbody>'+rows+'</tbody>';
}}

function onHeatmapClick(mun){{renderMap(mun);renderHeatmap(mun);}}

/* ── RANKING ── */
function renderRanking(eixoKey) {{
  const eixo=EIXOS.find(e=>e.key===eixoKey);
  if(!eixo) return;
  document.getElementById('ranking-title').textContent=`Ranking — ${{eixo.label}} (0 = pior · 100 = melhor)`;
  const sorted=[...MUN_KEYS].map(m=>({{mun:m,score:munEixoScore(m,eixo)}})).sort((a,b)=>{{
    if(a.score===null&&b.score===null)return 0;
    if(a.score===null)return 1;
    if(b.score===null)return -1;
    return a.score-b.score;
  }});
  const t=document.getElementById('ranking-table');
  const rows=sorted.map((item,i)=>{{
    const c=scoreColor(item.score);
    return`<tr>
      <td style="padding:3px 8px;color:#aab0bb;font-weight:700;width:20px">${{i+1}}</td>
      <td style="padding:3px 8px;white-space:nowrap">${{MC[item.mun].nome}}</td>
      <td style="padding:3px 8px;width:110px">
        <div style="height:5px;background:#eef0f3;border-radius:3px;overflow:hidden">
          <div style="height:100%;width:${{item.score !== null ? item.score : 0}}%;background:${{eixo.cor}};border-radius:3px"></div>
        </div>
      </td>
      <td style="padding:3px 8px"><span class="badge" style="background:${{c.bg}};color:${{c.txt}}">${{item.score !== null ? item.score : 'n/d'}}</span></td>
    </tr>`;
  }}).join('');
  t.innerHTML=`<thead><tr><th>#</th><th>Município</th><th>Desempenho</th><th>Score</th></tr></thead><tbody>${{rows}}</tbody>`;
}}

/* ── INIT ── */
(function init(){{
  renderThermo();
  renderHeatmap(null);
  document.getElementById('ranking-table').innerHTML=
    '<tr><td colspan="4" style="padding:16px;text-align:center;font-size:11px;color:#aab0bb">Clique num eixo para ver o ranking</td></tr>';
  renderMap(null);
  const mapCont=document.getElementById('map-container');
  const ro=new ResizeObserver(()=>renderMap(null));
  ro.observe(mapCont);
}})();
</script>
</body>
</html>"""


def render_visao_geral(df: pd.DataFrame):
    import json as _json

    _render_contexto_nav("VisaoGeral")

    MUN_META = {
        'teresina': {'nome': 'Teresina',         'ibge7': '2211001', 'ibge6': '221100'},
        'parnaiba': {'nome': 'Parnaíba',          'ibge7': '2207702', 'ibge6': '220770'},
        'picos':    {'nome': 'Picos',             'ibge7': '2208007', 'ibge6': '220800'},
        'floriano': {'nome': 'Floriano',          'ibge7': '2203909', 'ibge6': '220390'},
        'oeiras':   {'nome': 'Oeiras',            'ibge7': '2207009', 'ibge6': '220700'},
        'srnona':   {'nome': 'S. R. Nonato',      'ibge7': '2209401', 'ibge6': '221060'},
        'piripiri': {'nome': 'Piripiri',          'ibge7': '2208403', 'ibge6': '220840'},
        'barras':   {'nome': 'Barras',            'ibge7': '2201200', 'ibge6': '220120'},
        'campogr':  {'nome': 'Campo Grande',      'ibge7': '2202117', 'ibge6': '220213'},
        'guaribas': {'nome': 'Guaribas',          'ibge7': '2204550', 'ibge6': '220455'},
    }

    def _latest(cod6, pattern, min_val=None):
        mask = (
            df['cod_ibge'].astype(str).str[:6] == str(cod6)
        ) & df['indicador'].astype(str).str.contains(pattern, case=False, regex=True, na=False)
        sub = df[mask].copy()
        if sub.empty:
            return None
        sub['_a'] = pd.to_numeric(sub['ano'],   errors='coerce')
        sub['_v'] = pd.to_numeric(sub['valor'], errors='coerce')
        sub = sub.dropna(subset=['_a', '_v'])
        if min_val is not None:
            sub = sub[sub['_v'] >= min_val]
        if sub.empty:
            return None
        return float(sub.sort_values('_a', ascending=False).iloc[0]['_v'])

    MI = {}
    for key, meta in MUN_META.items():
        cod6 = meta['ibge6']
        pop = _latest(cod6, r'Popula[çc][aã]o do munic[íi]pio')
        if not pop or pop <= 0:
            pop = _latest(cod6, r'Popula[çc][aã]o')

        def _rate(v):
            if v is None or not pop or pop <= 0:
                return None
            return round(v / pop * 100_000, 1)

        MI[key] = {
            # Saúde — direto do banco (já são taxas)
            'mort_mat': _latest(cod6, r'mortalidade materna',  min_val=0.01),
            'mort_neo': _latest(cod6, r'mortalidade neonatal', min_val=0.01),
            'mort_inf': _latest(cod6, r'mortalidade infantil', min_val=0.01),
            'bx_peso':  _latest(cod6, r'baixo peso',           min_val=0.01),
            'sifilis':  _latest(cod6, r's[íi]filis cong',      min_val=0.01),
            # Nutrição — direto do banco (percentuais)
            'def_est':  _latest(cod6, r'd[eé]ficit estatural',  min_val=0.01),
            'def_pon':  _latest(cod6, r'd[eé]ficit ponderal',   min_val=0.01),
            'obesi':    _latest(cod6, r'obesidade.*crian|crian.*obesidade', min_val=0.01),
            # Aprendizagem — não disponível no banco
            'ideb':  None,
            'alfab': None,
            'aband': None,
            'dist':  None,
            # Segurança — banco tem contagens absolutas → convertemos para taxa/100k
            'v_fis':  _rate(_latest(cod6, r'viol[eê]ncia f[íi]sica.*crian|crian.*viol[eê]ncia f[íi]sica')),
            'v_sex':  _rate(_latest(cod6, r'viol[eê]ncia sexual.*crian|crian.*viol[eê]ncia sexual')),
            'neglig': _latest(cod6, r'neglig[eê]ncia.*abandon|taxa.*neglig[eê]ncia'),
            'o_hom':  _rate(_latest(cod6, r'homic[íi]dio.*crian|[óo]bitos.*homic')),
            # Cuidado — não disponível no banco
            'reg_nas': None,
            'so_mae':  None,
            'cas_inf': None,
        }

    geo_data = {}
    try:
        with open(PIAUI_GEOJSON, 'r', encoding='utf-8') as _gf:
            geo_data = _json.load(_gf)
    except Exception:
        pass

    MC = {k: {'nome': v['nome']} for k, v in MUN_META.items()}

    geo_js = _json.dumps(geo_data) if geo_data else 'null'
    mi_js  = _json.dumps(MI)
    mc_js  = _json.dumps(MC)

    html = _build_visao_geral_html(geo_js, mi_js, mc_js)
    st_html(html, height=760, scrolling=False)


def render_panorama(df: pd.DataFrame):
    _render_contexto_nav("Panorama")
    st.markdown("### Panorama Geral — Piauí")
    st.caption("Visão consolidada dos indicadores monitorados em todos os municípios.")

    anos = sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
    c1, c2 = st.columns([2, 1])
    with c1:
        ano = st.selectbox("Ano de referência", anos, key="panorama_ano")
    with c2:
        eixo_opts = ["Todos"] + sorted(df["eixo"].dropna().unique().tolist())
        eixo = st.selectbox("Eixo", eixo_opts, key="panorama_eixo")

    dff = df[df["ano"] == ano].copy()
    if eixo != "Todos":
        dff = dff[dff["eixo"] == eixo]

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Municípios cobertos", fmt_int(dff["municipio"].nunique()), f"Ano {ano}")
    with k2:
        kpi_card("Indicadores ativos", fmt_int(dff["indicador"].nunique()), eixo if eixo != "Todos" else "todos os eixos")
    with k3:
        kpi_card("Registros", fmt_int(len(dff)), "fato_indicador")
    with k4:
        kpi_card("Eixos monitorados", fmt_int(dff["eixo"].nunique()), "dimensões")

    st.markdown("---")

    col_heat, col_rank = st.columns([1.4, 1])

    with col_heat:
        with st.container(border=True):
            st.markdown('<div class="pi-panel-title">Distribuição por eixo — média dos valores</div>', unsafe_allow_html=True)
            pivot = (
                dff.groupby(["municipio", "eixo"])["valor"]
                .mean()
                .reset_index()
                .pivot(index="municipio", columns="eixo", values="valor")
            )
            if not pivot.empty:
                if PLOTLY_OK:
                    fig_heat = px.imshow(
                        pivot,
                        color_continuous_scale="RdYlGn",
                        aspect="auto",
                        labels=dict(color="Média"),
                    )
                    fig_heat.update_layout(
                        height=max(300, len(pivot) * 22 + 60),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=4, r=4, t=8, b=4),
                        font=dict(family="Manrope, sans-serif", size=10),
                        coloraxis_showscale=False,
                    )
                    st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.dataframe(
                        pivot,
                        use_container_width=True,
                        height=max(300, len(pivot) * 22 + 60),
                    )
            else:
                st.info("Sem dados suficientes para o heatmap.")

    with col_rank:
        with st.container(border=True):
            st.markdown('<div class="pi-panel-title">Top municípios — média geral</div>', unsafe_allow_html=True)
            rank = (
                dff.groupby("municipio", as_index=False)["valor"]
                .mean()
                .sort_values("valor", ascending=False)
                .head(15)
            )
            if not rank.empty:
                if PLOTLY_OK:
                    fig_rank = px.bar(
                        rank, x="valor", y="municipio", orientation="h",
                        color_discrete_sequence=[COR_ESFORCO],
                    )
                    fig_rank.update_layout(
                        height=max(300, len(rank) * 28 + 60),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=4, r=4, t=8, b=4),
                        font=dict(family="Manrope, sans-serif", size=10),
                        yaxis=dict(autorange="reversed"),
                        showlegend=False,
                        xaxis=dict(gridcolor="#f0f2f5"),
                    )
                    st.plotly_chart(fig_rank, use_container_width=True, config={"displayModeBar": False})
                else:
                    rank2 = rank.set_index("municipio")[["valor"]].rename(columns={"valor": "Média"})
                    st.bar_chart(rank2, use_container_width=True, height=max(300, len(rank) * 24 + 60))
            else:
                st.info("Sem dados para ranking.")

    with st.container(border=True):
        st.markdown('<div class="pi-panel-title">Tabela de dados (amostra — 2000 linhas)</div>', unsafe_allow_html=True)
        st.dataframe(
            dff.sort_values(["municipio", "indicador"]).reset_index(drop=True).head(2000),
            use_container_width=True,
            hide_index=True,
            height=360,
        )


def render_perfil(df: pd.DataFrame):
    _render_contexto_nav("Perfil")
    st.markdown("### Perfil do Município")

    cod_ibge, nome_mun, ano = _seletores_mun_ano(df, key_prefix="perfil")
    pop_06 = extract_latest_mun_value(df, cod_ibge, r"Popula[çc][aã]o entre 0 a 6 anos|pop\.?\s*0.?6", ano_ref=ano)
    _ctx_bar(nome_mun, int(pop_06) if pop_06 is not None and pop_06 >= 1 else None, ano)

    dff = df[(df["cod_ibge"] == cod_ibge) & (df["ano"] == ano)].copy()

    k1, k2, k3, k4 = st.columns(4)
    idhm = extract_latest_mun_value(df, cod_ibge, r"\bIDHM\b", ano_ref=ano)
    pob  = extract_latest_mun_value(df, cod_ibge, r"Crian[çc]as <5 anos em pobreza", ano_ref=ano)
    ext  = extract_latest_mun_value(df, cod_ibge, r"Crian[çc]as <5 anos em extrema pobreza", ano_ref=ano)
    urb  = extract_latest_mun_value(df, cod_ibge, r"situa[çc][aã]o urbano-rural|[áa]rea urbana", ano_ref=ano)
    idhm = _normalize_display_value("IDHM", idhm)
    with k1:
        kpi_card("IDHM", fmt_num(idhm, 3), f"Ref. {ano}")
    with k2:
        kpi_card("Crianças <5 em pobreza", fmt_num(pob, 0), "valor absoluto")
    with k3:
        kpi_card("Crianças <5 em extrema pobreza", fmt_num(ext, 0), "valor absoluto")
    with k4:
        kpi_card("Área urbana", fmt_num(urb, 1, "%"), "estimativa")

    st.markdown("---")

    eixos = sorted(dff["eixo"].dropna().unique().tolist())
    for eixo in eixos:
        with st.expander(f"📊 {eixo}", expanded=False):
            sub = dff[dff["eixo"] == eixo][["indicador", "valor", "fonte_principal"]].copy()
            sub["valor"] = pd.to_numeric(sub["valor"], errors="coerce")
            sub = sub.dropna(subset=["valor"]).sort_values("indicador")
            if not sub.empty:
                if PLOTLY_OK:
                    fig = px.bar(
                        sub.head(20), x="valor", y="indicador", orientation="h",
                        color_discrete_sequence=[COR_RESULTADO],
                        hover_data=["fonte_principal"],
                    )
                    fig.update_layout(
                        height=max(200, len(sub.head(20)) * 30 + 50),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=4, r=4, t=8, b=4),
                        font=dict(family="Manrope, sans-serif", size=10),
                        showlegend=False,
                        yaxis=dict(autorange="reversed"),
                        xaxis=dict(gridcolor="#f0f2f5"),
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.bar_chart(
                        sub.head(20).set_index("indicador")[["valor"]],
                        use_container_width=True,
                        height=max(200, len(sub.head(20)) * 26 + 50),
                    )
            else:
                st.info("Sem dados para este eixo / ano.")


@st.cache_data(show_spinner=False)
def _load_piaui_geojson():
    if not PIAUI_GEOJSON.exists():
        return None
    try:
        return json.loads(PIAUI_GEOJSON.read_text(encoding="utf-8"))
    except Exception:
        return None


def render_mapa_piaui(df: pd.DataFrame):
    _render_contexto_nav("MapaPiaui")
    st.markdown("### Mapa do Piauí — Indicador por Município")

    geo = _load_piaui_geojson()
    if not geo:
        st.warning("GeoJSON do Piauí não encontrado.")
        return

    anos = sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
    indicadores = sorted(df["indicador"].dropna().unique().tolist())

    c1, c2 = st.columns([1, 2])
    with c1:
        ano = st.selectbox("Ano", anos, key="mapa_ano")
    with c2:
        indicador = st.selectbox("Indicador", indicadores, key="mapa_indicador")

    dff = df[(df["ano"] == ano) & (df["indicador"] == indicador)].copy()
    if dff.empty:
        st.info("Sem dados para o recorte selecionado.")
        return

    dff["cod6"] = dff["cod_ibge"].astype(str).str.zfill(6).str[:6]
    id_map = {}
    for f in geo.get("features", []):
        pid = str(f.get("properties", {}).get("id", "")).strip()
        if len(pid) >= 6:
            id_map[pid[:6]] = pid

    dff["geo_id"] = dff["cod6"].map(id_map)
    miss_ct = int(dff["geo_id"].isna().sum())
    dff = dff.dropna(subset=["geo_id"])
    if dff.empty:
        st.info("Não foi possível casar códigos do banco com o GeoJSON.")
        return
    if miss_ct > 0:
        st.caption(f"{miss_ct} município(s) sem geometria no GeoJSON atual.")

    agg = (
        dff.groupby(["geo_id", "municipio"], as_index=False)["valor"]
        .mean()
        .rename(columns={"valor": "valor_medio"})
    )

    if PLOTLY_OK:
        fig = px.choropleth_mapbox(
            agg,
            geojson=geo,
            locations="geo_id",
            featureidkey="properties.id",
            color="valor_medio",
            hover_name="municipio",
            hover_data={"valor_medio": ":.2f", "geo_id": False},
            color_continuous_scale="Blues",
            mapbox_style="carto-positron",
            zoom=6,
            center={"lat": -7.2, "lon": -42.8},
            opacity=0.75,
            height=560,
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Mapa interativo disponível quando Plotly estiver instalado. Exibindo tabela como fallback.")
        st.dataframe(
            agg.sort_values("valor_medio", ascending=False),
            use_container_width=True,
            hide_index=True,
            height=440,
        )


def _normalize_page_name(v: str | None) -> str | None:
    if not v:
        return None
    raw = str(v).strip().lower()
    aliases = {
        "capa":               "Capa",
        "visaogeral":         "VisaoGeral",
        "visão geral":        "VisaoGeral",
        "visao geral":        "VisaoGeral",
        "panorama":           "VisaoGeral",
        "panorama geral":     "VisaoGeral",
        "saude":              "Saude",
        "saúde":              "Saude",
        "saude e bem-estar":  "Saude",
        "saúde e bem-estar":  "Saude",
        "alimentacao":        "Alimentacao",
        "alimentação":        "Alimentacao",
        "aprendizagem":       "Aprendizagem",
        "protecao":           "Protecao",
        "proteção":           "Protecao",
        "cuidado":            "Cuidado",
        "perfil":             "Perfil",
        "perfil do município": "Perfil",
    }
    return aliases.get(raw)


def main():
    apply_app_css()

    if "page" not in st.session_state:
        st.session_state.page = "Capa"

    try:
        page_qp = st.query_params.get("page")
    except Exception:
        page_qp = None
    page_from_url = _normalize_page_name(page_qp)
    if page_from_url:
        st.session_state.page = page_from_url
        mapped_menu = MENU_FROM_PAGE.get(page_from_url)
        if mapped_menu:
            st.session_state["pagina_ativa"] = mapped_menu

    pagina = st.session_state.page

    if pagina == "Capa":
        render_capa_html_navegavel()
        return

    render_sidebar_menu()
    pagina = st.session_state.page

    engine = None
    dsn = get_dsn()
    if dsn:
        try:
            engine = get_engine(dsn)
            st.caption("Fonte de dados: Supabase (PostgreSQL)")
        except Exception as e:
            st.warning(f"Falha no Supabase, usando SQLite local: {e}")
    else:
        st.caption("Fonte de dados: SQLite oficial local")

    try:
        sqlite_token = str(SQLITE_DB.stat().st_mtime_ns) if SQLITE_DB.exists() else ""
        cache_token = sqlite_token if engine is None else (dsn or "")
        df = load_fato(engine, cache_token)
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return

    if pagina == "VisaoGeral":
        try:
            render_visao_geral(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Visão Geral: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Perfil":
        try:
            render_perfil(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Perfil: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Saude":
        try:
            render_saude(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Saúde: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Alimentacao":
        try:
            render_alimentacao(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Alimentação: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Aprendizagem":
        try:
            render_aprendizagem(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Aprendizagem: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Protecao":
        try:
            render_protecao(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Proteção: {e}")
            import traceback
            st.write(traceback.format_exc())
    elif pagina == "Cuidado":
        try:
            render_cuidado(df)
        except Exception as e:
            st.error(f"Erro ao renderizar Cuidado: {e}")
            import traceback
            st.write(traceback.format_exc())
    else:
        st.info("Selecione uma página no menu lateral.")


if __name__ == "__main__":
    main()
