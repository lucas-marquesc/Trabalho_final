"""POUs do CLP do trabalho II2P13 (OpenPLC dentro do LasecSimul).

- PI_AW        (ST, fornecido)  PI com anti-windup e transferência manual/automático sem salto.
- CONTROLE_3E  (ST, fornecido)  malha a três elementos: mestre LIC-101 + feedforward + escravo FIC-102.
- MAIN         (LD)             programa principal em Ladder. O ALUNO escreve as etapas 1 a 4
                                (corrente, validação NAMUR NE 43, nível e as DUAS placas de orifício);
                                o modelo já traz a chamada do CONTROLE_3E e a saída analógica.

A interface do MAIN (VAR_INPUT/VAR_OUTPUT) é a MESMA no modelo do aluno e no gabarito: é ela que cria
os pinos do bloco "PLC IEC 61131-3" no esquemático, já ligados ao painel.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ladder import Bloco, Bobina, Contato, Paralelo, Rung, declaracao_editor, pou_ld   # noqa: E402

TS_TASK = 0.1   # s, TASK de 100 ms

# Ordem dos pinos do bloco CLP (= ordem das variáveis do MAIN)
IO = [
    ("AI_LT101", "input", "REAL", "AI-01: tensao no shunt de 250 ohm (1 a 5 V) - LT-101 nivel do tambor"),
    ("AI_FT101", "input", "REAL", "AI-02: tensao no shunt de 250 ohm (1 a 5 V) - FT-101 vazao de vapor"),
    ("AI_FT102", "input", "REAL", "AI-03: tensao no shunt de 250 ohm (1 a 5 V) - FT-102 vazao de agua"),
    ("SP_NIVEL", "input", "REAL", "IHM: setpoint de nivel do LIC-101 (%)"),
    ("KP_LIC", "input", "REAL", "IHM: ganho do mestre LIC-101 ((t/h) por %)"),
    ("TI_LIC", "input", "REAL", "IHM: tempo integral do mestre (s)"),
    ("K_FF", "input", "REAL", "IHM: razao do feedforward (t/h de agua por t/h de vapor)"),
    ("KP_FIC", "input", "REAL", "IHM: ganho do escravo FIC-102 (% por t/h)"),
    ("TI_FIC", "input", "REAL", "IHM: tempo integral do escravo (s)"),
    ("MODO_AUTO", "input", "BOOL", "IHM: FALSE = manual, TRUE = automatico (tres elementos)"),
    ("MV_MANUAL", "input", "REAL", "IHM: sinal para a FV-102 em manual (%)"),
    ("AO_FV102", "output", "REAL", "AO-01: corrente para o FY-102 em mA (4 mA = fechada, 20 mA = aberta)"),
]

PI_AW = """FUNCTION_BLOCK PI_AW
  VAR_INPUT
    AUTO : BOOL;      (* TRUE = automatico; FALSE = manual (a saida segue TRACK) *)
    PV : REAL;        (* variavel de processo, em unidade de engenharia *)
    SP : REAL;        (* setpoint, na mesma unidade da PV *)
    KP : REAL;        (* ganho proporcional: unidade da saida por unidade da PV *)
    TI : REAL;        (* tempo integral em SEGUNDOS (0 = sem acao integral) *)
    REVERSA : BOOL;   (* TRUE: E = SP - PV (a saida sobe quando a PV fica abaixo do SP) *)
    TRACK : REAL;     (* valor que a saida segue em manual (transferencia sem salto) *)
    YMIN : REAL;      (* limite inferior da saida *)
    YMAX : REAL;      (* limite superior da saida *)
    TS : REAL;        (* periodo de execucao em segundos (o mesmo da TASK do CLP) *)
  END_VAR
  VAR_OUTPUT
    Y : REAL;         (* saida limitada *)
    E : REAL;         (* erro usado no calculo *)
    SAT : BOOL;       (* TRUE enquanto a saida esta num limite *)
  END_VAR
  VAR
    I : REAL;         (* parcela integral acumulada *)
    U : REAL;         (* saida antes do limite *)
  END_VAR

(* PI na forma de posicao: Y = KP*E + I, com I(k) = I(k-1) + KP*TS/TI*E. *)
IF REVERSA THEN
  E := SP - PV;
ELSE
  E := PV - SP;
END_IF;

IF NOT AUTO THEN
  (* Manual: recalcula a integral para que, ao voltar ao automatico, a saida comece em TRACK. *)
  I := TRACK - KP * E;
  U := TRACK;
ELSE
  IF TI > 0.0 THEN
    I := I + KP * TS / TI * E;
  END_IF;
  U := KP * E + I;
END_IF;

(* Anti-windup: com a saida no limite, a integral e recalculada e para de crescer. *)
SAT := FALSE;
IF U > YMAX THEN
  U := YMAX;
  I := YMAX - KP * E;
  SAT := TRUE;
ELSIF U < YMIN THEN
  U := YMIN;
  I := YMIN - KP * E;
  SAT := TRUE;
END_IF;
Y := U;
END_FUNCTION_BLOCK"""

# A primeira entrada e a primeira saída são BOOL: no Ladder o bloco fica na linha de energia (como um
# TON), sem EN/ENO -- um FB escrito em ST não liga ENO, e o LD só copiaria as saídas com ENO verdadeiro.
CONTROLE_3E_ENTRADAS = [
    ("MODO_AUTO", "BOOL", "pedido de automatico (IHM): ligado pela linha de energia do degrau"),
    ("NIVEL", "REAL", "nivel do tambor (% entre tomadas)"),
    ("VAZAO_VAPOR", "REAL", "vazao de vapor (t/h)"),
    ("VAZAO_AGUA", "REAL", "vazao de agua de alimentacao (t/h)"),
    ("FALHA_NIVEL", "BOOL", "sinal do LT-101 invalido (NAMUR NE 43)"),
    ("FALHA_VAPOR", "BOOL", "sinal do FT-101 invalido"),
    ("FALHA_AGUA", "BOOL", "sinal do FT-102 invalido"),
    ("SP_NIVEL", "REAL", "setpoint de nivel (%)"),
    ("KP_LIC", "REAL", "ganho do mestre ((t/h) por %)"),
    ("TI_LIC", "REAL", "tempo integral do mestre (s)"),
    ("K_FF", "REAL", "razao do feedforward"),
    ("KP_FIC", "REAL", "ganho do escravo (% por t/h)"),
    ("TI_FIC", "REAL", "tempo integral do escravo (s)"),
    ("MV_MANUAL", "REAL", "sinal para a valvula em manual (%)"),
    ("QMAX_AGUA", "REAL", "fundo de escala do FT-102 (t/h)"),
]
CONTROLE_3E_SAIDAS = [
    ("EM_AUTO", "BOOL", "malha em automatico (pedido, sem falha e apos a partida)"),
    ("ABERTURA", "REAL", "sinal para a FV-102 (0 a 100 %)"),
    ("SP_AGUA", "REAL", "setpoint do escravo FIC-102 (t/h)"),
]

CONTROLE_3E = f"""FUNCTION_BLOCK CONTROLE_3E
  VAR_INPUT
{chr(10).join(f"    {n} : {t};   (* {d} *)" for n, t, d in CONTROLE_3E_ENTRADAS)}
  END_VAR
  VAR_OUTPUT
{chr(10).join(f"    {n} : {t};   (* {d} *)" for n, t, d in CONTROLE_3E_SAIDAS)}
  END_VAR
  VAR
    FF_VAPOR : REAL;     (* parcela de antecipacao (t/h) *)
    TRIM : REAL;         (* correcao do mestre LIC-101 (t/h) *)
    TRIM_MIN : REAL;
    TRIM_MAX : REAL;
    LIMITE_TRIM : REAL;  (* o mestre so corrige +-20 % do fundo de escala da agua *)
    PARTIDA : TON;       (* 10 s em manual/rastreamento depois que o CLP entra em RUN *)
    LIC_101 : PI_AW;     (* mestre: nivel -> correcao de vazao *)
    FIC_102 : PI_AW;     (* escravo: vazao de agua -> abertura da valvula *)
  END_VAR

(* ============================================================================
   Controle de nivel do tambor a tres elementos (FORNECIDO - nao altere)
   nivel (LIC-101, mestre) + vazao de vapor (feedforward) + vazao de agua (FIC-102, escravo)
   ============================================================================ *)

(* Feedforward: sem medicao de vapor confiavel, a antecipacao sai. *)
IF FALHA_VAPOR THEN
  FF_VAPOR := 0.0;
ELSE
  FF_VAPOR := K_FF * VAZAO_VAPOR;
END_IF;

(* Modo: falha no nivel ou na vazao de agua leva a malha para manual.
   Na partida do CLP os PI rastreiam por 10 s (sem salto na valvula). *)
PARTIDA(IN := TRUE, PT := T#10s);
EM_AUTO := MODO_AUTO AND PARTIDA.Q AND NOT FALHA_NIVEL AND NOT FALHA_AGUA;

(* Mestre LIC-101: nivel baixo -> correcao positiva (acao reversa). Com feedforward a saida e uma
   correcao limitada; sem ele (K_FF = 0) o mestre fornece o setpoint inteiro (dois elementos).
   Em manual o mestre rastreia (VAZAO_AGUA - FF) para entrar em automatico sem salto. *)
LIMITE_TRIM := 0.2 * QMAX_AGUA;
IF K_FF > 0.05 THEN
  TRIM_MIN := -LIMITE_TRIM;
  TRIM_MAX := LIMITE_TRIM;
ELSE
  TRIM_MIN := 0.0;
  TRIM_MAX := QMAX_AGUA;
END_IF;
LIC_101(AUTO := EM_AUTO, PV := NIVEL, SP := SP_NIVEL, KP := KP_LIC, TI := TI_LIC,
        REVERSA := TRUE, TRACK := VAZAO_AGUA - FF_VAPOR,
        YMIN := TRIM_MIN, YMAX := TRIM_MAX, TS := {TS_TASK});
TRIM := LIC_101.Y;

(* Setpoint do escravo: antecipacao + correcao, na mesma base (t/h). *)
SP_AGUA := LIMIT(0.0, FF_VAPOR + TRIM, QMAX_AGUA);

(* Escravo FIC-102: vazao abaixo do SP -> abre a valvula (acao reversa). Em manual segue MV_MANUAL. *)
FIC_102(AUTO := EM_AUTO, PV := VAZAO_AGUA, SP := SP_AGUA, KP := KP_FIC, TI := TI_FIC,
        REVERSA := TRUE, TRACK := MV_MANUAL,
        YMIN := 0.0, YMAX := 100.0, TS := {TS_TASK});
ABERTURA := FIC_102.Y;
END_FUNCTION_BLOCK"""

_DEF_CONTROLE = ("function-block", False, [(n, t) for n, t, _ in CONTROLE_3E_ENTRADAS],
                 [(n, t) for n, t, _ in CONTROLE_3E_SAIDAS], None)


# =================================================================================================
# MAIN em Ladder
# =================================================================================================
def _cabecalho(locais: list[tuple]) -> tuple[str, dict]:
    """Bloco VAR do MAIN (texto IEC) e as declarações para os nós do diagrama.

    locais: (nome, tipo, valor inicial ou None, comentário)."""
    linhas = ["  VAR_INPUT"]
    linhas += [f"    {n} : {t};   (* {d} *)" for n, c, t, d in IO if c == "input"]
    linhas += ["  END_VAR", "  VAR_OUTPUT"]
    linhas += [f"    {n} : {t};   (* {d} *)" for n, c, t, d in IO if c == "output"]
    linhas += ["  END_VAR", "  VAR"]
    for n, t, ini, d in locais:
        inicial = f" := {ini}" if ini is not None else ""
        linhas.append(f"    {n} : {t}{inicial};   (* {d} *)")
    linhas.append("  END_VAR")
    decl = {n: declaracao_editor(n, c, t, doc=d) for n, c, t, d in IO}
    for n, t, ini, d in locais:
        decl[n] = declaracao_editor(n, "local", t, ini, d)
    return "\n".join(linhas), decl


# Variáveis que o modelo do aluno já declara (as que o CONTROLE_3E e a saída usam)
LOCAIS_MODELO = [
    ("CONTROLE", "CONTROLE_3E", None, "controle a tres elementos (bloco fornecido)"),
    ("NIVEL", "REAL", None, "ETAPA 3: nivel do tambor (%)"),
    ("VAZAO_VAPOR", "REAL", None, "ETAPA 4: vazao de vapor (t/h) - placa FE-101"),
    ("VAZAO_AGUA", "REAL", None, "ETAPA 4: vazao de agua (t/h) - placa FE-102"),
    ("FALHA_LT101", "BOOL", None, "ETAPA 2: sinal do LT-101 fora de 3,6 a 21 mA"),
    ("FALHA_FT101", "BOOL", None, "ETAPA 2: sinal do FT-101 fora de 3,6 a 21 mA"),
    ("FALHA_FT102", "BOOL", None, "ETAPA 2: sinal do FT-102 fora de 3,6 a 21 mA"),
    ("QMAX_AGUA", "REAL", None, "fundo de escala do FT-102 (t/h): preencha o valor inicial"),
    ("ABERTURA", "REAL", None, "sinal para a FV-102 (%)"),
    ("EM_AUTO", "BOOL", None, "malha em automatico"),
    ("SP_AGUA", "REAL", None, "setpoint do escravo (t/h)"),
    ("AO_X", "REAL", None, "auxiliar da saida analogica"),
]


def _rungs_controle_e_saida() -> list[Rung]:
    controle = Bloco("CONTROLE_3E", instancia="CONTROLE", definicao=_DEF_CONTROLE, entradas={
        "NIVEL": "NIVEL", "VAZAO_VAPOR": "VAZAO_VAPOR", "VAZAO_AGUA": "VAZAO_AGUA",
        "FALHA_NIVEL": "FALHA_LT101", "FALHA_VAPOR": "FALHA_FT101", "FALHA_AGUA": "FALHA_FT102",
        "SP_NIVEL": "SP_NIVEL", "KP_LIC": "KP_LIC", "TI_LIC": "TI_LIC", "K_FF": "K_FF", "KP_FIC": "KP_FIC",
        "TI_FIC": "TI_FIC", "MV_MANUAL": "MV_MANUAL", "QMAX_AGUA": "QMAX_AGUA"},
        saidas={"ABERTURA": "ABERTURA", "SP_AGUA": "SP_AGUA"})
    return [
        Rung("ETAPA 5 (FORNECIDA) - controle a tres elementos: mestre LIC-101 + feedforward do vapor + escravo FIC-102. "
             "Usa NIVEL, VAZAO_VAPOR, VAZAO_AGUA e as FALHAS calculadas nas etapas 1 a 4. O contato MODO_AUTO "
             "pede o automatico; a bobina EM_AUTO mostra se a malha entrou.").serie(Contato("MODO_AUTO"), controle, Bobina("EM_AUTO")),
        Rung("ETAPA 6 (FORNECIDA) - saida analogica: AO = 4 + 0,16 x ABERTURA (mA)").serie(
            Bloco("MUL", {"IN1": "ABERTURA", "IN2": "0.16"}, {"OUT": "AO_X"})),
        Rung("").serie(Bloco("ADD", {"IN1": "AO_X", "IN2": "4.0"}, {"OUT": "AO_FV102"})),
    ]


def main_aluno(qmax_agua_inicial: float | None = None) -> str:
    """Modelo do aluno: etapas 5 e 6 prontas; etapas 1 a 4 em branco (a malha funciona em manual)."""
    locais = [list(x) for x in LOCAIS_MODELO]
    if qmax_agua_inicial is not None:
        for item in locais:
            if item[0] == "QMAX_AGUA":
                item[2] = qmax_agua_inicial
    locais = [tuple(x) for x in locais]
    cab, decl = _cabecalho(locais)
    rungs = _rungs_controle_e_saida()
    rungs[0].comentario = (
        "II2P13 - TRABALHO: escreva em LADDER as ETAPAS 1 a 4 em degraus ACIMA deste (botao + Rung e arraste). "
        "ETAPA 1: corrente de cada AI (mA) = V / 0,25. ETAPA 2: FALHA = I < 3,6 mA OU I > 21 mA (NAMUR NE 43). "
        "ETAPA 3: NIVEL (%) pela faixa do LT-101. ETAPA 4: vazao de cada placa de orificio (t/h): dP pela faixa do "
        "transmissor, corte de vazao baixa e raiz quadrada. Dica: um bloco por degrau (a saida de um bloco so e "
        "gravada no fim do degrau). ETAPA 5 (FORNECIDA): controle a tres elementos.")
    return pou_ld("PROGRAM", "MAIN", cab, rungs, decl)


def main_gabarito(g) -> str:
    """Solução completa do grupo g (grupos.Grupo)."""
    locais = [x for x in LOCAIS_MODELO if x[0] != "QMAX_AGUA"]
    locais += [
        ("QMAX_AGUA", "REAL", g.qmax_ft102, "fundo de escala do FT-102 (t/h)"),
        ("I_LT101", "REAL", None, "corrente do AI-01 (mA)"),
        ("I_FT101", "REAL", None, "corrente do AI-02 (mA)"),
        ("I_FT102", "REAL", None, "corrente do AI-03 (mA)"),
        ("LT101_BAIXO", "BOOL", None, ""), ("LT101_ALTO", "BOOL", None, ""),
        ("FT101_BAIXO", "BOOL", None, ""), ("FT101_ALTO", "BOOL", None, ""),
        ("FT102_BAIXO", "BOOL", None, ""), ("FT102_ALTO", "BOOL", None, ""),
        ("X_LT101", "REAL", None, "I - 4 (mA)"),
        ("X_FT101", "REAL", None, "I - 4 (mA)"),
        ("X_FT102", "REAL", None, "I - 4 (mA)"),
        ("DP_FT101", "REAL", None, "dP na placa FE-101 (mmH2O)"),
        ("DP_FT102", "REAL", None, "dP na placa FE-102 (mmH2O)"),
        ("RAIZ_FT101", "REAL", None, "raiz de dP"),
        ("RAIZ_FT102", "REAL", None, "raiz de dP"),
        ("CORTE_FT101", "BOOL", None, "dP abaixo do corte: vazao zero"),
        ("CORTE_FT102", "BOOL", None, "dP abaixo do corte: vazao zero"),
        ("SPAN16_FT101", "REAL", round(g.ft101_urv / 16.0, 4), "URV/16 do FT-101 (mmH2O por mA)"),
        ("SPAN16_FT102", "REAL", round(g.ft102_urv / 16.0, 4), "URV/16 do FT-102 (mmH2O por mA)"),
        ("K_FT101", "REAL", round(g.k_ft101, 5), "constante da FE-101: Q(t/h) = K x raiz(dP mmH2O)"),
        ("K_FT102", "REAL", round(g.k_ft102, 5), "constante da FE-102"),
        ("CORTE_DP_FT101", "REAL", round(0.01 * g.ft101_urv, 2), "corte: 1 % da faixa de dP (10 % da vazao)"),
        ("CORTE_DP_FT102", "REAL", round(0.01 * g.ft102_urv, 2), "corte: 1 % da faixa de dP"),
    ]
    cab, decl = _cabecalho(locais)
    R = []
    R.append(Rung("ETAPA 1 - corrente de cada canal AI: I (mA) = V / 0,25 kohm").serie(
        Bloco("DIV", {"IN1": "AI_LT101", "IN2": "0.25"}, {"OUT": "I_LT101"})))
    R.append(Rung("").serie(Bloco("DIV", {"IN1": "AI_FT101", "IN2": "0.25"}, {"OUT": "I_FT101"})))
    R.append(Rung("").serie(Bloco("DIV", {"IN1": "AI_FT102", "IN2": "0.25"}, {"OUT": "I_FT102"})))
    for tag, var in (("LT101", "I_LT101"), ("FT101", "I_FT101"), ("FT102", "I_FT102")):
        R.append(Rung(f"ETAPA 2 - validacao NAMUR NE 43 do {tag[:2]}-{tag[2:]}: falha abaixo de 3,6 mA ou acima de 21 mA").serie(
            Bloco("LT", {"IN1": var, "IN2": "3.6"}, {"OUT": f"{tag}_BAIXO"})))
        R.append(Rung("").serie(Bloco("GT", {"IN1": var, "IN2": "21.0"}, {"OUT": f"{tag}_ALTO"})))
        R.append(Rung("").serie(Paralelo([Contato(f"{tag}_BAIXO")], [Contato(f"{tag}_ALTO")]), Bobina(f"FALHA_{tag}")))
    R.append(Rung("ETAPA 3 - nivel: o LT-101 foi calibrado com LRV/URV do tambor -> NIVEL = (I - 4) / 16 x 100 = (I - 4) x 6,25").serie(
        Bloco("SUB", {"IN1": "I_LT101", "IN2": "4.0"}, {"OUT": "X_LT101"})))
    R.append(Rung("").serie(Bloco("MUL", {"IN1": "X_LT101", "IN2": "6.25"}, {"OUT": "NIVEL"})))
    for tag, nome_placa, urv, k in (("FT101", "FE-101 (vapor)", g.ft101_urv, g.k_ft101), ("FT102", "FE-102 (agua)", g.ft102_urv, g.k_ft102)):
        vazao = "VAZAO_VAPOR" if tag == "FT101" else "VAZAO_AGUA"
        R.append(Rung(f"ETAPA 4 - placa de orificio {nome_placa}: o {tag[:2]}-{tag[2:]} sai LINEAR em dP (0 a {urv} mmH2O). "
                      f"dP = (I - 4) x URV / 16").serie(Bloco("SUB", {"IN1": f"I_{tag}", "IN2": "4.0"}, {"OUT": f"X_{tag}"})))
        R.append(Rung("").serie(Bloco("MUL", {"IN1": f"X_{tag}", "IN2": f"SPAN16_{tag}"}, {"OUT": f"DP_{tag}"})))
        R.append(Rung("dP negativo (abaixo de 4 mA) vale zero").serie(
            Bloco("MAX", {"IN1": f"DP_{tag}", "IN2": "0.0"}, {"OUT": f"DP_{tag}"})))
        R.append(Rung("corte de vazao baixa: abaixo de 1 % da faixa de dP a vazao e zero (a raiz amplifica ruido perto de zero)").serie(
            Bloco("LT", {"IN1": f"DP_{tag}", "IN2": f"CORTE_DP_{tag}"}, {"OUT": f"CORTE_{tag}"})))
        R.append(Rung(f"Q (t/h) = K x raiz(dP), K = {k:.5f} (t/h)/raiz(mmH2O) pela equacao da placa").serie(
            Contato(f"CORTE_{tag}", negado=True), Bloco("SQRT", {"IN": f"DP_{tag}"}, {"OUT": f"RAIZ_{tag}"})))
        R.append(Rung("").serie(Contato(f"CORTE_{tag}", negado=True),
                                Bloco("MUL", {"IN1": f"RAIZ_{tag}", "IN2": f"K_{tag}"}, {"OUT": vazao})))
        R.append(Rung("").serie(Contato(f"CORTE_{tag}"), Bloco("MOVE", {"IN": "0.0"}, {"OUT": vazao})))
    R += _rungs_controle_e_saida()
    return pou_ld("PROGRAM", "MAIN", cab, R, decl)


def lsplc(nome: str, main_ld: str) -> dict:
    return {
        "format": "lasecsimul.plc-project",
        "formatVersion": 1,
        "editor": {"name": "OpenPLC Editor", "version": "4.2.8"},
        "project": {
            "meta": {"name": nome, "type": "plc-project"},
            "data": {"pous": [], "dataTypes": [], "libraries": [],
                     "configuration": {"resource": {
                         "tasks": [{"name": "MAIN_TASK", "triggering": "Cyclic", "interval": "T#100ms", "priority": 1}],
                         "instances": [{"name": "MAIN_INSTANCE", "program": "MAIN", "task": "MAIN_TASK"}],
                         "globalVariables": []}}},
        },
        "devices": {"configuration": {"deviceBoard": "OpenPLC Simulator", "communicationPort": "", "runtimeIpAddress": "",
                                      "vendorScreenData": {}, "vendorScreenDataByBoard": {}, "selectedPlatformOptions": {}},
                    "pinMapping": {}},
        "files": {"pous/function-blocks/PI_AW.st": PI_AW, "pous/function-blocks/CONTROLE_3E.st": CONTROLE_3E,
                  "pous/programs/MAIN.ld": main_ld},
    }
