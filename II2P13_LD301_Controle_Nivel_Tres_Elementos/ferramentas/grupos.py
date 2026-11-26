"""Dados de processo dos 4 grupos do trabalho II2P13 e as respostas (gabarito) calculadas a partir deles.

    python ferramentas/grupos.py          # imprime a folha de respostas de cada grupo

Fonte única dos números: o gerador dos projetos (`gerar_projeto.py`), o avaliador
(`corrigir_trabalho.py`), as folhas de dados e o GABARITO_PROFESSOR usam ESTE arquivo.

Convenções
- Pressão diferencial em mmH2O a 20 °C (código HART 4, a unidade do LD301): 1 mmH2O = 9,7890 Pa.
  Uma coluna de h metros de um fluido com densidade relativa SG (relativa à água a 20 °C,
  998,2 kg/m³) vale 1000·SG·h mmH2O.
- Placa de orifício (ISO 5167, com C e ε dados): qm = C/√(1−β⁴)·ε·(π/4)·d²·√(2·ρ·ΔP)  [kg/s, m, Pa].
  Assim Q[t/h] = K·√ΔP[mmH2O], com K = 3,6·C/√(1−β⁴)·ε·(π/4)·d²·√(2·ρ·9,789).
- Válvula (líquido, sem correções): Kv = Q[m³/h]·√(G/ΔP[bar]), Cv = 1,156·Kv, G = ρ/1000.
  Característica inerente: linear Cv/Cvmax = x; igual porcentagem (R = 50) Cv/Cvmax = (R^x − 1)/(R − 1).
- Bomba + linha: p1 − p2 na válvula = ΔP_disp − k·Q² (bar), ΔP_disp = pressão da bomba em vazão nula
  − pressão no tambor − coluna estática; k = perdas da linha (economizador, tubulação) por (m³/h)².
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

RHO_REF = 998.2                 # kg/m³, água a 20 °C (base do mmH2O@20C)
PA_POR_MMH2O = RHO_REF * 9.80665 / 1000.0   # 9,789 Pa
MMH2O_POR_BAR = 1e5 / PA_POR_MMH2O           # 10 215,5 mmH2O por bar
G_GRAV = 9.80665
R_EP = 50.0                     # rangeabilidade da igual porcentagem (válvula e FY301 "EP 1:50")
R_SHUNT = 250.0
V_FONTE = 24.0
PATM = 1.013                    # bar

# Catálogo de válvulas globo (dados didáticos): opção -> (diâmetro, característica, Cv a 100 %)
CATALOGO = {
    1: ('3/4"', "linear", 6.0),
    2: ('1"', "linear", 10.0),
    3: ('1 1/4"', "linear", 16.0),
    4: ('1 1/2"', "linear", 25.0),
    5: ('2"', "linear", 40.0),
    6: ('3"', "linear", 100.0),
    7: ('1"', "igual %", 9.0),
    8: ('1 1/2"', "igual %", 22.0),
    9: ('2"', "igual %", 36.0),
    10: ('3"', "igual %", 90.0),
    11: ('4"', "igual %", 160.0),
}
ABERTURA_MIN, ABERTURA_MAX = 20.0, 85.0     # critério de seleção (% do curso), como no caderno da II2P10


def cv_relativo(x: float, caracteristica: str) -> float:
    x = min(max(x, 0.0), 1.0)
    return x if caracteristica == "linear" else (R_EP ** x - 1.0) / (R_EP - 1.0)


def abertura_para(cv_rel: float, caracteristica: str) -> float:
    """Abertura (0-1) que dá a fração Cv/Cvmax."""
    if caracteristica == "linear":
        return cv_rel
    return math.log(1.0 + (R_EP - 1.0) * cv_rel) / math.log(R_EP)


def ep_posicionador(s: float) -> float:
    """Curva 'EP 1:50' do FY301 (s e saída em 0-1)."""
    return (R_EP ** min(max(s, 0.0), 1.0) - 1.0) / (R_EP - 1.0)


def ep_inversa(y: float) -> float:
    return math.log(1.0 + (R_EP - 1.0) * min(max(y, 0.0), 1.0)) / math.log(R_EP)


@dataclass
class Grupo:
    nome: str
    # --- tambor e LT-101 -------------------------------------------------------------------------
    p_tambor_abs: float          # bar abs
    rho_agua: float              # kg/m³, água saturada no tambor
    rho_vapor: float             # kg/m³, vapor saturado no tambor
    t_pernas: float              # °C, condensado nas pernas de impulso
    rho_cond: float              # kg/m³
    h_tomadas: float             # m, distância entre as tomadas (0-100 % de nível)
    desnivel_lt: float           # m, transmissor abaixo da tomada inferior
    d_tambor: float              # m
    area_espelho: float          # m², superfície livre equivalente (dinâmica)
    # --- vapor e FT-101 ------------------------------------------------------------------------------
    mcr: float                   # t/h, produção máxima contínua
    qmax_ft101: float            # t/h, fundo de escala do FT-101
    d_tubo_vapor: float          # mm, diâmetro interno
    d_orif_vapor: float          # mm
    c_vapor: float               # coeficiente de descarga
    eps_vapor: float             # fator de expansão
    # --- água de alimentação, FT-102 e FV-102 --------------------------------------------------------
    t_agua: float                # °C
    rho_alim: float              # kg/m³
    qmax_ft102: float            # t/h
    d_tubo_agua: float           # mm
    d_orif_agua: float           # mm
    c_agua: float
    caracteristica: str          # característica pedida pela engenharia ("linear" / "igual %")
    usa_ep_no_fy301: bool        # o almoxarifado só tem a outra característica: caracterizar no FY301
    p_bomba_shutoff: float       # bar g, bomba com vazão nula
    h_estatica: float            # m, tambor acima da bomba
    k_linha: float               # bar/(m³/h)², perdas de linha (economizador + tubulação)
    # --- atuador e FY301 ---------------------------------------------------------------------------------
    curso: float                 # mm
    ar_para: str                 # "abrir" (falha fecha) ou "fechar" (falha abre)
    mola: tuple                  # bar (início, fim do curso)
    suprimento_encontrado: float # bar, filtro-regulador como encontrado
    fy301_extra: dict            # ajustes particulares do grupo (ver fy301_config)
    # --- dinâmica e sintonia ---------------------------------------------------------------------------------
    purga_pct: float = 2.0       # % da MCR
    demanda_inicial: float = 60.0
    sintonia: dict = field(default_factory=dict)
    vazao_bomba_pct: float = 100.0

    # ==============================================================================================
    # Densidades relativas
    # ==============================================================================================
    @property
    def p_tambor_g(self) -> float:
        return round(self.p_tambor_abs - PATM, 2)

    @property
    def sg_agua(self) -> float:
        return self.rho_agua / RHO_REF

    @property
    def sg_vapor(self) -> float:
        return self.rho_vapor / RHO_REF

    @property
    def sg_cond(self) -> float:
        return self.rho_cond / RHO_REF

    # ==============================================================================================
    # LT-101 (HIGH na tomada inferior; LOW na perna de referência cheia de condensado)
    # ==============================================================================================
    def dp_lt101(self, nivel_frac: float) -> float:
        h = min(max(nivel_frac, 0.0), 1.0) * self.h_tomadas
        return 1000.0 * (self.sg_agua * h + self.sg_vapor * (self.h_tomadas - h) - self.sg_cond * self.h_tomadas)

    @property
    def lt101_lrv(self) -> float:
        return round(self.dp_lt101(0.0), 1)

    @property
    def lt101_urv(self) -> float:
        return round(self.dp_lt101(1.0), 1)

    # ==============================================================================================
    # Placas de orifício
    # ==============================================================================================
    @staticmethod
    def k_orificio(d_mm: float, D_mm: float, c: float, eps: float, rho: float) -> float:
        beta = d_mm / D_mm
        area = math.pi / 4.0 * (d_mm / 1000.0) ** 2
        return 3.6 * c / math.sqrt(1.0 - beta ** 4) * eps * area * math.sqrt(2.0 * rho * PA_POR_MMH2O)

    @property
    def k_ft101(self) -> float:
        return self.k_orificio(self.d_orif_vapor, self.d_tubo_vapor, self.c_vapor, self.eps_vapor, self.rho_vapor)

    @property
    def k_ft102(self) -> float:
        return self.k_orificio(self.d_orif_agua, self.d_tubo_agua, self.c_agua, 1.0, self.rho_alim)

    @property
    def ft101_urv(self) -> float:
        return round((self.qmax_ft101 / self.k_ft101) ** 2, 1)

    @property
    def ft102_urv(self) -> float:
        return round((self.qmax_ft102 / self.k_ft102) ** 2, 1)

    @property
    def beta_vapor(self) -> float:
        return self.d_orif_vapor / self.d_tubo_vapor

    @property
    def beta_agua(self) -> float:
        return self.d_orif_agua / self.d_tubo_agua

    # ==============================================================================================
    # Válvula FV-102
    # ==============================================================================================
    @property
    def purga(self) -> float:
        return self.mcr * self.purga_pct / 100.0

    @property
    def g_alim(self) -> float:
        return self.rho_alim / 1000.0

    @property
    def dp_disponivel(self) -> float:
        """bar: bomba em vazão nula − tambor (manométrica) − coluna estática."""
        return self.p_bomba_shutoff - self.p_tambor_g - self.rho_alim * G_GRAV * self.h_estatica / 1e5

    def m3h(self, q_th: float) -> float:
        return q_th * 1000.0 / self.rho_alim

    def dp_valvula(self, q_th: float, bomba_pct: float = 100.0) -> float:
        disp = self.p_bomba_shutoff * bomba_pct / 100.0 - self.p_tambor_g - self.rho_alim * G_GRAV * self.h_estatica / 1e5
        return disp - self.k_linha * self.m3h(q_th) ** 2

    def p1_p2(self, q_th: float) -> tuple[float, float]:
        """Pressões manométricas na entrada e na saída da válvula (bar g), para a folha de dados.

        A perda de linha é metade antes (sucção/descarga até a válvula) e metade depois (economizador)."""
        perda = self.k_linha * self.m3h(q_th) ** 2
        p1 = self.p_bomba_shutoff - 0.25 * perda
        p2 = p1 - self.dp_valvula(q_th)
        return round(p1, 2), round(p2, 2)

    def condicoes_valvula(self) -> dict:
        """Vazões de dimensionamento (t/h): mínima 35 %, normal 70 %, máxima 110 % da MCR (+ purga)."""
        return {nome: round(self.mcr * f + self.purga, 2) for nome, f in (("min", 0.35), ("normal", 0.70), ("max", 1.10))}

    def kv_requerido(self, q_th: float) -> float:
        p1, p2 = self.p1_p2(q_th)
        return self.m3h(q_th) * math.sqrt(self.g_alim / (p1 - p2))

    def cv_requerido(self, q_th: float) -> float:
        return 1.156 * self.kv_requerido(q_th)

    @property
    def caracteristica_corpo(self) -> str:
        """Característica do corpo instalado (a do catálogo usado)."""
        if self.usa_ep_no_fy301:
            return "linear" if self.caracteristica == "igual %" else "igual %"
        return self.caracteristica

    def aberturas(self, opcao: int) -> dict:
        _, car, cvmax = CATALOGO[opcao]
        return {k: 100.0 * abertura_para(self.cv_requerido(q) / cvmax, car) if self.cv_requerido(q) <= cvmax else float("inf")
                for k, q in self.condicoes_valvula().items()}

    @property
    def opcoes_validas(self) -> list[int]:
        out = []
        for op, (_, car, _) in CATALOGO.items():
            if car != self.caracteristica_corpo:
                continue
            ab = self.aberturas(op)
            if ab["min"] >= ABERTURA_MIN and ab["max"] <= ABERTURA_MAX:
                out.append(op)
        return out

    @property
    def valvula(self) -> int:
        """A menor válvula (menor Cv: menor custo e melhor resolução) que atende ao critério de abertura."""
        validas = self.opcoes_validas
        assert validas, f"grupo {self.nome}: nenhuma opção atende {ABERTURA_MIN}-{ABERTURA_MAX} %"
        return min(validas, key=lambda op: CATALOGO[op][2])

    @property
    def cv_valvula(self) -> float:
        return CATALOGO[self.valvula][2]

    def sinal_para_abertura(self, abertura_pct: float) -> float:
        """Sinal do CLP (% de 4-20 mA) que leva a válvula à abertura dada (curva do FY301)."""
        if self.usa_ep_no_fy301:
            return 100.0 * ep_inversa(abertura_pct / 100.0)
        return abertura_pct

    # ==============================================================================================
    # Atuador / FY301
    # ==============================================================================================
    @property
    def suprimento_minimo(self) -> float:
        return round(self.mola[1] + 0.4, 2)

    @property
    def suprimento_correto(self) -> float:
        return max(self.suprimento_encontrado, self.suprimento_minimo)

    @property
    def fy301_config(self) -> dict:
        """Configuração HART esperada do FY-102 (nomes das variáveis do LasecSimul)."""
        cfg = {
            "tag": "FY-102",
            "airTo": 0 if self.ar_para == "abrir" else 1,       # 0 Open, 1 Close
            "valve.action": 0,                                  # Direct: 20 mA = aberta
            "flowChar": 1 if self.usa_ep_no_fy301 else 0,       # 0 Linear, 1 EP 1:50
            "tso.cutoff": 0.0,
            "sp.rateUpTime": 0.0,
            "sp.rateDownTime": 0.0,
            "sp.lowLimit": 0.0,
            "sp.highLimit": 100.0,
            "deviation.deadband": 5.0,                          # alarme de desvio (fábrica 5 % / 10 s)
            "deviation.time": 10.0,
            "display.indication": 1,
            "curso_calibrado": self.curso,                      # |setup.full − setup.rest| (Auto Setup)
        }
        cfg.update(self.fy301_extra)
        return cfg

    # ==============================================================================================
    # Operação
    # ==============================================================================================
    @property
    def q_vapor_inicial(self) -> float:
        return self.mcr * self.demanda_inicial / 100.0

    @property
    def q_agua_inicial(self) -> float:
        return self.q_vapor_inicial + self.purga

    def abertura_equilibrio(self, q_th: float | None = None, bomba_pct: float = 100.0, opcao: int | None = None) -> float:
        """Abertura (% do curso) que dá a vazão q_th com a válvula escolhida (instalada)."""
        q_th = self.q_agua_inicial if q_th is None else q_th
        _, car, cvmax = CATALOGO[opcao or self.valvula]
        kv = cvmax / 1.156
        cv_rel = self.m3h(q_th) / kv / math.sqrt(self.dp_valvula(q_th, bomba_pct) / self.g_alim)
        return 100.0 * abertura_para(cv_rel, car)

    def corrente_lt(self, nivel_pct: float) -> float:
        return 4.0 + 16.0 * (self.dp_lt101(nivel_pct / 100.0) - self.lt101_lrv) / (self.lt101_urv - self.lt101_lrv)


# =================================================================================================
# Os quatro grupos
# =================================================================================================
GRUPOS = {
    "A": Grupo(
        nome="A", p_tambor_abs=11.0, rho_agua=882.6, rho_vapor=5.64, t_pernas=40, rho_cond=992.2,
        h_tomadas=0.60, desnivel_lt=1.50, d_tambor=1.00, area_espelho=0.80,
        mcr=20.0, qmax_ft101=25.0, d_tubo_vapor=254.5, d_orif_vapor=160.0, c_vapor=0.604, eps_vapor=0.995,
        t_agua=105, rho_alim=955.1, qmax_ft102=30.0, d_tubo_agua=77.9, d_orif_agua=46.5, c_agua=0.606,
        caracteristica="linear", usa_ep_no_fy301=False, p_bomba_shutoff=17.0, h_estatica=8.0, k_linha=0.0025,
        curso=20.0, ar_para="abrir", mola=(0.2, 1.0), suprimento_encontrado=1.4,
        fy301_extra={"tso.cutoff": 1.0},
        sintonia={"SP_NIVEL": 50.0, "KP_LIC": 0.6, "TI_LIC": 90.0, "K_FF": 1.0, "KP_FIC": 2.0, "TI_FIC": 3.0},
    ),
    "B": Grupo(
        nome="B", p_tambor_abs=16.0, rho_agua=862.8, rho_vapor=8.08, t_pernas=30, rho_cond=995.6,
        h_tomadas=0.80, desnivel_lt=2.00, d_tambor=1.20, area_espelho=1.20,
        mcr=30.0, qmax_ft101=36.0, d_tubo_vapor=254.5, d_orif_vapor=161.0, c_vapor=0.605, eps_vapor=0.996,
        t_agua=120, rho_alim=943.4, qmax_ft102=40.0, d_tubo_agua=102.3, d_orif_agua=51.5, c_agua=0.605,
        caracteristica="igual %", usa_ep_no_fy301=False, p_bomba_shutoff=24.0, h_estatica=9.0, k_linha=0.0012,
        curso=25.0, ar_para="fechar", mola=(0.4, 2.0), suprimento_encontrado=1.4,
        fy301_extra={"sp.lowLimit": 3.0},
        sintonia={"SP_NIVEL": 50.0, "KP_LIC": 0.9, "TI_LIC": 100.0, "K_FF": 1.0, "KP_FIC": 1.5, "TI_FIC": 4.0},
    ),
    "C": Grupo(
        nome="C", p_tambor_abs=8.0, rho_agua=896.9, rho_vapor=4.16, t_pernas=50, rho_cond=988.0,
        h_tomadas=0.50, desnivel_lt=1.20, d_tambor=0.90, area_espelho=0.60,
        mcr=12.0, qmax_ft101=15.0, d_tubo_vapor=202.7, d_orif_vapor=139.0, c_vapor=0.603, eps_vapor=0.994,
        t_agua=105, rho_alim=955.1, qmax_ft102=16.0, d_tubo_agua=62.7, d_orif_agua=33.5, c_agua=0.607,
        caracteristica="igual %", usa_ep_no_fy301=True, p_bomba_shutoff=13.0, h_estatica=6.0, k_linha=0.0060,
        curso=16.0, ar_para="abrir", mola=(0.8, 2.4), suprimento_encontrado=2.0,
        fy301_extra={},
        sintonia={"SP_NIVEL": 50.0, "KP_LIC": 0.4, "TI_LIC": 80.0, "K_FF": 1.0, "KP_FIC": 3.0, "TI_FIC": 3.0},
    ),
    "D": Grupo(
        nome="D", p_tambor_abs=20.0, rho_agua=849.6, rho_vapor=10.04, t_pernas=60, rho_cond=983.2,
        h_tomadas=0.70, desnivel_lt=1.80, d_tambor=1.10, area_espelho=1.60,
        mcr=40.0, qmax_ft101=50.0, d_tubo_vapor=254.5, d_orif_vapor=172.0, c_vapor=0.603, eps_vapor=0.996,
        t_agua=140, rho_alim=925.9, qmax_ft102=50.0, d_tubo_agua=102.3, d_orif_agua=55.5, c_agua=0.604,
        caracteristica="igual %", usa_ep_no_fy301=False, p_bomba_shutoff=27.0, h_estatica=10.0, k_linha=0.0008,
        curso=38.0, ar_para="fechar", mola=(0.4, 1.2), suprimento_encontrado=1.6,
        fy301_extra={"tso.cutoff": 2.0, "deviation.deadband": 3.0, "deviation.time": 5.0},
        sintonia={"SP_NIVEL": 50.0, "KP_LIC": 1.2, "TI_LIC": 120.0, "K_FF": 1.0, "KP_FIC": 1.0, "TI_FIC": 4.0},
    ),
}


def relatorio(g: Grupo) -> str:
    L = []
    L.append(f"=== GRUPO {g.nome} ===")
    L.append(f"Tambor {g.p_tambor_abs} bar abs ({g.p_tambor_g} bar g): SG água {g.sg_agua:.4f}, vapor {g.sg_vapor:.4f}, "
             f"condensado {g.sg_cond:.4f}")
    L.append(f"LT-101: LRV = {g.lt101_lrv} mmH2O, URV = {g.lt101_urv} mmH2O (span {g.lt101_urv - g.lt101_lrv:.1f})")
    L.append(f"FT-101: beta {g.beta_vapor:.4f}, K = {g.k_ft101:.5f} (t/h)/sqrt(mmH2O), URV = {g.ft101_urv} mmH2O para {g.qmax_ft101} t/h")
    L.append(f"FT-102: beta {g.beta_agua:.4f}, K = {g.k_ft102:.5f} (t/h)/sqrt(mmH2O), URV = {g.ft102_urv} mmH2O para {g.qmax_ft102} t/h")
    L.append(f"Válvula: ΔP disponível {g.dp_disponivel:.2f} bar, G = {g.g_alim:.4f}")
    for k, q in g.condicoes_valvula().items():
        p1, p2 = g.p1_p2(q)
        L.append(f"   {k:6s} {q:6.2f} t/h = {g.m3h(q):6.2f} m³/h  p1 {p1:6.2f}  p2 {p2:6.2f}  ΔP {p1 - p2:5.2f} bar  "
                 f"Kv {g.kv_requerido(q):6.2f}  Cv {g.cv_requerido(q):6.2f}")
    for op, (dn, car, cv) in CATALOGO.items():
        if car != g.caracteristica_corpo:
            continue
        ab = g.aberturas(op)
        L.append(f"   opção {op:2d} {dn:7s} {car:8s} Cv {cv:6.1f}: aberturas " +
                 ", ".join(f"{k} {v:5.1f} %" for k, v in ab.items()) + ("  <== ESCOLHA" if op in g.opcoes_validas else ""))
    L.append(f"   válvula escolhida: opção {g.valvula} (Cv {g.cv_valvula}); abertura em {g.q_agua_inicial:.2f} t/h = "
             f"{g.abertura_equilibrio():.1f} % -> sinal do CLP {g.sinal_para_abertura(g.abertura_equilibrio()):.1f} %")
    L.append(f"Atuador: ar para {g.ar_para}, curso {g.curso} mm, mola {g.mola} bar, suprimento encontrado {g.suprimento_encontrado} "
             f"-> mínimo {g.suprimento_minimo} bar")
    L.append(f"FY301: {g.fy301_config}")
    L.append(f"LT-101 a 50 %: {g.corrente_lt(50):.3f} mA")
    return "\n".join(L)


if __name__ == "__main__":
    for g in GRUPOS.values():
        print(relatorio(g))
        print()
