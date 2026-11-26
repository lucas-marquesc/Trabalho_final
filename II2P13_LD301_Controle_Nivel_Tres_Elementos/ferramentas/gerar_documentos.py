"""Gera as folhas de dados de cada grupo e o gabarito do professor a partir de `grupos.py`.

    python ferramentas/gerar_documentos.py

Saídas:
    grupos/Grupo_X/FOLHA_DE_DADOS_GRUPO_X.md   o que o grupo recebe (dados de processo, sem respostas)
    GABARITO_PROFESSOR.md                       respostas de todos os grupos + como corrigir
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import grupos as G            # noqa: E402
import gerar_projeto as GP    # noqa: E402


def br(x, casas=2):
    """Número no formato brasileiro."""
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def requisitos_fy(g: G.Grupo) -> list[str]:
    cfg = g.fy301_config
    req = ["Tag **FY-102**; LCD mostrando a posição (PV %).",
           "Convenção do CLP para todos os grupos: **4 mA = FV-102 fechada, 20 mA = FV-102 aberta** (ação direta), "
           "qualquer que seja o atuador.",
           "Fazer o **Auto Setup** somente depois de acertar o suprimento de ar."]
    if g.usa_ep_no_fy301:
        req.append("A engenharia especificou característica **igual porcentagem**, mas o almoxarifado só tem válvulas "
                   "**lineares**: a característica igual porcentagem (R = 50) fica por conta do posicionador.")
    if cfg["tso.cutoff"]:
        req.append(f"Fechamento estanque (TSO): abaixo de **{br(cfg['tso.cutoff'], 1)} %** de sinal a válvula fecha totalmente.")
    if cfg["sp.lowLimit"]:
        req.append(f"Vazão mínima do economizador: o posicionador nunca pode levar a FV-102 abaixo de "
                   f"**{br(cfg['sp.lowLimit'], 0)} %** de abertura, mesmo que o CLP mande fechar (limite inferior do setpoint).")
    if cfg["deviation.deadband"] != 5.0 or cfg["deviation.time"] != 10.0:
        req.append(f"Alarme de desvio do posicionador: avisar quando a posição ficar mais de "
                   f"**{br(cfg['deviation.deadband'], 0)} %** longe do setpoint por mais de **{br(cfg['deviation.time'], 0)} s** "
                   f"(fábrica: 5 % / 10 s).")
    return req


def folha(g: G.Grupo) -> str:
    cond = g.condicoes_valvula()
    L = []
    a = L.append
    a(f"# II2P13 — Trabalho em grupo · Folha de dados do **GRUPO {g.nome}**")
    a("")
    a("Caldeira B-101 com controle de nível do tambor a três elementos. Estes são os dados de projeto da **sua** "
      "caldeira; os outros grupos têm outra caldeira. Use o roteiro [`README.md`](../../README.md) para a sequência "
      "do trabalho. Tudo o que você calcular aqui vai para o LasecFDT (transmissores e posicionador), para o "
      "sinótico (válvula e ar) e para o Ladder do CLP.")
    a("")
    a("> Pressões diferenciais em **mmH2O a 20 °C** (unidade dos LD301, código HART 4): 1 mmH2O = 9,789 Pa; "
      "uma coluna de *h* metros de um fluido de densidade *ρ* vale 1000·(ρ/998,2)·*h* mmH2O.")
    a("")
    a("## 1. Tambor de vapor e LT-101")
    a("")
    a("| Dado | Valor |")
    a("|---|---|")
    a(f"| Pressão no tambor | {br(g.p_tambor_abs, 1)} bar abs ({br(g.p_tambor_g, 2)} bar g) |")
    a(f"| Água saturada no tambor | ρ = {br(g.rho_agua, 1)} kg/m³ |")
    a(f"| Vapor saturado no tambor | ρ = {br(g.rho_vapor, 2)} kg/m³ |")
    a(f"| Condensado nas pernas de impulso | {g.t_pernas} °C, ρ = {br(g.rho_cond, 1)} kg/m³ |")
    a(f"| Diâmetro interno do tambor | {br(g.d_tambor, 2)} m |")
    a(f"| Distância entre as tomadas do LT-101 (0 a 100 % de nível) | {br(g.h_tomadas, 2)} m |")
    a(f"| LT-101 abaixo da tomada inferior | {br(g.desnivel_lt, 2)} m (as duas pernas cheias de condensado) |")
    a("| Ligação | HIGH na tomada **inferior** (perna variável); LOW na perna de referência, que desce do **pote de condensado** da tomada superior |")
    a("| Transmissor | SMAR LD301, sensor M2 (−5107,7 a +5107,7 mmH2O) |")
    a("")
    a("## 2. Placas de orifício (ISO 5167, tomadas de flange)")
    a("")
    a("Use $q_m = \\dfrac{C}{\\sqrt{1-\\beta^4}}\\,\\varepsilon\\,\\dfrac{\\pi}{4}d^2\\sqrt{2\\,\\rho\\,\\Delta P}$ "
      "(SI: kg/s, m, kg/m³, Pa) e considere *C* e *ε* constantes. Os transmissores de vazão saem **lineares em ΔP**; "
      "a raiz quadrada é feita **no CLP**.")
    a("")
    a("| Dado | FE-101 / FT-101 (vapor) | FE-102 / FT-102 (água de alimentação) |")
    a("|---|---|---|")
    a(f"| Fluido na placa | vapor saturado, ρ = {br(g.rho_vapor, 2)} kg/m³ | água a {g.t_agua} °C, ρ = {br(g.rho_alim, 1)} kg/m³ |")
    a(f"| Diâmetro interno do tubo *D* | {br(g.d_tubo_vapor, 1)} mm | {br(g.d_tubo_agua, 1)} mm |")
    a(f"| Diâmetro do orifício *d* | {br(g.d_orif_vapor, 1)} mm | {br(g.d_orif_agua, 1)} mm |")
    a(f"| Coeficiente de descarga *C* | {br(g.c_vapor, 3)} | {br(g.c_agua, 3)} |")
    a(f"| Fator de expansão *ε* | {br(g.eps_vapor, 3)} | 1 (líquido) |")
    a(f"| Vazão de fundo de escala (20 mA) | {br(g.qmax_ft101, 0)} t/h | {br(g.qmax_ft102, 0)} t/h |")
    a("| Corte de vazão baixa (no CLP) | abaixo de 1 % da faixa de ΔP → vazão zero | idem |")
    a("")
    a("## 3. Válvula de controle FV-102 (água de alimentação)")
    a("")
    a(f"Água a {g.t_agua} °C, ρ = {br(g.rho_alim, 1)} kg/m³ (G = ρ/1000 = {br(g.g_alim, 4)}). "
      "Pressões manométricas na entrada (*p1*) e na saída (*p2*) da válvula nas três condições de projeto "
      "(a queda na válvula muda com a vazão por causa das perdas na linha e no economizador):")
    a("")
    a("| Condição | Vazão (t/h) | p1 (bar g) | p2 (bar g) |")
    a("|---|---|---|---|")
    for nome, rot in (("min", "Mínima (35 % da MCR + purga)"), ("normal", "Normal (70 % da MCR + purga)"), ("max", "Máxima (110 % da MCR + purga)")):
        p1, p2 = g.p1_p2(cond[nome])
        a(f"| {rot} | {br(cond[nome], 2)} | {br(p1, 2)} | {br(p2, 2)} |")
    a("")
    a(f"**Característica inerente especificada pela engenharia:** {g.caracteristica}"
      + (" — mas veja a seção 4: o almoxarifado só tem válvulas **lineares**." if g.usa_ep_no_fy301 else "."))
    a("")
    a("Equações (líquido, sem correções): $K_v = Q\\,[\\text{m}^3/\\text{h}]\\sqrt{G/\\Delta P\\,[\\text{bar}]}$, "
      "$C_v = 1{,}156\\,K_v$. Abertura *x* (0 a 1) que dá $C_v$: linear $C_v = x\\,C_{v,max}$; igual porcentagem "
      "(R = 50) $C_v = C_{v,max}\\,(R^x - 1)/(R - 1)$.")
    a("")
    a("**Critério de seleção:** abertura entre **20 % e 85 %** nas três condições; entre as que atendem, a de "
      "**menor Cv** (menor custo e melhor resolução).")
    a("")
    a("Catálogo do almoxarifado (dados didáticos):")
    a("")
    a("| Opção | Diâmetro | Característica | Cv a 100 % | Almoxarifado |")
    a("|---|---|---|---|---|")
    for op, (dn, car, cv) in G.CATALOGO.items():
        estoque = "**em falta**" if g.usa_ep_no_fy301 and car != g.caracteristica_corpo else "disponível"
        a(f"| {op} | {dn} | {car} | {br(cv, 0)} | {estoque} |")
    a("")
    a("A válvula **instalada** se escolhe no sinótico (quadro verde *Campo: válvula e ar*, \"FV-102: opção do "
      "catálogo\") ou nas Propriedades exportadas da planta.")
    a("")
    a("## 4. Atuador e posicionador FY-102 (SMAR FY301)")
    a("")
    a("| Dado | Valor |")
    a("|---|---|")
    falha = "falha **fechada**" if g.ar_para == "abrir" else "falha **aberta**"
    a(f"| Atuador | diafragma e mola, **ar para {g.ar_para}** ({falha}) |")
    a(f"| Faixa da mola (bench set) | {br(g.mola[0], 1)} a {br(g.mola[1], 1)} bar |")
    a(f"| Curso da válvula | {br(g.curso, 0)} mm |")
    a("| Suprimento de ar | filtro-regulador ajustável (quadro verde do sinótico); regra: **≥ fim da faixa da mola + 0,4 bar** e ≤ 6 bar |")
    a("")
    a("Requisitos de configuração do FY-102:")
    a("")
    for r in requisitos_fy(g):
        a(f"- {r}")
    a("")
    a("## 5. Sintonia recomendada (IHM do sinótico)")
    a("")
    s = g.sintonia
    a("| SP_NIVEL | KP_LIC | TI_LIC | K_FF | KP_FIC | TI_FIC |")
    a("|---|---|---|---|---|---|")
    a(f"| {br(s['SP_NIVEL'], 0)} % | {br(s['KP_LIC'], 2)} (t/h)/% | {br(s['TI_LIC'], 0)} s | {br(s['K_FF'], 2)} | "
      f"{br(s['KP_FIC'], 2)} %/(t/h) | {br(s['TI_FIC'], 1)} s |")
    a("")
    a("## 6. Portas HART deste PC")
    a("")
    a("| Instrumento | Modem no esquemático | Porta no LasecFDT |")
    a("|---|---|---|")
    for tag, (cnc, com) in GP.PORTAS.items():
        a(f"| {tag} | {cnc} | {com} |")
    a("")
    return "\n".join(L)


def gabarito() -> str:
    L = []
    a = L.append
    a("# II2P13 — Gabarito do professor (NÃO distribuir)")
    a("")
    a("Respostas calculadas por `ferramentas/grupos.py` (fonte única dos números). Projetos comissionados em "
      "`gabarito/Grupo_X/` (abrem em AUTOMÁTICO, com o Ladder completo do grupo).")
    a("")
    a("## Como corrigir")
    a("")
    a("Tudo o que o grupo faz fica salvo em dois arquivos da pasta `Grupo_X` que ele entrega:")
    a("")
    a("- `II2P13_Grupo_X.lsproj`: configuração HART dos três LD301 e do FY301 (o LasecSimul copia a configuração "
      "dos dispositivos para o projeto ao **parar a simulação** e ao **salvar**), a calibração do Auto Setup, a "
      "válvula instalada e o suprimento de ar (quadro verde do sinótico) e os ajustes da IHM;")
    a("- `clp/CLP_Grupo_X.lsplc`: o programa do CLP (MAIN em Ladder).")
    a("")
    a("```text")
    a("python ferramentas/corrigir_trabalho.py <pasta Grupo_X entregue> --grupo X [--dinamico] [--relatorio nota.md]")
    a("```")
    a("")
    a("O avaliador confere cada item contra este gabarito, **compila o Ladder como o LasecSimul e o executa no CLP "
      "do Core com vetores de teste** (correntes conhecidas → nível, vazões, falhas, saída) e, com `--dinamico`, "
      "roda o projeto inteiro (sem o VS Code) em automático com um degrau de +20 % de carga. Precisa do LasecSimul "
      "≥ 0.0.111 instalado (ou do repositório) e do Node. A memória de cálculo (Kv/Cv, K das placas, LRV/URV) e as "
      "respostas das perguntas vêm no relatório do grupo.")
    a("")
    a("`ferramentas/rodar_projeto.cjs` roda qualquer `.lsproj` da prática sem interface e grava as variáveis "
      "pedidas (planta, FY301, CLP) — útil para conferir uma entrega que \"não funciona\".")
    a("")
    a("## Ladder do gabarito")
    a("")
    a("Um bloco por degrau. Exemplo (grupo D), etapa 4 da placa FE-101: ΔP = (I − 4)·URV/16; depois o corte de vazão "
      "baixa (LT contra 1 % do URV, bobina CORTE_FT101) e a raiz quadrada só sem corte (contato NF de CORTE_FT101 no EN do "
      "SQRT), seguida do MUL pelo K da placa; com corte, um MOVE 0.0 zera a vazão.")
    a("")
    a("![Etapa 4: dP pela faixa](assets/gab_ladder_placa_a.png)")
    a("")
    a("![Etapa 4: corte e raiz](assets/gab_ladder_placa_b.png)")
    a("")
    for g in G.GRUPOS.values():
        cond = g.condicoes_valvula()
        cfg = g.fy301_config
        ini = GP.estado_inicial(g, True)
        enc = GP.ld301_encontrado(g)
        a(f"## Grupo {g.nome}")
        a("")
        a("### Transmissores (como deixado)")
        a("")
        a("| Tag | LRV (mmH2O) | URV (mmH2O) | Função | Observação |")
        a("|---|---|---|---|---|")
        a(f"| LT-101 | {br(g.lt101_lrv, 1)} | {br(g.lt101_urv, 1)} | linear | SG água {br(g.sg_agua, 4)}, vapor {br(g.sg_vapor, 4)}, "
          f"condensado {br(g.sg_cond, 4)}; LRV = 1000·H·(SGv − SGc), URV = 1000·H·(SGa − SGc); o desnível de "
          f"{br(g.desnivel_lt, 2)} m se cancela |")
        a(f"| FT-101 | 0 | {br(g.ft101_urv, 1)} | linear | β = {br(g.beta_vapor, 4)}, K = {br(g.k_ft101, 5)} (t/h)/√mmH2O; "
          f"{br(g.qmax_ft101, 0)} t/h → URV = (Q/K)² |")
        a(f"| FT-102 | 0 | {br(g.ft102_urv, 1)} | linear | β = {br(g.beta_agua, 4)}, K = {br(g.k_ft102, 5)} (t/h)/√mmH2O; "
          f"{br(g.qmax_ft102, 0)} t/h |")
        a("")
        a("Como encontrado (o que o grupo tem de perceber):")
        a("")
        for tag, c in enc.items():
            obs = []
            if c.get("polling", 0):
                obs.append(f"endereço de polling {c['polling']} (multidrop: corrente presa em 4 mA)")
            if c.get("funcao"):
                obs.append("função **raiz quadrada** no transmissor (raiz duplicada com a do CLP)")
            if c.get("unidade_usuario"):
                obs.append("unidade do usuário ligada (m3/h) de outro serviço")
            obs.append(f"tag {c['tag']}, faixa {br(c['lrv'], 0)}–{br(c['urv'], 0)}, amortecimento {br(c['damping'], 1)} s")
            a(f"- **{tag}**: " + "; ".join(obs))
        a("")
        a("### Válvula FV-102")
        a("")
        a("| Condição | t/h | m³/h | p1 − p2 (bar) | Kv | Cv |")
        a("|---|---|---|---|---|---|")
        for nome in ("min", "normal", "max"):
            q = cond[nome]
            p1, p2 = g.p1_p2(q)
            a(f"| {nome} | {br(q, 2)} | {br(g.m3h(q), 2)} | {br(p1 - p2, 2)} | {br(g.kv_requerido(q), 2)} | {br(g.cv_requerido(q), 2)} |")
        a("")
        a(f"Característica do corpo: **{g.caracteristica_corpo}**"
          + (" (a igual porcentagem fica no FY301, curva EP 1:50)" if g.usa_ep_no_fy301 else "") + ".")
        a("")
        a("| Opção | Cv | Abertura mín | normal | máx | Atende 20–85 %? |")
        a("|---|---|---|---|---|---|")
        for op, (dn, car, cv) in G.CATALOGO.items():
            if car != g.caracteristica_corpo:
                continue
            ab = g.aberturas(op)
            ok = op in g.opcoes_validas
            fmt = lambda v: "—" if v == float("inf") else f"{br(v, 1)} %"   # noqa: E731
            a(f"| {op} ({dn}) | {br(cv, 0)} | {fmt(ab['min'])} | {fmt(ab['normal'])} | {fmt(ab['max'])} | "
              f"{'**sim — escolhida**' if op == g.valvula else ('sim (maior)' if ok else 'não')} |")
        a("")
        a(f"Na condição inicial ({br(g.q_agua_inicial, 2)} t/h) a válvula escolhida fica a **{br(ini['abertura'], 1)} %** "
          f"({br(ini['stem'], 2)} mm na régua da haste); sinal do CLP {br(ini['mv'], 1)} % = {br(4 + 0.16 * ini['mv'], 2)} mA. "
          f"Válvula como encontrada: opção {GP.VALVULA_ENCONTRADA[g.nome]}.")
        a("")
        a("### Posicionador FY-102")
        a("")
        nomes_curva = {0: "Linear", 1: "EP 1:50"}
        a(f"- Atuador ar para {g.ar_para}: **AIR_T = {'Open' if cfg['airTo'] == 0 else 'Close'}**, ação **direta** "
          f"(Direct). Com o AIR_T de fábrica (Open) num atuador ar-para-fechar a realimentação do servo fica positiva e a "
          f"válvula vai a um extremo." if g.ar_para == "fechar" else
          f"- Atuador ar para abrir: AIR_T = **Open** (fábrica), ação **direta**.")
        a(f"- Curva **{nomes_curva[cfg['flowChar']]}**; TSO {br(cfg['tso.cutoff'], 1)} %; limites do setpoint "
          f"{br(cfg['sp.lowLimit'], 0)}–{br(cfg['sp.highLimit'], 0)} %; alarme de desvio {br(cfg['deviation.deadband'], 0)} % / "
          f"{br(cfg['deviation.time'], 0)} s (DTM: Configuration › Advanced Config.).")
        a(f"- Suprimento: encontrado {br(g.suprimento_encontrado, 1)} bar; mínimo {br(g.suprimento_minimo, 1)} bar "
          f"(mola até {br(g.mola[1], 1)} bar + 0,4)"
          + (" → **precisa subir antes do Auto Setup** (senão o Auto Setup grava um curso menor)." if g.suprimento_encontrado < g.suprimento_minimo else " → ok."))
        a(f"- Auto Setup: curso calibrado {br(g.curso, 0)} mm (antes dele o FY301 usa a escala de fábrica de 30 mm).")
        a("")
        a("### CLP (constantes do Ladder)")
        a("")
        a(f"NIVEL = (I − 4)·6,25; ΔP_FT101 = (I − 4)·{br(g.ft101_urv / 16, 4)}; VAZAO_VAPOR = {br(g.k_ft101, 5)}·√ΔP "
          f"(corte < {br(0.01 * g.ft101_urv, 2)} mmH2O); ΔP_FT102 = (I − 4)·{br(g.ft102_urv / 16, 4)}; "
          f"VAZAO_AGUA = {br(g.k_ft102, 5)}·√ΔP (corte < {br(0.01 * g.ft102_urv, 2)} mmH2O); QMAX_AGUA = {br(g.qmax_ft102, 0)}.")
        a("")
        a("Correntes esperadas na condição inicial (nível 50 %, demanda "
          f"{br(g.demanda_inicial, 0)} %): LT-101 12,00 mA; FT-101 "
          f"{br(4 + 16 * (g.q_vapor_inicial / g.k_ft101) ** 2 / g.ft101_urv, 2)} mA; FT-102 "
          f"{br(4 + 16 * (g.q_agua_inicial / g.k_ft102) ** 2 / g.ft102_urv, 2)} mA.")
        a("")
    return "\n".join(L)


def gravar(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto.rstrip() + "\n")
    print("gravado", os.path.relpath(caminho, RAIZ))


if __name__ == "__main__":
    for g in G.GRUPOS.values():
        gravar(os.path.join(RAIZ, "grupos", f"Grupo_{g.nome}", f"FOLHA_DE_DADOS_GRUPO_{g.nome}.md"), folha(g))
    gravar(os.path.join(RAIZ, "GABARITO_PROFESSOR.md"), gabarito())
