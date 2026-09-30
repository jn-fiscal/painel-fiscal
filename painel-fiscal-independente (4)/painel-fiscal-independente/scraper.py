"""
Painel Fiscal - Scraper
Busca novidades exclusivamente nas fontes oficiais listadas abaixo,
filtra por palavras-chave de interesse e salva em data.json.

Roda de graça via GitHub Actions (veja .github/workflows/atualizar.yml).
Também pode ser rodado manualmente: python scraper.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
SEEN_FILE = BASE_DIR / "seen_urls.json"
META_FILE = BASE_DIR / "meta.json"

# ------------------------------------------------------------------
# Palavras-chave gerais (aplicadas a todas as fontes)
# ------------------------------------------------------------------
KEYWORDS = [
    "ibs", "cbs", "reforma tributária", "reforma tributaria",
    "icms", "mdf-e", "mdfe", "manifesto eletrônico", "manifesto eletronico",
    "cte", "ct-e", "conhecimento de transporte",
    "transportador autônomo", "transportador autonomo", "tac",
    "funrural", "senar",
    "nf-e", "nfe", "nfc-e", "nfce", "nota fiscal eletrônica", "nota fiscal eletronica",
    "nota técnica", "nota tecnica", "schema", "leiaute", "evento", "contingência", "contingencia",
    "homologação", "homologacao", "produção", "producao",
    "split payment", "frigorífico", "frigorifico",
    "agropecuária", "agropecuaria", "carne bovina", "abate",
    "produtor rural", "cnpj rural",
]

# Palavras-chave extras só para as fontes estaduais de MS (mais específicas)
KEYWORDS_MS = KEYWORDS + [
    "gado", "carne", "couro", "miúdos", "miudos",
    "proape", "precoce", "fundersul", "fadefe", "pauta fiscal", "vrp", "pmpf",
]

# ------------------------------------------------------------------
# As 20 fontes oficiais. Cada uma: (jurisdição, nome, url, usa_keywords_ms)
# ------------------------------------------------------------------
FONTES = [
    # --- Receita Federal e reforma tributária ---
    ("federal", "Notícias da Receita Federal", "https://www.gov.br/receitafederal/pt-br/assuntos/noticias", False),
    ("federal", "Programa da Reforma Tributária do Consumo", "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/reforma-tributaria", False),
    ("federal", "Comitê Gestor do IBS", "https://www.cgibs.gov.br/", False),
    ("federal", "CGIBS - Atos Conjuntos", "https://www.cgibs.gov.br/atos-conjuntos", False),
    ("federal", "CGIBS - Regulamentos", "https://www.cgibs.gov.br/regulamentos", False),
    ("federal", "CGIBS - Portarias", "https://www.cgibs.gov.br/portarias", False),
    ("federal", "Portal de Serviços do CGIBS", "https://www.servicos.cgibs.gov.br/", False),
    ("federal", "Legislação do CONFAZ", "https://www.confaz.fazenda.gov.br/legislacao", False),
    ("federal", "Diário Oficial da União", "https://www.in.gov.br/", False),

    # --- Mato Grosso do Sul (usa palavras-chave extras) ---
    ("ms", "Legislação da SEFAZ-MS", "https://arq.sefaz.ms.gov.br/inicio/legislacao.asp", True),
    ("ms", "Diário Oficial Eletrônico de MS", "https://www.spdo.ms.gov.br/", True),
    ("ms", "Indicadores da SEFAZ-MS", "https://www.sefaz.ms.gov.br/indicadores/", True),
    ("ms", "Consulta de valores da SEFAZ-MS", "https://consultavalorsefaz.ms.gov.br/busca", True),

    # --- Documentos fiscais eletrônicos ---
    ("federal", "Portal Nacional da NF-e", "https://www.nfe.fazenda.gov.br/portal/principal.aspx", False),
    ("federal", "Informes da NF-e", "https://www.nfe.fazenda.gov.br/portal/informes.aspx", False),
    ("federal", "Avisos oficiais da NF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Nfe/Avisos", False),
    ("federal", "Portal Nacional do CT-e", "https://www.cte.fazenda.gov.br/portal/", False),
    ("federal", "Avisos oficiais do CT-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Cte/Avisos", False),
    ("federal", "Portal oficial do MDF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Mdfe", False),
    ("federal", "Avisos oficiais do MDF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Mdfe/Avisos", False),
]


def matches_keywords(text: str, keywords) -> bool:
    text_low = text.lower()
    return any(k in text_low for k in keywords)


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------
# Busca genérica: baixa a página e filtra links cujo texto bate com
# as palavras-chave. Sites institucionais mudam de estrutura com o
# tempo — se uma fonte parar de trazer resultados, inspecione o HTML
# atual da página e ajuste esta função ou adicione um caso especial.
# ------------------------------------------------------------------
def fetch_fonte(jur: str, nome: str, url: str, usar_keywords_ms: bool):
    itens = []
    keywords = KEYWORDS_MS if usar_keywords_ms else KEYWORDS
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link_tag in soup.select("a"):
            texto = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            if texto and matches_keywords(texto, keywords):
                if href.startswith("http"):
                    full_link = href
                else:
                    base = url.rsplit("/", 1)[0] if "/" in url.rsplit("://", 1)[-1] else url
                    full_link = f"{base.rstrip('/')}/{href.lstrip('/')}"
                itens.append({
                    "jur": jur,
                    "titulo": texto,
                    "resumo": "",
                    "fonte": nome,
                    "link": full_link,
                    "data": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
                })
    except Exception as e:
        print(f"[aviso] Falha ao acessar {nome} ({url}): {e}")
    return itens


def main():
    seen = set(load_json(SEEN_FILE, []))
    dados = load_json(DATA_FILE, [])

    novos = []
    for jur, nome, url, usar_ms in FONTES:
        novos.extend(fetch_fonte(jur, nome, url, usar_ms))

    adicionados = 0
    for item in novos:
        chave = item["link"] or item["titulo"]
        if chave in seen:
            continue
        seen.add(chave)
        dados.insert(0, item)
        adicionados += 1

    dados = dados[:300]  # mantém só as 300 entradas mais recentes

    save_json(DATA_FILE, dados)
    save_json(SEEN_FILE, list(seen))
    save_json(META_FILE, {"ultima_execucao": datetime.now(timezone.utc).isoformat()})

    print(f"Concluído: {adicionados} nova(s) entrada(s) adicionada(s). Total no painel: {len(dados)}.")


if __name__ == "__main__":
    main()
