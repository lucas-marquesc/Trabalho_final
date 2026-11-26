"""Gerador de diagramas Ladder (LD) no formato do editor OpenPLC v4 que roda dentro do LasecSimul.

Um POU em LD dentro do `.lsplc` é o texto que o editor grava em `pous/<pasta>/<nome>.ld`:
cabeçalho IEC (PROGRAM/FUNCTION_BLOCK + VAR ... END_VAR), o JSON do diagrama (`{"name", "rungs"}`,
nós e arestas do React Flow) e o fim (END_PROGRAM/END_FUNCTION_BLOCK).

As regras de geometria (largura/altura dos blocos, alças, espaçamentos) são as do próprio editor
(funções de layout do frontend do OpenPLC 4.2.8): o diagrama gerado abre no editor como se tivesse
sido desenhado à mão e o aluno pode editá-lo normalmente.

Uso:
    r = Rung("comentário")
    r.serie(Contato("PARTIDA"), Bloco("MUL", entradas={"IN1": "X", "IN2": "2.0"}, saidas={"OUT": "Y"}))
    texto = pou_ld("PROGRAM", "MAIN", declaracao, [r, ...])
"""
from __future__ import annotations

import json
import os
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------------------------
# Catálogo dos blocos padrão (extraído do transpilador do OpenPLC: std_block_catalog.json)
# --------------------------------------------------------------------------------------------
_CATALOGO = {
    "ADD": ("function", True, [("IN1", "ANY_NUM"), ("IN2", "ANY_NUM")], [("OUT", "ANY_NUM")], "Arithmetic"),
    "SUB": ("function", False, [("IN1", "ANY_NUM"), ("IN2", "ANY_NUM")], [("OUT", "ANY_NUM")], "Arithmetic"),
    "MUL": ("function", True, [("IN1", "ANY_NUM"), ("IN2", "ANY_NUM")], [("OUT", "ANY_NUM")], "Arithmetic"),
    "DIV": ("function", False, [("IN1", "ANY_NUM"), ("IN2", "ANY_NUM")], [("OUT", "ANY_NUM")], "Arithmetic"),
    "SQRT": ("function", False, [("IN", "ANY_REAL")], [("OUT", "ANY_REAL")], "Numerical"),
    "LT": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "BOOL")], "Comparison"),
    "GT": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "BOOL")], "Comparison"),
    "LE": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "BOOL")], "Comparison"),
    "GE": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "BOOL")], "Comparison"),
    "MOVE": ("function", False, [("IN", "ANY")], [("OUT", "ANY")], "Data"),
    "LIMIT": ("function", False, [("MN", "ANY"), ("IN", "ANY"), ("MX", "ANY")], [("OUT", "ANY")], "Selection"),
    "MAX": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "ANY")], "Selection"),
    "MIN": ("function", True, [("IN1", "ANY"), ("IN2", "ANY")], [("OUT", "ANY")], "Selection"),
    "TON": ("function-block", False, [("IN", "BOOL"), ("PT", "TIME")], [("Q", "BOOL"), ("ET", "TIME")], "Timers"),
}

# Geometria do editor (constantes do frontend do OpenPLC 4.2.8)
K_PASSO_ALCA = 40        # distância vertical entre alças de um bloco
Y_PRIMEIRA_ALCA = 36     # primeira alça do bloco, a partir do topo
LARG_MAX_BLOCO = 216
GAP = {"powerRail": 20, "contact": 45, "coil": 45, "block": 120, "parallel": 0}
VAR_W, VAR_H, VAR_GAP = 80, 32, 30
CONT_W, CONT_H = 24, 24
COIL_W, COIL_H = 28, 24
Y_LINHA = 50             # linha principal do degrau (alça do trilho esquerdo)
DY_RAMO = 92             # distância entre ramos paralelos de contatos


def _uid() -> str:
    return str(uuid.uuid4())


def _num_id() -> str:
    return str(int(uuid.uuid4().int % 9_000_000) + 1_000_000)


def _tipo(valor: str) -> dict:
    return {"definition": "generic-type" if valor.startswith("ANY") else "base-type", "value": valor}


def _alca(hid, x, y, rx, ry, lado, tipo, estilo):
    return {"glbPosition": {"x": x, "y": y}, "relPosition": {"x": rx, "y": ry}, "id": hid, "position": lado,
            "isConnectable": False, "type": tipo, "style": estilo}


# --------------------------------------------------------------------------------------------
# Elementos
# --------------------------------------------------------------------------------------------
class Contato:
    def __init__(self, variavel: str, negado: bool = False):
        self.variavel, self.negado = variavel, negado
        self.tipo = "contact"


class Bobina:
    def __init__(self, variavel: str, variante: str = "default"):
        """variante: default, negated, set, reset, risingEdge, fallingEdge."""
        self.variavel, self.variante = variavel, variante
        self.tipo = "coil"


class Paralelo:
    """Ramos de contatos em paralelo (OU). Cada ramo é uma lista de Contato."""

    def __init__(self, *ramos: list):
        self.ramos = [list(r) for r in ramos]
        self.tipo = "parallel"


class Bloco:
    """Função ou bloco de função. entradas/saidas: alça -> nome de variável ou literal.

    `definicao`: (tipo, extensível, [(entrada, tipo)], [(saida, tipo)], categoria) para blocos do
    usuário; os padrão saem de _CATALOGO. `instancia`: nome da instância (blocos de função).
    """

    def __init__(self, nome: str, entradas: dict | None = None, saidas: dict | None = None,
                 instancia: str = "", definicao: tuple | None = None, documentacao: str = ""):
        self.nome = nome
        self.entradas = entradas or {}
        self.saidas = saidas or {}
        self.instancia = instancia
        self.definicao = definicao or _CATALOGO[nome]
        self.documentacao = documentacao
        self.tipo = "block"


# --------------------------------------------------------------------------------------------
# Degrau
# --------------------------------------------------------------------------------------------
class Rung:
    def __init__(self, comentario: str = ""):
        self.comentario = comentario
        self.elementos: list = []

    def serie(self, *elementos) -> "Rung":
        self.elementos.extend(elementos)
        return self


class _Montador:
    def __init__(self, pou: str, variaveis: dict):
        self.pou = pou
        self.variaveis = variaveis   # nome -> declaração no formato do editor
        self.nos: list = []
        self.arestas: list = []
        self.base = 0.0              # maior y inferior (para a altura do degrau)

    # -- utilidades -------------------------------------------------------------------------
    def _var_ref(self, nome: str) -> dict:
        decl = self.variaveis.get(nome.split(".")[0]) if "." not in nome else None
        return dict(decl) if decl else {"name": nome}

    def aresta(self, origem, alca_o, destino, alca_d):
        self.arestas.append({"id": f"e_{origem}_{destino}__{alca_o}_{alca_d}", "source": origem, "target": destino,
                             "sourceHandle": alca_o, "targetHandle": alca_d})

    def _baixo(self, y):
        self.base = max(self.base, y)

    # -- nós ----------------------------------------------------------------------------------
    def trilho(self, lado: str, x: float, rung_id: str) -> str:
        nid = f"{lado}-rail-{rung_id}"
        alca = _alca(f"{lado}-rail", x + (3 if lado == "left" else 0), Y_LINHA, 3 if lado == "left" else 0, 20,
                     "right" if lado == "left" else "left", "source" if lado == "left" else "target",
                     {"right": -3} if lado == "left" else {"left": -3})
        self.nos.append({"id": nid, "type": "powerRail", "position": {"x": x, "y": Y_LINHA - 20},
                         "data": {"handles": [alca], "variant": lado,
                                  ("outputConnector" if lado == "left" else "inputConnector"): alca,
                                  ("outputHandles" if lado == "left" else "inputHandles"): [alca],
                                  ("inputHandles" if lado == "left" else "outputHandles"): [],
                                  "numericId": _num_id(), "variable": {"name": ""}, "executionOrder": 0,
                                  "draggable": False, "selectable": True, "deletable": False},
                         "width": 3, "height": 40, "measured": {"width": 3, "height": 40},
                         "draggable": False, "selectable": True, "selected": False, "dragging": False})
        return nid

    def contato_ou_bobina(self, el, x: float, y_linha: float) -> str:
        contato = el.tipo == "contact"
        w, h = (CONT_W, CONT_H) if contato else (COIL_W, COIL_H)
        nid = f"{'CONTACT' if contato else 'COIL'}_{_uid()}"
        ent = _alca("input", x, y_linha, 0, 12, "left", "target", {"left": -3})
        sai = _alca("output", x + w, y_linha, w, 12, "right", "source", {"right": -3})
        variante = ("negated" if el.negado else "default") if contato else el.variante
        self.nos.append({"id": nid, "type": el.tipo, "position": {"x": x, "y": y_linha - 12},
                         "data": {"handles": [ent, sai], "variant": variante, "inputHandles": [ent], "outputHandles": [sai],
                                  "inputConnector": ent, "outputConnector": sai, "numericId": _num_id(),
                                  "variable": self._var_ref(el.variavel), "executionOrder": 0,
                                  "draggable": True, "selectable": True, "deletable": True},
                         "width": w, "height": h, "measured": {"width": w, "height": h},
                         "draggable": True, "selectable": True, "selected": False, "dragging": False})
        self._baixo(y_linha - 12 + h)
        return nid

    def paralelo(self, x: float, abre: bool, ref: str | None = None) -> tuple[str, dict]:
        nid = f"PARALLEL_{'OPEN' if abre else 'CLOSE'}_{_uid()}"
        y = Y_LINHA - 1
        if abre:
            alcas = [_alca("input", x, Y_LINHA, 0, 1, "left", "target", {"left": -3}),
                     _alca("input-top", x + 4, Y_LINHA, 4, 1, "top", "target", {"top": -3}),
                     _alca("output-right", x + 4, Y_LINHA, 4, 1, "right", "source", {"right": -3}),
                     _alca("output-down", x + 4, Y_LINHA, 4, 1, "bottom", "source", {"bottom": -3})]
            dados = {"inputHandles": [alcas[0], alcas[1]], "outputHandles": [alcas[2], alcas[3]],
                     "parallelOutputConnector": alcas[3], "parallelCloseReference": ref}
        else:
            alcas = [_alca("input", x, Y_LINHA, 0, 1, "left", "target", {"left": -3}),
                     _alca("input-down", x + 4, Y_LINHA, 4, 1, "bottom", "target", {"bottom": -3}),
                     _alca("output-right", x + 4, Y_LINHA, 4, 1, "right", "source", {"right": -3}),
                     _alca("output-top", x + 4, Y_LINHA, 4, 1, "top", "source", {"top": -3})]
            dados = {"inputHandles": [alcas[0], alcas[1]], "outputHandles": [alcas[2], alcas[3]],
                     "parallelInputConnector": alcas[1], "parallelOpenReference": ref}
        no = {"id": nid, "type": "parallel", "position": {"x": x, "y": y},
              "data": {"handles": alcas, "variant": "open" if abre else "close", "type": "open" if abre else "close",
                       "inputConnector": alcas[0], "outputConnector": alcas[2], "numericId": _num_id(),
                       "variable": {"name": ""}, "executionOrder": 0, "draggable": True, "selectable": True,
                       "deletable": True, **dados},
              "width": 4, "height": 2, "measured": {"width": 4, "height": 2},
              "draggable": True, "selectable": True, "selected": False, "dragging": False}
        self.nos.append(no)
        return nid, no

    def bloco(self, el: Bloco, x: float) -> tuple[str, float]:
        tipo, extensivel, entradas, saidas, categoria = el.definicao
        precisa_en = (not entradas or entradas[0][1] != "BOOL" or not saidas or saidas[0][1] != "BOOL")
        variaveis = []
        if precisa_en:
            variaveis += [{"name": "EN", "class": "input", "type": _tipo("BOOL") | {"definition": "generic-type"}},
                          {"name": "ENO", "class": "output", "type": _tipo("BOOL") | {"definition": "generic-type"}}]
        variaveis += [{"name": n, "class": "output", "type": _tipo(t)} for n, t in saidas]
        variaveis += [{"name": n, "class": "input", "type": _tipo(t)} for n, t in entradas]
        nomes_in = [v["name"] for v in variaveis if v["class"] == "input"]
        nomes_out = [v["name"] for v in variaveis if v["class"] == "output"]
        altura = 60 + max(len(nomes_in) - 1, len(nomes_out) - 1) * K_PASSO_ALCA
        larg = min(max(max((12 * len(n) for n in nomes_in), default=0) + 18 + max((12 * len(n) for n in nomes_out), default=0),
                       12 * len(el.nome)), LARG_MAX_BLOCO)
        y0 = Y_LINHA - Y_PRIMEIRA_ALCA
        nid = f"BLOCK_{_uid()}"
        alcas_in = [_alca(n, x, Y_LINHA + i * K_PASSO_ALCA, 0, Y_PRIMEIRA_ALCA + i * K_PASSO_ALCA, "left", "target",
                          {"top": Y_PRIMEIRA_ALCA + i * K_PASSO_ALCA, "left": 0}) for i, n in enumerate(nomes_in)]
        alcas_out = [_alca(n, x + larg, Y_LINHA + i * K_PASSO_ALCA, larg, Y_PRIMEIRA_ALCA + i * K_PASSO_ALCA, "right",
                           "source", {"top": Y_PRIMEIRA_ALCA + i * K_PASSO_ALCA, "right": 0}) for i, n in enumerate(nomes_out)]
        if categoria:   # bloco da biblioteca padrão
            variante = {"name": el.nome, "type": tipo, "language": "st", "variables": variaveis, "body": "",
                        "documentation": el.documentacao, "extensible": extensivel, "category": categoria}
        else:           # POU do próprio projeto
            variante = {"name": el.nome, "type": tipo, "variables": variaveis, "documentation": el.documentacao,
                        "extensible": extensivel}
        conectadas = []
        for i, n in enumerate(nomes_in):
            if n in el.entradas:
                conectadas.append({"handleId": n, "type": "input", "variable": self._var_ref(el.entradas[n])})
        for i, n in enumerate(nomes_out):
            if n in el.saidas:
                conectadas.append({"handleId": n, "type": "output", "variable": self._var_ref(el.saidas[n])})
        self.nos.append({"id": nid, "type": "block", "position": {"x": x, "y": y0},
                         "data": {"handles": alcas_in + alcas_out, "inputHandles": alcas_in, "outputHandles": alcas_out,
                                  "inputConnector": alcas_in[0], "outputConnector": alcas_out[0], "numericId": _num_id(),
                                  "variant": variante, "variable": {"name": el.instancia}, "executionOrder": 0,
                                  "executionControl": precisa_en, "lockExecutionControl": precisa_en,
                                  "connectedVariables": conectadas, "draggable": True, "selectable": True, "deletable": True},
                         "width": larg, "height": altura, "measured": {"width": larg, "height": altura},
                         "draggable": True, "selectable": True, "selected": False, "dragging": False})
        self._baixo(y0 + altura)
        # variáveis ligadas às alças de dados (a primeira alça de cada lado é a do fluxo de energia)
        tipos = {v["name"]: v["type"] for v in variaveis}
        for i, n in enumerate(nomes_in):
            if i == 0 or n not in el.entradas:
                continue
            vid = f"VARIABLE_{_uid()}"
            yh = Y_LINHA + i * K_PASSO_ALCA
            vx = x - VAR_W - VAR_GAP
            a = _alca("output", vx + VAR_W, yh, VAR_W, 16, "right", "source", {})
            a.pop("style")
            self.nos.append({"id": vid, "type": "variable", "position": {"x": vx, "y": yh - 16}, "width": VAR_W,
                             "height": VAR_H, "measured": {"width": VAR_W, "height": VAR_H},
                             "data": {"handles": [a], "inputHandles": [], "outputHandles": [a], "outputConnector": a,
                                      "numericId": _num_id(), "variable": self._var_ref(el.entradas[n]), "executionOrder": 0,
                                      "variant": "input", "block": {"id": nid, "handleId": n,
                                                                    "variableType": {"name": n, "class": "input", "type": tipos[n]}},
                                      "draggable": False, "selectable": True, "deletable": False},
                             "deletable": False, "selectable": True, "draggable": False, "selected": False, "dragging": False})
            self.aresta(vid, "output", nid, n)
            self._baixo(yh - 16 + VAR_H)
        for i, n in enumerate(nomes_out):
            if i == 0 or n not in el.saidas:
                continue
            vid = f"VARIABLE_{_uid()}"
            yh = Y_LINHA + i * K_PASSO_ALCA
            vx = x + larg + VAR_GAP
            a = _alca("input", vx, yh, 0, 16, "left", "target", {})
            a.pop("style")
            self.nos.append({"id": vid, "type": "variable", "position": {"x": vx, "y": yh - 16}, "width": VAR_W,
                             "height": VAR_H, "measured": {"width": VAR_W, "height": VAR_H},
                             "data": {"handles": [a], "inputHandles": [a], "outputHandles": [], "inputConnector": a,
                                      "numericId": _num_id(), "variable": self._var_ref(el.saidas[n]), "executionOrder": 0,
                                      "variant": "output", "block": {"id": nid, "handleId": n,
                                                                     "variableType": {"name": n, "class": "output", "type": tipos[n]}},
                                      "draggable": False, "selectable": True, "deletable": False},
                             "deletable": False, "selectable": True, "draggable": False, "selected": False, "dragging": False})
            self.aresta(nid, n, vid, "input")
            self._baixo(yh - 16 + VAR_H)
        return nid, larg, nomes_in[0], nomes_out[0]


def _montar_rung(rung: Rung, pou: str, variaveis: dict) -> dict:
    m = _Montador(pou, variaveis)
    rid = f"rung_{pou}_{_uid()}"
    esquerdo = m.trilho("left", 0, rid)
    anterior, alca_ant, tipo_ant, x = esquerdo, "left-rail", "powerRail", 3.0
    for el in rung.elementos:
        if el.tipo in ("contact", "coil"):
            x += GAP[tipo_ant] + GAP[el.tipo]
            nid = m.contato_ou_bobina(el, x, Y_LINHA)
            m.aresta(anterior, alca_ant, nid, "input")
            anterior, alca_ant, tipo_ant = nid, "output", el.tipo
            x += CONT_W if el.tipo == "contact" else COIL_W
        elif el.tipo == "parallel":
            x += GAP[tipo_ant] + GAP["parallel"]
            abre_id, abre = m.paralelo(x, True)
            m.aresta(anterior, alca_ant, abre_id, "input")
            x0 = x + 4
            fins = []
            largura = 0.0
            for k, ramo in enumerate(el.ramos):
                y = Y_LINHA + k * DY_RAMO
                xr, ant_r, alca_r, tipo_r = x0, abre_id, "output-right" if k == 0 else "output-down", "parallel"
                for c in ramo:
                    xr += GAP[tipo_r] + GAP[c.tipo]
                    nid = m.contato_ou_bobina(c, xr, y)
                    m.aresta(ant_r, alca_r, nid, "input")
                    ant_r, alca_r, tipo_r = nid, "output", c.tipo
                    xr += CONT_W
                fins.append((ant_r, alca_r))
                largura = max(largura, xr - x0)
            x = x0 + largura + GAP["contact"]
            fecha_id, fecha = m.paralelo(x, False, abre_id)
            abre["data"]["parallelCloseReference"] = fecha_id
            for k, (nid, alca) in enumerate(fins):
                m.aresta(nid, alca, fecha_id, "input" if k == 0 else "input-down")
            anterior, alca_ant, tipo_ant = fecha_id, "output-right", "parallel"
            x += 4
        elif el.tipo == "block":
            x += GAP[tipo_ant] + GAP["block"] + VAR_W   # espaço para as variáveis de entrada
            nid, larg, en, eno = m.bloco(el, x)
            m.aresta(anterior, alca_ant, nid, en)
            anterior, alca_ant, tipo_ant = nid, eno, "block"
            x += larg + VAR_W                          # variáveis de saída
        else:
            raise ValueError(el.tipo)
    x += GAP[tipo_ant] + GAP["powerRail"] + GAP[tipo_ant]
    direito = m.trilho("right", x, rid)
    m.aresta(anterior, alca_ant, direito, "right-rail")
    return {"id": rid, "comment": rung.comentario, "defaultBounds": [300, 100],
            "reactFlowViewport": [round(x + 3), round(max(100, m.base) + 20)], "selectedNodes": [],
            "nodes": m.nos, "edges": m.arestas}


# --------------------------------------------------------------------------------------------
# POU
# --------------------------------------------------------------------------------------------
def declaracao_editor(nome: str, classe: str, tipo: str, inicial=None, doc: str = "") -> dict:
    """Variável no formato que o editor guarda nos nós (classe: input, output, local)."""
    base = tipo.upper()
    if base in ("BOOL", "REAL", "INT", "DINT", "TIME", "LREAL", "UINT", "SINT", "WORD", "DWORD", "BYTE", "STRING", "UDINT"):
        t = {"definition": "base-type", "value": base}
    else:
        t = {"definition": "derived", "value": tipo}
    return {"name": nome, "class": classe, "type": t, "location": "", "initialValue": inicial,
            "documentation": doc, "debug": False}


def pou_ld(tipo_pou: str, nome: str, cabecalho_var: str, rungs: list[Rung], variaveis: dict) -> str:
    """Texto do arquivo .ld: cabeçalho IEC + JSON do diagrama + fim do POU.

    `cabecalho_var`: o bloco VAR_INPUT/VAR_OUTPUT/VAR ... END_VAR (texto IEC, como o editor grava).
    `variaveis`: nome -> declaração do editor (declaracao_editor), usada nos nós.
    """
    corpo = {"name": nome, "rungs": [_montar_rung(r, nome, variaveis) for r in rungs]}
    fim = "END_PROGRAM" if tipo_pou == "PROGRAM" else "END_FUNCTION_BLOCK"
    return f"{tipo_pou} {nome}\n{cabecalho_var.rstrip()}\n\n\n{json.dumps(corpo, ensure_ascii=False, indent=2)}\n{fim}"
