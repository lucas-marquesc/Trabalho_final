# II2P13 — Trabalho em grupo · Folha de dados do **GRUPO B**

Caldeira B-101 com controle de nível do tambor a três elementos. Estes são os dados de projeto da **sua** caldeira; os outros grupos têm outra caldeira. Use o roteiro [`README.md`](../../README.md) para a sequência do trabalho. Tudo o que você calcular aqui vai para o LasecFDT (transmissores e posicionador), para o sinótico (válvula e ar) e para o Ladder do CLP.

> Pressões diferenciais em **mmH2O a 20 °C** (unidade dos LD301, código HART 4): 1 mmH2O = 9,789 Pa; uma coluna de *h* metros de um fluido de densidade *ρ* vale 1000·(ρ/998,2)·*h* mmH2O.

## 1. Tambor de vapor e LT-101

| Dado | Valor |
|---|---|
| Pressão no tambor | 16,0 bar abs (14,99 bar g) |
| Água saturada no tambor | ρ = 862,8 kg/m³ |
| Vapor saturado no tambor | ρ = 8,08 kg/m³ |
| Condensado nas pernas de impulso | 30 °C, ρ = 995,6 kg/m³ |
| Diâmetro interno do tambor | 1,20 m |
| Distância entre as tomadas do LT-101 (0 a 100 % de nível) | 0,80 m |
| LT-101 abaixo da tomada inferior | 2,00 m (as duas pernas cheias de condensado) |
| Ligação | HIGH na tomada **inferior** (perna variável); LOW na perna de referência, que desce do **pote de condensado** da tomada superior |
| Transmissor | SMAR LD301, sensor M2 (−5107,7 a +5107,7 mmH2O) |

## 2. Placas de orifício (ISO 5167, tomadas de flange)

Use $q_m = \dfrac{C}{\sqrt{1-\beta^4}}\,\varepsilon\,\dfrac{\pi}{4}d^2\sqrt{2\,\rho\,\Delta P}$ (SI: kg/s, m, kg/m³, Pa) e considere *C* e *ε* constantes. Os transmissores de vazão saem **lineares em ΔP**; a raiz quadrada é feita **no CLP**.

| Dado | FE-101 / FT-101 (vapor) | FE-102 / FT-102 (água de alimentação) |
|---|---|---|
| Fluido na placa | vapor saturado, ρ = 8,08 kg/m³ | água a 120 °C, ρ = 943,4 kg/m³ |
| Diâmetro interno do tubo *D* | 254,5 mm | 102,3 mm |
| Diâmetro do orifício *d* | 161,0 mm | 51,5 mm |
| Coeficiente de descarga *C* | 0,605 | 0,605 |
| Fator de expansão *ε* | 0,996 | 1 (líquido) |
| Vazão de fundo de escala (20 mA) | 36 t/h | 40 t/h |
| Corte de vazão baixa (no CLP) | abaixo de 1 % da faixa de ΔP → vazão zero | idem |

## 3. Válvula de controle FV-102 (água de alimentação)

Água a 120 °C, ρ = 943,4 kg/m³ (G = ρ/1000 = 0,9434). Pressões manométricas na entrada (*p1*) e na saída (*p2*) da válvula nas três condições de projeto (a queda na válvula muda com a vazão por causa das perdas na linha e no economizador):

| Condição | Vazão (t/h) | p1 (bar g) | p2 (bar g) |
|---|---|---|---|
| Mínima (35 % da MCR + purga) | 11,10 | 23,96 | 15,95 |
| Normal (70 % da MCR + purga) | 21,60 | 23,84 | 16,29 |
| Máxima (110 % da MCR + purga) | 33,60 | 23,62 | 16,96 |

**Característica inerente especificada pela engenharia:** igual %.

Equações (líquido, sem correções): $K_v = Q\,[\text{m}^3/\text{h}]\sqrt{G/\Delta P\,[\text{bar}]}$, $C_v = 1{,}156\,K_v$. Abertura *x* (0 a 1) que dá $C_v$: linear $C_v = x\,C_{v,max}$; igual porcentagem (R = 50) $C_v = C_{v,max}\,(R^x - 1)/(R - 1)$.

**Critério de seleção:** abertura entre **20 % e 85 %** nas três condições; entre as que atendem, a de **menor Cv** (menor custo e melhor resolução).

Catálogo do almoxarifado (dados didáticos):

| Opção | Diâmetro | Característica | Cv a 100 % | Almoxarifado |
|---|---|---|---|---|
| 1 | 3/4" | linear | 6 | disponível |
| 2 | 1" | linear | 10 | disponível |
| 3 | 1 1/4" | linear | 16 | disponível |
| 4 | 1 1/2" | linear | 25 | disponível |
| 5 | 2" | linear | 40 | disponível |
| 6 | 3" | linear | 100 | disponível |
| 7 | 1" | igual % | 9 | disponível |
| 8 | 1 1/2" | igual % | 22 | disponível |
| 9 | 2" | igual % | 36 | disponível |
| 10 | 3" | igual % | 90 | disponível |
| 11 | 4" | igual % | 160 | disponível |

A válvula **instalada** se escolhe no sinótico (quadro verde *Campo: válvula e ar*, "FV-102: opção do catálogo") ou nas Propriedades exportadas da planta.

## 4. Atuador e posicionador FY-102 (SMAR FY301)

| Dado | Valor |
|---|---|
| Atuador | diafragma e mola, **ar para fechar** (falha **aberta**) |
| Faixa da mola (bench set) | 0,4 a 2,0 bar |
| Curso da válvula | 25 mm |
| Suprimento de ar | filtro-regulador ajustável (quadro verde do sinótico); regra: **≥ fim da faixa da mola + 0,4 bar** e ≤ 6 bar |

Requisitos de configuração do FY-102:

- Tag **FY-102**; LCD mostrando a posição (PV %).
- Convenção do CLP para todos os grupos: **4 mA = FV-102 fechada, 20 mA = FV-102 aberta** (ação direta), qualquer que seja o atuador.
- Fazer o **Auto Setup** somente depois de acertar o suprimento de ar.
- Para evitar golpe de aríete, o fechamento total (100 → 0 %) não pode levar menos de **10 s**.

## 5. Sintonia recomendada (IHM do sinótico)

| SP_NIVEL | KP_LIC | TI_LIC | K_FF | KP_FIC | TI_FIC |
|---|---|---|---|---|---|
| 50 % | 0,90 (t/h)/% | 100 s | 1,00 | 1,50 %/(t/h) | 4,0 s |

## 6. Portas HART deste PC

| Instrumento | Modem no esquemático | Porta no LasecFDT |
|---|---|---|
| LT-101 | CNCB0 | COM20 |
| FT-101 | CNCB1 | COM21 |
| FT-102 | CNCB2 | COM22 |
| FY-102 | CNCB3 | COM23 |
