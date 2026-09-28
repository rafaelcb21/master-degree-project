# 05 — Alocação de slots lógicos (`slots.py`)

## 1. Objetivo do módulo

O arquivo `extractor/slots.py` é responsável por decidir em qual slot lógico cada saída intermediária da rede será armazenada.

O código atual é:

```python
# extractor/slots.py


def allocate_slots(layers, num_slots):
    """
    Aloca slots lógicos para as saídas das camadas.

    Parâmetros
    ----------
    layers:
        Lista de camadas produzida por graph.py.

    num_slots:
        Quantidade de slots lógicos disponíveis.

    Retorna
    -------
    allocation:
        Lista contendo os slots de entrada e saída de cada camada.

    layer_output_slot:
        Mapeamento:
            nome_da_camada -> slot_de_saida
    """

    layer_output_slot = {}
    slot_readers_count = {}
    allocation = []

    next_slot = 1

    for layer in layers:
        layer_name = layer["name"]
        layer_type = layer["type"]
        layers_above = layer["above"]
        layers_below = layer["below"]

        # ====================================================
        # QUANTIZE
        # ====================================================
        #
        # No comportamento atual, QUANTIZE é executado
        # in-place: entrada e saída utilizam o mesmo slot.
        #
        if layer_type == "QUANTIZE":
            if not layers_above:
                input_slot = 0
            else:
                input_slot = (
                    layer_output_slot[
                        layers_above[0]
                    ]
                )

            layer_output_slot[layer_name] = input_slot

            allocation.append(
                {
                    "layer": layer_name,
                    "type": layer_type,
                    "input_slots": [input_slot],
                    "output_slot": input_slot,
                    "in_place": True,
                }
            )

            continue

        # ====================================================
        # SLOTS DE ENTRADA
        # ====================================================

        if not layers_above:
            input_slots = [0]
            next_slot = 1

        else:
            input_slots = [
                layer_output_slot[above]
                for above in layers_above
            ]

        # ====================================================
        # DESCOBRIR SLOTS DISPONÍVEIS
        # ====================================================

        available_slots = list(
            range(num_slots)
        )

        for slot in list(available_slots):
            if (
                slot in slot_readers_count
                and slot_readers_count[slot] > 0
            ):
                available_slots.remove(slot)

        if not available_slots:
            raise RuntimeError(
                f"Sem slots livres em {layer_name}"
            )

        # ====================================================
        # ESCOLHER SLOT DE SAÍDA
        # ====================================================

        if next_slot in available_slots:
            output_slot = next_slot

        else:
            output_slot = available_slots[0]

        # ====================================================
        # REGISTRAR CONSUMO DAS ENTRADAS
        # ====================================================

        for input_slot in input_slots:
            if input_slot in slot_readers_count:
                slot_readers_count[input_slot] -= 1

                if (
                    slot_readers_count[input_slot]
                    == 0
                ):
                    del slot_readers_count[
                        input_slot
                    ]

        # ====================================================
        # REGISTRAR CONSUMIDORES DA NOVA SAÍDA
        # ====================================================

        if layers_below:
            slot_readers_count[output_slot] = (
                len(layers_below)
            )

        # ====================================================
        # CAMADA -> SLOT DE SAÍDA
        # ====================================================

        layer_output_slot[layer_name] = (
            output_slot
        )

        # ====================================================
        # REGISTRO DA ALOCAÇÃO
        # ====================================================

        allocation.append(
            {
                "layer": layer_name,
                "type": layer_type,
                "input_slots": input_slots,
                "output_slot": output_slot,
                "in_place": False,
            }
        )

        # ====================================================
        # PRÓXIMO SLOT PREFERENCIAL
        # ====================================================

        next_slot = (
            output_slot + 1
        ) % num_slots

    return allocation, layer_output_slot


def slot_allocation_to_text(allocation):
    """
    Gera uma representação textual da alocação de slots.

    Essa função é apenas para relatório/debug.
    A lógica de alocação não depende desse texto.
    """

    lines = []

    for alloc in allocation:
        input_slots = alloc["input_slots"]
        output_slot = alloc["output_slot"]

        if len(input_slots) == 1:
            inputs = str(input_slots[0])

        else:
            inputs = " e ".join(
                map(str, input_slots)
            )

        line = (
            f"{alloc['type']:25} "
            f"{alloc['layer']:5} "
            f"[{inputs} -> {output_slot}]"
        )

        if alloc["in_place"]:
            line += " (in-place)"

        lines.append(line)

    return "\n".join(lines)
```

---

# 2. Papel arquitetural

Até `graph.py`, o projeto conhece apenas dependências lógicas:

```text
L0 → L1 → L2
```

ou:

```text
L1 ─────────────┐
 ↓              │
L2              │
 ↓              │
L3              │
 └──────────────┤
                ↓
               L4 ADD
```

Mas o runtime precisa armazenar fisicamente as saídas de cada camada.

Como o ESP32 possui memória restrita, não é desejável reservar uma área exclusiva para cada tensor intermediário.

A estratégia adotada é reutilizar algumas regiões de memória.

Essas regiões são chamadas de:

```text
slots
```

No projeto atual:

```python
NUM_SLOTS = 3
```

Logo existem inicialmente:

```text
slot 0
slot 1
slot 2
```

---

# 3. Slot lógico versus endereço físico

Neste módulo, um slot é apenas um número.

Por exemplo:

```text
slot 0
slot 1
slot 2
```

Ainda não significa:

```text
507248
703856
900464
```

Esses endereços serão calculados posteriormente.

Portanto existem dois níveis:

```text
slots.py
    ↓
slot lógico

memory.py / layer_params.py
    ↓
endereço físico do slot
```

Exemplo:

```text
slot lógico 1
      ↓
SLOT1_BASE
      ↓
703856
```

O objetivo de `slots.py` é decidir **quem usa qual slot**, não onde esse slot começa na memória linear.

---

# 4. Por que reutilizar memória?

Considere uma rede linear:

```text
L0 → L1 → L2 → L3
```

Se cada camada tivesse uma região exclusiva:

```text
L0 output → buffer 0
L1 output → buffer 1
L2 output → buffer 2
L3 output → buffer 3
```

seriam necessárias quatro áreas de ativação.

Mas depois que L1 consumiu completamente o resultado de L0, aquela memória pode eventualmente ser reutilizada.

Então podemos ter algo como:

```text
L0 output → SLOT1
L1 output → SLOT2
L2 output → SLOT1
L3 output → SLOT2
```

Representação temporal:

```text
tempo ───────────────────────────────────►

SLOT1   [L0 output]          [L2 output]

SLOT2          [L1 output]          [L3 output]
```

Assim a memória é reutilizada.

---

# 5. Por que não basta alternar slots?

Uma rede neural não é necessariamente uma cadeia linear.

Em MobileNetV2 existem conexões residuais.

Por exemplo:

```text
        ┌────────────────────────┐
        │                        │
        │                        ▼
L5 → L6 → L7 → L8 ───────────── ADD
```

A saída de L5 precisa continuar existindo enquanto L6, L7 e L8 são executadas.

Se reutilizarmos imediatamente o slot de L5:

```text
L5 output → SLOT1
L6 output → SLOT2
L7 output → SLOT1
```

o conteúdo de L5 seria destruído antes de chegar ao `ADD`.

Por isso a alocação depende do grafo.

---

# 6. Relação com `graph.py`

O módulo recebe:

```python
layers
```

produzido por:

```text
graph.py
```

Cada camada possui:

```python
{
    "type": ...,
    "name": ...,
    "above": ...,
    "below": ...,
    "op_index": ...,
}
```

Os campos mais importantes aqui são:

```text
above
below
```

`above` informa quem produz as entradas.

`below` informa quantas operações ainda usarão a saída atual.

---

# 7. Entrada principal

A função é:

```python
def allocate_slots(
    layers,
    num_slots,
):
```

Recebe:

### `layers`

A representação estruturada do grafo.

### `num_slots`

Quantidade máxima de slots lógicos disponíveis.

No uso atual:

```python
num_slots = 3
```

---

# 8. Saídas da função

A função retorna:

```python
return (
    allocation,
    layer_output_slot,
)
```

São duas representações complementares.

---

# 9. `allocation`

A lista:

```python
allocation
```

guarda a alocação completa de cada camada.

Exemplo:

```python
[
    {
        "layer": "L0",
        "type": "QUANTIZE",
        "input_slots": [0],
        "output_slot": 0,
        "in_place": True,
    },

    {
        "layer": "L1",
        "type": "CONV_2D",
        "input_slots": [0],
        "output_slot": 1,
        "in_place": False,
    },
]
```

Ela registra tanto:

```text
de onde a camada lê
```

quanto:

```text
onde a camada escreve
```

---

# 10. `layer_output_slot`

O segundo resultado é um mapa mais simples:

```python
layer_output_slot
```

Exemplo:

```python
{
    "L0": 0,
    "L1": 1,
    "L2": 2,
}
```

Ele responde diretamente:

```text
em qual slot está a saída de Lx?
```

Isso é útil quando uma camada posterior possui:

```python
"above": ["L1"]
```

Nesse caso:

```python
layer_output_slot["L1"]
```

fornece o slot de entrada.

---

# 11. Estado interno inicial

No início:

```python
layer_output_slot = {}
```

```python
slot_readers_count = {}
```

```python
allocation = []
```

```python
next_slot = 1
```

Cada estrutura possui uma finalidade diferente.

---

# 12. `layer_output_slot`

Começa vazio porque nenhuma camada foi processada.

À medida que a rede é percorrida:

```python
layer_output_slot[layer_name] = output_slot
```

vai preenchendo o estado.

Exemplo:

```text
depois de L0:
L0 → 0

depois de L1:
L0 → 0
L1 → 1

depois de L2:
L0 → 0
L1 → 1
L2 → 2
```

---

# 13. `slot_readers_count`

Essa é a estrutura central do algoritmo.

Ela representa:

```text
slot
 ↓
quantos consumidores ainda precisam ler seu conteúdo
```

Exemplo:

```python
slot_readers_count = {
    1: 2
}
```

significa:

```text
o conteúdo armazenado no SLOT1
ainda será utilizado por duas operações
```

Enquanto:

```text
count > 0
```

o slot não deve ser sobrescrito.

---

# 14. Conceito de leitor

Suponha:

```text
L1
 ├──→ L2
 └──→ L4
```

A saída de L1 possui:

```text
2 consumidores
```

Então:

```python
slot_readers_count[
    slot_de_L1
] = 2
```

Quando L2 usar esse dado:

```text
2 → 1
```

Quando L4 usar:

```text
1 → 0
```

A partir desse momento, o slot pode ser reutilizado.

---

# 15. `allocation`

A lista:

```python
allocation = []
```

registra cada decisão tomada pelo algoritmo.

É diferente de `slot_readers_count`.

`slot_readers_count` é estado temporário utilizado durante o cálculo.

`allocation` é o resultado permanente.

---

# 16. `next_slot`

Inicialmente:

```python
next_slot = 1
```

Isso indica a preferência inicial de escrita.

O slot 0 recebe um tratamento especial porque normalmente contém a entrada inicial do grafo.

Assim, para uma primeira camada não in-place:

```text
entrada → slot 0
saída   → preferencialmente slot 1
```

---

# 17. Iteração sobre as camadas

A função percorre:

```python
for layer in layers:
```

A ordem de `layers` vem de `graph.py`, que constrói a lista em ordem topológica.

Portanto, quando uma camada é analisada, espera-se que seus produtores já tenham sido processados.

Essa propriedade é essencial para:

```python
layer_output_slot[
    layers_above[0]
]
```

funcionar.

---

# 18. Informações extraídas de cada camada

Para cada camada:

```python
layer_name = layer["name"]
```

```python
layer_type = layer["type"]
```

```python
layers_above = layer["above"]
```

```python
layers_below = layer["below"]
```

Exemplo:

```python
{
    "type": "ADD",
    "name": "L10",
    "above": [
        "L6",
        "L9",
    ],
    "below": [
        "L11",
    ],
}
```

resulta em:

```text
layer_name = L10
layer_type = ADD
layers_above = [L6, L9]
layers_below = [L11]
```

---

# 19. Caso especial: `QUANTIZE`

O primeiro tratamento especial é:

```python
if layer_type == "QUANTIZE":
```

No runtime atual, essa operação é tratada como:

```text
in-place
```

ou seja:

```text
slot de entrada = slot de saída
```

---

# 20. O que significa execução in-place?

Normalmente temos:

```text
input buffer
    ↓
operação
    ↓
output buffer diferente
```

Por exemplo:

```text
SLOT0 → CONV → SLOT1
```

Em uma operação in-place:

```text
SLOT0 → QUANTIZE → SLOT0
```

A operação lê e escreve na mesma região lógica.

---

# 21. Primeiro `QUANTIZE` da rede

Se:

```python
not layers_above
```

é verdadeiro, significa que a camada não possui uma operação útil anterior.

Nesse caso:

```python
input_slot = 0
```

Isso representa a entrada externa do modelo.

Fluxo:

```text
entrada externa
     ↓
   SLOT0
     ↓
 QUANTIZE
     ↓
   SLOT0
```

---

# 22. `QUANTIZE` depois de outra camada

Se existe uma camada anterior:

```python
input_slot = (
    layer_output_slot[
        layers_above[0]
    ]
)
```

Exemplo:

```text
L5 output → SLOT2
```

Então:

```text
L5 → QUANTIZE
```

faz:

```text
input_slot = 2
output_slot = 2
```

---

# 23. Registro da saída do `QUANTIZE`

Depois:

```python
layer_output_slot[
    layer_name
] = input_slot
```

Se:

```text
L4 lê SLOT1
```

então:

```text
L4 também passa a ter output em SLOT1
```

---

# 24. Registro completo do `QUANTIZE`

É inserido:

```python
{
    "layer": layer_name,
    "type": layer_type,
    "input_slots": [
        input_slot
    ],
    "output_slot": input_slot,
    "in_place": True,
}
```

Exemplo:

```python
{
    "layer": "L0",
    "type": "QUANTIZE",
    "input_slots": [0],
    "output_slot": 0,
    "in_place": True,
}
```

---

# 25. `continue`

Depois:

```python
continue
```

Isso significa que `QUANTIZE` não percorre o restante da lógica normal de alocação.

Ou seja, não:

```text
procura slot livre
escolhe next_slot
registra novo output_slot
```

porque sua saída obrigatoriamente reutiliza a entrada.

---

# 26. Observação importante sobre `QUANTIZE`

O comportamento in-place não é uma propriedade universal de qualquer `QUANTIZE` TFLite.

É uma decisão da implementação atual deste runtime.

Portanto a regra correta é:

```text
neste projeto:
QUANTIZE é executado in-place
```

e não:

```text
QUANTIZE sempre deve ser in-place
```

---

# 27. Camada normal: determinação das entradas

Se a operação não é `QUANTIZE`, começa a lógica geral.

O primeiro passo é determinar os slots de entrada.

---

# 28. Camada sem predecessora

Se:

```python
if not layers_above:
```

então:

```python
input_slots = [0]
```

e:

```python
next_slot = 1
```

Isso representa uma operação cuja entrada vem diretamente do input externo.

---

# 29. Exemplo da primeira convolução

```text
imagem
  ↓
SLOT0
  ↓
CONV_2D
  ↓
SLOT1
```

Para essa operação:

```python
input_slots = [0]
```

e a preferência é escrever em:

```python
next_slot = 1
```

---

# 30. Camada com predecessores

Se:

```python
layers_above
```

não está vazio:

```python
input_slots = [
    layer_output_slot[above]
    for above in layers_above
]
```

---

# 31. Exemplo com uma entrada

Se:

```python
layers_above = [
    "L4"
]
```

e:

```python
layer_output_slot[
    "L4"
] = 2
```

então:

```python
input_slots = [
    2
]
```

---

# 32. Exemplo com duas entradas

Para um `ADD`:

```python
layers_above = [
    "L6",
    "L9",
]
```

e:

```python
layer_output_slot = {
    "L6": 1,
    "L9": 2,
}
```

o resultado será:

```python
input_slots = [
    1,
    2,
]
```

Representação:

```text
SLOT1 ─┐
       ├→ ADD
SLOT2 ─┘
```

---

# 33. Descoberta dos slots disponíveis

A função começa assumindo:

```python
available_slots = list(
    range(num_slots)
)
```

Para:

```python
num_slots = 3
```

isso resulta em:

```python
[
    0,
    1,
    2,
]
```

---

# 34. Filtragem dos slots ocupados

Depois:

```python
for slot in list(
    available_slots
):
```

é verificado:

```python
if (
    slot in slot_readers_count
    and slot_readers_count[
        slot
    ] > 0
):
```

Se ainda existem consumidores pendentes:

```python
available_slots.remove(
    slot
)
```

---

# 35. Exemplo

Suponha:

```python
slot_readers_count = {
    1: 2,
    2: 1,
}
```

Começamos com:

```python
available_slots = [
    0,
    1,
    2,
]
```

Após a filtragem:

```python
available_slots = [
    0
]
```

Porque:

```text
SLOT1 ainda tem 2 leitores
SLOT2 ainda tem 1 leitor
SLOT0 não possui leitores pendentes
```

---

# 36. Significado de slot livre

Neste algoritmo, um slot é considerado disponível quando:

```text
não existe em slot_readers_count
```

ou quando não possui leitores pendentes.

Como entradas com contagem zero são removidas do dicionário, normalmente:

```text
slot livre
    ↓
slot não está em slot_readers_count
```

---

# 37. Nenhum slot disponível

Se:

```python
not available_slots
```

a função lança:

```python
raise RuntimeError(
    f"Sem slots livres em {layer_name}"
)
```

Esse erro significa que, para o estado atual do grafo e quantidade configurada de slots, todas as regiões ainda contêm valores que o algoritmo considera vivos.

---

# 38. Exemplo

Com três slots:

```text
SLOT0 → ainda necessário
SLOT1 → ainda necessário
SLOT2 → ainda necessário
```

e uma nova camada precisa produzir outra saída:

```text
não há espaço lógico disponível
```

Nesse caso, a execução do extrator é interrompida.

---

# 39. Escolha do slot de saída

Se existem slots livres:

```python
if next_slot in available_slots:
    output_slot = next_slot
```

Caso contrário:

```python
output_slot = (
    available_slots[0]
)
```

---

# 40. Papel de `next_slot`

`next_slot` não é obrigatório.

Ele funciona como:

```text
slot preferencial
```

O algoritmo tenta manter uma rotação simples.

Para três slots:

```text
0 → 1 → 2 → 0 → 1 → ...
```

Mas apenas se o próximo slot estiver realmente livre.

---

# 41. Exemplo

Suponha:

```text
next_slot = 2
available_slots = [0, 2]
```

Então:

```text
output_slot = 2
```

---

# 42. Exemplo com slot preferencial ocupado

Se:

```text
next_slot = 2
available_slots = [0, 1]
```

então:

```text
2 não está disponível
```

Logo:

```python
output_slot = (
    available_slots[0]
)
```

resultado:

```text
output_slot = 0
```

---

# 43. Por que existe uma preferência?

Sem isso, o algoritmo poderia sempre escolher:

```python
available_slots[0]
```

A preferência circular ajuda a distribuir naturalmente as ativações entre os slots.

Mas a correção depende primeiro da disponibilidade.

A prioridade é:

```text
1. slot precisa estar livre
2. se next_slot estiver livre, prefira-o
3. senão use o primeiro livre
```

---

# 44. Consumo das entradas

Depois que o slot de saída foi escolhido, a função registra que a operação atual consumiu suas entradas.

O código é:

```python
for input_slot in input_slots:
```

Para cada uma:

```python
if input_slot in slot_readers_count:
```

a contagem é decrementada:

```python
slot_readers_count[
    input_slot
] -= 1
```

---

# 45. Significado do decremento

Considere:

```text
L2 output está em SLOT1
```

e:

```text
ainda existem 2 consumidores
```

Estado:

```python
slot_readers_count = {
    1: 2
}
```

Ao processar um deles:

```text
2 → 1
```

A saída ainda precisa ser preservada.

---

# 46. Último consumidor

Quando:

```python
slot_readers_count[
    input_slot
] == 0
```

é executado:

```python
del slot_readers_count[
    input_slot
]
```

Isso significa:

```text
não existe mais nenhum consumidor conhecido
para o valor armazenado nesse slot
```

Logo ele poderá ser reutilizado posteriormente.

---

# 47. Exemplo de vida útil

Considere:

```text
L1 output → SLOT1

L2 usa L1
L5 usa L1
```

Ao produzir L1:

```python
slot_readers_count = {
    1: 2
}
```

Depois de L2:

```python
slot_readers_count = {
    1: 1
}
```

Depois de L5:

```python
slot_readers_count = {}
```

Agora SLOT1 está liberado.

---

# 48. Registro dos leitores da nova saída

Depois de consumir as entradas, a função registra quantas operações futuras consumirão a nova saída:

```python
if layers_below:
```

Então:

```python
slot_readers_count[
    output_slot
] = len(
    layers_below
)
```

---

# 49. Exemplo simples

Se:

```python
layers_below = [
    "L4"
]
```

então:

```python
slot_readers_count[
    output_slot
] = 1
```

---

# 50. Exemplo de ramificação

Se:

```python
layers_below = [
    "L4",
    "L7",
]
```

então:

```python
slot_readers_count[
    output_slot
] = 2
```

O valor não poderá ser sobrescrito até ambas as operações terem sido processadas.

---

# 51. Camada sem consumidores

Se:

```python
layers_below == []
```

nenhuma entrada é criada em:

```python
slot_readers_count
```

Isso normalmente ocorre na saída final.

A saída continua existindo fisicamente no slot, mas o algoritmo não precisa protegê-la para outra camada da rede.

---

# 52. Registro camada → slot

Depois:

```python
layer_output_slot[
    layer_name
] = output_slot
```

Essa informação será usada por camadas futuras.

Exemplo:

```python
layer_output_slot[
    "L8"
] = 2
```

Quando L9 possuir:

```python
"above": ["L8"]
```

ela descobrirá que sua entrada está em:

```text
SLOT2
```

---

# 53. Registro detalhado em `allocation`

A função adiciona:

```python
{
    "layer": layer_name,
    "type": layer_type,
    "input_slots": input_slots,
    "output_slot": output_slot,
    "in_place": False,
}
```

Esse registro contém tudo que as etapas seguintes precisam saber sobre a movimentação lógica das ativações.

---

# 54. Exemplo

Uma convolução poderia gerar:

```python
{
    "layer": "L12",
    "type": "CONV_2D",
    "input_slots": [1],
    "output_slot": 2,
    "in_place": False,
}
```

Representando:

```text
SLOT1
  ↓
CONV_2D L12
  ↓
SLOT2
```

---

# 55. Exemplo de `ADD`

Um `ADD` poderia gerar:

```python
{
    "layer": "L18",
    "type": "ADD",
    "input_slots": [
        1,
        2,
    ],
    "output_slot": 0,
    "in_place": False,
}
```

Representando:

```text
SLOT1 ──┐
        ├── ADD L18 ──→ SLOT0
SLOT2 ──┘
```

---

# 56. Atualização do slot preferencial

No fim da iteração:

```python
next_slot = (
    output_slot + 1
) % num_slots
```

---

# 57. Operador `%`

Com:

```python
num_slots = 3
```

temos:

```text
output_slot 0
    ↓
(0 + 1) % 3
    ↓
1
```

```text
output_slot 1
    ↓
(1 + 1) % 3
    ↓
2
```

```text
output_slot 2
    ↓
(2 + 1) % 3
    ↓
0
```

Portanto existe uma rotação:

```text
0 → 1 → 2 → 0 → 1 → 2 ...
```

---

# 58. Retorno final

Ao final:

```python
return (
    allocation,
    layer_output_slot,
)
```

Exemplo:

```python
allocation = [
    ...,
]
```

e:

```python
layer_output_slot = {
    "L0": 0,
    "L1": 1,
    "L2": 2,
    ...
}
```

---

# 59. Exemplo completo de uma cadeia linear

Considere:

```text
L0 QUANTIZE
 ↓
L1 CONV
 ↓
L2 DW
 ↓
L3 CONV
```

Com três slots.

---

# 60. L0 — QUANTIZE

Não possui camada anterior.

Logo:

```text
input_slot = 0
output_slot = 0
```

Resultado:

```text
SLOT0 → QUANTIZE → SLOT0
```

---

# 61. L1 — CONV

Entrada:

```text
SLOT0
```

Preferência:

```text
next_slot = 1
```

Saída:

```text
SLOT1
```

Resultado:

```text
SLOT0 → CONV → SLOT1
```

---

# 62. L2 — DEPTHWISE

Entrada:

```text
SLOT1
```

Se SLOT2 estiver livre:

```text
output = SLOT2
```

Resultado:

```text
SLOT1 → DW → SLOT2
```

---

# 63. L3 — CONV

Entrada:

```text
SLOT2
```

Se SLOT0 já estiver liberado:

```text
output = SLOT0
```

Resultado:

```text
SLOT2 → CONV → SLOT0
```

---

# 64. Resultado da cadeia

```text
             entrada
                │
                ▼
             SLOT0
                │
             QUANTIZE
                │
                ▼
             SLOT0
                │
              CONV
                │
                ▼
             SLOT1
                │
                DW
                │
                ▼
             SLOT2
                │
              CONV
                │
                ▼
             SLOT0
```

A memória é reutilizada em ciclo.

---

# 65. Exemplo com residual

Considere:

```text
L1
 ├─────────────────────────────┐
 ↓                             │
L2                             │
 ↓                             │
L3                             │
 ↓                             │
L4                             │
 └───────────────┐             │
                 ▼             ▼
                    L5 ADD
```

Suponha:

```text
L1 output = SLOT1
```

Como L1 possui dois consumidores:

```text
L2
L5
```

o estado é:

```python
slot_readers_count = {
    1: 2
}
```

---

# 66. L2 consome SLOT1

Após L2:

```text
SLOT1 readers:
2 → 1
```

A memória continua protegida.

---

# 67. Camadas intermediárias

L3 e L4 podem utilizar outros slots.

SLOT1 continua indisponível porque:

```text
L5 ainda precisa dele
```

---

# 68. L5 ADD

L5 recebe:

```text
SLOT1
+
slot da saída de L4
```

Depois que L5 consome SLOT1:

```text
1 → 0
```

Agora o slot pode ser reutilizado.

Esse é o mecanismo que preserva skip connections.

---

# 69. Relação entre `above` e `input_slots`

O código não consulta diretamente tensors nesta fase.

Ele utiliza:

```text
layer["above"]
```

e:

```text
layer_output_slot
```

A transformação é:

```text
L6
 ↓
layer_output_slot["L6"]
 ↓
slot 1
```

Então:

```text
above
 ↓
input_slots
```

---

# 70. Relação entre `below` e liveness

Da mesma forma:

```text
layer["below"]
```

define:

```text
quantos leitores futuros existem
```

Ou seja:

```text
len(layers_below)
    ↓
slot_readers_count
```

Isso implementa uma forma simples de análise de vida útil.

---

# 71. Conceito de liveness

Em compiladores e planejamento de memória, um valor está "vivo" enquanto ainda poderá ser utilizado no futuro.

Neste módulo:

```text
slot_readers_count[slot] > 0
```

representa:

```text
o valor armazenado no slot ainda está vivo
```

Quando:

```text
slot_readers_count
não contém mais o slot
```

o valor é considerado morto para o restante do grafo.

---

# 72. Não é uma alocação de memória em bytes

É importante não confundir:

```text
allocate_slots()
```

com:

```text
malloc()
```

ou cálculo de endereços.

Aqui o resultado é:

```text
L10 → slot 2
```

não:

```text
L10 → endereço 900464
```

A conversão física ocorre depois.

---

# 73. Relação com `memory.py`

Posteriormente:

```text
memory.py
```

calcula:

```text
SLOT_BYTES
```

e depois:

```text
slot_bases
```

Por exemplo:

```text
SLOT0_BASE = 507248
SLOT1_BASE = 703856
SLOT2_BASE = 900464
```

Assim:

```text
output_slot = 2
```

pode virar:

```text
out_ptr = slot_bases[2]
        = 900464
```

---

# 74. Relação com `tensor_mapping.py`

`allocate_slots()` trabalha por camada.

Mas outras partes do pipeline precisam responder:

```text
em qual slot está o tensor TFLite 173?
```

Essa responsabilidade pertence a:

```text
tensor_mapping.py
```

Fluxo:

```text
layer
 ↓
allocate_slots()
 ↓
layer → slot
 ↓
tensor_mapping.py
 ↓
tensor → slot
```

---

# 75. Relação com `layer_params.py`

Depois:

```text
input_slots
output_slot
```

são transformados em ponteiros reais.

Conceitualmente:

```text
input_slot = 1
      ↓
slot_bases[1]
      ↓
in_ptr
```

e:

```text
output_slot = 2
      ↓
slot_bases[2]
      ↓
out_ptr
```

Esses ponteiros entram nas `LayerParams`.

---

# 76. Fluxo completo

```text
graph.py
  │
  │ acima / abaixo
  ▼
slots.py
  │
  │ input_slot / output_slot
  ▼
tensor_mapping.py
  │
  │ tensor → slot
  ▼
memory.py
  │
  │ slot → base
  ▼
layer_params.py
  │
  │ in_ptr / out_ptr
  ▼
params_blob
  │
  ▼
WAT
```

---

# 77. `slot_allocation_to_text()`

A segunda função do módulo é:

```python
def slot_allocation_to_text(
    allocation
):
```

Ela não influencia o cálculo.

Seu objetivo é apenas transformar:

```python
allocation
```

em texto legível.

---

# 78. Separação importante

A fonte de verdade é:

```python
allocation
```

O relatório é derivado dela.

Portanto:

```text
allocation
   ├──→ próximos módulos
   └──→ slot_allocation_to_text()
               ↓
            relatório
```

Nunca o contrário.

---

# 79. Inicialização do relatório

```python
lines = []
```

Cada decisão será convertida em uma linha textual.

---

# 80. Percorrendo registros

```python
for alloc in allocation:
```

Cada elemento contém:

```text
layer
type
input_slots
output_slot
in_place
```

---

# 81. Recuperando entradas e saída

```python
input_slots = (
    alloc["input_slots"]
)
```

```python
output_slot = (
    alloc["output_slot"]
)
```

---

# 82. Uma entrada

Se:

```python
len(input_slots) == 1
```

o texto é:

```python
inputs = str(
    input_slots[0]
)
```

Exemplo:

```text
[1 -> 2]
```

---

# 83. Múltiplas entradas

Caso contrário:

```python
inputs = " e ".join(
    map(str, input_slots)
)
```

Para:

```python
[1, 2]
```

produz:

```text
1 e 2
```

Então:

```text
[1 e 2 -> 0]
```

---

# 84. Montagem da linha

A linha usa:

```python
line = (
    f"{alloc['type']:25} "
    f"{alloc['layer']:5} "
    f"[{inputs} -> {output_slot}]"
)
```

Os especificadores:

```text
:25
:5
```

servem apenas para alinhar visualmente as colunas.

Não alteram os dados.

---

# 85. Exemplo de relatório

```text
QUANTIZE                  L0    [0 -> 0] (in-place)
CONV_2D                   L1    [0 -> 1]
DEPTHWISE_CONV_2D         L2    [1 -> 2]
CONV_2D                   L3    [2 -> 0]
ADD                       L4    [0 e 1 -> 2]
```

---

# 86. Marcador in-place

Se:

```python
alloc["in_place"]
```

for verdadeiro:

```python
line += " (in-place)"
```

Assim o relatório deixa explícito que entrada e saída compartilham a mesma região lógica.

---

# 87. Retorno textual

Por fim:

```python
return "\n".join(
    lines
)
```

transforma a lista em um único texto.

---

# 88. Estado temporário versus resultado permanente

É importante distinguir:

```text
slot_readers_count
```

de:

```text
allocation
```

`slot_readers_count` só existe durante a execução do algoritmo.

`allocation` é o resultado final.

Exemplo:

```text
durante L10:

slot_readers_count = {
    0: 1,
    2: 2
}
```

Esse estado não precisa ser preservado depois.

Já:

```python
{
    "layer": "L10",
    "input_slots": [0, 2],
    "output_slot": 1,
}
```

é permanente.

---

# 89. O algoritmo não reserva memória fisicamente

Quando executa:

```python
output_slot = 1
```

nenhum byte é alocado.

Ele apenas produz uma decisão lógica.

A alocação física será:

```text
slot 1
    ↓
SLOT1_BASE
    ↓
região [SLOT1_BASE,
       SLOT1_BASE + SLOT_BYTES)
```

---

# 90. Por que `NUM_SLOTS = 3` é suficiente para o modelo atual?

O modelo utilizado pelo projeto consegue ser planejado pelo algoritmo atual com três regiões reutilizáveis.

A necessidade vem principalmente da combinação de:

```text
entrada atual
saída nova
valor residual preservado
```

Em um bloco residual típico:

```text
SLOT A
  ├─────────────────────────┐
  ▼                         │
cadeia de operações         │
  ▼                         │
SLOT B/C                    │
                            ▼
                           ADD
```

três slots permitem manter um valor antigo enquanto outros dois participam da cadeia de cálculo.

Isso descreve o comportamento observado no modelo atual, não uma garantia de que qualquer rede possa ser executada com três slots.

---

# 91. `NUM_SLOTS` não é propriedade do TFLite

O arquivo TFLite não diz:

```text
use três slots
```

Essa é uma decisão do runtime desenvolvido no projeto.

Portanto:

```text
TFLite
    ↓
grafo
    ↓
estratégia própria
    ↓
3 slots
```

---

# 92. Limitação importante: contagem por slot

O algoritmo atual mantém:

```python
slot_readers_count
```

por slot.

Por exemplo:

```python
{
    1: 2
}
```

Ele não mantém explicitamente:

```text
tensor X possui 2 leitores
tensor Y possui 1 leitor
```

Essa é uma simplificação importante da implementação.

---

# 93. Por que isso funciona no cenário atual?

A estratégia pressupõe que um slot represente, naquele momento, um único valor lógico vivo.

Enquanto ele possui leitores pendentes:

```text
não pode ser sobrescrito
```

Quando a contagem chega a zero:

```text
pode receber outro valor
```

Assim, o slot atua como proxy da vida útil do tensor atualmente armazenado nele.

---

# 94. Limite conceitual dessa abordagem

Uma análise de liveness mais geral poderia rastrear:

```text
tensor_id
    ↓
número de usos restantes
```

e depois associar tensores a slots.

O algoritmo atual combina parte dessas duas responsabilidades:

```text
slot
    ↓
número de leitores restantes
```

Isso é mais simples, mas depende da estratégia de reutilização adotada.

---

# 95. Caso especial que merece atenção: `QUANTIZE`

No bloco:

```python
if layer_type == "QUANTIZE":
```

a função registra o mesmo slot para entrada e saída e executa:

```python
continue
```

Portanto o caminho `QUANTIZE` não executa a lógica comum de:

```text
decrementar leitores da entrada
registrar leitores da saída
```

Esse comportamento é exatamente o comportamento atual do código.

---

# 96. Implicação

Para o modelo atual, essa implementação foi mantida para preservar o comportamento da versão original.

Entretanto, conceitualmente existe uma diferença entre:

```text
operação in-place
```

e:

```text
vida útil do valor antes e depois da operação
```

Se no futuro houver modelos com diferentes padrões de ramificação em torno de um `QUANTIZE`, esse ponto merece validação específica.

---

# 97. Por que não alterar agora?

A refatoração teve como objetivo inicial:

```text
separar responsabilidades
preservando o comportamento funcional existente
```

Modificar simultaneamente o algoritmo de slots poderia introduzir diferenças difíceis de atribuir.

A estratégia adotada foi:

```text
primeiro modularizar
depois validar
depois melhorar
```

---

# 98. Invariante importante

Antes de uma camada utilizar:

```python
layer_output_slot[above]
```

o produtor correspondente deve já ter sido processado.

Isso depende da ordem topológica de `layers`.

Se `layers` não estivesse em uma ordem válida:

```text
consumidor antes do produtor
```

a função poderia gerar:

```text
KeyError
```

ao procurar um slot ainda inexistente.

---

# 99. Invariante dos slots

Todo valor em:

```python
input_slots
```

e:

```python
output_slot
```

deve satisfazer:

```text
0 <= slot < num_slots
```

Com:

```python
num_slots = 3
```

os únicos valores válidos são:

```text
0
1
2
```

---

# 100. Invariante de saída

Para cada camada processada deve existir:

```python
layer_output_slot[
    layer_name
]
```

Isso garante que qualquer consumidor posterior consiga descobrir sua entrada.

---

# 101. Invariante de slot vivo

Quando:

```python
slot_readers_count[slot] > 0
```

o algoritmo deve impedir que ele seja escolhido como saída de outra camada.

É exatamente isso que o filtro de:

```python
available_slots
```

implementa.

---

# 102. Exemplo passo a passo detalhado

Considere:

```text
L0 QUANTIZE
 ↓
L1 CONV
 ├───────────────┐
 ↓               │
L2 DW            │
 ↓               │
L3 CONV           │
 └───────┐       │
         ▼       ▼
          L4 ADD
```

Suponha:

```text
NUM_SLOTS = 3
```

---

# 103. Passo L0

`QUANTIZE`.

Sem predecessores.

```text
input = 0
output = 0
```

Estado:

```python
layer_output_slot = {
    "L0": 0
}
```

---

# 104. Passo L1

Entrada:

```text
L0 → SLOT0
```

Slots disponíveis inicialmente:

```text
0, 1, 2
```

Preferência:

```text
1
```

Então:

```text
L1 → SLOT1
```

Como L1 possui dois consumidores:

```text
L2
L4
```

registramos:

```python
slot_readers_count = {
    1: 2
}
```

---

# 105. Passo L2

Entrada:

```text
SLOT1
```

Antes de escolher a saída:

```text
SLOT1 protegido
```

Disponíveis:

```text
SLOT0
SLOT2
```

Preferência atual:

```text
SLOT2
```

Logo:

```text
L2 output → SLOT2
```

Ao consumir SLOT1:

```text
2 → 1
```

Se L2 possui um consumidor:

```text
L3
```

registramos:

```text
SLOT2 → 1 leitor
```

Estado:

```python
slot_readers_count = {
    1: 1,
    2: 1,
}
```

---

# 106. Passo L3

Entrada:

```text
SLOT2
```

Slots protegidos:

```text
1
2
```

Livre:

```text
0
```

Logo:

```text
L3 output → SLOT0
```

SLOT2 é consumido:

```text
1 → 0
```

Então SLOT2 é liberado.

Se L3 alimenta L4:

```text
SLOT0 → 1 leitor
```

Estado:

```python
slot_readers_count = {
    1: 1,
    0: 1,
}
```

---

# 107. Passo L4 — ADD

Entradas:

```text
L1 → SLOT1
L3 → SLOT0
```

Slots protegidos antes do consumo:

```text
SLOT1
SLOT0
```

Livre:

```text
SLOT2
```

Então:

```text
ADD output → SLOT2
```

Depois do consumo:

```text
SLOT1:
1 → 0

SLOT0:
1 → 0
```

Ambos são liberados.

---

# 108. Resultado final do exemplo

```text
L0 QUANTIZE  [0 → 0]
L1 CONV      [0 → 1]
L2 DW        [1 → 2]
L3 CONV      [2 → 0]
L4 ADD       [1,0 → 2]
```

Visualmente:

```text
                ┌──────────── SLOT1 ──────────────┐
                │                                  │
SLOT0 → L0 → SLOT0 → L1 → SLOT1 → L2 → SLOT2     │
                                      ↓            │
                                     L3            │
                                      ↓            │
                                    SLOT0          │
                                      │            │
                                      └──── L4 ADD ◄┘
                                             │
                                             ▼
                                           SLOT2
```

---

# 109. Relação entre liveness e residual connection

Esse exemplo mostra o ponto mais importante do módulo:

```text
o resultado de L1 permanece vivo
mesmo depois de L2 e L3
```

porque ainda existe:

```text
L4
```

como consumidor.

Sem esse controle, a residual connection seria destruída.

---

# 110. Complexidade

Para cada camada, o algoritmo examina:

```text
inputs
slots
consumidores
```

Como o número de slots é pequeno e fixo no projeto:

```text
3
```

o custo dessa etapa é insignificante comparado à inferência.

Conceitualmente, o custo depende aproximadamente de:

```text
número de camadas
+
número de relações do grafo
```

---

# 111. O que este módulo deliberadamente não faz

`slots.py` não:

```text
calcula SLOT_BYTES
calcula SLOT0_BASE
calcula SLOT1_BASE
calcula SLOT2_BASE
lê tensors TFLite
calcula quantização
gera LayerParam
gera params_blob
gera WAT
```

Ele responde apenas:

```text
qual slot lógico cada camada lê e escreve?
```

---

# 112. Por que essa separação é importante?

Se `slots.py` também calculasse endereços físicos, ele precisaria conhecer:

```text
tamanho máximo de tensor
alinhamento
params_base
tamanho da memória
```

Isso criaria acoplamento com `memory.py`.

A arquitetura atual mantém:

```text
slots.py
    ↓
identidade lógica

memory.py
    ↓
posição física
```

---

# 113. Representação final do módulo

Podemos resumir assim:

```text
           graph.py
              │
              │ layers
              ▼
       ┌───────────────┐
       │   slots.py    │
       └───────────────┘
              │
        ┌─────┴─────┐
        ▼           ▼
 allocation   layer_output_slot
        │           │
        │           └──→ tensor_mapping.py
        │
        ├──→ relatório
        │
        └──→ layer_params.py
```

---

# 114. Relação com o problema de memória do ESP32

A escolha de slots reutilizáveis é particularmente importante no contexto deste projeto porque o dispositivo alvo possui recursos limitados.

Uma implementação conceitualmente simples poderia fazer:

```text
uma região por tensor
```

Mas isso aumentaria significativamente o consumo de memória.

A estratégia adotada é:

```text
determinar vida útil
       ↓
reutilizar regiões
       ↓
reduzir memória de ativações
```

---

# 115. Slots versus pesos

Os slots guardam:

```text
ativações intermediárias
```

e não:

```text
pesos
bias
multipliers
shifts
q6
LayerParams
```

Esses dados possuem outras regiões.

Layout conceitual:

```text
memória WASM

┌──────────────────────┐
│ região inicial       │
├──────────────────────┤
│ WEIGHTS              │
├──────────────────────┤
│ BIAS                 │
├──────────────────────┤
│ MUL                  │
├──────────────────────┤
│ SHIFT                │
├──────────────────────┤
│ Q6                   │
├──────────────────────┤
│ PARAMS               │
├──────────────────────┤
│ SLOT0                │
├──────────────────────┤
│ SLOT1                │
├──────────────────────┤
│ SLOT2                │
└──────────────────────┘
```

`slots.py` decide apenas a ocupação lógica das três últimas regiões.

---

# 116. Slots versus tensors

Um mesmo slot pode armazenar muitos tensors diferentes ao longo da inferência.

Exemplo:

```text
SLOT1

tempo 1:
tensor de saída de L1

tempo 2:
tensor de saída de L4

tempo 3:
tensor de saída de L7
```

Portanto:

```text
slot ≠ tensor
```

A relação é temporal:

```text
tensor utiliza slot durante parte da execução
```

---

# 117. Consequência para depuração

Quando o relatório mostra:

```text
L5 → SLOT1
```

isso não significa:

```text
SLOT1 sempre contém L5
```

Significa:

```text
depois da execução de L5,
seu output é colocado em SLOT1
até que seja consumido ou sobrescrito de forma segura
```

---

# 118. Por que guardar `in_place`

O campo:

```python
"in_place": True
```

pode parecer redundante porque:

```text
input_slot == output_slot
```

já revela o compartilhamento.

Mas mantê-lo torna a intenção explícita.

É possível conceber situações em que:

```text
input_slot == output_slot
```

aconteça por algum outro motivo.

O flag informa:

```text
esta operação foi deliberadamente planejada como in-place
```

---

# 119. Diferença entre slot livre e slot vazio

O algoritmo não limpa bytes quando um slot é liberado.

Portanto:

```text
slot livre
```

não significa:

```text
memória contém zeros
```

Significa apenas:

```text
o valor anterior não é mais semanticamente necessário
```

A próxima operação poderá sobrescrever a região.

---

# 120. Importância dessa distinção

Após:

```text
SLOT1 liberado
```

ele ainda pode conter os bytes da ativação antiga.

Mas isso não importa porque nenhuma camada futura deve lê-los como aquele tensor.

Logo, "livre" é uma propriedade lógica, não uma propriedade do conteúdo físico.

---

# 121. Dependência da qualidade do grafo

A correção deste módulo depende diretamente de:

```text
layers_above
layers_below
```

estarem corretos.

Se `graph.py` esquecer um consumidor:

```text
readers_count menor do que deveria
```

o slot poderá ser reutilizado cedo demais.

Resultado possível:

```text
tensor sobrescrito antes de uso
```

---

# 122. Cadeia de consequência de um erro

```text
grafo incorreto
      ↓
readers_count incorreto
      ↓
slot liberado cedo demais
      ↓
outro tensor sobrescreve memória
      ↓
camada futura lê dado errado
      ↓
inferência incorreta
```

Isso mostra que a alocação de slots é uma etapa crítica mesmo sem realizar nenhuma operação neural.

---

# 123. Validação atual

O algoritmo possui uma validação explícita:

```python
if not available_slots:
    raise RuntimeError(...)
```

Ela detecta:

```text
necessidade de mais slots
```

segundo o estado calculado.

Outras propriedades são verificadas indiretamente durante a execução do pipeline.

---

# 124. Possíveis validações futuras

Uma versão futura mais rigorosa poderia verificar explicitamente:

```text
todos os input_slots estão no intervalo
todos os output_slots estão no intervalo
nenhuma camada referencia predecessor inexistente
todo predecessor já possui output_slot
in-place só ocorre em tipos permitidos
```

Também seria possível comparar a alocação contra uma análise de vida útil por tensor.

Essas melhorias não são necessárias para explicar o comportamento atual, mas são caminhos naturais de validação.

---

# 125. Papel do relatório

`slot_allocation_to_text()` permite visualizar imediatamente padrões suspeitos.

Por exemplo:

```text
CONV_2D             L10   [1 -> 2]
ADD                 L11   [1 e 2 -> 0]
```

é coerente com duas entradas distintas.

Já uma saída inesperada como:

```text
ADD                 L11   [1 e 1 -> 2]
```

pode justificar inspeção adicional, dependendo do grafo.

---

# 126. O relatório não é usado pela inferência

Depois que o texto é gravado:

```text
reports/03-alocacao-slots.txt
```

o pipeline não o lê novamente.

Logo:

```text
relatório = observabilidade
```

e:

```text
allocation = dados de execução
```

---

# 127. Resumo das estruturas

| Estrutura            | Função                                                                   |
| -------------------- | ------------------------------------------------------------------------ |
| `layer_output_slot`  | Descobrir em qual slot está a saída de cada camada                       |
| `slot_readers_count` | Controlar quantos consumidores ainda necessitam do conteúdo de cada slot |
| `allocation`         | Registrar a alocação final de cada camada                                |
| `next_slot`          | Indicar o slot preferencial para a próxima saída                         |
| `available_slots`    | Slots que podem ser sobrescritos naquele momento                         |

---

# 128. Resumo dos campos de `allocation`

| Campo         | Significado                                       |
| ------------- | ------------------------------------------------- |
| `layer`       | Label lógico da camada                            |
| `type`        | Tipo da operação                                  |
| `input_slots` | Slots contendo as entradas                        |
| `output_slot` | Slot onde a saída será armazenada                 |
| `in_place`    | Indica reutilização deliberada do slot de entrada |

---

# 129. Resumo do algoritmo

A lógica geral pode ser representada assim:

```text
para cada camada
      │
      ▼
descobrir slots das entradas
      │
      ▼
é QUANTIZE?
  │          │
 sim        não
  │          │
  ▼          ▼
reusar     encontrar
entrada    slots livres
  │          │
  │          ▼
  │       escolher
  │       output_slot
  │          │
  │          ▼
  │       consumir
  │       leitores das entradas
  │          │
  │          ▼
  │       registrar leitores
  │       da nova saída
  │          │
  └──────┬───┘
         ▼
registrar camada → slot
         │
         ▼
próxima camada
```

---

# 130. Visão mais abstrata

O problema resolvido pelo módulo é:

```text
GRAFO DE DEPENDÊNCIAS
        │
        ▼
ANÁLISE DE VIDA ÚTIL
        │
        ▼
REUTILIZAÇÃO DE BUFFERS
        │
        ▼
MENOR QUANTIDADE DE REGIÕES
DE ATIVAÇÃO NECESSÁRIAS
```

---

# 131. Papel no pipeline completo

Neste ponto, o projeto pode ser entendido assim:

```text
┌──────────────────────────────┐
│          config.py           │
│                              │
│ define NUM_SLOTS = 3         │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│          graph.py            │
│                              │
│ Lx → predecessores           │
│ Lx → consumidores            │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│          slots.py            │
│                              │
│ Lx → input slots             │
│ Lx → output slot             │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│      tensor_mapping.py       │
│                              │
│ tensor TFLite → slot         │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│         memory.py            │
│                              │
│ slot → endereço físico       │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│      layer_params.py         │
│                              │
│ in_ptr / out_ptr             │
└──────────────────────────────┘
```

---

# 132. Síntese

O `slots.py` implementa a transição entre:

```text
dependência lógica
```

e:

```text
reutilização concreta de memória
```

Ele ainda não conhece bytes ou endereços, mas decide uma propriedade essencial:

```text
qual resultado pode ocupar qual região
sem destruir dados que ainda serão necessários
```

A lógica central é:

```text
saída possui consumidores?
        │
        ▼
mantenha o slot protegido

último consumidor executou?
        │
        ▼
libere o slot

nova camada precisa de saída?
        │
        ▼
escolha um slot disponível
```

Essa estratégia permite que uma rede com dezenas de camadas reutilize apenas três grandes buffers intermediários, em vez de reservar uma região independente para cada saída de camada.

Ao mesmo tempo, o código preserva o comportamento especial do `QUANTIZE`, que atualmente opera in-place, e mantém explícitas as limitações da estratégia de contagem por slot para que futuras generalizações do extrator possam ser feitas de forma consciente e validada.
