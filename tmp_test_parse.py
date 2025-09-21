from app.parser import parse_text

# OCR text extracted from the screenshot (trimmed to relevant block)
ocr_text = '''ZEISS | Versão de Template 0.1 05/2012 | Copyright 2012 Todos os direitos reservados
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
OD: Cilindro: -2,79 D. Nota: astigmatismo elevado
OD
direita
LS: Fácico
Ref: ---
de:
Administrator
n:
1,3375
Análise
Status de olho
Vs: Corpo vítreo
VA:
---
http://www.hcloe.com.br
Resultado:
CVD:
OK
12,00 mm
LVC: Não tratado
Valores biométricos
WTW: 11,9 mm
P: 2,7 mm
(!) Ix: +0,3 mm
ly: +0,0 mm
CW-Chord: 0,3 mm @ 212°
CCT:
AL: 23,73 mm
554 μm
SD: 20 μm
SD:
4 μm
ACD: 2,89 mm
SD:
10 μm
LT: 4,90 mm
SD: 20 μm
SE: 42,30 D
SD: 0,01 D
TSE:
K1: 40,95 D
@ 100°
SD: 0,02 D
TK1:
K2: 43,74 D
@ 10°
SD: 0,01 D
TK2:
AK: -2,79 D
@ 100°
ATK:
B-Scan
Central Topography
Ceratometria
Branco a branco
Licença inexistente para Central
Topography
(!) Valor-limite
(*) Valor editado manualmente
--- nenhum valor medido
Comentário
Fixação
ZEISS
IOLMaster 700
Versão 1.90.12.05
Gerado em: 01/02/2023 13:20, por Administrator.
Página 1 de 1'''

res = parse_text('screenshot-test', ocr_text)
print(res.json())
