# Ferramentas do trabalho II2P13 (professor)

Python 3 (só `hart_mestre.py` usa `pyserial`) e Node 18+. Os scripts `.cjs` usam os módulos da extensão
LasecSimul (≥ 0.0.111): o repositório `C:\SourceCode\LasecSimul` se existir, senão a extensão instalada mais
nova (`LASECSIMUL_EXT` escolhe outra).

| Arquivo | Para quê |
|---|---|
| `grupos.py` | **dados dos 4 grupos** e todas as respostas (LRV/URV, K das placas, Cv, válvula, FY301). Fonte única dos números |
| `programas_clp.py` | POUs do CLP: `PI_AW` e `CONTROLE_3E` (ST, fornecidos) e o `MAIN` em Ladder (modelo do aluno e gabarito por grupo) |
| `ladder.py` | gerador de Ladder no formato do editor OpenPLC do LasecSimul (degraus, contatos, bobinas, paralelos, blocos) |
| `gerar_projeto.py` | gera `grupos/Grupo_X/` (aluno, como encontrado) e `gabarito/Grupo_X/` (comissionado, AUTO) |
| `gerar_documentos.py` | gera as folhas de dados dos grupos e o `GABARITO_PROFESSOR.md` |
| `corrigir_trabalho.py` | **avaliador**: lê o `.lsproj` e o `.lsplc` entregues, roda o Ladder no CLP do Core com vetores de teste e (com `--dinamico`) o projeto inteiro em automático |
| `testar_clp.cjs` | compila um `.lsplc` como o LasecSimul e executa no CLP do Core com entradas forçadas (usado pelo avaliador) |
| `rodar_projeto.cjs` | roda um `.lsproj` no Core sem o VS Code, com eventos programados, e grava as variáveis pedidas |
| `hart_mestre.py` | mestre HART pela COM (LD301 e FY301): varrer, ler, endereço, faixa, tag, função, AIR_T, curva, TSO/TIME, Auto Setup |
| `capturar_telas.cjs` | capturas de tela do LasecSimul num VS Code de teste (Playwright) |

## Refazer tudo

```text
python ferramentas/grupos.py              # confere os números de cada grupo
python ferramentas/gerar_projeto.py       # projetos dos alunos e gabaritos
python ferramentas/gerar_documentos.py    # folhas de dados e gabarito do professor
python ferramentas/corrigir_trabalho.py gabarito/Grupo_A --grupo A --dinamico   # deve dar 100 %
```

Distribua só `grupos/Grupo_X/` (e o `README.md` da prática) para cada grupo. **A pasta `gabarito/` e o
`GABARITO_PROFESSOR.md` não vão para os alunos.**

## Correção

```text
python ferramentas/corrigir_trabalho.py <pasta entregue pelo grupo> --grupo X --dinamico --relatorio nota_X.md
```

Rode uma correção por vez: duas compilações do mesmo programa ao mesmo tempo disputam o mesmo cache do CLP.

## Teste por HART sem o LasecFDT

Com a simulação rodando, o `hart_mestre.py` fala com o instrumento pela outra ponta do par com0com do modem
(COM20–COM23). No simulador em tempo real o HART é mais lento que o real; o script espera até 8 s por resposta.
