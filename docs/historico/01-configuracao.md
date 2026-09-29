> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.md). O corpo original foi mantido.

# 01 — Configuração do pipeline (`config.py`)

## 1. Objetivo do módulo

O arquivo `extractor/config.py` centraliza os parâmetros globais utilizados durante o processo de extração do modelo TFLite e geração do arquivo WebAssembly Text (`.wat`).

Seu objetivo é evitar que caminhos, alinhamentos, quantidade de slots e outros parâmetros estruturais sejam repetidos ou definidos diretamente em vários módulos do projeto.

O arquivo atual é:

```python
from pathlib import Path


MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)

WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)

OUT_WAT_PATH = Path(
    "generated/model.wat"
)

REPORTS_DIR = Path(
    "reports"
)

NUM_SLOTS = 3

BATCH = 1

ALIGN = 16

KERNEL_BASE_HINT = 2048
```

O módulo não executa nenhuma extração nem modifica arquivos. Ele apenas disponibiliza valores de configuração para os demais componentes.

---

# 2. Visão geral

O fluxo das configurações pode ser representado da seguinte forma:

```text
                         config.py
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      MODEL_PATH        parâmetros         caminhos
          │             de memória         de saída
          │                 │                 │
          ▼                 ▼                 ▼
    model_loader.py     NUM_SLOTS        REPORTS_DIR
          │             BATCH            OUT_WAT_PATH
          │             ALIGN            WAT_TEMPLATE_PATH
          │             KERNEL_BASE_HINT
          ▼
      modelo TFLite
          │
          ▼
    pipeline de extração
          │
          ├── grafo
          ├── slots
          ├── pesos e bias
          ├── quantização
          ├── layout de memória
          ├── LayerParams
          ├── params_blob
          │
          ▼
     geração do WAT
```

Portanto, `config.py` está no início do fluxo, mas suas constantes influenciam diversas etapas posteriores.

---

# 3. `Path` e manipulação de caminhos

O módulo começa com:

```python
from pathlib import Path
```

`Path` pertence à biblioteca padrão do Python e representa caminhos do sistema de arquivos como objetos.

Por exemplo:

```python
MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)
```

em vez de:

```python
MODEL_PATH = "model_int8_esp32.tflite"
```

A utilização de `Path` facilita operações posteriores como:

```python
MODEL_PATH.read_bytes()
```

ou:

```python
REPORTS_DIR / "02-grafo.txt"
```

Neste segundo caso:

```python
REPORTS_DIR = Path("reports")
```

e:

```python
REPORTS_DIR / "02-grafo.txt"
```

produzem conceitualmente:

```text
reports/02-grafo.txt
```

No Windows, o Python faz automaticamente a adaptação adequada do separador de diretórios.

---

# 4. Caminhos relativos

Todos os caminhos definidos neste arquivo são relativos:

```python
Path("model_int8_esp32.tflite")
Path("wat/model_template.wat")
Path("generated/model.wat")
Path("reports")
```

Isso significa que eles são interpretados em relação ao diretório de trabalho atual do processo Python.

No uso normal do projeto:

```powershell
PS C:\Users\rafae\Downloads\master-degree-project> python .\main.py
```

o diretório de trabalho é:

```text
C:\Users\rafae\Downloads\master-degree-project
```

Consequentemente:

```text
MODEL_PATH
```

representa:

```text
C:\Users\rafae\Downloads\master-degree-project\
model_int8_esp32.tflite
```

e:

```text
WAT_TEMPLATE_PATH
```

representa:

```text
C:\Users\rafae\Downloads\master-degree-project\
wat\
model_template.wat
```

A estrutura esperada é aproximadamente:

```text
master-degree-project/
│
├── model_int8_esp32.tflite
├── main.py
│
├── extractor/
│   ├── config.py
│   ├── ...
│   └── wat_generator.py
│
├── wat/
│   └── model_template.wat
│
├── generated/
│   └── model.wat
│
├── reports/
│   └── ...
│
└── docs/
    └── ...
```

---

# 5. `MODEL_PATH`

```python
MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)
```

## Função

Define o arquivo TFLite utilizado como entrada do pipeline.

Esse arquivo contém o modelo neural já convertido para TensorFlow Lite e quantizado.

O extrator utiliza esse artefato como sua representação canônica do modelo.

Fluxo:

```text
model_int8_esp32.tflite
        │
        ▼
   model_loader.py
        │
        ▼
   objeto Model
        │
        ▼
    SubGraph 0
        │
        ├── operadores
        ├── tensors
        ├── buffers
        ├── shapes
        ├── pesos
        ├── bias
        └── parâmetros de quantização
```

A partir desse arquivo são obtidas as informações necessárias para construir a representação executável usada posteriormente pelo WAT.

## Importante

`MODEL_PATH` identifica apenas o arquivo de entrada.

Ele não carrega o modelo.

O carregamento ocorre posteriormente, por exemplo:

```python
model = load_model(
    MODEL_PATH
)
```

Isso mantém `config.py` livre de efeitos colaterais.

---

# 6. `WAT_TEMPLATE_PATH`

```python
WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)
```

## Função

Indica onde está armazenado o template WebAssembly Text utilizado pela etapa final de geração.

Diferentemente da implementação antiga, o Python não constrói mais todo o código WAT linha por linha.

Agora existe uma separação entre:

```text
algoritmos WebAssembly
        +
dados extraídos do modelo
```

O arquivo:

```text
wat/model_template.wat
```

contém a implementação relativamente estática dos algoritmos, como:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

Além das funções auxiliares de requantização e execução.

Os valores dependentes do modelo aparecem no template através de placeholders.

Exemplo conceitual:

```wat
(memory (export "memory") @@MEM_PAGES@@)

(global $PARAMS_BASE
    i32
    (i32.const @@PARAMS_BASE@@)
)

(global $NUM_LAYERS
    i32
    (i32.const @@NUM_LAYERS@@)
)
```

Durante a geração:

```text
template WAT
      +
dados produzidos pelo extrator
      ↓
generated/model.wat
```

Essa separação evita misturar a lógica dos algoritmos com a lógica de extração do TFLite.

---

# 7. `OUT_WAT_PATH`

```python
OUT_WAT_PATH = Path(
    "generated/model.wat"
)
```

## Função

Define o destino do arquivo WAT final gerado pelo pipeline.

Depois que todos os valores foram extraídos e calculados, o gerador substitui os placeholders do template e insere os segmentos binários necessários.

O resultado é gravado em:

```text
generated/model.wat
```

Fluxo:

```text
wat/model_template.wat
          │
          │
          ├── MEM_PAGES
          ├── PARAMS_BASE
          ├── NUM_LAYERS
          ├── bases de memória
          └── data segments
          │
          ▼
    wat_generator.py
          │
          ▼
generated/model.wat
```

Posteriormente esse arquivo pode ser compilado com:

```text
wat2wasm
```

produzindo o módulo WebAssembly binário.

O fato de o arquivo gerado ficar em `generated/` também separa claramente:

```text
wat/model_template.wat
```

que é código-fonte mantido manualmente,

de:

```text
generated/model.wat
```

que é um artefato produzido automaticamente.

---

# 8. `REPORTS_DIR`

```python
REPORTS_DIR = Path(
    "reports"
)
```

## Função

Define o diretório no qual são gravados os relatórios das diferentes etapas da extração.

Durante a refatoração, informações que anteriormente eram inseridas como comentários dentro do WAT passaram a ser registradas nesses arquivos.

O princípio adotado é:

```text
WAT
    → somente o necessário para execução

reports/
    → explicação dos valores gerados
    → rastreabilidade
    → depuração
    → validação do processo
```

Exemplos:

```text
reports/
├── 02-grafo.txt
├── 03-alocacao-slots.txt
├── 04-mapeamento-tensor-slot.txt
├── 05-pesos-bias.txt
├── 06-quantizacao.txt
├── 07-slot-bytes.txt
├── 08-layout-parametros.txt
├── 09-layer-params.txt
├── 10-params-blob.txt
└── 11-layout-final-memoria.txt
```

Essa organização permite verificar passo a passo como o modelo TFLite foi transformado na estrutura consumida pelo runtime WebAssembly.

---

# 9. `NUM_SLOTS`

```python
NUM_SLOTS = 3
```

## Função

Define quantas regiões reutilizáveis de memória são disponibilizadas para armazenar tensors intermediários da rede.

Neste projeto:

```text
NUM_SLOTS = 3
```

significa:

```text
SLOT0
SLOT1
SLOT2
```

Esses slots não representam três tensors específicos.

Eles são regiões físicas reutilizadas por diferentes tensors ao longo da execução da rede.

A ideia é:

```text
tensor A → SLOT0

tensor A deixa de ser necessário

tensor D → SLOT0
```

Assim, não é necessário reservar uma região de memória independente para cada tensor intermediário.

---

# 10. Relação entre tensors e slots

Considere uma sequência simplificada:

```text
L1
 ↓
L2
 ↓
L3
 ↓
L4
```

Uma possível alocação seria:

```text
L1 → SLOT1
L2 → SLOT2
L3 → SLOT0
L4 → SLOT1
```

Representação:

```text
tempo ───────────────────────────────►

SLOT0                  [ L3 output ]

SLOT1     [ L1 output ]              [ L4 output ]

SLOT2           [ L2 output ]
```

O mesmo espaço físico pode ser reutilizado depois que seu conteúdo anterior deixa de ser necessário.

---

# 11. Por que três slots?

O valor atual:

```python
NUM_SLOTS = 3
```

faz parte da estratégia de alocação utilizada neste projeto.

O algoritmo de `slots.py` calcula quais outputs podem compartilhar as regiões sem sobrescrever tensors que ainda serão consumidos por camadas posteriores.

Além disso, o template WAT atual possui explicitamente:

```text
SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
```

Portanto, neste momento existe uma relação estrutural entre:

```python
NUM_SLOTS = 3
```

e o template WAT.

Alterar simplesmente para:

```python
NUM_SLOTS = 4
```

não é suficiente.

O gerador atual valida essa condição e o template precisaria ser adaptado para aceitar um quarto slot.

Assim, `NUM_SLOTS` atualmente deve ser considerado uma configuração estrutural do runtime, e não apenas um número arbitrário.

---

# 12. `BATCH`

```python
BATCH = 1
```

## Função

Define o tamanho de batch considerado pelo planejamento de memória.

No modelo atual, a inferência é realizada para uma imagem por vez:

```text
batch = 1
```

Conceitualmente, uma entrada poderia ter shape:

```text
[1, 128, 128, 3]
```

representando:

```text
1 imagem
128 pixels de altura
128 pixels de largura
3 canais
```

Número de elementos:

```text
1 × 128 × 128 × 3
= 49.152 elementos
```

No caso de um tensor `int8` ou `uint8`:

```text
49.152 × 1 byte
= 49.152 bytes
```

---

# 13. Relação de `BATCH` com shapes dinâmicos

A função atual utilizada para calcular o número de elementos de um tensor possui compatibilidade herdada com dimensões negativas.

Conceitualmente:

```python
if dimension < 0:
    dimension = batch
```

Assim, para:

```text
[-1, 128, 128, 3]
```

com:

```python
BATCH = 1
```

o cálculo torna-se:

```text
[1, 128, 128, 3]
```

Entretanto, essa regra deve ser interpretada com cuidado.

Uma dimensão `-1` em um modelo não significa necessariamente que aquela dimensão seja o batch.

Por exemplo:

```text
[1, -1, 128, 3]
```

poderia representar altura dinâmica.

Nesse caso, substituir automaticamente:

```text
-1 → BATCH
```

seria incorreto.

Para o modelo atualmente utilizado no projeto, espera-se que as dimensões relevantes estejam definidas estaticamente. A presença de dimensões negativas deve portanto ser tratada como um ponto de validação caso novos modelos sejam utilizados futuramente.

---

# 14. `ALIGN`

```python
ALIGN = 16
```

## Função

Define o alinhamento, em bytes, utilizado para organizar diferentes regiões da memória linear.

O valor atual é:

```text
16 bytes
```

Diversas regiões são posicionadas usando:

```python
align_up(
    address,
    ALIGN
)
```

Assim, cada nova região começa em um endereço múltiplo de 16.

Exemplo:

```text
endereço atual = 1001
ALIGN = 16
```

Os múltiplos próximos são:

```text
992
1008
1024
...
```

Portanto:

```text
align_up(1001, 16)
= 1008
```

---

# 15. Por que existe alinhamento?

Considere duas regiões:

```text
WEIGHTS
BIAS
```

Se os pesos terminarem no endereço:

```text
386651
```

a próxima região não precisa necessariamente começar imediatamente em:

```text
386651
```

Com alinhamento de 16 bytes:

```text
align_up(386651, 16)
= 386656
```

Assim:

```text
WEIGHTS
│
├── dados
│
└── fim = 386651
        │
        ├── 5 bytes de padding
        │
        ▼
BIAS começa em 386656
```

Esses espaços entre regiões são chamados de padding de alinhamento.

---

# 16. Fórmula utilizada

O projeto utiliza conceitualmente:

```python
(value + alignment - 1) & ~(alignment - 1)
```

Para:

```text
alignment = 16
```

o cálculo é apropriado porque 16 é uma potência de dois:

```text
16 = 2⁴
```

Essa implementação por operações bit a bit pressupõe um alinhamento que seja potência de dois.

Portanto, valores naturais para essa implementação seriam:

```text
1
2
4
8
16
32
64
...
```

e não valores arbitrários como:

```text
10
12
20
```

No projeto atual:

```python
ALIGN = 16
```

satisfaz essa condição.

---

# 17. Onde `ALIGN` é utilizado

O alinhamento participa de várias decisões de memória.

Exemplo simplificado:

```text
KERNEL_BASE_HINT
      │
      ▼
align_up()
      │
      ▼
KERNEL_BASE
      │
      │ + kernel_bytes
      ▼
align_up()
      │
      ▼
BIAS_BASE
      │
      │ + bias_bytes
      ▼
align_up()
      │
      ▼
MUL_BASE
      │
      ▼
SHIFT_BASE
      │
      ▼
Q6_BASE
      │
      ▼
PARAMS_BASE
      │
      ▼
SLOT0_BASE
```

Portanto, `ALIGN` não é apenas uma propriedade dos pesos. Ele influencia o layout global da memória.

---

# 18. `KERNEL_BASE_HINT`

```python
KERNEL_BASE_HINT = 2048
```

## Função

Define o endereço inicial de referência a partir do qual o bloco de pesos poderá ser colocado na memória linear.

O valor ainda passa pela função de alinhamento:

```python
kernel_base = align_up(
    KERNEL_BASE_HINT,
    ALIGN
)
```

No caso atual:

```text
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

Como:

```text
2048 / 16 = 128
```

o endereço já está alinhado.

Portanto:

```text
kernel_base = 2048
```

---

# 19. Por que o nome contém `HINT`?

O valor não é utilizado diretamente como uma verdade absoluta.

Ele funciona como ponto inicial solicitado para a região dos pesos:

```text
KERNEL_BASE_HINT
        │
        ▼
    align_up()
        │
        ▼
   KERNEL_BASE real
```

Exemplo hipotético:

```python
KERNEL_BASE_HINT = 2050
ALIGN = 16
```

produziria:

```text
KERNEL_BASE = 2064
```

Portanto:

```text
hint ≠ necessariamente base efetiva
```

No valor atual, ambos coincidem porque `2048` já está alinhado.

---

# 20. Região anterior aos pesos

Como:

```text
KERNEL_BASE = 2048
```

os endereços anteriores:

```text
0 ... 2047
```

não são utilizados pelo bloco de pesos.

Isso permite que essa região permaneça disponível para estruturas ou comunicação do runtime.

Por exemplo, o template WAT atualmente utiliza uma pequena região inicial para flags de comunicação com o host.

O ponto importante para o extrator é que os pesos **não começam no endereço zero**.

Representação simplificada:

```text
memória linear WASM

0
│
│ região inicial/reservada
│
│
2048  ← KERNEL_BASE
│
├── WEIGHTS
│
├── BIAS
│
├── MUL
│
├── SHIFT
│
├── Q6
│
├── LayerParams
│
├── SLOT0
│
├── SLOT1
│
└── SLOT2
```

O motivo histórico exato da escolha do valor `2048` deve ser documentado separadamente caso seja necessário demonstrar por que especificamente 2 KiB foram reservados, em vez de outro valor.

Para o pipeline atual, o fato objetivo é:

```text
2048 é o ponto inicial configurado para o layout dos parâmetros.
```

---

# 21. Relação entre `KERNEL_BASE_HINT` e o layout

O planejamento posterior pode ser visualizado assim:

```text
KERNEL_BASE_HINT = 2048
           │
           ▼
    align_up(2048, 16)
           │
           ▼
    KERNEL_BASE = 2048
           │
           │ + tamanho dos pesos
           ▼
     fim dos pesos
           │
           ▼
       align_up
           │
           ▼
       BIAS_BASE
           │
           │ + tamanho dos bias
           ▼
       align_up
           │
           ▼
        MUL_BASE
           │
           ▼
       SHIFT_BASE
           │
           ▼
         Q6_BASE
           │
           ▼
       PARAMS_BASE
           │
           ▼
       SLOT0_BASE
           │
           ▼
       SLOT1_BASE
           │
           ▼
       SLOT2_BASE
```

Assim, somente a primeira região possui uma base configurada inicialmente.

As seguintes são derivadas matematicamente dos tamanhos das regiões anteriores.

---

# 22. Separação entre configuração e valores extraídos

É importante distinguir duas categorias de informação no projeto.

## Valores configurados manualmente

São definidos em `config.py`:

```text
MODEL_PATH
WAT_TEMPLATE_PATH
OUT_WAT_PATH
REPORTS_DIR

NUM_SLOTS
BATCH
ALIGN
KERNEL_BASE_HINT
```

## Valores descobertos ou calculados automaticamente

São produzidos durante a extração:

```text
kernel_bytes
bias_bytes
mul_bytes
shift_bytes
q6_bytes

SLOT_BYTES

kernel_base
bias_base
mul_base
shift_base
q6_base
params_base

slot_bases

NUM_LAYERS
MEM_END
MEM_PAGES
RESULT_BASE
RESULT_COUNT
```

Essa divisão é fundamental.

Por exemplo, não devemos colocar no `config.py`:

```python
PARAMS_BASE = 499360
```

porque `PARAMS_BASE` depende do conteúdo real do modelo.

Da mesma maneira, não devemos colocar:

```python
MEM_PAGES = 17
```

porque a quantidade de páginas depende do layout final calculado.

Esses valores são resultados da extração, não configurações.

---

# 23. Configuração versus resultado

Podemos resumir a relação como:

```text
config.py
   │
   │ parâmetros de entrada
   ▼
extrator
   │
   │ cálculos
   ▼
resultados
```

Por exemplo:

```text
ALIGN = 16
KERNEL_BASE_HINT = 2048
        │
        ▼
calculate_parameter_layout()
        │
        ▼
kernel_base
bias_base
mul_base
shift_base
q6_base
params_base
```

E:

```text
NUM_SLOTS = 3
        │
        ▼
allocate_slots()
calculate_slot_bytes()
        │
        ▼
slot allocation
SLOT_BYTES
slot_bases
```

---

# 24. Dependências principais

Uma visão simplificada das dependências atuais é:

```text
MODEL_PATH
    ↓
model_loader.py


NUM_SLOTS
    ↓
slots.py
    ↓
layer_params.py
    ↓
wat_generator.py


BATCH
    ↓
memory.py


ALIGN
    ↓
memory.py
    ↓
parameter layout
    ↓
layer memory layout


KERNEL_BASE_HINT
    ↓
memory.py
    ↓
kernel_base


REPORTS_DIR
    ↓
reporting.py / main.py


WAT_TEMPLATE_PATH
    ↓
wat_generator.py


OUT_WAT_PATH
    ↓
wat_generator.py
```

---

# 25. Por que centralizar essas informações?

Sem `config.py`, seria possível encontrar valores como:

```python
3
1
16
2048
```

espalhados por diversos módulos.

Por exemplo:

```python
allocate_slots(
    layers,
    num_slots=3
)
```

e depois:

```python
align_up(
    value,
    16
)
```

e ainda:

```python
kernel_base = 2048
```

Isso introduziria números mágicos.

Centralizando:

```python
NUM_SLOTS = 3
BATCH = 1
ALIGN = 16
KERNEL_BASE_HINT = 2048
```

o significado desses números passa a ser explícito.

---

# 26. O que acontece se cada configuração for alterada?

### `MODEL_PATH`

Trocar:

```python
MODEL_PATH = Path(
    "outro_modelo.tflite"
)
```

faz com que o pipeline tente extrair outro modelo.

Entretanto, isso não garante automaticamente que o novo modelo seja compatível com todos os operadores implementados no template WAT.

---

### `WAT_TEMPLATE_PATH`

Trocar esse valor faz o gerador utilizar outro template WAT.

Isso permitiria futuramente possuir, por exemplo:

```text
wat/
├── model_template.wat
├── model_template_debug.wat
└── model_template_simd.wat
```

sem alterar a lógica do extrator.

---

### `OUT_WAT_PATH`

Altera apenas o destino do WAT gerado.

Por exemplo:

```python
OUT_WAT_PATH = Path(
    "generated/model_debug.wat"
)
```

---

### `REPORTS_DIR`

Altera o local onde os relatórios são gravados.

Não deve alterar os cálculos da inferência.

---

### `NUM_SLOTS`

Tem impacto estrutural no planejamento das ativações e também no template WAT.

No estado atual:

```text
NUM_SLOTS = 3
```

deve permanecer sincronizado com o template que possui três bases de slot.

---

### `BATCH`

Afeta cálculos de tamanho quando uma dimensão dinâmica precisa ser resolvida pela regra atualmente utilizada pelo extrator.

Para o modelo atual:

```text
BATCH = 1
```

é coerente com inferência individual.

---

### `ALIGN`

Afeta praticamente todo o layout de memória.

Alterá-lo pode modificar:

```text
kernel_base
bias_base
mul_base
shift_base
q6_base
params_base
slot_bases
MEM_END
MEM_PAGES
```

---

### `KERNEL_BASE_HINT`

Move o ponto inicial da região dos parâmetros.

Por consequência, todas as regiões posteriores também podem ser deslocadas.

---

# 27. Exemplo de propagação de uma configuração

Considere:

```python
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

A primeira operação é:

```text
kernel_base =
align_up(2048, 16)

kernel_base = 2048
```

Suponha, apenas como exemplo:

```text
kernel_bytes = 384608
```

então:

```text
fim dos pesos =
2048 + 384608

= 386656
```

A próxima região:

```text
bias_base =
align_up(386656, 16)

= 386656
```

Depois o mesmo processo é aplicado às demais regiões.

Portanto, uma única configuração inicial participa da formação de toda a cadeia de endereços.

---

# 28. O que não deve ficar em `config.py`

Este módulo não deve receber valores que pertencem ao modelo específico após a extração.

Por exemplo, não é adequado colocar:

```python
NUM_LAYERS = 68

SLOT_BYTES = 196608

WEIGHTS_BASE = 2048

BIAS_BASE = 386656

PARAMS_BASE = 499360

MEM_PAGES = 17
```

Mesmo que esses valores sejam verdadeiros para uma execução específica.

Eles devem ser calculados.

Caso contrário, trocar o arquivo TFLite poderia produzir um WAT estruturalmente incorreto.

A regra adotada é:

```text
config.py
    ↓
define políticas e entradas

extrator
    ↓
descobre propriedades do modelo

relatórios
    ↓
registram os resultados

wat_generator
    ↓
consome os resultados
```

---

# 29. Estado atual do módulo

O módulo é pequeno propositalmente.

```python
from pathlib import Path


MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)

WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)

OUT_WAT_PATH = Path(
    "generated/model.wat"
)

REPORTS_DIR = Path(
    "reports"
)

NUM_SLOTS = 3

BATCH = 1

ALIGN = 16

KERNEL_BASE_HINT = 2048
```

Não há necessidade de classes, funções ou estruturas mais complexas neste momento.

O módulo funciona como uma fonte centralizada de configuração para um pipeline executado localmente.

---

# 30. Resumo

O papel de cada variável pode ser resumido da seguinte forma:

| Configuração        | Função                                                          |
| ------------------- | --------------------------------------------------------------- |
| `MODEL_PATH`        | Caminho do modelo TFLite utilizado como entrada                 |
| `WAT_TEMPLATE_PATH` | Caminho do código WAT estático usado como template              |
| `OUT_WAT_PATH`      | Caminho do WAT gerado automaticamente                           |
| `REPORTS_DIR`       | Diretório dos relatórios de extração                            |
| `NUM_SLOTS`         | Quantidade de regiões reutilizáveis para tensors intermediários |
| `BATCH`             | Batch utilizado no planejamento de shapes/tamanhos              |
| `ALIGN`             | Alinhamento em bytes das regiões da memória                     |
| `KERNEL_BASE_HINT`  | Endereço inicial de referência para o bloco de pesos            |

A principal ideia arquitetural é que `config.py` contém apenas **entradas e políticas de configuração**.

Informações dependentes do modelo devem ser obtidas pelo próprio extrator.

Em outras palavras:

```text
CONFIGURAÇÃO
     │
     ▼
   EXTRAÇÃO
     │
     ▼
   CÁLCULO
     │
     ▼
  VALIDAÇÃO
     │
     ▼
 SERIALIZAÇÃO
     │
     ▼
 GERAÇÃO DO WAT
```

Essa separação torna o pipeline mais reproduzível, rastreável e adequado para receber outros modelos no futuro sem exigir a alteração manual de endereços e parâmetros internos.
