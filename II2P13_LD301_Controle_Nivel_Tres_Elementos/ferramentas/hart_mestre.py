"""Mestre HART mínimo (lado do PC) para conferir os LD301 da prática pela porta serial do modem.

Fala com o transmissor pelo MESMO caminho do PACTware: COM do PC -> par com0com -> Modem HART do
LasecSimul (em paralelo com o shunt de 250 ohm) -> laço 4–20 mA -> LD301. Use com a simulação
rodando e com o PACTware FECHADO (a porta só aceita um programa por vez).

    python ferramentas/hart_mestre.py COM20 varrer           # Comando 0 nos endereços 0 a 15
    python ferramentas/hart_mestre.py COM20 ler              # identificação, faixa, PV, corrente
    python ferramentas/hart_mestre.py COM21 endereco 0 --de 3
    python ferramentas/hart_mestre.py COM20 faixa -593.0 -65.9   # LRV URV em mmH2O (Comando 35)
    python ferramentas/hart_mestre.py COM20 amortecimento 1.0     # Comando 34 (s)
    python ferramentas/hart_mestre.py COM20 tag LT-101 "NIVEL TAMBOR B101"
    python ferramentas/hart_mestre.py COM20 mensagem "LT-101 NIVEL DO TAMBOR DE VAPOR"
    python ferramentas/hart_mestre.py COM20 funcao linear          # Comando 47 (linear | raiz)
    python ferramentas/hart_mestre.py COM20 corrente 12            # loop test (Comando 40); 0 sai

FY301 (posicionador, comandos do DD da Smar, os mesmos do DTM):
    python ferramentas/hart_mestre.py COM23 fy-ar close            # AIR_T (Cmd 129): open | close
    python ferramentas/hart_mestre.py COM23 fy-acao direta         # ação (Cmd 157): direta | reversa
    python ferramentas/hart_mestre.py COM23 fy-curva 1             # caracterização (Cmd 47): 0 linear, 1 EP 1:50 ...
    python ferramentas/hart_mestre.py COM23 fy-limites tso=2 inf=3 # Cmd 221/222: tso, inf, sup (% do setpoint), abre, fecha (TIME, s)
    python ferramentas/hart_mestre.py COM23 fy-desvio 3 5          # Cmd 193/194: alarme de desvio, banda (%) e tempo (s)
    python ferramentas/hart_mestre.py COM23 fy-autosetup           # Cmd 152 e acompanha o progresso (Cmd 33 código 17)
    python ferramentas/hart_mestre.py COM23 fy-ler                 # posição, setpoint, entrada e progresso do setup

Mapa da prática: LT-101 = COM20, FT-101 = COM21, FT-102 = COM22, FY-102 = COM23 (pares CNCB0/1/2/3).
"""
from __future__ import annotations

import argparse
import datetime
import struct
import sys
import time

import serial  # pyserial

UNIDADES = {4: "mmH2O@20C", 12: "kPa", 57: "%", 39: "mA", 7: "bar", 19: "m3/h", 32: "°C"}
FUNCOES = {0: "Linear", 1: "Raiz quadrada"}


# ------------------------------------------------------------------------------ ASCII empacotado
def desempacotar(dados: bytes) -> str:
    bits = int.from_bytes(dados, "big")
    n = len(dados) * 8 // 6
    chars = []
    for i in range(n):
        v = (bits >> (6 * (n - 1 - i))) & 0x3F
        chars.append(chr(v + 64 if v < 32 else v))
    return "".join(chars).rstrip()


def empacotar(texto: str, n_chars: int) -> bytes:
    texto = texto.upper().ljust(n_chars)[:n_chars]
    bits = 0
    for c in texto:
        v = ord(c) & 0x3F
        bits = (bits << 6) | v
    return bits.to_bytes(n_chars * 6 // 8, "big")


# ------------------------------------------------------------------------------ quadros
def quadro(endereco: bytes, comando: int, dados: bytes = b"") -> bytes:
    delim = 0x82 if len(endereco) == 5 else 0x02
    corpo = bytes([delim]) + endereco + bytes([comando, len(dados)]) + dados
    cks = 0
    for b in corpo:
        cks ^= b
    return b"\xff" * 5 + corpo + bytes([cks])


def ler_resposta(porta: serial.Serial, timeout: float = 8.0) -> bytes | None:
    """No simulador em tempo real a camada física HART é mais lenta que a real: espera até 8 s."""
    fim = time.time() + timeout
    buf = bytearray()
    while time.time() < fim:
        buf.extend(porta.read(64))
        for i, b in enumerate(buf):
            if b in (0x06, 0x86):
                q = buf[i:]
                na = 5 if b == 0x86 else 1
                if len(q) >= na + 3 and len(q) >= na + 3 + q[na + 2] + 1:
                    corpo = bytes(q[: na + 3 + q[na + 2] + 1])
                    cks = 0
                    for x in corpo[:-1]:
                        cks ^= x
                    return corpo if cks == corpo[-1] else None
                break
    return None


class Mestre:
    def __init__(self, porta: str):
        self.p = serial.Serial(porta, 1200, bytesize=8, parity="O", stopbits=1, timeout=0.2)
        self.longo: bytes | None = None

    def transacao(self, comando: int, dados: bytes = b"", curto: int | None = None, tentativas: int = 3):
        end = bytes([0x80 | (curto & 0x3F)]) if curto is not None else self.longo
        for _ in range(tentativas):
            self.p.reset_input_buffer()
            self.p.write(quadro(end, comando, dados))
            self.p.flush()
            r = ler_resposta(self.p)
            if r:
                na = 5 if r[0] == 0x86 else 1
                n = r[na + 2]
                corpo = r[na + 3: na + 3 + n]
                return corpo[0], corpo[1], corpo[2:]   # código de resposta, status do aparelho, dados
            time.sleep(0.3)
        raise TimeoutError(f"sem resposta ao Comando {comando}")

    def identificar(self, endereco: int = 0, tentativas: int = 1) -> dict:
        rc, st, d = self.transacao(0, curto=endereco, tentativas=tentativas)
        info = {"fabricante": d[1], "tipo": d[2], "rev_universal": d[4], "rev_aparelho": d[5], "software": d[6],
                "id_unico": d[9:12].hex().upper(), "endereco": endereco}
        self.longo = bytes([0x80 | (d[1] & 0x3F), d[2]]) + d[9:12]
        return info

    def ler(self) -> dict:
        out = {}
        _, _, d = self.transacao(13)
        out["tag"], out["descritor"] = desempacotar(d[0:6]), desempacotar(d[6:18])
        out["data"] = f"{d[18]:02d}/{d[19]:02d}/{1900 + d[20]}"
        _, _, d = self.transacao(12)
        out["mensagem"] = desempacotar(d[0:24])
        _, _, d = self.transacao(15)
        out["funcao"] = FUNCOES.get(d[1], d[1])
        out["unidade"] = UNIDADES.get(d[2], d[2])
        out["URV"], out["LRV"], out["amortecimento_s"] = struct.unpack(">fff", d[3:15])
        _, _, d = self.transacao(1)
        out["PV"] = struct.unpack(">f", d[1:5])[0]
        out["unidade_PV"] = UNIDADES.get(d[0], d[0])
        _, _, d = self.transacao(2)
        out["corrente_mA"], out["percentual"] = struct.unpack(">ff", d[0:8])
        _, _, d = self.transacao(7) if True else (0, 0, b"")
        if d:
            out["endereco"] = d[0]
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("porta")
    ap.add_argument("acao", choices=["varrer", "ler", "endereco", "faixa", "amortecimento", "tag", "mensagem", "funcao", "corrente",
                                     "fy-ar", "fy-acao", "fy-curva", "fy-limites", "fy-desvio", "fy-autosetup", "fy-ler"])
    ap.add_argument("valores", nargs="*")
    ap.add_argument("--de", type=int, default=None, help="endereço atual (padrão: varre 0 a 15 e usa o primeiro que responder)")
    a = ap.parse_args()
    m = Mestre(a.porta)
    if a.acao == "varrer":
        for e in range(16):
            try:
                info = m.identificar(e)
                print(f"endereço {e:2d}: fabricante 0x{info['fabricante']:02X} tipo 0x{info['tipo']:02X} ID {info['id_unico']} "
                      f"rev HART {info['rev_universal']} rev aparelho {info['rev_aparelho']}")
            except TimeoutError:
                print(f"endereço {e:2d}: —")
        return 0
    enderecos = [a.de] if a.de is not None else range(16)
    for e in enderecos:
        try:
            info = m.identificar(e)
            break
        except TimeoutError:
            continue
    else:
        print("nenhum instrumento respondeu"); return 1
    print(f"instrumento (fabricante 0x{info['fabricante']:02X}, tipo 0x{info['tipo']:02X}) no endereço {info['endereco']} · ID {info['id_unico']}")
    v = a.valores
    if a.acao == "endereco":
        rc, _, d = m.transacao(6, bytes([int(v[0])]))
    elif a.acao == "faixa":
        lrv, urv = float(v[0]), float(v[1])
        rc, _, d = m.transacao(35, bytes([4]) + struct.pack(">ff", urv, lrv))
    elif a.acao == "amortecimento":
        rc, _, d = m.transacao(34, struct.pack(">f", float(v[0])))
    elif a.acao == "tag":
        hoje = datetime.date.today()
        rc, _, d = m.transacao(18, empacotar(v[0], 8) + empacotar(v[1] if len(v) > 1 else "", 16)
                               + bytes([hoje.day, hoje.month, hoje.year - 1900]))
    elif a.acao == "mensagem":
        rc, _, d = m.transacao(17, empacotar(" ".join(v), 32))
    elif a.acao == "funcao":
        rc, _, d = m.transacao(47, bytes([1 if v[0].lower().startswith("raiz") else 0]))
    elif a.acao == "corrente":
        rc, _, d = m.transacao(40, struct.pack(">f", float(v[0])))
    elif a.acao == "fy-ar":
        rc, _, d = m.transacao(129, bytes([1 if v[0].lower().startswith("c") else 0]))
    elif a.acao == "fy-acao":
        rc, _, d = m.transacao(157, bytes([1 if v[0].lower().startswith("r") else 0]))
    elif a.acao == "fy-curva":
        rc, _, d = m.transacao(47, bytes([int(v[0])]))
    elif a.acao == "fy-limites":
        _, _, d = m.transacao(221)
        atual = dict(zip(("abre", "fecha", "tso", "sup", "inf", "tso_banda"), struct.unpack(">ffffff", d[0:24])))
        for par in v:
            chave, valor = par.split("=")
            if chave not in atual:
                print(f"parâmetro desconhecido: {chave} (use abre, fecha, tso, sup, inf)"); return 2
            atual[chave] = float(valor)
        rc, _, d = m.transacao(222, struct.pack(">ffffff", *atual.values()))
        print("  " + ", ".join(f"{k} {x:g}" for k, x in atual.items()))
    elif a.acao == "fy-desvio":
        _, _, d = m.transacao(193)
        banda, tempo, rev_banda, rev_limite = struct.unpack(">ffff", d[0:16])
        banda, tempo = float(v[0]), float(v[1])
        rc, _, d = m.transacao(194, struct.pack(">ffff", banda, tempo, rev_banda, rev_limite))
    elif a.acao == "fy-autosetup":
        rc, _, d = m.transacao(152)
        print(f"Auto Setup iniciado (código {rc}); acompanhando o progresso...")
        for _ in range(240):
            time.sleep(2)
            _, _, d = m.transacao(33, bytes([17]))
            progresso = struct.unpack(">f", d[2:6])[0]
            print(f"  progresso {progresso:5.1f} %", flush=True)
            if progresso >= 100:
                break
    elif a.acao == "fy-ler":
        _, _, d = m.transacao(33, bytes([1, 6, 0, 17]))
        for k, nome in enumerate(("posição (%)", "setpoint (%)", "entrada (mA)", "Auto Setup (%)")):
            print(f"  {nome:16s} {struct.unpack('>f', d[6 * k + 2:6 * k + 6])[0]:.3f}")
        _, _, d = m.transacao(13)
        print(f"  tag              {desempacotar(d[0:6])}")
        return 0
    else:
        rc = 0
    if a.acao.startswith("fy-"):
        print(f"código de resposta {rc} ({'aceito' if rc == 0 else 'ver Tabela de códigos HART'})")
        return 0
    if a.acao != "ler":
        print(f"código de resposta {rc} ({'aceito' if rc == 0 else 'ver Tabela de códigos HART'})")
        time.sleep(0.5)
        if a.acao == "endereco":
            info = m.identificar(int(v[0]))
    for k, val in m.ler().items():
        print(f"  {k:16s} {val:.3f}" if isinstance(val, float) else f"  {k:16s} {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
