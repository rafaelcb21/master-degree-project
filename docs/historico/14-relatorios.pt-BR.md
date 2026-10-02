[English](14-reporting.md) | [Português (Brasil)](14-relatorios.pt-BR.md)

> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.pt-BR.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.pt-BR.md). O corpo original foi mantido.

# 14 — Persistência dos relatórios (`reporting.py`)

## 1. Objetivo do módulo

O arquivo `extractor/reporting.py` possui uma responsabilidade única:

```text
receber um texto já pronto
        ↓
garantir que o diretório de destino exista
        ↓
salvar esse texto em um arquivo UTF-8
```

Seu código é:

```python
from pathlib import Path


def save_report(
    path: Path,
    content: str,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )
```

Apesar de ser um módulo muito pequeno, ele ajuda a manter uma separação importante no projeto:

```text
módulos de extração/cálculo
        ↓
produzem dados estruturados

funções *_to_text()
        ↓
produzem texto

reporting.py
        ↓
persiste o texto em disco
```

---

# 2. Responsabilidade exata

`reporting.py` não decide:

```text
o que deve aparecer no relatório

como formatar pesos

como mostrar quantização

como descrever memória

como apresentar LayerParams
```

Essas decisões pertencem aos próprios módulos.

Por exemplo:

```text
weights.py
    ↓
weights_bias_to_text()

quantization.py
    ↓
quantization_to_text()

memory.py
    ↓
slot_memory_to_text()
    ↓
parameter_layout_to_text()
    ↓
final_memory_layout_to_text()

layer_params.py
    ↓
layer_params_to_text()

params_blob.py
    ↓
params_blob_to_text()
```

`reporting.py` recebe apenas o resultado final dessas funções.

---

# 3. Separação arquitetural

A arquitetura adotada é:

```text
DADOS
  ↓
estrutura Python

APRESENTAÇÃO
  ↓
string

PERSISTÊNCIA
  ↓
arquivo
```

Mais concretamente:

```text
extract_weights_and_bias()
        ↓
dict
        ↓
weights_bias_to_text()
        ↓
str
        ↓
save_report()
        ↓
arquivo .txt
```

Isso evita misturar:

```text
cálculo
formatação
I/O
```

na mesma função.

---

# 4. Importação de `Path`

O módulo importa:

```python
from pathlib import Path
```

`Path` pertence à biblioteca padrão do Python.

Ele fornece uma abstração orientada a objetos para caminhos de arquivos e diretórios.

---

# 5. Por que usar `Path`?

Em vez de manipular caminhos como strings:

```python
"reports/weights.txt"
```

podemos trabalhar com:

```python
Path("reports/weights.txt")
```

Isso permite operações como:

```python
path.parent
```

e:

```python
path.write_text(...)
```

diretamente.

---

# 6. Exemplo

Para:

```python
path = Path(
    "reports/weights.txt"
)
```

temos:

```python
path.parent
```

igual a:

```text
reports
```

---

# 7. Assinatura de `save_report()`

A função é declarada como:

```python
def save_report(
    path: Path,
    content: str,
):
```

Ela recebe dois argumentos.

---

# 8. `path`

O primeiro parâmetro representa:

```text
caminho do arquivo
que será criado ou sobrescrito
```

Exemplo:

```python
Path(
    "reports/quantization.txt"
)
```

---

# 9. `content`

O segundo parâmetro contém:

```text
texto completo
que será escrito no arquivo
```

Seu type hint é:

```python
str
```

Portanto a função espera conteúdo textual.

---

# 10. Exemplo de chamada

```python
save_report(
    Path("reports/weights.txt"),
    weights_bias_to_text(
        weights_bias
    ),
)
```

O fluxo é:

```text
weights_bias
     ↓
weights_bias_to_text()
     ↓
string
     ↓
save_report()
     ↓
reports/weights.txt
```

---

# 11. Primeira operação: diretório pai

A função começa com:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

---

# 12. `path.parent`

Esse atributo retorna o diretório no qual o arquivo deverá ser salvo.

Exemplo:

```python
path = Path(
    "reports/memory/final.txt"
)
```

Então:

```python
path.parent
```

representa:

```text
reports/memory
```

---

# 13. `mkdir()`

O método:

```python
mkdir()
```

cria um diretório.

Neste caso, ele é chamado no diretório pai do arquivo.

---

# 14. Por que criar o diretório?

Sem essa etapa, a tentativa de gravar:

```text
reports/memory/final.txt
```

falharia caso:

```text
reports/memory/
```

ainda não existisse.

---

# 15. `parents=True`

A opção:

```python
parents=True
```

permite criar também diretórios intermediários.

---

# 16. Exemplo

Considere:

```python
Path(
    "reports/memory/final.txt"
)
```

e suponha que nenhum destes diretórios exista:

```text
reports/
reports/memory/
```

Com:

```python
parents=True
```

o Python pode criar:

```text
reports/
    └── memory/
```

automaticamente.

---

# 17. Sem `parents=True`

Se apenas:

```text
reports/
```

não existisse, uma tentativa de criar diretamente:

```text
reports/memory/
```

poderia falhar porque seu diretório pai também estaria ausente.

A opção resolve essa cadeia.

---

# 18. `exist_ok=True`

A segunda opção é:

```python
exist_ok=True
```

Isso significa:

```text
se o diretório já existe,
não tratar isso como erro
```

---

# 19. Exemplo

Na primeira execução:

```text
reports/
```

pode ser criado.

Na segunda execução:

```text
reports/
```

já existe.

Mesmo assim:

```python
mkdir(
    parents=True,
    exist_ok=True,
)
```

continua normalmente.

---

# 20. Idempotência da criação do diretório

Essa parte da função pode ser executada repetidas vezes sem exigir que o chamador saiba previamente:

```text
o diretório existe?
```

O próprio helper resolve isso.

---

# 21. Segunda operação: `write_text()`

Depois:

```python
path.write_text(
    content,
    encoding="utf-8",
)
```

é utilizado para gravar o conteúdo.

---

# 22. O que `write_text()` faz?

O método escreve uma string em um arquivo de texto.

Conceitualmente:

```text
content
   ↓
codificação UTF-8
   ↓
bytes
   ↓
arquivo no disco
```

---

# 23. `encoding="utf-8"`

A codificação é explicitamente definida:

```python
encoding="utf-8"
```

Isso evita depender da codificação padrão do sistema operacional.

---

# 24. Por que isso importa?

Os relatórios utilizam texto em português e podem conter caracteres como:

```text
á
ã
ç
é
ó
```

Com UTF-8 esses caracteres possuem representação previsível.

---

# 25. Exemplo

Uma linha como:

```text
Quantidade de parâmetros de quantização
```

pode ser salva corretamente independentemente da configuração regional da máquina.

---

# 26. Independência do sistema operacional

Sem codificação explícita, o comportamento poderia depender da configuração padrão do ambiente.

Com:

```python
encoding="utf-8"
```

o projeto define explicitamente seu formato textual.

---

# 27. Arquivo existente

`write_text()` abre o arquivo para escrita.

Se o arquivo já existir, seu conteúdo anterior é substituído.

---

# 28. Consequência

Executar novamente:

```python
save_report(
    Path("reports/weights.txt"),
    novo_conteudo,
)
```

atualiza o relatório.

A função não:

```text
anexa ao arquivo anterior
```

Ela grava o conteúdo recebido como o conteúdo atual do relatório.

---

# 29. Isso é adequado aos relatórios gerados

Os arquivos em:

```text
reports/
```

representam o estado da execução atual do extrator.

Portanto é coerente que:

```text
nova execução
    ↓
novo relatório
    ↓
substitui relatório anterior
```

---

# 30. A função não adiciona newline

`save_report()` escreve exatamente:

```python
content
```

Ela não acrescenta automaticamente:

```text
\n
```

no final.

---

# 31. Consequência

Se o relatório deve terminar com newline, essa decisão pertence à função:

```text
*_to_text()
```

ou ao conteúdo fornecido.

---

# 32. A função não altera o texto

Ela não faz:

```text
strip()

replace()

formatação

conversão de linhas

indentação
```

O texto recebido é passado diretamente para:

```python
write_text()
```

---

# 33. Isso preserva a separação de responsabilidades

A função não precisa entender o conteúdo.

Para ela, estas strings são equivalentes:

```text
relatório de pesos

relatório de memória

relatório de quantização

qualquer outro texto
```

---

# 34. Ela não conhece o modelo

`save_report()` não recebe:

```text
model

subgraph

tensor

operator
```

Logo não possui qualquer dependência do TFLite.

---

# 35. Ela não conhece a estrutura dos dados

Também não recebe:

```text
weight_records

layer_params

regions

mul_vals
```

A transformação dessas estruturas em texto já aconteceu antes.

---

# 36. Exemplo com pesos

```text
weights.py
    ↓
extract_weights_and_bias()
    ↓
dict

weights_bias_to_text()
    ↓
str

reporting.py
    ↓
arquivo
```

---

# 37. Exemplo com quantização

```text
quantization.py
    ↓
extract_quantization_parameters()
    ↓
dict

quantization_to_text()
    ↓
str

reporting.py
    ↓
arquivo
```

---

# 38. Exemplo com memória

```text
memory.py
    ↓
calculate_final_memory_layout()
    ↓
dict

final_memory_layout_to_text()
    ↓
str

reporting.py
    ↓
arquivo
```

---

# 39. Exemplo com `LayerParam`

```text
layer_params.py
    ↓
build_layer_params()
    ↓
list[dict]

layer_params_to_text()
    ↓
str

reporting.py
    ↓
arquivo
```

---

# 40. Exemplo com `params_blob`

```text
params_blob.py
    ↓
build_params_blob()
    ↓
dict

params_blob_to_text()
    ↓
str

reporting.py
    ↓
arquivo
```

---

# 41. Papel de `main.py`

Normalmente quem combina essas partes é:

```text
main.py
```

Por exemplo, conceitualmente:

```python
report = weights_bias_to_text(
    weights_bias
)

save_report(
    REPORTS_DIR / "weights.txt",
    report,
)
```

---

# 42. Responsabilidade do `main.py`

`main.py` decide:

```text
qual relatório gerar

qual nome de arquivo utilizar

quando salvá-lo
```

`reporting.py` apenas executa a persistência.

---

# 43. Relação com `config.py`

`config.py` possui:

```python
REPORTS_DIR = Path(
    "reports"
)
```

Essa configuração pode ser combinada com nomes específicos.

Exemplo:

```python
REPORTS_DIR / "weights.txt"
```

resulta em:

```text
reports/weights.txt
```

---

# 44. O módulo não importa `REPORTS_DIR`

Essa é uma decisão importante.

`reporting.py` não faz:

```python
from extractor.config import (
    REPORTS_DIR,
)
```

---

# 45. Por que isso é bom?

Porque a função não fica presa a:

```text
reports/
```

Ela pode salvar em qualquer caminho fornecido pelo chamador.

---

# 46. Exemplo

A mesma função pode receber:

```python
Path(
    "reports/weights.txt"
)
```

ou:

```python
Path(
    "debug/current-run.txt"
)
```

ou:

```python
Path(
    "/tmp/model-report.txt"
)
```

desde que o ambiente permita a escrita.

---

# 47. Configuração fora do helper

Portanto:

```text
onde salvar?
    ↓
decisão do chamador

como salvar?
    ↓
reporting.py
```

---

# 48. Princípio de responsabilidade única

Esse módulo é um exemplo muito claro do princípio:

```text
uma função
    ↓
uma responsabilidade
```

A função faz exatamente duas operações necessárias para persistir o relatório:

```text
1. criar diretório

2. escrever arquivo
```

---

# 49. Por que essas duas operações pertencem juntas?

Porque salvar um arquivo em um caminho arbitrário normalmente exige que seu diretório exista.

Assim:

```text
garantir destino
+
gravar arquivo
```

formam uma única operação conceitual:

```text
salvar relatório
```

---

# 50. O que não deveria entrar aqui?

Não seria adequado acrescentar coisas como:

```text
calcular total de pesos

formatar tabela de quantização

determinar maior tensor

calcular MEM_PAGES

converter bytes de parâmetros
```

Essas funções pertencem aos módulos de domínio.

---

# 51. Tampouco deveria gerar WAT

O módulo não possui relação com:

```text
wat_generator.py
```

além de ambos realizarem I/O de arquivos.

O conteúdo e a responsabilidade são diferentes.

---

# 52. Comparação com `wat_generator.py`

`wat_generator.py`:

```text
recebe template
substitui placeholders
insere blobs
gera conteúdo WAT
salva artefato
```

`reporting.py`:

```text
recebe texto pronto
salva texto
```

---

# 53. Por que não usar `print()` para tudo?

O projeto separa:

```text
saída resumida de execução
    ↓
print()
```

de:

```text
informação detalhada de diagnóstico
    ↓
reports/
```

Isso evita poluir o terminal com centenas ou milhares de linhas.

---

# 54. Exemplo

O terminal pode mostrar apenas:

```text
Modelo carregado.
68 camadas processadas.
WAT gerado com sucesso.
```

Enquanto os arquivos podem conter:

```text
todos os tensors
todos os pesos
todos os multipliers
todos os offsets
todas as LayerParams
```

---

# 55. Benefício para o projeto

Essa divisão torna a execução:

```text
legível
```

sem perder:

```text
rastreabilidade detalhada
```

---

# 56. Relatórios como artefatos de diagnóstico

Os arquivos salvos por esse módulo não fazem parte diretamente da inferência.

O runtime não lê:

```text
reports/*.txt
```

---

# 57. Consequência

Excluir os relatórios depois da geração não altera:

```text
weights_raw

params_blob

model.wat

model.wasm
```

Eles são auxiliares de inspeção.

---

# 58. Mas são importantes para validação

Eles permitem responder:

```text
qual tensor determinou SLOT_BYTES?

qual peso começou em determinado offset?

qual multiplier foi calculado?

qual LayerParam recebeu determinado ponteiro?

qual região de memória começa em determinado endereço?
```

Sem precisar inserir debug dentro do WAT.

---

# 59. Essa separação melhorou o WAT

Um dos princípios da refatoração é evitar transformar:

```text
generated/model.wat
```

em um misto de:

```text
código
+
dump de debug
+
relatório
```

---

# 60. Estrutura desejada

```text
generated/model.wat
    ↓
artefato executável/textual


reports/
    ↓
artefatos de diagnóstico


docs/
    ↓
explicação da arquitetura
```

---

# 61. Três tipos de artefato

É importante distinguir:

### `docs/`

Explica:

```text
como o código funciona
```

---

### `reports/`

Mostra:

```text
o que aconteceu
em uma execução específica
com um modelo específico
```

---

### `generated/`

Contém:

```text
artefato gerado
para execução/compilação
```

---

# 62. Exemplo da diferença

`docs/09-memory-layout.md` explica:

```text
como MEM_PAGES é calculado
```

Já um relatório poderia mostrar:

```text
MEM_PAGES = 17
```

para um modelo concreto.

---

# 63. Outro exemplo

`docs/08-quantization.md` explica:

```text
como multiplier e shift são calculados
```

Enquanto:

```text
reports/quantization.txt
```

pode mostrar:

```text
op 12:
multiplier = ...
shift = ...
```

da execução atual.

---

# 64. `reporting.py` não mistura essas camadas

Ele apenas sabe:

```text
tenho uma string

tenho um destino

vou salvar
```

---

# 65. Tratamento de erros

A função não possui:

```python
try:
    ...
except:
    ...
```

---

# 66. Consequência

Se ocorrer um erro de sistema de arquivos, ele é propagado naturalmente para o chamador.

Exemplos:

```text
sem permissão de escrita

caminho inválido

disco sem espaço

destino incompatível
```

---

# 67. Por que isso é razoável?

Se um relatório solicitado não puder ser salvo, esconder o erro poderia dificultar muito o diagnóstico.

A implementação atual prefere:

```text
erro real
    ↓
exceção
    ↓
chamador percebe
```

---

# 68. Não existe fallback silencioso

A função não faz:

```text
falhou ao salvar
    ↓
ignora
```

ou:

```text
falhou
    ↓
printa e continua
```

O erro de I/O permanece visível.

---

# 69. Retorno da função

Não existe:

```python
return ...
```

explícito.

Portanto, em Python, o retorno é:

```python
None
```

---

# 70. Por que não retornar o caminho?

A implementação atual não precisa disso.

O chamador já conhece:

```python
path
```

porque foi ele quem forneceu o argumento.

---

# 71. Por que não retornar número de bytes?

Também não é necessário para o fluxo atual.

Se futuramente isso for útil, poderia ser acrescentado, mas hoje a função permanece minimalista.

---

# 72. Type hints

A assinatura utiliza:

```python
path: Path
```

e:

```python
content: str
```

Esses type hints documentam a interface esperada.

---

# 73. Type hint não é validação de runtime

Python não impede automaticamente:

```python
save_report(
    "reports/a.txt",
    "abc",
)
```

apenas porque o type hint diz:

```python
Path
```

---

# 74. Consequência prática

A implementação acessa:

```python
path.parent
```

Logo uma string comum:

```python
"reports/a.txt"
```

não possui essa interface.

No uso atual, espera-se que o chamador forneça um `Path`.

---

# 75. Possível generalização futura

Seria possível normalizar internamente:

```python
path = Path(path)
```

como `wat_generator.py` faz.

Mas essa não é a implementação atual.

---

# 76. Portanto a interface atual é deliberadamente simples

```text
entrada:
Path + str

saída:
arquivo
```

---

# 77. Exemplo completo

Suponha:

```python
report_path = Path(
    "reports/memory.txt"
)

report_content = (
    "MEM_END = 1097072\n"
    "MEM_PAGES = 17"
)
```

A chamada:

```python
save_report(
    report_path,
    report_content,
)
```

executa:

```text
reports/
    ↓
cria se necessário

reports/memory.txt
    ↓
escreve UTF-8
```

---

# 78. Resultado conceitual

```text
reports/
└── memory.txt
```

com:

```text
MEM_END = 1097072
MEM_PAGES = 17
```

Os valores acima são apenas exemplos de conteúdo.

---

# 79. Reexecução

Se o arquivo já contiver:

```text
MEM_PAGES = 16
```

e a função for chamada novamente com:

```text
MEM_PAGES = 17
```

o arquivo será substituído.

---

# 80. Não existe histórico automático

A função não cria:

```text
memory-1.txt

memory-2.txt

memory-2026-09-27.txt
```

automaticamente.

Se houver necessidade de versionar relatórios, o nome do arquivo deve ser decidido pelo chamador.

---

# 81. Isso mantém o helper neutro

A função não precisa conhecer:

```text
datas

nomes de modelos

versões

runs
```

Essas decisões permanecem fora dela.

---

# 82. Relação com a reprodutibilidade

Como cada módulo produz texto a partir das estruturas calculadas e `save_report()` grava esse texto sem modificá-lo, os relatórios podem ser usados para comparar execuções.

Por exemplo:

```text
execução A
    ↓
quantization.txt

execução B
    ↓
quantization.txt
```

e então comparar:

```text
offsets
multipliers
shifts
Q6
```

---

# 83. Mas o módulo não realiza comparação

Essa atividade está fora de sua responsabilidade.

`reporting.py` apenas persiste os resultados.

---

# 84. Relação com testes

Esse helper é suficientemente simples para que seu comportamento esperado possa ser descrito por três casos principais:

```text
1. diretório não existe
    → cria e escreve

2. diretório existe
    → apenas escreve

3. arquivo existe
    → sobrescreve
```

---

# 85. Possível teste 1

```text
reports_test/
não existe

save_report(
    reports_test/a.txt,
    "abc"
)

resultado esperado:
diretório criado
arquivo criado
conteúdo = "abc"
```

---

# 86. Possível teste 2

```text
diretório já existe

save_report(...)

resultado:
nenhum erro por causa do mkdir
```

graças a:

```python
exist_ok=True
```

---

# 87. Possível teste 3

Arquivo anterior:

```text
abc
```

Nova chamada:

```text
xyz
```

Resultado:

```text
xyz
```

e não:

```text
abcxyz
```

---

# 88. Não há necessidade de testar lógica de domínio aqui

Não faria sentido testar:

```text
multiplier correto

SLOT_BYTES correto

offset correto
```

em `reporting.py`.

Essas verificações pertencem aos respectivos módulos.

---

# 89. Uma função pequena é desejável

Não existe problema em possuir um arquivo com apenas:

```text
uma função
```

quando essa função representa uma responsabilidade arquitetural própria.

---

# 90. Evitar abstração excessiva

Também não existe necessidade atual de criar:

```text
ReportManager

ReportWriter

ReportFactory

BaseReport
```

A operação necessária é muito simples.

A função:

```python
save_report()
```

resolve o problema diretamente.

---

# 91. Por que não colocar isso em `main.py`?

Seria possível repetir:

```python
path.parent.mkdir(...)
path.write_text(...)
```

para cada relatório.

Mas isso geraria duplicação.

---

# 92. Exemplo do problema

Sem o helper:

```python
weights_path.parent.mkdir(...)
weights_path.write_text(...)

memory_path.parent.mkdir(...)
memory_path.write_text(...)

quant_path.parent.mkdir(...)
quant_path.write_text(...)
```

---

# 93. Com `save_report()`

O código do orquestrador fica:

```python
save_report(
    weights_path,
    weights_text,
)

save_report(
    memory_path,
    memory_text,
)

save_report(
    quant_path,
    quant_text,
)
```

---

# 94. Benefício

A política:

```text
criar diretório automaticamente
+
UTF-8
```

fica definida em um único lugar.

---

# 95. Se a política mudar

Suponha que futuramente todos os relatórios devam usar outra regra de persistência.

A alteração pode ficar centralizada em:

```text
reporting.py
```

sem editar cada módulo.

---

# 96. Porém a formatação continua descentralizada

Isso é importante.

Centralizar a persistência não significa centralizar todos os relatórios.

Continuamos com:

```text
weights_bias_to_text()
quantization_to_text()
layer_params_to_text()
...
```

junto aos módulos que conhecem seus próprios dados.

---

# 97. Por que essa divisão é boa?

Quem conhece melhor:

```text
weight_records
```

é:

```text
weights.py
```

Quem conhece melhor:

```text
regions
MEM_END
MEM_PAGES
```

é:

```text
memory.py
```

Quem conhece melhor:

```text
LayerParams
```

é:

```text
layer_params.py
```

Mas nenhum deles precisa conhecer detalhes repetitivos de persistência.

---

# 98. Fluxo arquitetural de relatórios

```text
┌───────────────────────────┐
│       graph.py            │
│       graph_to_text()     │
└─────────────┬─────────────┘
              │
              │
┌─────────────▼─────────────┐
│       slots.py            │
│ slot_allocation_to_text() │
└─────────────┬─────────────┘
              │
              │
┌─────────────▼─────────────┐
│      weights.py           │
│ weights_bias_to_text()    │
└─────────────┬─────────────┘
              │
              │
           ... etc.
              │
              ▼
┌───────────────────────────┐
│      reporting.py         │
│                           │
│      save_report()        │
└─────────────┬─────────────┘
              │
              ▼
          reports/
```

---

# 99. Relação com a estrutura do projeto

```text
master-degree-project/
│
├── extractor/
│   ├── reporting.py
│   └── ...
│
├── docs/
│   └── documentação
│
├── reports/
│   └── resultados textuais
│
└── generated/
    └── artefatos gerados
```

`reporting.py` é a interface simples entre:

```text
extractor/
```

e:

```text
reports/
```

---

# 100. Princípio central

O desenho adotado pode ser resumido como:

```text
dados estruturados são a fonte de verdade
```

e não:

```text
texto do relatório é a fonte de verdade
```

---

# 101. Consequência

Nenhuma etapa posterior deve fazer:

```text
abrir report.txt
    ↓
parsear texto
    ↓
recuperar offsets
```

---

# 102. Fluxo correto

```text
dict Python
   │
   ├──→ próxima etapa do pipeline
   │
   └──→ *_to_text()
            │
            ▼
       save_report()
```

---

# 103. Fluxo incorreto

```text
dict
 ↓
texto
 ↓
arquivo
 ↓
ler arquivo
 ↓
parsear texto
 ↓
continuar pipeline
```

Isso transformaria uma representação humana em protocolo interno, o que não é desejável.

---

# 104. Relatório é saída lateral

Podemos representar:

```text
                  ┌──→ relatório
                  │
dados estruturados│
                  └──→ próxima etapa
```

Ou seja, o relatório é uma saída auxiliar.

Ele não fica no caminho crítico dos cálculos.

---

# 105. Exemplo

```text
weights_bias
      │
      ├──────────────→ memory.py
      │
      └→ to_text()
          ↓
       report
```

O `memory.py` recebe:

```text
weights_bias
```

diretamente.

Ele nunca lê:

```text
weights.txt
```

---

# 106. Essa característica aumenta robustez

Formatos de relatório podem mudar:

```text
espaçamento

cabeçalhos

nomes

alinhamento visual
```

sem quebrar o pipeline.

---

# 107. Exemplo

Podemos mudar:

```text
Total de bytes de pesos: 1234
```

para:

```text
Pesos totais = 1234 bytes
```

e nenhuma etapa de cálculo é afetada.

---

# 108. Isso confirma a função dos relatórios

Eles existem para:

```text
seres humanos
```

não para:

```text
comunicação interna entre módulos
```

---

# 109. `save_report()` como último passo da ramificação

A sequência é:

```text
dados
 ↓
to_text()
 ↓
save_report()
 ↓
fim
```

Nenhuma etapa do pipeline depende do retorno.

---

# 110. Dependências mínimas

`reporting.py` depende apenas de:

```text
pathlib
```

Não depende de:

```text
tflite

numpy

struct

re

outros módulos extractor
```

---

# 111. Benefício

Isso torna o helper:

```text
simples

isolado

reutilizável

fácil de testar
```

---

# 112. Ausência de estado global

Não existem:

```text
variáveis globais mutáveis

cache

arquivo aberto permanentemente

singleton
```

Cada chamada funciona independentemente.

---

# 113. Não mantém handles abertos

`Path.write_text()` cuida internamente da abertura e fechamento do arquivo.

O módulo não precisa fazer manualmente:

```python
open(...)
close()
```

---

# 114. Versão equivalente conceitual

O código poderia ser escrito aproximadamente como:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with path.open(
    "w",
    encoding="utf-8",
) as file:
    file.write(content)
```

`write_text()` apenas fornece uma forma mais curta para esse caso.

---

# 115. Por que a versão atual é melhor?

Para uma função tão simples:

```python
path.write_text(...)
```

deixa a intenção imediata:

```text
escrever este texto neste caminho
```

sem boilerplate desnecessário.

---

# 116. Ausência de append

Também fica evidente que o objetivo é escrever o arquivo completo, e não adicionar fragmentos progressivamente.

---

# 117. Tamanho dos relatórios

Mesmo que determinados relatórios sejam grandes, a função recebe:

```text
content
```

inteiro como uma string e então grava tudo.

---

# 118. Consequência

O design atual pressupõe que os relatórios são pequenos o suficiente para existir em memória como strings completas.

Para os relatórios deste projeto isso é coerente com a implementação atual.

---

# 119. Não é um logger

`save_report()` não deve ser confundido com:

```text
logging
```

---

# 120. Diferença

Um logger normalmente trabalha com:

```text
mensagens incrementais

níveis:
INFO
DEBUG
WARNING
ERROR

timestamps

handlers
```

`save_report()` trabalha com:

```text
documento completo
```

---

# 121. Exemplo

Não se espera utilizar:

```python
save_report(
    path,
    "Processando layer 1..."
)
```

repetidamente durante o loop.

Isso sobrescreveria o arquivo a cada chamada.

---

# 122. Uso pretendido

O padrão correto é:

```text
processar tudo
    ↓
montar relatório completo
    ↓
salvar uma vez
```

---

# 123. Relação com `print()`

Podemos ter simultaneamente:

```python
print(
    "WAT gerado com sucesso."
)
```

e:

```python
save_report(
    report_path,
    report_content,
)
```

As duas saídas têm públicos e níveis de detalhe diferentes.

---

# 124. Terminal

Ideal para:

```text
resumo operacional
```

---

# 125. Relatórios

Ideais para:

```text
detalhes técnicos

auditoria

comparação

debug

documentação de execução
```

---

# 126. Não há conflito entre ambos

A existência de `reports/` não impede o `main.py` de imprimir um resumo curto.

O princípio é apenas evitar:

```text
centenas de linhas
```

no terminal.

---

# 127. Tratamento de diretórios

A chamada:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

também torna cada relatório independente.

Não é necessário que `main.py` faça previamente:

```python
REPORTS_DIR.mkdir(...)
```

para todos.

---

# 128. Mesmo assim, `main.py` poderia fazê-lo

Mas seria redundante.

Cada chamada de `save_report()` já garante sua própria pré-condição de diretório.

---

# 129. Exemplo com subpastas futuras

Se futuramente o projeto quiser:

```text
reports/
├── graph/
├── quantization/
└── memory/
```

a função continua funcionando sem modificação.

---

# 130. Exemplo

```python
save_report(
    Path(
        "reports/quantization/"
        "parameters.txt"
    ),
    content,
)
```

cria automaticamente:

```text
reports/quantization/
```

se necessário.

---

# 131. Essa flexibilidade vem de `parents=True`

Portanto o helper não está limitado a um único nível de diretório.

---

# 132. Possível melhoria futura: retornar o caminho

Poderia ser útil fazer:

```python
return path
```

para permitir:

```python
saved_path = save_report(...)
```

Mas isso não é necessário atualmente porque o chamador já possui esse valor.

---

# 133. Possível melhoria futura: normalizar `Path`

Também poderia começar com:

```python
path = Path(path)
```

permitindo aceitar:

```text
Path

ou string
```

Mas a assinatura atual pede explicitamente:

```text
Path
```

e a implementação segue essa expectativa.

---

# 134. Possível melhoria futura: gravação atômica

Para cenários mais críticos, poderia ser feito:

```text
gravar arquivo temporário
        ↓
rename atômico
        ↓
arquivo final
```

Isso evitaria arquivos parcialmente escritos em caso de interrupção.

---

# 135. Isso é necessário aqui?

Para os relatórios diagnósticos atuais, provavelmente seria complexidade desnecessária.

A função atual atende bem ao papel simples que possui.

---

# 136. Possível melhoria futura: retorno de metadados

Também poderia retornar:

```text
path

bytes gravados
```

Mas novamente não existe necessidade atual no pipeline.

---

# 137. Possível melhoria futura: formatos diferentes

Se futuramente o projeto gerar:

```text
JSON

CSV

Markdown
```

`save_report()` ainda poderia salvar qualquer um deles, desde que o conteúdo já venha como:

```text
str
```

---

# 138. Exemplo Markdown

```python
save_report(
    Path(
        "reports/memory.md"
    ),
    markdown_text,
)
```

funcionaria sem alterações.

---

# 139. Exemplo CSV

```python
save_report(
    Path(
        "reports/layers.csv"
    ),
    csv_text,
)
```

também.

---

# 140. A extensão não é interpretada

A função não verifica:

```text
.txt

.md

.csv
```

O conteúdo e a extensão são responsabilidade do chamador.

---

# 141. Isso mantém o helper genérico

Seu contrato permanece:

```text
Path + texto
    ↓
arquivo UTF-8
```

---

# 142. Invariantes esperados

Antes da chamada:

```text
path é um Path utilizável

content é uma string
```

---

# 143. Depois de uma chamada bem-sucedida

Devemos ter:

```text
path.parent existe

path existe

conteúdo do arquivo
corresponde a content
```

codificado em UTF-8.

---

# 144. O que a função não garante?

Ela não garante:

```text
que o conteúdo esteja correto

que o relatório esteja completo

que os valores calculados estejam corretos

que o arquivo tenha determinado formato
```

Essas propriedades pertencem às funções que produziram `content`.

---

# 145. Erro de conteúdo versus erro de persistência

É importante separar:

```text
multiplier errado no relatório
    ↓
problema em quantization.py
```

de:

```text
não foi possível criar quantization.txt
    ↓
problema de I/O/reporting
```

---

# 146. Isso ajuda no diagnóstico

Cada módulo possui um domínio de responsabilidade claro.

---

# 147. Fluxo completo do sistema de relatórios

```text
                       DADOS
                         │
                         ▼
              função de processamento
                         │
                         ▼
                estrutura Python
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
      próxima etapa             *_to_text()
      do pipeline                    │
                                     ▼
                                  string
                                     │
                                     ▼
                              save_report()
                                     │
                                     ▼
                                  reports/
```

---

# 148. Relação com a filosofia geral do projeto

A refatoração segue o princípio:

```text
calcular
    ↓
retornar estrutura
    ↓
validar
    ↓
serializar
    ↓
gerar artefato
```

Os relatórios acompanham esse fluxo sem controlá-lo.

---

# 149. O relatório não vira fonte de dados

Essa é uma regra arquitetural importante:

```text
nunca parsear os relatórios
para recuperar dados do pipeline
```

A fonte de verdade permanece:

```text
dicionários

listas

bytes

objetos estruturados
```

---

# 150. Consequência para manutenção

Podemos modificar a apresentação humana sem risco de alterar o comportamento da inferência.

Isso permite melhorar os relatórios livremente.

---

# 151. Exemplo

Hoje:

```text
Total de tensors de pesos: 54
```

amanhã poderia ser:

```text
Pesos extraídos: 54 tensors
```

sem qualquer impacto no WAT.

---

# 152. Isso também facilita documentação

Os arquivos em:

```text
docs/
```

podem explicar o significado dos relatórios.

Já:

```text
reports/
```

mostram os valores concretos.

---

# 153. Visão da estrutura final do projeto

```text
master-degree-project/
│
├── extractor/
│   │
│   ├── graph.py
│   ├── slots.py
│   ├── weights.py
│   ├── quantization.py
│   ├── memory.py
│   ├── layer_params.py
│   ├── params_blob.py
│   ├── wat_generator.py
│   └── reporting.py
│
├── wat/
│   └── model_template.wat
│
├── generated/
│   └── model.wat
│
├── reports/
│   └── *.txt
│
└── docs/
    └── *.md
```

---

# 154. Papel de cada saída

```text
docs/
    ↓
explica o sistema


reports/
    ↓
explica uma execução


generated/
    ↓
contém o artefato gerado
```

---

# 155. O módulo mais simples também ajuda a arquitetura

Mesmo contendo apenas:

```text
uma função de poucas linhas
```

`reporting.py` elimina duplicação e impede que lógica de sistema de arquivos seja espalhada pelos módulos de domínio.

---

# 156. Síntese

`reporting.py` possui uma responsabilidade extremamente pequena e bem definida:

```text
salvar conteúdo textual
em um arquivo
de forma previsível
```

A função:

```python
save_report()
```

recebe:

```text
Path
+
str
```

garante que o diretório pai exista por meio de:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

e grava o conteúdo utilizando:

```python
path.write_text(
    content,
    encoding="utf-8",
)
```

Ela não gera o relatório, não modifica o conteúdo, não interpreta dados do modelo e não interfere no pipeline de inferência.

Sua existência permite manter três responsabilidades separadas:

```text
PROCESSAMENTO
    ↓
módulos de domínio


FORMATAÇÃO
    ↓
funções *_to_text()


PERSISTÊNCIA
    ↓
reporting.save_report()
```

Essa separação também reforça uma regra arquitetural importante do projeto:

```text
os dados estruturados são
a fonte de verdade

os relatórios são
representações humanas auxiliares
```

Assim, `reporting.py` funciona como o último passo de uma ramificação de diagnóstico do pipeline, sem criar dependência entre os relatórios textuais e a geração efetiva do artefato WebAssembly.
