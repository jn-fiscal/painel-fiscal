# Painel Fiscal — versão independente (sem Claude)

Sistema que roda sozinho, de graça, sem depender do Claude no dia a dia:

- `scraper.py` — busca novidades em fontes oficiais e salva em `data.json`:
  - RSS do gov.br (Finanças/Impostos e Agricultura/Pecuária) — **confiável, testado**
  - CONFAZ, SEFAZ-MS, Portal Nacional da NF-e, Portal do MDF-e — **melhor esforço** (ver "Manutenção esperada" abaixo)
- `.github/workflows/atualizar.yml` — roda o scraper automaticamente todo dia, na nuvem do GitHub (gratuito)
- `index.html` — site que exibe o conteúdo de `data.json`, com filtro por Federal/MS e busca por palavra-chave

## Passo a passo para publicar (uma vez só)

1. Crie uma conta gratuita no GitHub (já feito).
2. Crie um repositório novo (já feito: `painel-fiscal`).
3. Envie estes arquivos para o repositório — em "Code" → "enviando um arquivo existente" (ou "Add file" → "Upload files"), arraste todos os arquivos desta pasta, **incluindo a subpasta `.github/workflows`** (pode estar oculta no seu sistema — ative "mostrar itens ocultos" se precisar).
4. Ative o GitHub Pages:
   - "Settings" → "Pages"
   - Em "Source", escolha "Deploy from a branch"
   - Branch: `main`, pasta: `/ (root)`
   - Salve. Em alguns minutos, o GitHub mostra o link do seu site.
5. Confira a tarefa agendada:
   - Aba "Actions" do repositório → workflow "Atualizar Painel Fiscal" → "Run workflow" para testar agora.
6. Pronto. Todo dia às 8:30 (horário de MS), roda sozinho.

## Manutenção esperada

Sites de governo mudam de estrutura de vez em quando. As fontes marcadas como "melhor esforço" (CONFAZ, SEFAZ-MS, Portal da NF-e, Portal do MDF-e) usam uma busca genérica por links na página — se um dia pararem de trazer resultados, é sinal de que a estrutura da página mudou. Abra `scraper.py`, localize a função correspondente e ajuste. Isso é normal em qualquer scraper.

## Ajustando os temas monitorados

Edite a lista `KEYWORDS` no início de `scraper.py`.
