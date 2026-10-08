"""
Painel Fiscal - Scraper
Busca novidades nas fontes oficiais listadas abaixo, filtra por
palavras-chave de interesse e salva em data.json.

Roda de graça via GitHub Actions (veja .github/workflows/atualizar.yml).
Também pode ser rodado manualmente: python scraper.py
"""

import json
import unicodedata
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

HEADERS = {"User-Agent": "Mozilla/5.0"}

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

KEYWORDS_MS = KEYWORDS + [
    "gado", "carne", "couro", "miúdos", "miudos",
    "proape", "precoce", "fundersul", "fadefe", "pauta fiscal", "vrp", "pmpf",
    "decreto", "resolução", "resolucao", "portaria", "ricms",
]


def _normalizar(texto: str) -> str:
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

PALAVRAS_DESCARTE = ["instagram", "facebook", "youtube", "podcast"]


def eh_lixo(titulo: str, link: str) -> bool:
    titulo_norm = _normalizar(titulo)
    if titulo_norm in TITULOS_GENERICOS:
        return True
    if titulo.strip().startswith("http"):
        return True
    if "safelinks.protection.outlook.com" in link:
        return True
    if any(p in titulo_norm for p in PALAVRAS_DESCARTE):
        return True
    return False


# (jurisdição, nome, url, usa_keywords_ms, verificar_ssl)
FONTES = [
    ("federal", "Notícias da Receita Federal", "https://www.gov.br/receitafederal/pt-br/assuntos/noticias", False, True),
    ("federal", "Programa da Reforma Tributária do Consumo", "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/reforma-tributaria", False, True),
    ("federal", "Comitê Gestor do IBS", "https://www.cgibs.gov.br/", False, True),
    ("federal", "CGIBS - Atos Conjuntos", "https://www.cgibs.gov.br/atos-conjuntos", False, True),
    ("federal", "CGIBS - Regulamentos", "https://www.cgibs.gov.br/regulamentos", False, True),
    ("federal", "CGIBS - Portarias", "https://www.cgibs.gov.br/portarias", False, True),
    ("federal", "Portal de Serviços do CGIBS", "https://www.servicos.cgibs.gov.br/", False, True),
    ("federal", "Legislação do CONFAZ", "https://www.confaz.fazenda.gov.br/legislacao", False, True),
    ("federal", "Diário Oficial da União", "https://www.in.gov.br/", False, True),

    ("ms", "Legislação da SEFAZ-MS", "https://arq.sefaz.ms.gov.br/inicio/legislacao.asp", True, False),
    ("ms", "Diário Oficial Eletrônico de MS", "https://www.spdo.ms.gov.br/", True, True),
    ("ms", "Indicadores da SEFAZ-MS", "https://www.sefaz.ms.gov.br/indicadores/", True, True),
    ("ms", "Consulta de valores da SEFAZ-MS", "https://consultavalorsefaz.ms.gov.br/busca", True, True),

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


def fetch_fonte(jur, nome, url, usar_keywords_ms, verificar_ssl=True):
    itens = []
    keywords = KEYWORDS_MS if usar_keywords_ms else KEYWORDS

    resp = None
    ultimo_erro = None
    for _ in range(2):  # duas tentativas, timeout maior
        try:
            resp = requests.get(url, timeout=30, headers=HEADERS, verify=verificar_ssl)
            resp.raise_for_status()
            break
        except Exception as e:
            ultimo_erro = e
            resp = None
    if resp is None:
        print(f"[aviso] Falha ao acessar {nome} ({url}): {ultimo_erro}")
        return itens

    soup = BeautifulSoup(resp.text, "html.parser")
    titulo_pagina = soup.title.get_text(strip=True) if soup.title else ""
    links = soup.select("a")
    textos = []
    for link_tag in links:
        texto = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        if not texto:
            continue
        textos.append(texto)
        if matches_keywords(texto, keywords):
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

    print(f"[info] {nome}: página com {len(resp.text)} caracteres, título '{titulo_pagina}', "
          f"{len(links)} links, {len(itens)} combinaram com as palavras-chave")
    if not itens:
        print(f"[info]    amostra dos links encontrados: {textos[:12]}")
    return itens


def main():
    seen = set(load_json(SEEN_FILE, []))
    dados = load_json(DATA_FILE, [])

    novos = []
    for jur, nome, url, usar_ms, verificar_ssl in FONTES:
        novos.extend(fetch_fonte(jur, nome, url, usar_ms, verificar_ssl))

    # Evita repetir o mesmo aviso (mesmo título) já existente no painel,
    # mesmo que venha de outro portal ou em outro dia.
    titulos_existentes = {_normalizar(d.get("titulo", "")) for d in dados}

    adicionados = 0
    for item in novos:
        titulo_norm = _normalizar(item["titulo"])
        chave = item["link"] or item["titulo"]
        if titulo_norm in titulos_existentes or chave in seen:
            continue
        seen.add(chave)
        titulos_existentes.add(titulo_norm)
        dados.insert(0, item)
        adicionados += 1

    dados = dados[:300]

    save_json(DATA_FILE, dados)
    save_json(SEEN_FILE, list(seen))
    save_json(META_FILE, {"ultima_execucao": datetime.now(timezone.utc).isoformat()})

    print(f"Concluído: {adicionados} nova(s) entrada(s) adicionada(s). Total no painel: {len(dados)}.")


if __name__ == "__main__":
    main()
