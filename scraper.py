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
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
# Filtro de "lixo de menu": títulos genéricos que aparecem repetidos
# em várias páginas desses portais (links de navegação, não notícias).
# Comparação por texto exato, sem acento e minúsculo.
# ------------------------------------------------------------------
def _normalizar(texto: str) -> str:
    import unicodedata
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto

TITULOS_GENERICOS = {
    "portal da nfe", "portal da nfce", "portal do cte", "portal do mdfe",
    "nfe", "nfce", "cte", "mdfe",
    "visualizador de schema", "conformidade facil - nfe/nfce",
    "consultar ct-e", "consultar nf-e", "conheca o ct-e", "conheca a nf-e",
    "atos tecnicos rfb/cgibs", "atos rfb/cgibs",
    "moc mdfe 3.00b visao geral", "agenda e eventos",
    "cgibs - comite gestor do ibs",
}

# Palavras que, se aparecerem no título, descartam o item mesmo que bata
# alguma keyword (ruído institucional sem relevância fiscal real).
PALAVRAS_DESCARTE = ["instagram", "facebook", "youtube", "podcast"]


def eh_lixo(titulo: str, link: str) -> bool:
    titulo_norm = _normalizar(titulo)
    if titulo_norm in TITULOS_GENERICOS:
        return True
    if titulo.strip().startswith("http"):  # título é a própria URL
        return True
    if "safelinks.protection.outlook.com" in link:
        return True
    if any(p in titulo_norm for p in PALAVRAS_DESCARTE):
        return True
    return False

# ------------------------------------------------------------------
# As 20 fontes oficiais. Cada uma: (jurisdição, nome, url, usa_keywords_ms, verificar_ssl)
# ------------------------------------------------------------------
FONTES = [
    # --- Receita Federal e reforma tributária ---
    ("federal", "Notícias da Receita Federal", "https://www.gov.br/receitafederal/pt-br/assuntos/noticias", False, True),
    ("federal", "Programa da Reforma Tributária do Consumo", "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/reforma-tributaria", False, True),
    ("federal", "Comitê Gestor do IBS", "https://www.cgibs.gov.br/", False, True),
    ("federal", "CGIBS - Atos Conjuntos", "https://www.cgibs.gov.br/atos-conjuntos", False, True),
    ("federal", "CGIBS - Regulamentos", "https://www.cgibs.gov.br/regulamentos", False, True),
    ("federal", "CGIBS - Portarias", "https://www.cgibs.gov.br/portarias", False, True),
    ("federal", "Portal de Serviços do CGIBS", "https://www.servicos.cgibs.gov.br/", False, True),
    ("federal", "Legislação do CONFAZ", "https://www.confaz.fazenda.gov.br/legislacao", False, True),
    ("federal", "Diário Oficial da União", "https://www.in.gov.br/", False, True),

    # --- Mato Grosso do Sul (usa palavras-chave extras) ---
    ("ms", "Legislação da SEFAZ-MS", "https://arq.sefaz.ms.gov.br/inicio/legislacao.asp", True, False),
    ("ms", "Diário Oficial Eletrônico de MS", "https://www.spdo.ms.gov.br/", True, True),
    ("ms", "Indicadores da SEFAZ-MS", "https://www.sefaz.ms.gov.br/indicadores/", True, True),
    ("ms", "Consulta de valores da SEFAZ-MS", "https://consultavalorsefaz.ms.gov.br/busca", True, True),

    # --- Documentos fiscais eletrônicos ---
    ("federal", "Portal Nacional da NF-e", "https://www.nfe.fazenda.gov.br/portal/principal.aspx", False, True),
    ("federal", "Informes da NF-e", "https://www.nfe.fazenda.gov.br/portal/informes.aspx", False, True),
    ("federal", "Avisos oficiais da NF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Nfe/Avisos", False, True),
    ("federal", "Portal Nacional do CT-e", "https://www.cte.fazenda.gov.br/portal/", False, True),
    ("federal", "Avisos oficiais do CT-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Cte/Avisos", False, True),
    ("federal", "Portal oficial do MDF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Mdfe", False, True),
    ("federal", "Avisos oficiais do MDF-e (SVRS)", "https://dfe-portal.svrs.rs.gov.br/Mdfe/Avisos", False, True),
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
def fetch_fonte(jur: str, nome: str, url: str, usar_keywords_ms: bool, verificar_ssl: bool = True):
    itens = []
    keywords = KEYWORDS_MS if usar_keywords_ms else KEYWORDS
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, verify=verificar_ssl)
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
                if eh_lixo(texto, full_link):
                    continue
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
    for jur, nome, url, usar_ms, verificar_ssl in FONTES:
        novos.extend(fetch_fonte(jur, nome, url, usar_ms, verificar_ssl))

    adicionados = 0
    titulos_nesta_execucao = set()
    for item in novos:
        titulo_norm = _normalizar(item["titulo"])
        chave = item["link"] or item["titulo"]
        # Evita repetir o mesmo aviso (mesmo título) vindo de vários
        # portais espelhados (NFe/CTe/MDFe compartilham os mesmos avisos).
        if titulo_norm in titulos_nesta_execucao:
            continue
        if chave in seen:
            continue
        seen.add(chave)
        titulos_nesta_execucao.add(titulo_norm)
        dados.insert(0, item)
        adicionados += 1

    dados = dados[:300]  # mantém só as 300 entradas mais recentes

    save_json(DATA_FILE, dados)
    save_json(SEEN_FILE, list(seen))
    save_json(META_FILE, {"ultima_execucao": datetime.now(timezone.utc).isoformat()})

    print(f"Concluído: {adicionados} nova(s) entrada(s) adicionada(s). Total no painel: {len(dados)}.")


if __name__ == "__main__":
    main()
