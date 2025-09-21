from app import parser


full_pdf_text = '''ZEISS | Versão de Template 0.1 05/2012 | Copyright 2012 Todos os direitos reservados
Paciente
CUNHA, GERALDO JOSE FILIAGI
Data de nascim.
ID de paciente
17/12/1943
0391611
Médico
Sexo
Masculino
HCLOE - Hospital de Olhos
Rua Itapeva, 240
Operador
Administrator
01131240999
Data de verific. da calibr: 01/02/2023
de:
Data da medição:
01/02/2023
n:
Administrator
1,3375
OD: Cilindro: -2,79 D. Nota: astigmatismo elevado
OD
direita
LS: Fácico
Ref:
Análise
sac@hcloe.com.br
http://www.hcloe.com.br
Resultado:
CVD:
OK
12,00 mm
Status de olho
VS: Corpo vítreo
LVC: Não tratado
VA:
Valores biométricos
AL: 23,73 mm
SD:
20 μm
WTW: 11,9 mm (!) lx: +0,3 mm
CCT:
554 μm
SD:
4 μm
P:
2,7 mm
ly: +0,0 mm
CW-Chord: 0,3 mm @ 212°
ACD:
2,89 mm
SD:
10 μm
LT:
4,90 mm
SD:
20 μm
SE: 42,30 D
K1: 40,95 D
K2: 43,74 D
AK: -2,79 D
SD: 0,01 D
TSE:
@ 100°
SD: 0,02 D
TK1:
@ 10°
@ 100°
SD: 0,01 D
TK2:
ATK:
B-Scan
Fixação
Central Topography
Ceratometria
Branco a branco
Licença inexistente para Central
Topography
(!) Valor-limite
Comentário
(*) Valor editado manualmente
- nenhum valor medido
ZEISS
IOLMaster 700
Versão 1.90.12.05
Gerado em: 01/02/2023 13:20, por Administrator.
Página 1 de 1
ZEISS | Versão de Template 0.1 05/2012 | Copyright 2012 Todos os direitos reservados
Paciente
CUNHA, GERALDO JOSE FILIAGI
Data de nascim.
ID de paciente
17/12/1943
0391611
Médico
Sexo
Masculino
HCLOE - Hospital de Olhos
Rua Itapeva, 240
Operador
Administrator
01131240999
Data de verific. da calibr: 01/02/2023

Data da medição:
01/02/2023
n:
Administrator
1,3375
LS: Fácico
Ref:
sac@hcloe.com.br
http://www.hcloe.com.br
Resultado:
CVD:
OK
12,00 mm
Análise
Status de olho
LVC: Não tratado
OS
esquerda
VS: Corpo vítreo
VA:
Valores biométricos
AL: 23,77 mm
SD:
16 μm
CCT:
544 μm
SD:
4 μm
WTW: 11,6 mm (!)
P: 2,5 mm
Ix: -0,4 mm
ly: +0,0 mm
CW-Chord: 0,1 mm @ 39°
ACD:
2,83 mm
SD:
11 μm
LT:
4,95 mm
SD: 17 μm
SE: 42,59 D
SD: 0,01 D
TSE:
K1: 41,45 D
K2: 43,80 D
AK: -2,35 D
@ 75°
SD: 0,03 D
TK1:
@ 165°
SD: 0,02 D
TK2:
@
75°
ATK:
B-Scan
Fixação
Central Topography
Ceratometria
Branco a branco
Licença inexistente para Central
Topography
(!) Valor-limite
Comentário
(*) Valor editado manualmente
- nenhum valor medido
ZEISS
IOLMaster 700
Versão 1.90.12.05
Gerado em: 01/02/2023 13:21, por Administrator.
Página 1 de 1'''

os_screenshot_text = '''Versão de Template 0.1 05/2012 | Copyright 2012 Todos os direitos reservados
Paciente
CUNHA, GERALDO JOSE FILIAGI
Data de nascim.
ID de paciente
17/12/1943
0391611
Médico
Data de verific. da calibr: 01/02/2023
Data da medição:
Sexo
Masculino
HCLOE - Hospital de Olhos
Operador Administrator
de:
01/02/2023
n:
Administrator
1,3375
Rua Itapeva, 240
01131240999
sac@hcloe.com.br
http://www.hcloe.com.br
Resultado:
CVD:
OK
12,00 mm
LS: Fácico
Ref:
--
Análise
Status de olho
vs: Corpo vítreo
LVC: Não tratado
VA:
---
Valores biométricos
OS
esquerda
AL: 23,77 mm
SD:
16 μm
WTW: 11,6 mm (!) Ix: -0,4 mm
CCT:
544 μm
SD:
4 μm
P: 2,5 mm
ly: +0,0 mm
CW-Chord: 0,1 mm @ 39°
ACD: 2,83 mm
SD:
11 μm
LT: 4,95 mm
SD:
17 μm
SE: 42,59 D
SD: 0,01 D
TSE:
K1: 41,45 D @
K2: 43,80 D
AK:
-2,35 D
888
75°
SD: 0,03 D
TK1:
---
@ 165°
SD: 0,02 D
TK2:
@
75°
ATK:
---
B-Scan
Fixação
Central Topography
Ceratometria
Branco a branco
Licença inexistente para Central
Topography
(!) Valor-limite
Comentário
(*) Valor editado manualmente
--- nenhum valor medido
ZEISS
IOLMaster 700
Versão 1.90.12.05
Gerado em: 01/02/2023 13:21, por Administrator.
Página 1 de 1'''
noop_llm = lambda text, missing: {"od": {}, "os": {}}


def test_full_pdf_axes():
    r = parser.parse_text('file1', full_pdf_text, llm_func=noop_llm)
    # full_pdf sample should yield k1_axis 100 and k2_axis 100 for OD, and 75 for OS
    assert r.od.k1_axis == '100'
    assert r.od.k2_axis == '100'
    assert r.os.k1_axis == '75'
    assert r.os.k2_axis == '75'


def test_os_screenshot_axes():
    r = parser.parse_text('file2', os_screenshot_text, llm_func=noop_llm)
    # os screenshot should detect 165 axes for k1/k2 (layout or next-line TK pairing), not the stray '75' or '888'
    assert r.os.k1_axis == '165'
    assert r.os.k2_axis == '165'
    # OD should be empty
    assert r.od.k1 == '' and r.od.k2 == ''
