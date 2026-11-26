"""Gera os projetos do trabalho II2P13 (um por grupo) a partir de `grupos.py` e `programas_clp.py`.

    python ferramentas/gerar_projeto.py            # os 4 grupos
    python ferramentas/gerar_projeto.py A C        # só alguns

Saídas (na pasta da prática):
    grupos/Grupo_X/II2P13_Grupo_X.lsproj              planta "como encontrada" do grupo + CLP do aluno
    grupos/Grupo_X/clp/CLP_Grupo_X.lsplc              modelo do aluno (Ladder: etapas 5 e 6 prontas)
    gabarito/Grupo_X/II2P13_Grupo_X_GABARITO.lsproj   tudo comissionado (LD301, FY301, válvula, suprimento) + AUTO
    gabarito/Grupo_X/clp/CLP_Grupo_X_GABARITO.lsplc   Ladder completo do grupo

A planta é um subsistema EMBUTIDO no .lsproj (`subsystems`, `subsystem.local.caldeira_b101`): modelo
dinâmico em blocos `sl.*` + símbolo com o sinótico. Os três LD301 e o FY301 são instâncias dos
subcircuitos da biblioteca do LasecSimul, colocadas sobre o sinótico; o FY301 comanda o atuador da
FV-102 (OUT1) e lê o curso da haste (POS). Os laços 4–20 mA, o cartão AI, o cartão AO, os modems
HART e o CLP ficam no painel abaixo. Portas HART fixas (cada grupo num PC):
LT-101 CNCB0/COM20, FT-101 CNCB1/COM21, FT-102 CNCB2/COM22, FY-102 CNCB3/COM23.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import grupos as G            # noqa: E402
import programas_clp as CLP   # noqa: E402


def _biblioteca(nome: str) -> str:
    for base in (os.environ.get("LASECSIMUL_REPO", r"C:\SourceCode\LasecSimul"),):
        caminho = os.path.join(base, "subcircuits", nome)
        if os.path.exists(caminho):
            return caminho
    ext = os.path.join(os.path.expanduser("~"), ".vscode", "extensions")
    for pasta in sorted(os.listdir(ext), reverse=True):
        caminho = os.path.join(ext, pasta, "bundled", "subcircuits", nome)
        if pasta.startswith("josuemoraisgh.lasecsimul-") and os.path.exists(caminho):
            return caminho
    raise FileNotFoundError(nome)


LD301_LIB = _biblioteca("hart_smar_ld301.lssubcircuit")
FY301_LIB = _biblioteca("hart_smar_fy301.lssubcircuit")
TS_PROC = "0.01"      # s, blocos do processo
TS_ATUADOR = "0.001"  # s, atuador da FV-102 (o servo do FY301 roda a 1 ms)
PORTAS = {"LT-101": ("CNCB0", "COM20"), "FT-101": ("CNCB1", "COM21"), "FT-102": ("CNCB2", "COM22"), "FY-102": ("CNCB3", "COM23")}
TAU_VAPOR, TAU_INCHAMENTO, TAU_ATUADOR, ATRITO = 3.0, 15.0, 0.5, 0.5

# =============================================================================================
# Geometria do sinótico (coordenadas do símbolo = coordenadas do esquemático, planta em 0,0)
# =============================================================================================
S, OX, OY = 1.4, 300.0, 10.0


def m(x: float, y: float) -> tuple[float, float]:
    return (round(OX + S * x, 1), round(OY + S * y, 1))


W, H = 2300, 1340
COR_VAPOR, COR_AGUA, COR_TAMBOR = "#9e9e9e", "#0000ee", "#0000ff"
COR_BOLHA, COR_BOLHA_AI_VAPOR = "#f4b896", "#eeeeee"
LARG_VAPOR, LARG_AGUA, LARG_IMPULSO = 9, 7, 4
Y_VAPOR = m(0, 235)[1]
Y_AGUA = m(0, 712)[1]
TAMBOR = {"cx": m(402, 0)[0], "cy": m(0, 385)[1], "rx": 112.0, "ry": 94.0}
LAMA = {"cx": m(402, 0)[0], "cy": m(0, 698)[1], "rx": 88.0, "ry": 74.0}
PAREDE_DIR = m(512, 0)[0]
LD_W, LD_H, LD_HIGH, LD_LOW = 150, 228, 168, 188
FY_W, FY_SUP, FY_OUT1, FY_POS, FY_LP, FY_LN = 230, 130, 150, 170, 140, 160
PIN_LEAD = 8
FE101_X = 160.0
FE102_X = m(1010, 0)[0]
FV102_X = m(1190, 0)[0]
FY = {"x": 2040.0, "y": 1080.0}
BOLHAS = {
    "ai_vapor": (m(97, 48), "AI", COR_BOLHA_AI_VAPOR), "pid_mestre": (m(712, 187), "PID", COR_BOLHA),
    "ai_nivel": ((m(712, 0)[0], 420.0), "AI", COR_BOLHA), "soma": (m(1190, 187), "+", COR_BOLHA),
    "pid_escravo": (m(1191, 358), "PID", COR_BOLHA), "ai_agua": (m(1006, 525), "AI", COR_BOLHA),
    "ao": (m(1193, 595), "AO", COR_BOLHA),
}
BOLHA_RX, BOLHA_RY = 78, 58
X_DIR = W - 190
DISP_W, DISP_H, SLID_W, SLID_H = 170, 71, 170, 27
PASSO_AJUSTE = DISP_H + SLID_H + 8
X_LIC, Y_LIC = 985.0, 92.0
# id, rótulo, unidade, casas, min, max, x, y, cor ("ihm" laranja, "campo" verde)
AJUSTES = [
    ("c_demanda", "Demanda de vapor", "%", 0, 0, 100, 20, 150, "ihm"),
    ("c_sp", "SP nível LIC-101", "%", 1, 0, 100, X_LIC, Y_LIC, "ihm"),
    ("c_kp_lic", "KP LIC-101 (t/h)/%", "", 2, 0, 5, X_LIC, Y_LIC + PASSO_AJUSTE, "ihm"),
    ("c_ti_lic", "TI LIC-101", "s", 0, 0, 600, X_LIC, Y_LIC + 2 * PASSO_AJUSTE, "ihm"),
    ("c_kff", "K_FF vapor→água", "", 2, 0, 1.5, X_DIR, 222, "ihm"),
    ("c_kp_fic", "KP FIC-102 %/(t/h)", "", 2, 0, 10, X_DIR, 420, "ihm"),
    ("c_ti_fic", "TI FIC-102", "s", 1, 0, 30, X_DIR, 520, "ihm"),
    ("c_mv", "MV manual FV-102", "%", 1, 0, 100, X_DIR, 820, "ihm"),
    ("c_pbomba", "Pressão da bomba", "%", 0, 50, 120, 20, 700, "ihm"),
    ("c_valvula", "FV-102: opção do catálogo", "", 0, 1, len(G.CATALOGO), 1470, 1075, "campo"),
    ("c_suprimento", "Ar do filtro-regulador", "bar", 1, 0, 6, 1470, 1205, "campo"),
]
MODO_POS, MODO_W, MODO_H = (X_DIR + 26, 735.0), 117, 57
PINOS_INFERIORES = ["sp_nivel", "kp_lic", "ti_lic", "k_ff", "kp_fic", "ti_fic", "modo_auto", "mv_manual"]
X_PINO0, DX_PINO = 1000.0, 125.0
Y_PINO = H - 4
ROTULO_PINO = {"sp_nivel": "SP_NIVEL", "kp_lic": "KP_LIC", "ti_lic": "TI_LIC", "k_ff": "K_FF", "kp_fic": "KP_FIC",
               "ti_fic": "TI_FIC", "modo_auto": "MODO", "mv_manual": "MV_MAN"}


def x_pino_inferior(pid: str) -> float:
    return X_PINO0 + PINOS_INFERIORES.index(pid) * DX_PINO


def geometria_ld(g: G.Grupo) -> dict:
    dy = TAMBOR["ry"] * (g.h_tomadas / 2) / (g.d_tambor / 2)
    y_sup, y_inf = round(TAMBOR["cy"] - dy, 1), round(TAMBOR["cy"] + dy, 1)
    ld = {"LT-101": {"x": PAREDE_DIR + 70, "y": y_inf - LD_HIGH},
          "FT-101": {"x": 240.0, "y": Y_VAPOR + 52},
          "FT-102": {"x": m(1010, 0)[0] + 70, "y": Y_AGUA + 52}}
    return {"y_sup": y_sup, "y_inf": y_inf, "ld": ld}


def x_elipse(e: dict, y: float, lado: int = 1) -> float:
    k = 1 - ((y - e["cy"]) / e["ry"]) ** 2
    return round(e["cx"] + lado * e["rx"] * math.sqrt(max(k, 0.0)), 1)


# =============================================================================================
# Blocos de sinal (formato novo: sl.fcn, sl.mux, sl.discrete_transfer_fcn, process.accumulator)
# =============================================================================================
_FUNCOES = {"abs", "acos", "asin", "atan", "atan2", "ceil", "cos", "cosh", "exp", "floor", "hypot", "log", "log10",
            "power", "rem", "sgn", "sin", "sinh", "sqrt", "tan", "tanh"}
_PORTA_SAIDA = {"control.constant": "out", "sl.fcn": "out1", "sl.discrete_transfer_fcn": "out1",
                "process.accumulator": "out", "connectors.signal_tunnel": "value", "sl.mux": "out1"}


class Modelo:
    def __init__(self):
        self.comps: list[dict] = []
        self.fios: list[dict] = []
        self.tipo: dict[str, str] = {}

    def comp(self, cid, type_id, props, label=None, x=0, y=0):
        e = {"id": cid, "typeId": type_id, "properties": props, "visual": {"x": x, "y": y, "rotation": 0}}
        if label:
            e["label"] = label
        self.comps.append(e)
        self.tipo[cid] = type_id
        return cid

    def fio(self, origem, destino, pino_destino, pino_origem=None):
        # pino de saída resolvido em finalizar(): a origem pode ser criada depois (realimentação)
        self.fios.append({"id": f"w-{len(self.fios) + 1}", "from": {"kind": "port", "componentId": origem, "pinId": pino_origem},
                          "to": {"kind": "port", "componentId": destino, "pinId": pino_destino}, "vertices": []})

    def finalizar(self):
        for f in self.fios:
            if f["from"]["pinId"] is None:
                origem = f["from"]["componentId"]
                assert origem in self.tipo, f"origem desconhecida: {origem}"
                f["from"]["pinId"] = _PORTA_SAIDA.get(self.tipo[origem], "out1")
        return self

    def const(self, cid, valor, unidade, label, opcoes=None):
        props = {"value": valor, "unit": unidade}
        if opcoes:
            props["options"] = opcoes
        return self.comp(cid, "control.constant", props, label)

    def fcn(self, cid, entradas: list[tuple[str, str]], expr: str, label: str, ts: str = TS_PROC):
        """entradas: (nome, componente de origem); expr usa os nomes (viram u(1), u(2) ...)."""
        nomes = {n: i + 1 for i, (n, _) in enumerate(entradas)}

        def troca(mt):
            nome = mt.group(0)
            fim = mt.end()
            if nome in _FUNCOES and fim < len(expr) and expr[fim] == "(":
                return nome
            if nome in nomes:
                return f"u({nomes[nome]})"
            raise ValueError(f"{cid}: nome '{nome}' sem entrada em {expr}")
        u = re.sub(r"(?<![\w.])[A-Za-z_][A-Za-z0-9_]*", troca, expr)
        self.comp(cid, "sl.fcn", {"Expr": u, "SampleTime": ts}, label)
        if len(entradas) == 1:
            self.fio(entradas[0][1], cid, "in1")
        else:
            mux = self.comp(f"{cid}__mux", "sl.mux", {"Inputs": str(len(entradas))}, x=-80)
            for i, (_, origem) in enumerate(entradas):
                self.fio(origem, mux, f"in{i + 1}")
            self.fio(mux, cid, "in1")
        return cid

    def atraso(self, cid, origem, tau, inicial, label, ts=TS_PROC):
        a = math.exp(-float(ts) / tau)
        # realização do bloco: x(k+1) = a·x(k) + u(k), y = (1 − a)·x  ->  estado inicial = saída inicial / (1 − a)
        self.comp(cid, "sl.discrete_transfer_fcn", {"Numerator": f"[{1 - a!r}]", "Denominator": f"[1 {-a!r}]",
                                                    "InitialStates": repr(float(inicial) / (1 - a)), "SampleTime": ts}, label)
        self.fio(origem, cid, "in1")
        return cid

    def acumulador(self, cid, entrada, saida, inicial, label, ts=TS_PROC):
        self.comp(cid, "process.accumulator", {"initial": inicial, "samplePeriodNs": int(round(float(ts) * 1e9))}, label)
        self.fio(entrada, cid, "in")
        self.fio(saida, cid, "outflow")
        return cid


def lim(e: str, lo, hi) -> str:
    return f"(({e}) + (({e}) < {lo})*(({lo}) - ({e})) + (({e}) > {hi})*(({hi}) - ({e})))"


def pos(e: str) -> str:
    return f"((({e}) > 0)*({e}))"


# =============================================================================================
# Estado inicial e valores dos ajustes
# =============================================================================================
VALVULA_ENCONTRADA = {"A": 6, "B": 11, "C": 4, "D": 8}


def estado_inicial(g: G.Grupo, comissionado: bool) -> dict:
    """Abertura inicial da FV-102, pressão no atuador e o MV manual que a mantém."""
    opcao = g.valvula if comissionado else VALVULA_ENCONTRADA[g.nome]
    abertura = g.abertura_equilibrio(opcao=opcao)          # % do curso
    lo, hi = g.mola
    frac = abertura / 100.0
    p_act = lo + (hi - lo) * (frac if g.ar_para == "abrir" else 1.0 - frac)
    if comissionado:
        mv = g.sinal_para_abertura(abertura)
    elif g.ar_para == "abrir":
        mv = abertura * g.curso / 30.0                      # FY301 sem Auto Setup: escala de fábrica de 30 mm
    else:
        mv = 50.0                                           # AIR_T de fábrica num atuador ar-para-fechar: não segura
    return {"opcao": opcao, "abertura": abertura, "stem": g.curso * frac, "p_act": p_act, "mv": round(mv, 1)}


def valores_ihm(g: G.Grupo, comissionado: bool) -> dict:
    ini = estado_inicial(g, comissionado)
    s = g.sintonia
    v = {"c_demanda": g.demanda_inicial, "c_pbomba": 100.0, "c_sp": s["SP_NIVEL"], "c_kff": s["K_FF"],
         "c_kp_lic": s["KP_LIC"], "c_ti_lic": s["TI_LIC"], "c_kp_fic": s["KP_FIC"], "c_ti_fic": s["TI_FIC"],
         "c_modo": 5.0 if comissionado else 0.0, "c_mv": ini["mv"], "c_inchamento": 1.0,
         "c_valvula": float(ini["opcao"]), "c_suprimento": g.suprimento_correto if comissionado else g.suprimento_encontrado}
    if not comissionado:
        v.update({"c_kp_lic": 0.0, "c_ti_lic": 0.0, "c_kp_fic": 0.0, "c_ti_fic": 0.0})
    return v


# =============================================================================================
# Subsistema da planta
# =============================================================================================
def gerar_subsistema(g: G.Grupo, comissionado: bool) -> dict:
    valores = valores_ihm(g, comissionado)
    ini = estado_inicial(g, comissionado)
    geo = geometria_ld(g)
    LD = geo["ld"]
    Y_TOMADA_SUP, Y_TOMADA_INF = geo["y_sup"], geo["y_inf"]
    X_PERNA_REF = LD["LT-101"]["x"] + LD_W + 150
    X_RISER = X_PERNA_REF + 70
    md = Modelo()
    interface: list[dict] = []
    expostos: list[dict] = []
    shapes: list[dict] = []
    pinos: list[dict] = []

    def tunel_saida(nome, origem, rotulo):
        tid = md.comp(f"t_{nome}", "connectors.signal_tunnel", {"name": nome, "pinId": nome, "direction": "Output", "valueType": "Real"})
        md.fio(origem, tid, "value")
        interface.append({"pinId": nome, "label": rotulo, "internalTunnel": nome, "domain": "signal", "direction": "out",
                          "valueType": "Real", "width": 1})

    # --- ajustes (constantes exportadas) ---------------------------------------------------------
    CONSTANTES = [
        ("c_demanda", "Demanda de vapor (% da MCR)", "%", None),
        ("c_pbomba", "Pressão da bomba de alimentação (% do projeto)", "%", None),
        ("c_sp", "IHM: setpoint de nível do LIC-101", "%", None),
        ("c_kp_lic", "IHM: ganho KP do mestre LIC-101", "(t/h)/%", None),
        ("c_ti_lic", "IHM: tempo integral TI do mestre LIC-101", "s", None),
        ("c_kff", "IHM: razão do feedforward K_FF", "", None),
        ("c_kp_fic", "IHM: ganho KP do escravo FIC-102", "%/(t/h)", None),
        ("c_ti_fic", "IHM: tempo integral TI do escravo FIC-102", "s", None),
        ("c_modo", "IHM: modo (0 = MAN, 5 = AUTO)", "", None),
        ("c_mv", "IHM: sinal manual para a FV-102", "%", None),
        ("c_valvula", "FV-102: válvula instalada (opção do catálogo da folha de dados)", "",
         ";".join(f"{k}={dn} {car} Cv {cv:g}" for k, (dn, car, cv) in G.CATALOGO.items())),
        ("c_suprimento", "FY-102: pressão de saída do filtro-regulador (suprimento de ar)", "bar", None),
        ("c_inchamento", "Inchamento/contração (0 = desliga, 1 = normal)", "", None),
    ]
    for cid, label, unit, opcoes in CONSTANTES:
        md.const(cid, valores[cid], unit, label, opcoes)

    # --- vapor -------------------------------------------------------------------------------------
    qs0 = g.q_vapor_inicial
    md.fcn("qs_alvo", [("d", "c_demanda")], f"{g.mcr}*{lim('d', 0, 100)}/100", "Vazão de vapor pedida (t/h)")
    md.atraso("qs", "qs_alvo", TAU_VAPOR, qs0, "Vazão de vapor (t/h)")
    md.atraso("qs_lento", "qs", TAU_INCHAMENTO, qs0, "Vazão de vapor filtrada (t/h)")

    # --- FV-102: atuador pneumático (mola x diafragma), haste e vazão instalada ---------------------
    lo, hi = g.mola
    acao = 0 if g.ar_para == "abrir" else 1
    curso = g.curso
    md.comp("t_fv_out1", "connectors.signal_tunnel", {"name": "fv_out1", "pinId": "fv_out1", "direction": "Input",
                                                       "valueType": "Real", "defaultValue": 0})
    interface.append({"pinId": "fv_out1", "label": "FV-102: OUT1 do FY-102 (bar)", "internalTunnel": "fv_out1",
                      "domain": "signal", "direction": "in", "valueType": "Real", "width": 1})
    md.fcn("fv_sup", [("s", "c_suprimento")], pos("s"), "Suprimento de ar do FY-102 (bar)", TS_ATUADOR)
    tunel_saida("fv_sup", "fv_sup", "FV-102: suprimento de ar (bar)")
    md.fcn("p_in", [("o", "t_fv_out1"), ("p", "p_act")], f"{pos('o - p')}/{TAU_ATUADOR}", "Enchimento do atuador (bar/s)", TS_ATUADOR)
    md.fcn("p_out", [("o", "t_fv_out1"), ("p", "p_act")], f"{pos('p - o')}/{TAU_ATUADOR}", "Exaustão do atuador (bar/s)", TS_ATUADOR)
    md.acumulador("p_act", "p_in", "p_out", round(ini["p_act"], 4), "Pressão no atuador (bar)", TS_ATUADOR)
    frac = f"(p - {lo})/{hi - lo}"
    md.fcn("x_eq", [("p", "p_act")], f"{curso}*({frac})" if acao == 0 else f"{curso}*(1 - {frac})",
           f"Equilíbrio mola x diafragma (mm; ar para {g.ar_para})", TS_ATUADOR)
    db = curso * ATRITO / 200.0
    md.fcn("gap", [("e", "x_eq"), ("x", "stem")], f"(e - x > {db})*(e - x - {db}) + (e - x < -{db})*(e - x + {db})",
           "Força líquida além do atrito da gaxeta (mm)", TS_ATUADOR)
    md.fcn("stem_in", [("d", "gap"), ("x", "stem")], f"(d > 0)*d/0.15*(x < {curso})", "Haste abrindo (mm/s)", TS_ATUADOR)
    md.fcn("stem_out", [("d", "gap"), ("x", "stem")], "(d < 0)*(0 - d)/0.15*(x > 0)", "Haste fechando (mm/s)", TS_ATUADOR)
    md.acumulador("stem", "stem_in", "stem_out", round(ini["stem"], 4), "Curso da haste: abertura (mm)", TS_ATUADOR)
    tunel_saida("fv_pos", "stem", "FV-102: curso da haste para o ímã do FY-102 (mm)")
    md.fcn("abertura", [("x", "stem")], f"{lim(f'x/{curso}', 0, 1)}", "Abertura da FV-102 (0-1)")
    cv_expr = " + ".join(f"(abs(v - {k}) < 0.5)*{cv}" for k, (_, _, cv) in G.CATALOGO.items())
    eq_expr = " + ".join(f"(abs(v - {k}) < 0.5)" for k, (_, car, _) in G.CATALOGO.items() if car != "linear")
    md.fcn("cv_fv", [("v", "c_valvula")], cv_expr, "Cv da válvula instalada")
    md.fcn("eq_fv", [("v", "c_valvula")], eq_expr, "Válvula instalada é igual porcentagem (1) ou linear (0)")
    md.fcn("kvf", [("x", "abertura"), ("c", "cv_fv"), ("e", "eq_fv")],
           f"c/1.156*((e < 0.5)*x + (e > 0.5)*({G.R_EP}^x - 1)/{G.R_EP - 1})", "Kv·f(x) (m³/h·bar^-½)")
    hidro = g.rho_alim * G.G_GRAV * g.h_estatica / 1e5
    md.fcn("dp_disp", [("b", "c_pbomba")], pos(f"{g.p_bomba_shutoff}*b/100 - {g.p_tambor_g} - {hidro:.4f}"),
           "ΔP disponível bomba − tambor − coluna (bar)")
    md.fcn("qfw", [("k", "kvf"), ("d", "dp_disp")],
           f"k*sqrt(d/{g.g_alim:.4f})/sqrt(1 + k*k*{g.k_linha}/{g.g_alim:.4f})*{g.rho_alim}/1000",
           "Vazão de água de alimentação (t/h): Q = Kv·f·√(ΔPv/G), ΔPv = ΔPdisp − k·Q²")

    # --- tambor (nível físico h acima do fundo, m) --------------------------------------------------
    h_inf = (g.d_tambor - g.h_tomadas) / 2
    h0 = h_inf + 0.5 * g.h_tomadas
    k_inch = 0.2 * g.h_tomadas / g.mcr
    base = f"3.6/({g.rho_agua}*{g.area_espelho})"
    md.fcn("dh_in", [("q", "qfw"), ("h", "tambor")], f"q*(h < {g.d_tambor})/{base}", "Entrada de água (m/s)")
    md.fcn("dh_out", [("q", "qs"), ("h", "tambor")], f"(q + {g.purga})*(h > 0)/{base}", "Saída de vapor + purga (m/s)")
    md.acumulador("tambor", "dh_in", "dh_out", round(h0, 4), "Nível físico no tambor (m)")
    md.fcn("h_aparente", [("h", "tambor"), ("q", "qs"), ("qf", "qs_lento"), ("k", "c_inchamento")],
           f"h + {k_inch:.5f}*k*(q - qf)", "Nível aparente (m), com inchamento/contração")
    md.fcn("nivel_pct", [("h", "h_aparente")], f"(h - {h_inf:.4f})/{g.h_tomadas}*100", "Nível entre tomadas (%) - visor LG-101")
    md.fcn("h_rel", [("h", "h_aparente")], lim(f"h - {h_inf:.4f}", 0, g.h_tomadas), "Coluna de água acima da tomada inferior (m)")

    # --- LT-101: HIGH = tomada inferior; LOW = perna de referência (condensado) ---------------------
    p_tambor = round(g.p_tambor_g * G.MMH2O_POR_BAR, 1)
    md.fcn("lt_high", [("h", "h_rel")],
           f"{p_tambor} + 1000*({g.sg_agua:.5f}*h + {g.sg_vapor:.5f}*({g.h_tomadas} - h) + {g.sg_cond:.5f}*{g.desnivel_lt})",
           "LT-101 HIGH (mmH2O)")
    md.fcn("lt_low", [("h", "h_rel")], f"{p_tambor} + 1000*{g.sg_cond:.5f}*({g.h_tomadas} + {g.desnivel_lt}) + 0*h",
           "LT-101 LOW (mmH2O)")
    # --- FT-101 (FE-101, vapor) e FT-102 (FE-102, água): ΔP = (Q/K)² --------------------------------
    p_agua = round((g.p_tambor_g + 0.5 * (g.p_bomba_shutoff - g.p_tambor_g)) * G.MMH2O_POR_BAR, 1)
    md.fcn("fs_high", [("q", "qs")], f"{p_tambor} + 1000*{g.sg_cond:.5f}*1.0 + (q/{g.k_ft101:.6f})^2", "FT-101 HIGH (mmH2O)")
    md.fcn("fs_low", [("q", "qs")], f"{p_tambor} + 1000*{g.sg_cond:.5f}*1.0 + 0*q", "FT-101 LOW (mmH2O)")
    md.fcn("fw_high", [("q", "qfw")], f"{p_agua} + 1000*{g.sg_cond:.5f}*1.0 + (q/{g.k_ft102:.6f})^2", "FT-102 HIGH (mmH2O)")
    md.fcn("fw_low", [("q", "qfw")], f"{p_agua} + 1000*{g.sg_cond:.5f}*1.0 + 0*q", "FT-102 LOW (mmH2O)")
    for nome, rot in (("lt_high", "LT-101 HIGH (mmH2O)"), ("lt_low", "LT-101 LOW (mmH2O)"), ("fs_high", "FT-101 HIGH (mmH2O)"),
                      ("fs_low", "FT-101 LOW (mmH2O)"), ("fw_high", "FT-102 HIGH (mmH2O)"), ("fw_low", "FT-102 LOW (mmH2O)")):
        tunel_saida(nome, nome, rot)

    # --- IHM -> CLP (cada ajuste passa por um bloco antes do túnel de saída) ------------------------
    for nome, origem in (("sp_nivel", "c_sp"), ("kp_lic", "c_kp_lic"), ("ti_lic", "c_ti_lic"), ("k_ff", "c_kff"),
                         ("kp_fic", "c_kp_fic"), ("ti_fic", "c_ti_fic"), ("modo_auto", "c_modo"), ("mv_manual", "c_mv")):
        md.fcn(f"ihm_{nome}", [("v", origem)], "v", f"IHM {ROTULO_PINO[nome]}")
        tunel_saida(nome, f"ihm_{nome}", f"IHM {ROTULO_PINO[nome]}")

    # =========================================================================================
    # Desenho estático do sinótico
    # =========================================================================================
    def linha(pts, cor, larg, tracejado=None):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            s = {"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": cor, "strokeWidth": larg, "strokeLinecap": "round"}
            if tracejado:
                s["strokeDasharray"] = tracejado
            shapes.append(s)

    def texto(x, y, valor, tam=16, cor="#1f2937", ancora="middle", peso=None):
        s = {"kind": "text", "x": x, "y": y, "value": valor, "fontSize": tam, "textAnchor": ancora, "color": cor,
             "fontFamily": "Arial, Helvetica, sans-serif"}
        if peso:
            s["fontWeight"] = peso
        shapes.append(s)

    def seta(x1, y1, x2, y2, cor="#000000"):
        shapes.append({"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": cor, "strokeWidth": 1.6})
        ang = math.atan2(y2 - y1, x2 - x1)
        a, b = 13, 5.5
        p1 = (x2 - a * math.cos(ang) + b * math.sin(ang), y2 - a * math.sin(ang) - b * math.cos(ang))
        p2 = (x2 - a * math.cos(ang) - b * math.sin(ang), y2 - a * math.sin(ang) + b * math.cos(ang))
        shapes.append({"kind": "polygon", "points": [{"x": round(x2, 1), "y": round(y2, 1)}, {"x": round(p1[0], 1), "y": round(p1[1], 1)},
                                                       {"x": round(p2[0], 1), "y": round(p2[1], 1)}], "fill": cor, "stroke": cor, "strokeWidth": 1})

    def placa(x, y, alt=24):
        for dx in (-6, 6):
            shapes.append({"kind": "line", "x1": x + dx - 3, "y1": y - alt / 2, "x2": x + dx + 3, "y2": y + alt / 2,
                           "stroke": "#111111", "strokeWidth": 5, "strokeDasharray": "8 4"})

    shapes.append({"kind": "rect", "x": 0, "y": 0, "w": W, "h": H, "fill": "#ffffff", "stroke": "#94a3b8", "strokeWidth": 2})
    contorno = [m(130, 340), m(320, 340), m(320, 315), m(480, 235), m(512, 235), m(512, 780), m(545, 805),
                m(545, 832), m(100, 832), m(100, 805), m(130, 780)]
    pts = " ".join(f"{x},{y}" for x, y in contorno)
    shapes.append({"kind": "svg", "value": (
        "<defs><pattern id=\"ii2p13-tijolo\" width=\"64\" height=\"28\" patternUnits=\"userSpaceOnUse\">"
        "<rect width=\"64\" height=\"28\" fill=\"#808000\"/>"
        "<path d=\"M0 0.5H64M0 14H64M0 27.5H64M16 0V14M48 14V28\" stroke=\"#2b2b00\" stroke-width=\"1.6\" fill=\"none\"/>"
        "</pattern></defs>"
        f"<polygon points=\"{pts}\" fill=\"url(#ii2p13-tijolo)\" stroke=\"#000000\" stroke-width=\"7\" stroke-linejoin=\"round\"/>")})
    cx = TAMBOR["cx"]
    t_top, t_bot = TAMBOR["cy"] + 60, LAMA["cy"] - 52
    linha([(cx, t_top), (cx, t_bot)], COR_AGUA, LARG_AGUA)
    for xs in ([cx - 38, cx - 46, cx - 46, cx - 26], [cx + 38, cx + 50, cx + 50, cx + 28],
               [cx - 74, cx - 90, cx - 90, cx - 52], [cx + 74, cx + 92, cx + 92, cx + 54]):
        linha([(xs[0], t_top - 8), (xs[1], t_top + 40), (xs[2], t_bot - 60), (xs[3], t_bot + 4)], COR_AGUA, LARG_AGUA)
    shapes.append({"kind": "ellipse", "cx": LAMA["cx"], "cy": LAMA["cy"], "rx": LAMA["rx"], "ry": LAMA["ry"],
                   "fill": COR_TAMBOR, "stroke": "#00008b", "strokeWidth": 1.5})
    topo = TAMBOR["cy"] - TAMBOR["ry"]
    shapes.append({"kind": "path", "d": f"M {cx} {topo + 6} L {cx} {Y_VAPOR + 40} Q {cx} {Y_VAPOR} {cx - 40} {Y_VAPOR} L 8 {Y_VAPOR}",
                   "stroke": COR_VAPOR, "fill": "none", "strokeWidth": LARG_VAPOR, "strokeLinecap": "round"})
    texto(m(277, 0)[0], Y_VAPOR - 26, "Vapor", 38, "#5f5f5f", peso="bold")
    placa(FE101_X, Y_VAPOR, 30)
    texto(FE101_X, Y_VAPOR - 30, "FE-101", 20, "#374151", peso="bold")
    shapes.append({"kind": "ellipse", "cx": cx, "cy": TAMBOR["cy"], "rx": TAMBOR["rx"], "ry": TAMBOR["ry"],
                   "fill": COR_TAMBOR, "stroke": "#00008b", "strokeWidth": 1.5})
    ft = LD["FT-101"]
    xh, xl = FE101_X + 34, FE101_X - 34
    for xt, dy in ((xh, LD_HIGH), (xl, LD_LOW)):
        shapes.append({"kind": "rect", "x": xt - 7, "y": Y_VAPOR + 10, "w": 14, "h": 16, "fill": "#d1d5db", "stroke": "#4b5563", "strokeWidth": 1.2})
        linha([(xt, Y_VAPOR + 5), (xt, Y_VAPOR + 10)], COR_VAPOR, LARG_IMPULSO)
        linha([(xt, Y_VAPOR + 26), (xt, ft["y"] + dy), (ft["x"] - 22, ft["y"] + dy)], COR_VAPOR, LARG_IMPULSO)
    texto(xh + 6, Y_VAPOR + 48, "H", 17, "#374151", "start", "bold")
    texto(xl - 6, Y_VAPOR + 48, "L", 17, "#374151", "end", "bold")
    xlg = TAMBOR["cx"] - TAMBOR["rx"] - 62
    for y in (Y_TOMADA_SUP, Y_TOMADA_INF):
        linha([(x_elipse(TAMBOR, y, -1), y), (xlg + 18, y)], COR_AGUA, LARG_IMPULSO)
    texto(xlg + 18, Y_TOMADA_SUP - 14, "LG-101", 19, "#ffffff", peso="bold")
    lt = LD["LT-101"]
    linha([(x_elipse(TAMBOR, Y_TOMADA_INF), Y_TOMADA_INF), (lt["x"] - 22, Y_TOMADA_INF)], COR_AGUA, LARG_IMPULSO)
    x_volta, y_baixo = lt["x"] - 40, lt["y"] + LD_H + 18
    linha([(x_elipse(TAMBOR, Y_TOMADA_SUP), Y_TOMADA_SUP), (X_PERNA_REF - 10, Y_TOMADA_SUP)], COR_AGUA, LARG_IMPULSO)
    shapes.append({"kind": "rect", "x": X_PERNA_REF - 12, "y": Y_TOMADA_SUP - 14, "w": 24, "h": 30, "rx": 4,
                   "fill": "#9ca3af", "stroke": "#374151", "strokeWidth": 1.5})
    linha([(X_PERNA_REF, Y_TOMADA_SUP + 16), (X_PERNA_REF, y_baixo), (x_volta, y_baixo), (x_volta, lt["y"] + LD_LOW),
           (lt["x"] - 22, lt["y"] + LD_LOW)], COR_AGUA, LARG_IMPULSO)
    texto(X_PERNA_REF + 18, Y_TOMADA_SUP + 2, "pote de", 16, "#374151", "start")
    texto(X_PERNA_REF + 18, Y_TOMADA_SUP + 20, "condensado", 16, "#374151", "start")
    texto(X_PERNA_REF + 10, (Y_TOMADA_SUP + y_baixo) / 2 + 40, "perna de", 16, "#374151", "start")
    texto(X_PERNA_REF + 10, (Y_TOMADA_SUP + y_baixo) / 2 + 58, "referência", 16, "#374151", "start")
    texto(lt["x"] - 30, Y_TOMADA_INF - 8, "H", 17, "#374151", "end", "bold")
    texto(lt["x"] - 30, lt["y"] + LD_LOW + 20, "L", 17, "#374151", "end", "bold")
    y_ent = Y_TOMADA_INF + 120
    x_ent = x_elipse(TAMBOR, TAMBOR["cy"] + 60) - 6
    linha([(W - 8, Y_AGUA), (X_RISER, Y_AGUA), (X_RISER, y_ent), (PAREDE_DIR + 10, y_ent), (x_ent, TAMBOR["cy"] + 60)],
          COR_AGUA, LARG_AGUA)
    texto(m(1196, 0)[0] + 60, Y_AGUA + 46, "Água", 38, COR_AGUA, peso="bold")
    placa(FE102_X, Y_AGUA, 28)
    texto(FE102_X, Y_AGUA - 26, "FE-102", 20, "#374151", peso="bold")
    ftw = LD["FT-102"]
    xh, xl = FE102_X + 34, FE102_X - 34
    for xt, dy in ((xh, LD_HIGH), (xl, LD_LOW)):
        linha([(xt, Y_AGUA), (xt, ftw["y"] + dy), (ftw["x"] - 22, ftw["y"] + dy)], COR_AGUA, LARG_IMPULSO)
    texto(xh + 6, Y_AGUA + 42, "H", 17, "#374151", "start", "bold")
    texto(xl - 6, Y_AGUA + 42, "L", 17, "#374151", "end", "bold")
    # válvula FV-102 (globo + atuador de diafragma) e a tubulação de ar do FY-102
    vx, vy = FV102_X, Y_AGUA
    for sx in (-1, 1):
        shapes.append({"kind": "polygon", "points": [{"x": vx + sx * 28, "y": vy - 15}, {"x": vx, "y": vy}, {"x": vx + sx * 28, "y": vy + 15}],
                       "fill": COR_AGUA, "stroke": "#000000", "strokeWidth": 1.5})
    linha([(vx, vy), (vx, vy - 44)], "#000000", 2)
    shapes.append({"kind": "path", "d": f"M {vx - 22} {vy - 44} A 22 16 0 0 1 {vx + 22} {vy - 44} Z",
                   "fill": "#ffffff", "stroke": "#000000", "strokeWidth": 2})
    texto(vx - 34, vy - 32, "FV-102", 20, "#374151", "end", "bold")
    ar_y = vy - 52
    linha([(FY["x"] + 115, FY["y"] + 72), (FY["x"] + 115, ar_y), (vx + 20, ar_y)], "#ea580c", 3, "9 5")
    texto(FY["x"] + 122, ar_y + 22, "ar (OUT1)", 15, "#ea580c", "start")
    texto(FY["x"] + 115, FY["y"] + 222, "FY-102 · posicionador", 17, "#374151", "middle", "bold")
    linha([(vx, vy + 15), (vx, FY["y"] + FY_POS - 20)], "#6b7280", 1.5, "3 4")
    # diagrama de controle (bolhas e setas)
    for (bx, by), rotulo, cor in BOLHAS.values():
        shapes.append({"kind": "ellipse", "cx": bx, "cy": by, "rx": BOLHA_RX, "ry": BOLHA_RY, "fill": cor, "stroke": "#000000", "strokeWidth": 1.3})
        texto(bx, by + 12, rotulo, 34, "#000000", peso="bold")
    (avx, avy), (pmx, pmy), (anx, any_) = BOLHAS["ai_vapor"][0], BOLHAS["pid_mestre"][0], BOLHAS["ai_nivel"][0]
    (smx, smy), (pex, pey), (aax, aay), (aox, aoy) = (BOLHAS[k][0] for k in ("soma", "pid_escravo", "ai_agua", "ao"))
    linha([(avx + BOLHA_RX, avy), (smx, avy)], "#000000", 1.6)
    seta(smx, avy, smx, smy - BOLHA_RY)
    seta(pmx + BOLHA_RX, pmy, smx - BOLHA_RX, smy)
    seta(anx, any_ - BOLHA_RY, pmx, pmy + BOLHA_RY)
    seta(smx, smy + BOLHA_RY, pex, pey - BOLHA_RY)
    linha([(aax, aay - BOLHA_RY), (aax, pey)], "#000000", 1.6)
    seta(aax, pey, pex - BOLHA_RX, pey)
    seta(pex, pey + BOLHA_RY, aox, aoy - BOLHA_RY)
    linha([(aox, aoy + BOLHA_RY), (vx, vy - 60)], "#000000", 1.6, "7 5")
    for chave, txt, dx, dy in (("ai_vapor", "AI-02 · FT-101", 0, BOLHA_RY + 20), ("pid_mestre", "LIC-101 (mestre)", 0, -BOLHA_RY - 10),
                               ("ai_nivel", "AI-01 · LT-101", -BOLHA_RX - 8, 6), ("soma", "Σ (feedforward)", -BOLHA_RX - 8, -BOLHA_RY + 4),
                               ("pid_escravo", "FIC-102 (escravo)", -BOLHA_RX - 8, BOLHA_RY + 4),
                               ("ai_agua", "AI-03 · FT-102", BOLHA_RX + 8, 4), ("ao", "AO-01 → FY-102", -BOLHA_RX - 8, 4)):
        (bx, by) = BOLHAS[chave][0]
        texto(bx + dx, by + dy, txt, 19, "#374151", "end" if dx < 0 else ("start" if dx > 0 else "middle"))
    texto(X_LIC + DISP_W / 2, Y_LIC - 12, "Ajustes do LIC-101", 18, "#7c2d12", peso="bold")
    texto(X_DIR + DISP_W / 2, 212, "Ajuste do somador", 18, "#7c2d12", peso="bold")
    texto(X_DIR + DISP_W / 2, 410, "Ajustes do FIC-102", 18, "#7c2d12", peso="bold")
    texto(X_DIR + DISP_W / 2, 725, "Modo da malha", 18, "#7c2d12", peso="bold")
    texto(20 + DISP_W / 2, 690, "Perturbação", 18, "#7c2d12", peso="bold")
    texto(20 + DISP_W / 2, 140, "Carga da caldeira", 18, "#7c2d12", peso="bold")
    texto(1470 + DISP_W / 2, 1062, "Campo: válvula e ar", 18, "#166534", peso="bold")
    texto(X_PINO0 - 24, Y_PINO - 8, "IHM → CLP:", 17, "#475569", "end")
    texto(24, H - 14, f"Caldeira B-101 · GRUPO {g.nome} · nível do tambor a três elementos (II2P13)", 18, "#475569", "start", "bold")

    # =========================================================================================
    # Gráficos ligados à simulação (expostos no símbolo)
    # =========================================================================================
    def grafico(cid, type_id, props, x, y):
        md.comp(cid, type_id, props, x=x, y=y)
        expostos.append({"componentId": cid, "x": x, "y": y, "rotation": 0, "flipH": False, "flipV": False, "scale": 1,
                         "layer": len(expostos)})

    def binding(fonte, unidade, casas, lo_, hi_):
        return {"bindSource": fonte, "bindChannel": 0, "bindScale": 1, "bindOffset": 0, "bindMin": lo_, "bindMax": hi_,
                "bindUnit": unidade, "bindDecimals": casas}

    span = Y_TOMADA_INF - Y_TOMADA_SUP
    alt_lg = span / (108 / 130)
    grafico("g_lg101", "graphics.level_bar", {"width": round(alt_lg * 36 / 130, 1), "height": round(alt_lg, 1), "stroke": "#111827",
                                              "fill": "#e5e7eb", "strokeWidth": 1.5, "opacity": 1, "barColor": "#1d4ed8", "highLimit": 90,
                                              "lowLimit": 10, "showLimits": False, "showValue": False, "value": 50,
                                              **binding("nivel_pct", "%", 1, 0, 100)},
            round(xlg, 1), round(Y_TOMADA_SUP - 4 / 130 * alt_lg, 1))
    for cid, rotulo, unidade, casas, lo_, hi_, x, y, cor in AJUSTES:
        traco, fundo = ("#7c2d12", "#fff7ed") if cor == "ihm" else ("#166534", "#f0fdf4")
        grafico(f"g_{cid}_disp", "graphics.value_display",
                {"width": DISP_W, "height": DISP_H, "stroke": traco, "fill": fundo, "strokeWidth": 1.5, "opacity": 1,
                 "label": rotulo, "valueColor": traco, "value": valores[cid], **binding(cid, unidade, casas, lo_, hi_)}, x, y)
        grafico(f"g_{cid}_slider", "graphics.slider",
                {"width": SLID_W, "height": SLID_H, "stroke": "currentColor", "fill": "#ffffff", "strokeWidth": 1.5, "opacity": 1,
                 "showTicks": True, "value": valores[cid], **binding(cid, unidade, casas, lo_, hi_),
                 "actionTarget": cid, "actionProperty": "value", "actionMode": "set", "actionValue": str(valores[cid]),
                 "actionReleaseValue": "0", "actionStep": 1 if cid == "c_valvula" else (0.1 if cid == "c_suprimento" else 1),
                 "actionMin": lo_, "actionMax": hi_}, x, y + DISP_H + 2)
    grafico("g_modo", "graphics.hmi_toggle",
            {"width": MODO_W, "height": MODO_H, "stroke": "currentColor", "fill": "#94a3b8", "strokeWidth": 1.5, "opacity": 1,
             "onText": "AUTO", "offText": "MAN", "value": 100 if valores["c_modo"] > 2.5 else 0,
             **binding("c_modo", "", 0, 0, 5), "bindThreshold": 2.5, "bindInvert": False,
             "actionTarget": "c_modo", "actionProperty": "value", "actionMode": "toggle", "actionValue": "5",
             "actionReleaseValue": "0", "actionStep": 1, "actionMin": 0, "actionMax": 5}, MODO_POS[0], MODO_POS[1])
    # indicador mecânico de curso da haste (régua da válvula), em mm
    grafico("g_curso", "graphics.value_display",
            {"width": 150, "height": 62, "stroke": "#374151", "fill": "#f8fafc", "strokeWidth": 1.5, "opacity": 1,
             "label": "Régua da haste FV-102", "valueColor": "#111827", "value": round(ini["stem"], 1),
             **binding("stem", "mm", 1, 0, curso)}, FV102_X - 230, Y_AGUA - 150)

    # =========================================================================================
    # Pinos do símbolo
    # =========================================================================================
    def pino(pid, tipo, x, y, angulo, rotulo):
        pinos.append({"id": pid, "kind": tipo, "x": round(x, 1), "y": round(y, 1), "angle": angulo, "length": PIN_LEAD, "label": rotulo})

    for tag, nome_h, nome_l in (("LT-101", "lt_high", "lt_low"), ("FT-101", "fs_high", "fs_low"), ("FT-102", "fw_high", "fw_low")):
        pino(nome_h, "ANALOG_OUT", LD[tag]["x"] - 22, LD[tag]["y"] + LD_HIGH, 0, "")
        pino(nome_l, "ANALOG_OUT", LD[tag]["x"] - 22, LD[tag]["y"] + LD_LOW, 0, "")
    pino("fv_sup", "ANALOG_OUT", FY["x"] - 22, FY["y"] + FY_SUP, 0, "")
    pino("fv_out1", "ANALOG_IN", FY["x"] - 22, FY["y"] + FY_OUT1, 0, "")
    pino("fv_pos", "ANALOG_OUT", FY["x"] - 22, FY["y"] + FY_POS, 0, "")
    for pid in PINOS_INFERIORES:
        pino(pid, "ANALOG_OUT", x_pino_inferior(pid), Y_PINO - PIN_LEAD, 90, ROTULO_PINO[pid])

    return {
        "schemaVersion": 3,
        "typeId": "subsystem.local.caldeira_b101",
        "name": f"Caldeira B-101 — grupo {g.nome} (II2P13)",
        "language": "pt-BR",
        "folderPath": ["Modelos"],
        "workspaceSection": "process",
        "help": {"description": (
            "Caldeira aquatubular com tambor de vapor: balanço de massa no tambor, inchamento/contração, vazão de vapor "
            "pela demanda, válvula FV-102 com atuador pneumático comandado pelo FY-102 (OUT1) e vazão instalada "
            "Q = Kv·f(x)·√(ΔPv/G) com bomba e perdas de linha; tomadas de pressão do LT-101 (perna de referência úmida), "
            "FT-101 (FE-101, vapor) e FT-102 (FE-102, água) em mmH2O@20C. Ajustes da IHM e do campo (válvula instalada, "
            "suprimento de ar) nas Propriedades exportadas e no sinótico. Gerado por ferramentas/gerar_projeto.py.")},
        "components": md.finalizar().comps,
        "topology": {"revision": 0, "nodes": [], "conductors": md.fios},
        "interface": interface,
        "symbolMode": "custom",
        "symbol": {"width": W, "height": H, "border": False, "shapes": shapes, "pins": pinos},
        "exposedComponents": expostos,
        "exportedPropertyComponentIds": [c[0] for c in CONSTANTES],
    }


# =============================================================================================
# LD301 e FY301
# =============================================================================================
def _variaveis(lib: str, filho: str) -> list:
    with open(lib, encoding="utf-8-sig") as f:
        doc = json.load(f)
    inner = next(c for c in doc["components"] if c["id"] == filho)
    return json.loads(inner["properties"]["hartVariablesJson"])


def ld301_props(cfg: dict, serial: int) -> dict:
    variaveis = _variaveis(LD301_LIB, "ld301")
    for v in variaveis:
        if v["id"] == "PV":
            v.update(lowerRangeValue=cfg["lrv"], upperRangeValue=cfg["urv"], dampingValue=cfg["damping"],
                     transducerSerialNumber=serial, value=0.0)
        elif v["id"] == "display.firstVariable":
            v["value"] = cfg["display1"]
        elif v["id"] == "display.secondVariable":
            v["value"] = cfg["display2"]
        elif v["id"] == "userUnit.byte0":
            v["value"] = 0 if cfg.get("unidade_usuario") else 255
        elif v["id"] == "userUnit.selectedUnit":
            v["value"] = cfg.get("unidade_usuario", {}).get("codigo", 57)
        elif v["id"] == "userUnit.label":
            v["text"] = cfg.get("unidade_usuario", {}).get("rotulo", "%")
        elif v["id"] == "pvUserUnit":
            uu = cfg.get("unidade_usuario", {"codigo": 57, "rotulo": "%", "lrv": 0.0, "urv": 100.0})
            v.update(deviceVariableUnit=uu["codigo"], unit=uu["rotulo"], lowerRangeValue=uu["lrv"], upperRangeValue=uu["urv"])
    props = {"@ld301.tag": cfg["tag"], "@ld301.descriptor": cfg["descriptor"], "@ld301.message": cfg["message"],
             "@ld301.pollingAddress": cfg["polling"], "@ld301.uniqueId": cfg["unique_id"],
             "@ld301.dateDay": cfg.get("dia", 26), "@ld301.dateMonth": cfg.get("mes", 11), "@ld301.dateYear": cfg.get("ano", 126),
             "@ld301.hartVariablesJson": json.dumps(variaveis, ensure_ascii=False, separators=(",", ":")),
             "@ld301.hartAdditionalJson": json.dumps({"pvTransferFunctionCode": cfg.get("funcao", 0)})}
    return props


def ld301_comissionado(g: G.Grupo) -> dict:
    return {
        "LT-101": {"tag": "LT-101", "descriptor": "NIVEL TAMBOR", "message": f"LT-101 NIVEL TAMBOR B-101 GRUPO {g.nome}",
                   "lrv": g.lt101_lrv, "urv": g.lt101_urv, "damping": 1.0, "polling": 0, "unique_id": "0B6511",
                   "display1": 3, "display2": 0},
        "FT-101": {"tag": "FT-101", "descriptor": "VAZAO VAPOR", "message": f"FT-101 0-{g.qmax_ft101:g} T/H RAIZ NO CLP",
                   "lrv": 0.0, "urv": g.ft101_urv, "damping": 0.5, "polling": 0, "unique_id": "0B6512", "display1": 2, "display2": 0},
        "FT-102": {"tag": "FT-102", "descriptor": "VAZAO AGUA ALIM", "message": f"FT-102 0-{g.qmax_ft102:g} T/H RAIZ NO CLP",
                   "lrv": 0.0, "urv": g.ft102_urv, "damping": 0.5, "polling": 0, "unique_id": "0B6513", "display1": 2, "display2": 0},
    }


def ld301_encontrado(g: G.Grupo) -> dict:
    fabrica = {"tag": "LD301", "descriptor": "SMAR LD301", "message": "CONFIGURACAO DE FABRICA", "lrv": 0.0, "urv": 5000.0,
               "damping": 0.0, "polling": 0, "display1": 3, "display2": 5, "dia": 3, "mes": 2, "ano": 125}
    multidrop = {"tag": "PT-310", "descriptor": "PRESSAO HEADER", "message": "REDE MULTIDROP SALA ELETRICA 3",
                 "lrv": 0.0, "urv": 5000.0, "damping": 2.0, "display1": 4, "display2": 5, "dia": 21, "mes": 8, "ano": 119}
    outra_area = {"tag": "FT-205", "descriptor": "VAZAO CONDENSADO", "message": "AREA 200 RETORNO DE CONDENSADO",
                  "lrv": 0.0, "urv": 2000.0, "damping": 4.0, "polling": 0, "display1": 4, "display2": 0,
                  "unidade_usuario": {"codigo": 19, "rotulo": "m3/h", "lrv": 0.0, "urv": 12.0}, "dia": 11, "mes": 5, "ano": 122}
    com_raiz = {"tag": "FT-118", "descriptor": "VAZAO GAS COMB", "message": "QUEIMADOR B-118 RAIZ NO TRANSMISSOR",
                "lrv": 0.0, "urv": 2500.0, "damping": 1.0, "polling": 0, "display1": 2, "display2": 0, "funcao": 1,
                "dia": 2, "mes": 9, "ano": 123}
    frio = {"tag": "LT-090", "descriptor": "NIVEL TANQUE", "message": "CALIBRADO A FRIO SEM PERNA UMIDA",
            "lrv": 0.0, "urv": 600.0, "damping": 0.0, "polling": 0, "display1": 3, "display2": 0, "dia": 14, "mes": 3, "ano": 124}
    planos = {
        "A": {"LT-101": fabrica, "FT-101": {**multidrop, "polling": 3}, "FT-102": outra_area},
        "B": {"LT-101": {**multidrop, "polling": 5}, "FT-101": fabrica, "FT-102": {**outra_area, "urv": 5000.0, "damping": 8.0}},
        "C": {"LT-101": frio, "FT-101": com_raiz, "FT-102": {**multidrop, "polling": 2}},
        "D": {"LT-101": fabrica, "FT-101": com_raiz, "FT-102": {**multidrop, "polling": 1}},
    }
    out = {}
    for i, tag in enumerate(("LT-101", "FT-101", "FT-102")):
        out[tag] = {**planos[g.nome][tag], "unique_id": f"0B651{i + 1}"}
    return out


def fy301_props(g: G.Grupo, comissionado: bool) -> dict:
    if not comissionado:
        return {}
    cfg = g.fy301_config
    variaveis = _variaveis(FY301_LIB, "fy301")
    lo, hi = (0.0, g.curso) if g.ar_para == "abrir" else (g.curso, 0.0)   # posição sem ar / com ar total (mm)
    for v in variaveis:
        vid = v["id"]
        if vid in cfg and vid not in ("tag", "flowChar"):
            v["value"] = cfg[vid]
        if vid in ("setup.rest", "setup.restMeasured"):
            v["value"] = lo
        if vid in ("setup.full", "setup.fullMeasured"):
            v["value"] = hi
        if vid == "travel.length":
            v["value"] = g.curso
    return {"@fy301.tag": "FY-102", "@fy301.descriptor": "POSICIONADOR FV102", "@fy301.message": f"FY-102 AGUA ALIM GRUPO {g.nome}",
            "@fy301.dateDay": 26, "@fy301.dateMonth": 11, "@fy301.dateYear": 126,
            "@fy301.hartVariablesJson": json.dumps(variaveis, ensure_ascii=False, separators=(",", ":")),
            "@fy301.hartAdditionalJson": json.dumps({"pvTransferFunctionCode": cfg["flowChar"]})}


# =============================================================================================
# Projeto .lsproj
# =============================================================================================
def largura_tunel(nome: str) -> float:
    n = len(nome)
    return 4 * n + (14 if n >= 6 else 10)


def gerar_lsproj(g: G.Grupo, comissionado: bool, ref_clp: str) -> dict:
    sub = gerar_subsistema(g, comissionado)
    geo = geometria_ld(g)
    LD = geo["ld"]
    comps: list[dict] = []
    fios: list[dict] = []

    def comp(cid, type_id, label, x, y, props=None, rot=0, **extra):
        e = {"id": cid, "typeId": type_id, "label": label, "showValue": False, "showDialValue": False,
             "visual": {"x": round(x, 1), "y": round(y, 1), "rotation": rot}, "properties": props or {}}
        e.update(extra)
        comps.append(e)
        return cid

    def tunel(cid, nome, px, py, pino_a_esquerda=False, rot=0):
        extra = {"flipH": True} if pino_a_esquerda else {}
        return comp(cid, "connectors.tunnel", nome, px - largura_tunel(nome), py - 6, {"name": nome}, rot, **extra)

    def fio(a, pa, b, pb, vertices=None):
        fios.append({"id": f"wire-ii2p13-{len(fios) + 1:03d}", "from": {"kind": "port", "componentId": a, "pinId": pa},
                     "to": {"kind": "port", "componentId": b, "pinId": pb}, "vertices": vertices or []})

    planta = comp("ii2p13-planta", "subsystem.local.caldeira_b101", "Caldeira B-101 (sinótico)", 0, 0)

    # --- transmissores e posicionador sobre o sinótico ------------------------------------------------
    cfgs = ld301_comissionado(g) if comissionado else ld301_encontrado(g)
    pinos_planta = {"LT-101": ("lt_high", "lt_low"), "FT-101": ("fs_high", "fs_low"), "FT-102": ("fw_high", "fw_low")}
    for i, tag in enumerate(("LT-101", "FT-101", "FT-102")):
        ld = LD[tag]
        cid = f"ii2p13-{tag.lower()}"
        comp(cid, "subcircuits.hart.smar_ld301", f"{tag} (SMAR LD301)", ld["x"] - PIN_LEAD, ld["y"], ld301_props(cfgs[tag], 653951 + i))
        h, l = pinos_planta[tag]
        fio(planta, h, cid, "high")
        fio(planta, l, cid, "low")
        for pino, sufixo, dy in (("loop_plus", "+", LD_HIGH), ("loop_minus", "-", LD_LOW)):
            tid = tunel(f"{cid}-tun{'p' if sufixo == '+' else 'n'}", f"{tag}{sufixo}", ld["x"] - PIN_LEAD + LD_W + 20, ld["y"] + dy,
                        pino_a_esquerda=True)
            fio(cid, pino, tid, "pin")
    fy = comp("ii2p13-fy-102", "subcircuits.hart.smar_fy301", "FY-102 (SMAR FY301)", FY["x"] - PIN_LEAD, FY["y"],
              fy301_props(g, comissionado))
    fio(planta, "fv_sup", fy, "supply")
    fio(fy, "out1", planta, "fv_out1")
    fio(planta, "fv_pos", fy, "position")
    for pino, sufixo, dy in (("loop_plus", "+", FY_LP), ("loop_minus", "-", FY_LN)):
        tid = tunel(f"ii2p13-fy-102-tun{'p' if sufixo == '+' else 'n'}", f"FY-102{sufixo}", FY["x"] - PIN_LEAD + FY_W + 22, FY["y"] + dy,
                    pino_a_esquerda=True)
        fio(fy, pino, tid, "pin")

    # --- painel (abaixo do sinótico) -------------------------------------------------------------------
    Y_BR = H + 52
    Y_AI = H + 420
    PX, PY = 1700.0, Y_AI - 10

    def moldura(cid, titulo, x, y, w, h, larg_titulo):
        comp(cid, "graphics.group_box", titulo, x, y,
             {"width": w, "height": h, "title": titulo, "titleSize": 16, "titleWidth": larg_titulo, "stroke": "#64748b",
              "fill": "none", "maskFill": "#ffffff", "strokeWidth": 1.5, "opacity": 1})

    moldura("ii2p13-q-ihm", "IHM → CLP: variáveis de ajuste (Sinal→Tensão)", 930, H + 18, 1310, 290, 420)
    moldura("ii2p13-q-ao", "Cartão AO-01 (4–20 mA) → FY-102 · modem HART FY-102 em CNCB3 (LasecFDT: COM23)", 10, H + 18, 900, 290, 690)
    moldura("ii2p13-q-ai", "Painel do CLP · cartão AI (shunt 250 Ω + filtro RC 10 kΩ/10 µF) · fontes 24 Vcc · modems HART (LasecFDT: COM20/21/22)",
            10, Y_AI - 110, 1570, 360, 960)
    moldura("ii2p13-q-clp", "CLP OpenPLC (IEC 61131-3) · TASK 100 ms", 1600, Y_AI - 110, 640, 360, 330)

    canais = [("LT-101", "AI_LT101", "AI-01"), ("FT-101", "AI_FT101", "AI-02"), ("FT-102", "AI_FT102", "AI-03")]
    for k, (tag, var, canal) in enumerate(canais):
        cnc, com = PORTAS[tag]
        bx = 40.0 + k * 520
        p = f"ii2p13-{canal.lower()}"
        fonte = comp(f"{p}-fonte", "sources.dc_voltage", f"Fonte 24 Vcc {canal}", bx, Y_AI + 8, {"voltage": G.V_FONTE}, 90, showValue=True)
        g1 = comp(f"{p}-gnd1", "other.ground", "GND", bx + 24, Y_AI + 100)
        amp = comp(f"{p}-amp", "meters.ampmeter", f"Amperímetro {canal}", bx + 80, Y_AI - 40, {"resistance": 1e-6})
        tpos = tunel(f"{p}-tunp", f"{tag}+", bx + 420, Y_AI, pino_a_esquerda=True)
        tneg = tunel(f"{p}-tunn", f"{tag}-", bx + 420, Y_AI + 110, pino_a_esquerda=True)
        shunt = comp(f"{p}-shunt", "passive.resistor", f"Shunt {canal} 250 Ω", bx + 324, Y_AI + 161, {"resistance": G.R_SHUNT}, 90, showValue=True)
        g2 = comp(f"{p}-gnd2", "other.ground", "GND", bx + 332, Y_AI + 230)
        modem = comp(f"{p}-modem", "protocol.hart.modem", f"Modem HART {tag} ({cnc} = LasecFDT {com})", bx + 370, Y_AI + 150,
                     {"pc_link": "serial", "port_name": cnc, "udp_address": "127.0.0.1", "udp_port": 5094 + k,
                      "auto_open": True, "connection": "parallel", "senseResistance": 250, "transmitAmplitudeMvpp": 500})
        rf = comp(f"{p}-rf", "passive.resistor", f"Filtro {canal} 10 kΩ", bx + 268, Y_AI + 145, {"resistance": 10000}, 180, showValue=True)
        cf = comp(f"{p}-cf", "passive.capacitor", f"Filtro {canal} 10 µF", bx + 234, Y_AI + 178, {"capacitance": 1e-5}, 90, showValue=True)
        g3 = comp(f"{p}-gnd3", "other.ground", "GND", bx + 242, Y_AI + 230)
        tai = tunel(f"{p}-tai", var, bx + 200, Y_AI + 150)
        fio(fonte, "pin-1", amp, "pin-1")
        fio(amp, "pin-2", tpos, "pin")
        fio(fonte, "pin-2", g1, "pin")
        fio(tneg, "pin", shunt, "pin-1", [{"x": bx + 340, "y": Y_AI + 110}])
        fio(shunt, "pin-2", g2, "pin")
        fio(shunt, "pin-1", rf, "pin-1")
        fio(rf, "pin-2", cf, "pin-1", [{"x": bx + 250, "y": Y_AI + 150}])
        fio(cf, "pin-2", g3, "pin")
        fio(rf, "pin-2", tai, "pin")
        fio(modem, "loop_plus", tneg, "pin", [{"x": bx + 356, "y": Y_AI + 158}, {"x": bx + 356, "y": Y_AI + 110}])
        fio(modem, "loop_minus", shunt, "pin-2", [{"x": bx + 356, "y": Y_AI + 174}, {"x": bx + 356, "y": Y_AI + 182}])

    # --- cartão AO-01: tensão do pino do CLP (= mA) -> fonte de corrente -> FY-102 -------------------
    Y_AO = H + 150
    t_ao = tunel("ii2p13-ao-t", "AO_FV102", 120, Y_AO)
    vs = comp("ii2p13-ao-sensor", "bridges.voltage_sensor", "AO-01: leitura do valor do CLP (mA)", 140, Y_AO - 40)
    g_vs = comp("ii2p13-ao-gnd1", "other.ground", "GND", 180, Y_AO + 70)
    esc = comp("ii2p13-ao-escala", "sl.fcn", "mA → A", 300, Y_AO - 40, {"Expr": "u(1)/1000", "SampleTime": "0.001"})
    fonte_i = comp("ii2p13-ao-fonte", "bridges.controlled_current_source", "AO-01: fonte de corrente 4–20 mA", 440, Y_AO - 40)
    g_cs = comp("ii2p13-ao-gnd2", "other.ground", "GND", 480, Y_AO + 70)
    amp = comp("ii2p13-ao-amp", "meters.ampmeter", "Amperímetro AO-01", 560, Y_AO - 100, {"resistance": 1e-6})
    t_fyp = tunel("ii2p13-ao-fyp", "FY-102+", 860, Y_AO - 80, pino_a_esquerda=True)
    t_fyn = tunel("ii2p13-ao-fyn", "FY-102-", 860, Y_AO + 60, pino_a_esquerda=True)
    g_fy = comp("ii2p13-ao-gnd3", "other.ground", "GND", 760, Y_AO + 100)
    cnc, com = PORTAS["FY-102"]
    modem = comp("ii2p13-ao-modem", "protocol.hart.modem", f"Modem HART FY-102 ({cnc} = LasecFDT {com})", 660, Y_AO,
                 {"pc_link": "serial", "port_name": cnc, "udp_address": "127.0.0.1", "udp_port": 5097,
                  "auto_open": True, "connection": "parallel", "senseResistance": 250, "transmitAmplitudeMvpp": 500})
    fio(t_ao, "pin", vs, "p")
    fio(vs, "n", g_vs, "pin")
    fio(vs, "value", esc, "in1")
    fio(esc, "out1", fonte_i, "command")
    fio(fonte_i, "n", g_cs, "pin")
    fio(fonte_i, "p", amp, "pin-1")
    fio(amp, "pin-2", t_fyp, "pin")
    fio(t_fyn, "pin", g_fy, "pin")
    fio(modem, "loop_plus", t_fyp, "pin")
    fio(modem, "loop_minus", g_fy, "pin")

    # --- CLP ---------------------------------------------------------------------------------------------
    exported = [{"ioId": n, "name": n, "direction": d, "iecType": t} for n, d, t, _ in CLP.IO]
    clp = comp("ii2p13-clp", "plc.instance", "CLP (OpenPLC / IEC 61131-3)", PX, PY,
               {"plcIecProjectRef": ref_clp, "plcArtifactRef": "", "plcEntryConfiguration": "", "plcTaskIntervalMs": 100},
               plc={"iecProjectRef": ref_clp, "exportedIoBindingVersion": 1, "exportedIo": exported},
               pins=[{"id": n, "x": 0, "y": i * 12} for i, (n, *_r) in enumerate(CLP.IO)])
    DY_CLP = [14, 27, 41, 55, 69, 82]
    for i, (n, *_r) in enumerate(CLP.IO):
        y = PY + DY_CLP[i // 2]
        if i % 2 == 0:
            t = tunel(f"ii2p13-clp-t{i}", n, PX - 40, y)
        else:
            t = tunel(f"ii2p13-clp-t{i}", n, PX + 130, y, pino_a_esquerda=True)
        fio(clp, n, t, "pin")

    # --- IHM -> CLP (Sinal->Tensão) ---------------------------------------------------------------------
    for pid, var in (("sp_nivel", "SP_NIVEL"), ("kp_lic", "KP_LIC"), ("ti_lic", "TI_LIC"), ("k_ff", "K_FF"),
                     ("kp_fic", "KP_FIC"), ("ti_fic", "TI_FIC"), ("modo_auto", "MODO_AUTO"), ("mv_manual", "MV_MANUAL")):
        x = x_pino_inferior(pid)
        cv = comp(f"ii2p13-ihm-{pid}", "bridges.controlled_voltage_source", f"IHM→CLP {var}", x - 64, Y_BR + 32, rot=90)
        tv = tunel(f"ii2p13-ihm-{pid}-t", var, x + 12, Y_BR + 150, rot=270)
        gv = comp(f"ii2p13-ihm-{pid}-g", "other.ground", "GND", x - 12 - 8, Y_BR + 150)
        fio(planta, pid, cv, "command")
        fio(cv, "p", tv, "pin")
        fio(cv, "n", gv, "pin")

    return {"schemaVersion": 2, "components": comps, "topology": {"revision": 1, "nodes": [], "conductors": fios},
            "visual": {"viewport": {"x": 20, "y": 10, "zoom": 0.6}, "wireRoutes": "explicit"}, "simulationSettings": {},
            "subsystems": [sub]}


def gravar(caminho: str, dados: dict) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("gravado", os.path.relpath(caminho, RAIZ))


def gerar_grupo(nome: str) -> None:
    g = G.GRUPOS[nome]
    pasta_aluno = os.path.join(RAIZ, "grupos", f"Grupo_{nome}")
    pasta_gab = os.path.join(RAIZ, "gabarito", f"Grupo_{nome}")
    gravar(os.path.join(pasta_aluno, "clp", f"CLP_Grupo_{nome}.lsplc"), CLP.lsplc(f"CLP_Grupo_{nome}", CLP.main_aluno()))
    gravar(os.path.join(pasta_aluno, f"II2P13_Grupo_{nome}.lsproj"), gerar_lsproj(g, False, f"clp/CLP_Grupo_{nome}.lsplc"))
    gravar(os.path.join(pasta_gab, "clp", f"CLP_Grupo_{nome}_GABARITO.lsplc"),
           CLP.lsplc(f"CLP_Grupo_{nome}_GABARITO", CLP.main_gabarito(g)))
    gravar(os.path.join(pasta_gab, f"II2P13_Grupo_{nome}_GABARITO.lsproj"),
           gerar_lsproj(g, True, f"clp/CLP_Grupo_{nome}_GABARITO.lsplc"))


if __name__ == "__main__":
    for nome in (sys.argv[1:] or list(G.GRUPOS)):
        gerar_grupo(nome.upper())
