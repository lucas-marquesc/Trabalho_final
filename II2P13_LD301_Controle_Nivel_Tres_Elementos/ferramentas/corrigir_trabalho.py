"""Avaliador do trabalho II2P13: confere o que o grupo deixou salvo no .lsproj e no .lsplc.

    python ferramentas/corrigir_trabalho.py <pasta do grupo | projeto.lsproj> --grupo A [--sem-clp] [--dinamico]
                                            [--relatorio saida.md]

Tudo o que o grupo faz fica nos dois arquivos:
- .lsproj: configuração HART dos três LD301 e do FY301 escrita pelo LasecFDT (o LasecSimul copia a configuração
  do dispositivo para o projeto ao salvar ou parar a simulação), a calibração do Auto Setup do FY301, a válvula
  escolhida e o suprimento de ar ajustados no sinótico (propriedades exportadas da planta) e os ajustes da IHM;
- .lsplc: o programa do CLP. O MAIN tem de estar em Ladder; o avaliador compila o projeto como o LasecSimul e
  o executa no CLP do Core com vetores de teste (correntes conhecidas -> nível, vazões, falhas, saída).

Com --dinamico o projeto inteiro roda no Core (sem o VS Code) em AUTOMÁTICO com um degrau de carga.
O que não está nos arquivos (memória de cálculo, justificativas) é corrigido pelo relatório do grupo.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import grupos as G   # noqa: E402

UNIDADE_MMH2O = 4


class Nota:
    def __init__(self):
        self.itens: list[tuple[str, str, bool, float, str]] = []   # seção, item, ok, peso, detalhe

    def add(self, secao, item, ok, peso, detalhe=""):
        self.itens.append((secao, item, bool(ok), peso, detalhe))

    def total(self):
        peso = sum(i[3] for i in self.itens)
        feito = sum(i[3] for i in self.itens if i[2])
        return feito, peso

    def markdown(self, titulo):
        L = [f"# {titulo}", ""]
        secao = None
        for s, item, ok, peso, det in self.itens:
            if s != secao:
                L += ["", f"## {s}", "", "| | Item | Peso | Detalhe |", "|---|---|---|---|"]
                secao = s
            L.append(f"| {'✅' if ok else '❌'} | {item} | {peso:g} | {det} |")
        feito, peso = self.total()
        L += ["", f"**Nota automática: {feito:g} / {peso:g} ({100 * feito / peso:.0f} %)**" if peso else ""]
        return "\n".join(L)


def perto(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


# =================================================================================================
# Leitura do projeto
# =================================================================================================
def ler_projeto(caminho: str):
    if os.path.isdir(caminho):
        candidatos = [p for p in glob.glob(os.path.join(caminho, "*.lsproj"))]
        if len(candidatos) != 1:
            raise SystemExit(f"esperava um .lsproj em {caminho}, achei {candidatos}")
        caminho = candidatos[0]
    with open(caminho, encoding="utf-8") as f:
        return caminho, json.load(f)


def componente(doc, cid):
    return next((c for c in doc["components"] if c["id"] == cid), None)


def variaveis_hart(c, filho):
    txt = c["properties"].get(f"@{filho}.hartVariablesJson")
    return {v["id"]: v for v in json.loads(txt)} if txt else {}


def adicional_hart(c, filho):
    txt = c["properties"].get(f"@{filho}.hartAdditionalJson")
    return json.loads(txt) if txt else {}


def constante_planta(doc, cid):
    """Valor de uma constante exportada da planta: o da instância (@cid.value) ou o da definição."""
    planta = componente(doc, "ii2p13-planta")
    chave = f"@{cid}.value"
    if planta and chave in planta.get("properties", {}):
        return float(planta["properties"][chave])
    for sub in doc.get("subsystems", []):
        for c in sub.get("components", []):
            if c["id"] == cid:
                return float(c["properties"]["value"])
    return None


# =================================================================================================
# Transmissores e posicionador
# =================================================================================================
def avaliar_ld301(nota: Nota, doc, g: G.Grupo):
    esperado = {"LT-101": (g.lt101_lrv, g.lt101_urv), "FT-101": (0.0, g.ft101_urv), "FT-102": (0.0, g.ft102_urv)}
    for tag, (lrv, urv) in esperado.items():
        c = componente(doc, f"ii2p13-{tag.lower()}")
        sec = f"{tag} (LD301)"
        if not c:
            nota.add(sec, "transmissor presente no projeto", False, 4, "componente apagado")
            continue
        p = c["properties"]
        pv = variaveis_hart(c, "ld301").get("PV", {})
        span = abs(urv - lrv)
        tol = max(0.005 * span, 2.0)
        nota.add(sec, f"tag = {tag}", str(p.get("@ld301.tag", "")).strip().upper() == tag, 1, p.get("@ld301.tag", ""))
        nota.add(sec, "endereço de polling 0 (corrente 4–20 mA ativa)", int(p.get("@ld301.pollingAddress", -1)) == 0, 1.5,
                 str(p.get("@ld301.pollingAddress")))
        nota.add(sec, f"LRV = {lrv:g} mmH2O (±{tol:.1f})", perto(pv.get("lowerRangeValue"), lrv, tol), 2, f"{pv.get('lowerRangeValue')}")
        nota.add(sec, f"URV = {urv:g} mmH2O (±{tol:.1f})", perto(pv.get("upperRangeValue"), urv, tol), 2, f"{pv.get('upperRangeValue')}")
        unidade = pv.get("rangeUnitCode", pv.get("deviceVariableUnit"))
        nota.add(sec, "unidade mmH2O (código 4)", unidade == UNIDADE_MMH2O, 0.5, str(unidade))
        funcao = adicional_hart(c, "ld301").get("pvTransferFunctionCode", 0)
        nota.add(sec, "função de transferência LINEAR (raiz só no CLP)", funcao == 0, 1.5 if tag != "LT-101" else 0.5,
                 "linear" if funcao == 0 else f"código {funcao}")
        amort = pv.get("dampingValue")
        nota.add(sec, "amortecimento entre 0,2 e 2 s", amort is not None and 0.2 <= amort <= 2.0, 0.5, f"{amort} s")


def avaliar_fy301(nota: Nota, doc, g: G.Grupo):
    sec = "FY-102 (FY301) e FV-102"
    c = componente(doc, "ii2p13-fy-102")
    if not c:
        nota.add(sec, "posicionador presente no projeto", False, 6, "componente apagado")
        return
    p = c["properties"]
    v = variaveis_hart(c, "fy301")
    cfg = g.fy301_config
    val = lambda k: v.get(k, {}).get("value")   # noqa: E731
    nota.add(sec, "tag = FY-102", str(p.get("@fy301.tag", "")).strip().upper() == "FY-102", 1, p.get("@fy301.tag", "(fábrica: FY301)"))
    nota.add(sec, f"AIR_T = {'Open' if cfg['airTo'] == 0 else 'Close'} (atuador ar para {g.ar_para})", val("airTo") == cfg["airTo"], 2,
             {0: "Open", 1: "Close"}.get(val("airTo"), str(val("airTo"))) if v else "(fábrica: Open)")
    nota.add(sec, "ação direta (20 mA = válvula aberta)", val("valve.action") in (0, None), 1.5, str(val("valve.action")))
    curva = adicional_hart(c, "fy301").get("pvTransferFunctionCode", 0)
    nomes = {0: "Linear", 1: "EP 1:50", 2: "AR 1:50", 3: "Tabela"}
    nota.add(sec, f"caracterização = {nomes[cfg['flowChar']]}", curva == cfg["flowChar"], 2, nomes.get(curva, str(curva)))
    rest, full = val("setup.rest"), val("setup.full")
    calibrado = rest is not None and full is not None and rest >= 0 and full >= 0 and perto(abs(full - rest), g.curso, 0.6)
    nota.add(sec, f"Auto Setup feito com ar suficiente (curso calibrado = {g.curso:g} mm)", calibrado, 3,
             f"sem ar {rest} mm, ar total {full} mm" if v else "não calibrado")
    pv = v.get("PV", {})
    nota.add(sec, "faixa de entrada 4–20 mA (sem split range)", perto(pv.get("lowerRangeValue", 4), 4, 0.01) and perto(pv.get("upperRangeValue", 20), 20, 0.01),
             0.5, f"{pv.get('lowerRangeValue', 4)}–{pv.get('upperRangeValue', 20)} mA")
    nota.add(sec, "setpoint remoto (4–20 mA)", val("sp.mode") in (1, None), 0.5, str(val("sp.mode")))
    fabrica = {"tso.cutoff": 0.0, "sp.lowLimit": 0.0, "deviation.deadband": 5.0, "deviation.time": 10.0}
    for chave, rotulo in (("tso.cutoff", "TSO (fechamento estanque) %"), ("sp.lowLimit", "limite inferior do setpoint %"),
                          ("deviation.deadband", "alarme de desvio: banda %"), ("deviation.time", "alarme de desvio: tempo (s)")):
        alvo = cfg[chave]
        lido = val(chave) if v else None
        if lido is None:
            lido = fabrica[chave]
        exigido = alvo != fabrica[chave]
        nota.add(sec, f"{rotulo} = {alvo:g}" + ("" if exigido else " (fábrica)"), perto(lido, alvo, 0.05 + 0.02 * alvo),
                 1.5 if exigido else 0.25, f"{lido:g}")
    opcao = constante_planta(doc, "c_valvula")
    dn, car, cv = G.CATALOGO[g.valvula]
    nota.add(sec, f"válvula instalada = opção {g.valvula} ({dn} {car}, Cv {cv:g})", opcao is not None and round(opcao) == g.valvula, 3,
             f"opção {opcao:g}" if opcao is not None else "?")
    sup = constante_planta(doc, "c_suprimento")
    nota.add(sec, f"suprimento de ar ≥ {g.suprimento_minimo:g} bar (mola até {g.mola[1]:g} bar + 0,4) e ≤ 6 bar",
             sup is not None and g.suprimento_minimo - 0.05 <= sup <= 6.0, 2, f"{sup} bar")


def avaliar_ihm(nota: Nota, doc, g: G.Grupo):
    sec = "IHM (ajustes salvos)"
    s = g.sintonia
    for cid, chave, tol in (("c_kp_lic", "KP_LIC", 0.25), ("c_ti_lic", "TI_LIC", 0.25), ("c_kp_fic", "KP_FIC", 0.25),
                            ("c_ti_fic", "TI_FIC", 0.25), ("c_kff", "K_FF", 0.1)):
        lido = constante_planta(doc, cid)
        alvo = s[chave]
        nota.add(sec, f"{chave} = {alvo:g} (folha de dados, ±{tol * 100:.0f} %)", perto(lido, alvo, tol * alvo), 0.5, f"{lido}")
    nota.add(sec, "malha deixada em AUTOMÁTICO", (constante_planta(doc, "c_modo") or 0) > 2.5, 1, str(constante_planta(doc, "c_modo")))


# =================================================================================================
# CLP: Ladder executado com vetores de teste
# =================================================================================================
def vetores(g: G.Grupo):
    """Casos (correntes em mA nos três canais) e os valores esperados."""
    casos = []

    def caso(nome, i_lt, i_fs, i_fw, mv=25.0):
        casos.append({"nome": nome, "segundos": 0.6,
                      "entradas": {"AI_LT101": round(0.25 * i_lt, 5), "AI_FT101": round(0.25 * i_fs, 5),
                                   "AI_FT102": round(0.25 * i_fw, 5), "MODO_AUTO": "FALSE", "MV_MANUAL": mv},
                      "i": (i_lt, i_fs, i_fw), "mv": mv})
    caso("meia escala", 12.0, 12.0, 12.0)
    caso("quarto de escala", 8.0, 8.0, 8.0, 60.0)
    caso("três quartos", 16.0, 16.0, 16.0)
    caso("fundo de escala", 20.0, 20.0, 20.0)
    caso("vazões abaixo do corte", 7.0, 4.03, 4.04)
    caso("sinais abaixo de 3,6 mA", 3.0, 3.0, 3.0)
    caso("sinais acima de 21 mA", 21.8, 21.8, 21.8)
    return casos


def esperado(g: G.Grupo, i_lt, i_fs, i_fw, mv):
    def falha(i):
        return i < 3.6 or i > 21.0

    def vazao(i, urv, k):
        dp = max((i - 4.0) / 16.0 * urv, 0.0)
        return 0.0 if dp < 0.01 * urv else k * math.sqrt(dp)
    return {"NIVEL": (i_lt - 4.0) / 16.0 * 100.0, "VAZAO_VAPOR": vazao(i_fs, g.ft101_urv, g.k_ft101),
            "VAZAO_AGUA": vazao(i_fw, g.ft102_urv, g.k_ft102), "FALHA_LT101": falha(i_lt), "FALHA_FT101": falha(i_fs),
            "FALHA_FT102": falha(i_fw), "AO_FV102": 4.0 + 0.16 * mv}


def avaliar_clp(nota: Nota, lsplc: str, g: G.Grupo):
    sec = "CLP (Ladder)"
    if not os.path.exists(lsplc):
        nota.add(sec, "projeto do CLP presente", False, 10, lsplc)
        return
    casos = vetores(g)
    ler = ["NIVEL", "VAZAO_VAPOR", "VAZAO_AGUA", "FALHA_LT101", "FALHA_FT101", "FALHA_FT102", "AO_FV102"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"ler": ler, "casos": [{k: c[k] for k in ("nome", "segundos", "entradas")} for c in casos]}, f)
        arq = f.name
    proc = subprocess.run(["node", os.path.join(AQUI, "testar_clp.cjs"), lsplc, arq], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    os.unlink(arq)
    linhas = [l for l in proc.stdout.splitlines() if l.startswith("{")]
    res = json.loads(linhas[-1]) if linhas else {"ok": False, "erros": [proc.stderr[-800:]]}
    main_ld = res.get("linguagens", {}).get("MAIN") == "ld"
    nota.add(sec, "programa MAIN em Ladder (LD)", main_ld, 2, res.get("linguagens", {}).get("MAIN", "?"))
    nota.add(sec, "compila no LasecSimul (OpenPLC → ST → C++)", res.get("ok", False), 2,
             "; ".join(e[:200].replace("|", "/").replace("\n", " ") for e in res.get("erros", []))[:400])
    if not res.get("ok"):
        return
    obtidos = {c["nome"]: c["lidos"] for c in res["casos"]}
    pesos = {"NIVEL": 1.5, "VAZAO_VAPOR": 3, "VAZAO_AGUA": 3, "FALHA": 1.5, "AO_FV102": 0.5}
    erros = {k: [] for k in pesos}
    for c in casos:
        exp = esperado(g, *c["i"], c["mv"])
        got = obtidos.get(c["nome"], {})
        if c["nome"].startswith("sinais"):
            for k in ("FALHA_LT101", "FALHA_FT101", "FALHA_FT102"):
                if bool(got.get(k)) != exp[k]:
                    erros["FALHA"].append(f"{c['nome']}: {k}={got.get(k)}")
            continue
        for k in ("FALHA_LT101", "FALHA_FT101", "FALHA_FT102"):
            if bool(got.get(k)) != exp[k]:
                erros["FALHA"].append(f"{c['nome']}: {k}={got.get(k)}")
        if not perto(got.get("NIVEL"), exp["NIVEL"], 0.5):
            erros["NIVEL"].append(f"{c['nome']}: {got.get('NIVEL')} (esperado {exp['NIVEL']:.2f})")
        for k, qmax in (("VAZAO_VAPOR", g.qmax_ft101), ("VAZAO_AGUA", g.qmax_ft102)):
            if not perto(got.get(k), exp[k], 0.01 * qmax):
                erros[k].append(f"{c['nome']}: {got.get(k)} (esperado {exp[k]:.3f})")
        if not perto(got.get("AO_FV102"), exp["AO_FV102"], 0.05):
            erros["AO_FV102"].append(f"{c['nome']}: {got.get('AO_FV102')}")
    nota.add(sec, "NIVEL (%) pela corrente do LT-101", not erros["NIVEL"], pesos["NIVEL"], "; ".join(erros["NIVEL"][:3]))
    nota.add(sec, f"VAZAO_VAPOR (t/h): placa FE-101 com raiz e corte (±1 % de {g.qmax_ft101:g} t/h)", not erros["VAZAO_VAPOR"],
             pesos["VAZAO_VAPOR"], "; ".join(erros["VAZAO_VAPOR"][:3]))
    nota.add(sec, f"VAZAO_AGUA (t/h): placa FE-102 com raiz e corte (±1 % de {g.qmax_ft102:g} t/h)", not erros["VAZAO_AGUA"],
             pesos["VAZAO_AGUA"], "; ".join(erros["VAZAO_AGUA"][:3]))
    nota.add(sec, "FALHA_* (NAMUR NE 43: < 3,6 mA ou > 21 mA)", not erros["FALHA"], pesos["FALHA"], "; ".join(erros["FALHA"][:3]))
    nota.add(sec, "saída AO preservada (4 + 0,16 × sinal)", not erros["AO_FV102"], pesos["AO_FV102"], "; ".join(erros["AO_FV102"][:2]))


# =================================================================================================
# Ensaio dinâmico (opcional): o projeto inteiro em AUTOMÁTICO
# =================================================================================================
def avaliar_dinamico(nota: Nota, lsproj: str, g: G.Grupo):
    sec = "Ensaio dinâmico (projeto inteiro no Core, AUTOMÁTICO)"
    # O projeto reabre com o estado inicial da planta (haste e nível da definição): 300 s para acomodar.
    roteiro = {"duracao": 660, "periodo": 5,
               "ler": {"nivel": "planta:nivel_pct", "em_auto": "clp:EM_AUTO", "qs": "planta:qs", "qfw": "planta:qfw"},
               "eventos": [{"t": 0, "clp": {"MODO_AUTO": "TRUE"}}, {"t": 360, "planta": {"c_demanda": g.demanda_inicial + 20}}]}
    with tempfile.TemporaryDirectory() as tmp:
        r_arq, s_arq = os.path.join(tmp, "rot.json"), os.path.join(tmp, "res.json")
        with open(r_arq, "w", encoding="utf-8") as f:
            json.dump(roteiro, f)
        proc = subprocess.run(["node", os.path.join(AQUI, "rodar_projeto.cjs"), lsproj, r_arq, s_arq], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=1800)
        if not os.path.exists(s_arq):
            nota.add(sec, "o projeto roda", False, 3, proc.stderr[-300:].replace("\n", " "))
            return
        am = json.load(open(s_arq, encoding="utf-8"))["amostras"]
    auto = [a for a in am if a["t"] >= 30]
    nota.add(sec, "malha entra e fica em automático", all((a.get("em_auto") or 0) > 0.5 for a in auto), 1)
    antes = [a["nivel"] for a in am if 300 <= a["t"] <= 360]
    depois = [a["nivel"] for a in am if a["t"] > 360]
    sp = g.sintonia["SP_NIVEL"]
    nota.add(sec, f"nível no setpoint antes do degrau (±3 %)", antes and all(abs(x - sp) <= 3 for x in antes), 1,
             f"{min(antes):.1f}–{max(antes):.1f} %" if antes else "")
    nota.add(sec, "degrau de +20 % de carga: nível fica entre 35 e 65 %", depois and all(35 <= x <= 65 for x in depois), 1,
             f"{min(depois):.1f}–{max(depois):.1f} %" if depois else "")
    fim = [a["nivel"] for a in am if a["t"] >= 620]
    nota.add(sec, "nível volta ao setpoint (±3 %) até o fim", fim and all(abs(x - sp) <= 3 for x in fim), 1,
             f"{min(fim):.1f}–{max(fim):.1f} %" if fim else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("caminho")
    ap.add_argument("--grupo", required=True, choices=sorted(G.GRUPOS))
    ap.add_argument("--sem-clp", action="store_true")
    ap.add_argument("--dinamico", action="store_true")
    ap.add_argument("--relatorio")
    a = ap.parse_args()
    g = G.GRUPOS[a.grupo]
    lsproj, doc = ler_projeto(a.caminho)
    nota = Nota()
    avaliar_ld301(nota, doc, g)
    avaliar_fy301(nota, doc, g)
    avaliar_ihm(nota, doc, g)
    if not a.sem_clp:
        clp = componente(doc, "ii2p13-clp")
        ref = clp["plc"]["iecProjectRef"] if clp else ""
        avaliar_clp(nota, os.path.join(os.path.dirname(lsproj), ref), g)
    if a.dinamico:
        avaliar_dinamico(nota, lsproj, g)
    texto = nota.markdown(f"II2P13 — avaliação automática do grupo {g.nome} ({os.path.basename(lsproj)})")
    if a.relatorio:
        with open(a.relatorio, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
    print(texto)


if __name__ == "__main__":
    main()
