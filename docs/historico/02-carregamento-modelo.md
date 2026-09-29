> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.md). O corpo original foi mantido.

# 02 — Carregamento do modelo TFLite (`model_loader.py`)

## 1. Objetivo do módulo

O arquivo `extractor/model_loader.py` é responsável pela primeira transformação realizada pelo pipeline:

```text
arquivo .tflite no disco
        │
        ▼
sequência de bytes
        │
        ▼
binding Python do TFLite
        │
        ▼
objeto Model
        │
        ▼
SubGraph utilizado pelo extrator
```

O código atual é:

```python
from pathlib import Path
import tflite.Model as TFLModel


def load_model(model_path):
    buf = Path(model_path).read_bytes()

    if hasattr(TFLModel, "GetRootAsModel"):
        model = TFLModel.GetRootAsModel(buf, 0)

    elif (
        hasattr(TFLModel, "Model")
        and hasattr(TFLModel.Model, "GetRootAsModel")
    ):
        model = TFLModel.Model.GetRootAsModel(buf, 0)

    else:
        raise RuntimeError(
            "Binding tflite.Model não possui GetRootAsModel."
        )

    return model


def get_subgraph(model, index=0):
    return model.Subgraphs(index)
```

Esse módulo possui duas responsabilidades bem delimitadas:

1. carregar e interpretar o arquivo TFLite;
2. selecionar o subgrafo que será utilizado pelo restante do pipeline.

Ele **não** analisa operadores, tensors, pesos, quantização ou memória.

Essas responsabilidades pertencem aos módulos posteriores.

---

# 2. Posição no pipeline

O módulo aparece imediatamente depois da configuração.

```text
config.py
   │
   │ MODEL_PATH
   ▼
model_loader.py
   │
   ├── load_model()
   │
   └── get_subgraph()
   ▼
Model + SubGraph
   │
   ├── graph.py
   ├── tflite_utils.py
   ├── weights.py
   ├── quantization.py
   ├── slots.py
   └── layer_params.py
```

Portanto, praticamente todo o restante do extrator depende indiretamente dessa etapa.

Se o modelo não puder ser carregado corretamente, nenhuma das fases seguintes pode ser executada.

---

# 3. Importação de `Path`

O arquivo começa com:

```python
from pathlib import Path
```

O `Path` é utilizado para manipular o caminho recebido por `load_model()`.

Dentro da função:

```python
buf = Path(model_path).read_bytes()
```

Isso permite que `model_path` seja fornecido tanto como:

```python
Path("model_int8_esp32.tflite")
```

quanto como:

```python
"model_int8_esp32.tflite"
```

porque:

```python
Path(model_path)
```

normaliza o argumento para um objeto `Path`.

---

# 4. Importação do binding TFLite

A segunda importação é:

```python
import tflite.Model as TFLModel
```

O nome:

```text
TFLModel
```

é apenas um alias Python utilizado para tornar explícito que esse módulo representa a estrutura `Model` definida pelo formato TFLite.

O extrator não utiliza TensorFlow para executar a rede nesta etapa.

Ele utiliza o binding Python do formato TFLite para navegar pela estrutura serializada do arquivo.

A distinção é importante:

```text
TensorFlow / TFLite Interpreter
        │
        └── executaria o modelo

binding tflite usado aqui
        │
        └── permite inspecionar sua estrutura
```

Neste projeto, o objetivo não é pedir ao TFLite que realize a inferência.

O objetivo é extrair informações como:

```text
operadores
tensors
shapes
buffers
pesos
bias
zero points
scales
opções dos operadores
```

para posteriormente construir uma representação própria utilizada pelo módulo WebAssembly.

---

# 5. Arquivo `.tflite`

Um arquivo:

```text
model_int8_esp32.tflite
```

não é um arquivo Python nem um arquivo textual.

Ele é uma representação binária estruturada.

Por isso não fazemos:

```python
open(...).read()
```

como texto.

O código utiliza:

```python
read_bytes()
```

produzindo:

```text
bytes
```

Conceitualmente:

```text
model_int8_esp32.tflite
       │
       ▼
  Path.read_bytes()
       │
       ▼
b'\x1c\x00\x00...'
```

O conteúdo real possui milhares ou milhões de bytes.

Essa sequência será interpretada pelo binding do TFLite.

---

# 6. Função `load_model()`

A função principal é:

```python
def load_model(model_path):
```

Sua responsabilidade é:

```text
caminho do arquivo
      ↓
ler bytes
      ↓
localizar o parser correto no binding
      ↓
obter objeto Model
      ↓
retornar Model
```

Ela recebe apenas uma informação:

```text
model_path
```

e retorna:

```text
model
```

Não existe estado global ou efeito colateral relacionado ao modelo.

---

# 7. Leitura dos bytes

A primeira instrução é:

```python
buf = Path(model_path).read_bytes()
```

Ela pode ser decomposta em:

```text
model_path
    │
    ▼
Path(model_path)
    │
    ▼
objeto Path
    │
    ▼
.read_bytes()
    │
    ▼
buf
```

O nome:

```text
buf
```

é abreviação de `buffer`.

Ele contém todo o arquivo TFLite em memória.

Conceitualmente:

```python
buf: bytes
```

---

# 8. Por que carregar o arquivo inteiro?

O código atual utiliza:

```python
read_bytes()
```

e portanto carrega o arquivo TFLite inteiro na memória.

Para o modelo utilizado neste projeto, isso é adequado porque o extrator precisa navegar por diferentes partes da estrutura:

```text
Model
 ├── OperatorCodes
 ├── SubGraphs
 │    ├── Operators
 │    ├── Tensors
 │    ├── Inputs
 │    └── Outputs
 └── Buffers
```

Durante a extração, diferentes módulos acessam repetidamente essas estruturas.

Manter o buffer disponível permite que o binding faça essas consultas.

---

# 9. `GetRootAsModel`

Depois da leitura:

```python
if hasattr(TFLModel, "GetRootAsModel"):
    model = TFLModel.GetRootAsModel(buf, 0)
```

A função:

```text
GetRootAsModel
```

interpreta a estrutura raiz armazenada no buffer como um objeto TFLite `Model`.

Conceitualmente:

```text
bytes
  │
  ▼
GetRootAsModel
  │
  ▼
Model
```

Esse passo é fundamental porque os bytes deixam de ser tratados como uma sequência opaca e passam a ser acessados por meio de métodos como:

```python
model.Subgraphs(...)
model.OperatorCodes(...)
model.Buffers(...)
```

---

# 10. O segundo argumento `0`

A chamada é:

```python
TFLModel.GetRootAsModel(
    buf,
    0
)
```

O segundo argumento:

```text
0
```

indica o deslocamento inicial utilizado para localizar a estrutura raiz no buffer.

No uso normal do arquivo TFLite completo, o parsing é iniciado a partir do início do buffer.

O extrator não precisa conhecer manualmente os offsets internos de cada tensor ou operador.

Essa navegação é fornecida pelo binding.

---

# 11. O objeto retornado não é uma cópia simplificada do modelo

É importante entender que:

```python
model = TFLModel.GetRootAsModel(buf, 0)
```

não converte todo o modelo para estruturas comuns como:

```python
dict
list
numpy.ndarray
```

O resultado é um objeto fornecido pelo binding do TFLite.

Ele expõe métodos de acesso à estrutura serializada.

Por exemplo:

```python
model.SubgraphsLength()
```

pode informar quantos subgrafos existem.

E:

```python
model.Subgraphs(0)
```

permite acessar um deles.

A extração acontece sob demanda à medida que esses métodos são chamados.

---

# 12. Compatibilidade entre versões do binding

O código contém duas formas possíveis de localizar `GetRootAsModel`.

Primeira:

```python
if hasattr(
    TFLModel,
    "GetRootAsModel"
):
```

Segunda:

```python
elif (
    hasattr(TFLModel, "Model")
    and hasattr(
        TFLModel.Model,
        "GetRootAsModel"
    )
):
```

Isso existe porque diferentes formas de empacotamento ou versões do binding Python podem expor a classe gerada com estruturas ligeiramente diferentes.

Em um ambiente, pode existir diretamente:

```python
TFLModel.GetRootAsModel(...)
```

Em outro:

```python
TFLModel.Model.GetRootAsModel(...)
```

O extrator aceita ambas.

---

# 13. Primeira forma suportada

A primeira tentativa é:

```python
if hasattr(TFLModel, "GetRootAsModel"):
```

Caso seja verdadeira:

```python
model = TFLModel.GetRootAsModel(
    buf,
    0
)
```

Estruturalmente:

```text
TFLModel
   │
   └── GetRootAsModel()
```

É a forma mais direta.

---

# 14. Segunda forma suportada

Se o método não existir diretamente, o código testa:

```python
elif (
    hasattr(TFLModel, "Model")
    and hasattr(
        TFLModel.Model,
        "GetRootAsModel"
    )
):
```

Nesse caso, a estrutura é:

```text
TFLModel
   │
   └── Model
         │
         └── GetRootAsModel()
```

E a chamada torna-se:

```python
model = (
    TFLModel.Model
    .GetRootAsModel(
        buf,
        0
    )
)
```

O resultado lógico é o mesmo:

```text
buffer TFLite
      ↓
objeto Model
```

---

# 15. Uso de `hasattr`

A função:

```python
hasattr(objeto, "atributo")
```

verifica se determinado objeto possui um atributo.

Exemplo:

```python
hasattr(
    TFLModel,
    "GetRootAsModel"
)
```

retorna:

```text
True
```

ou:

```text
False
```

Isso permite decidir dinamicamente qual interface do binding está disponível.

Sem essa verificação, utilizar diretamente:

```python
TFLModel.GetRootAsModel(...)
```

poderia produzir:

```text
AttributeError
```

em uma instalação cuja estrutura seja diferente.

---

# 16. Por que não usar `try/except` diretamente?

Também seria possível escrever algo semelhante a:

```python
try:
    model = TFLModel.GetRootAsModel(
        buf,
        0
    )
except AttributeError:
    ...
```

Mas o código atual prefere verificar explicitamente a estrutura disponível.

Isso deixa mais claro que existem **duas interfaces conhecidas e suportadas**.

A intenção não é ignorar qualquer erro.

É detectar qual formato de binding está instalado.

---

# 17. Falha explícita

Se nenhuma das duas formas estiver disponível:

```python
else:
    raise RuntimeError(
        "Binding tflite.Model não possui GetRootAsModel."
    )
```

O extrator interrompe a execução.

Isso é melhor do que continuar com:

```python
model = None
```

e produzir erros difíceis de interpretar posteriormente.

A falha ocorre exatamente na etapa responsável pela leitura do modelo.

Fluxo:

```text
GetRootAsModel disponível?
        │
     ┌──┴──┐
     │     │
    sim   não
     │     │
     ▼     ▼
 Model   RuntimeError
```

---

# 18. Por que `RuntimeError`?

O problema detectado não é simplesmente um arquivo ausente ou um argumento inválido.

Nesse ponto, o extrator encontrou uma incompatibilidade entre a interface esperada e o binding TFLite instalado.

Por isso a mensagem:

```text
Binding tflite.Model não possui GetRootAsModel.
```

explica diretamente qual requisito não foi atendido.

---

# 19. Outros erros possíveis

Nem todos os erros são tratados manualmente por `load_model()`.

Por exemplo, se:

```python
MODEL_PATH
```

apontar para um arquivo inexistente:

```python
Path(model_path).read_bytes()
```

produzirá a exceção correspondente do sistema de arquivos.

Isso é intencionalmente diferente de:

```text
binding incompatível
```

O código não tenta transformar todos os erros em uma única exceção genérica.

Assim é possível distinguir:

```text
arquivo inexistente
arquivo inacessível
binding incompatível
arquivo inválido
```

de acordo com o ponto em que ocorrer a falha.

---

# 20. Retorno de `load_model`

Ao final:

```python
return model
```

A função retorna o objeto que representa a raiz do modelo TFLite.

No `main.py`, seu uso conceitual é:

```python
model = load_model(
    MODEL_PATH
)
```

A partir desse momento:

```text
MODEL_PATH
```

não é mais a principal fonte utilizada pelo pipeline.

A estrutura em memória passa a ser:

```text
model
```

---

# 21. Estrutura conceitual de `Model`

Uma representação simplificada das informações posteriormente acessadas é:

```text
Model
│
├── OperatorCodes
│    ├── opcode 0
│    ├── opcode 1
│    └── ...
│
├── SubGraphs
│    │
│    └── SubGraph 0
│         ├── Inputs
│         ├── Outputs
│         ├── Tensors
│         └── Operators
│
└── Buffers
     ├── buffer 0
     ├── buffer 1
     └── ...
```

Essa estrutura é essencial para entender o restante do extrator.

---

# 22. Relação entre operadores e códigos de operação

Um operador armazenado dentro de um subgrafo não precisa carregar diretamente o nome:

```text
CONV_2D
```

O operador pode referenciar uma entrada da tabela de:

```text
OperatorCodes
```

Por isso posteriormente o extrator utiliza funções auxiliares para converter:

```text
OpcodeIndex
      ↓
OperatorCode
      ↓
BuiltinCode
      ↓
CONV_2D
```

Essa informação já existe no modelo carregado por `load_model()`.

O `model_loader.py`, entretanto, não interpreta esse conteúdo.

Ele apenas disponibiliza o objeto necessário para que `tflite_utils.py` e `graph.py` façam isso posteriormente.

---

# 23. Relação entre tensors e buffers

Outro exemplo importante é a relação:

```text
Tensor
  │
  └── Buffer()
         │
         ▼
      Model.Buffers(...)
```

Um tensor pode apontar para um buffer contendo dados constantes.

É dessa forma que, posteriormente, o extrator identifica e recupera:

```text
pesos
bias
outros tensors constantes
```

Novamente, `model_loader.py` apenas fornece acesso à estrutura.

A interpretação acontece em módulos posteriores.

---

# 24. Função `get_subgraph()`

A segunda função do arquivo é:

```python
def get_subgraph(
    model,
    index=0
):
    return model.Subgraphs(
        index
    )
```

Ela possui uma única responsabilidade:

```text
Model
  ↓
selecionar SubGraph
  ↓
retornar SubGraph
```

---

# 25. O que é um subgrafo neste contexto?

O modelo pode conter uma coleção de subgrafos.

Conceitualmente:

```text
Model
│
├── SubGraph 0
├── SubGraph 1
├── SubGraph 2
└── ...
```

Cada subgrafo pode possuir:

```text
inputs
outputs
tensors
operators
```

Para o pipeline atual, é utilizado por padrão:

```python
index = 0
```

Portanto:

```python
get_subgraph(model)
```

equivale a:

```python
model.Subgraphs(0)
```

---

# 26. Por que `index=0`?

O extrator atual trabalha com o subgrafo principal utilizado pelo modelo analisado.

Por isso a API fornece:

```python
index=0
```

como padrão.

Uso normal:

```python
subgraph = get_subgraph(
    model
)
```

Resultado:

```text
SubGraph 0
```

Mas a função ainda permite explicitamente:

```python
subgraph = get_subgraph(
    model,
    index=1
)
```

caso se deseje acessar outro subgrafo.

---

# 27. Por que criar `get_subgraph()` se a chamada é simples?

Seria possível escrever diretamente no `main.py`:

```python
subgraph = model.Subgraphs(0)
```

Entretanto, encapsular a operação possui algumas vantagens.

Primeiro, torna a intenção explícita:

```python
get_subgraph(model)
```

é semanticamente mais claro que:

```python
model.Subgraphs(0)
```

para quem está lendo o fluxo principal.

Segundo, centraliza a política atual:

```text
subgrafo padrão = índice 0
```

Terceiro, se futuramente houver validações adicionais, elas podem ser implementadas nesse ponto sem alterar todas as chamadas.

Por exemplo, futuramente poderia ser verificado:

```text
índice existente?
subgrafo possui inputs?
subgrafo possui outputs?
```

O código atual ainda não realiza essas validações.

---

# 28. Retorno de `get_subgraph()`

O resultado é armazenado normalmente como:

```python
subgraph = get_subgraph(
    model
)
```

A partir desse objeto, os módulos seguintes conseguem fazer consultas como:

```python
subgraph.OperatorsLength()
```

```python
subgraph.Operators(i)
```

```python
subgraph.Tensors(tensor_id)
```

```python
subgraph.Inputs(...)
```

```python
subgraph.Outputs(...)
```

Portanto:

```text
model
```

representa a estrutura global,

enquanto:

```text
subgraph
```

é o foco principal da análise da rede.

---

# 29. Relação entre `model` e `subgraph`

Uma forma simplificada de visualizar é:

```text
model
│
├── metadados globais
│
├── OperatorCodes
│
├── Buffers
│
│
└── SubGraphs
      │
      └── subgraph
            │
            ├── tensors
            ├── operators
            ├── inputs
            └── outputs
```

Por isso, várias funções posteriores recebem os dois:

```python
func(
    model,
    subgraph,
    ...
)
```

O motivo é que algumas informações estão no `subgraph`, enquanto outras permanecem no nível global do `model`.

---

# 30. Exemplo: resolução do nome de uma operação

Posteriormente, uma função como:

```python
op_name(
    model,
    op
)
```

precisa dos dois níveis.

O operador:

```text
op
```

pertence ao:

```text
subgraph
```

mas seu código pode ser resolvido por meio de:

```text
model.OperatorCodes(...)
```

Fluxo:

```text
SubGraph
   │
   └── Operator
          │
          └── OpcodeIndex
                 │
                 ▼
             Model
                 │
                 └── OperatorCodes
                        │
                        ▼
                     CONV_2D
```

Isso explica por que é importante preservar ambos os objetos.

---

# 31. Exemplo: leitura de pesos

Algo semelhante ocorre com um tensor constante.

O tensor é localizado no subgrafo:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

Depois ele informa qual buffer contém os dados:

```python
tensor.Buffer()
```

E esse buffer é acessado no modelo:

```python
model.Buffers(
    tensor.Buffer()
)
```

Fluxo:

```text
SubGraph
   │
   └── Tensor
          │
          └── Buffer ID
                 │
                 ▼
              Model
                 │
                 └── Buffers
                       │
                       ▼
                  bytes dos pesos
```

Portanto, `model_loader.py` prepara exatamente os dois níveis de acesso que o restante do extrator necessita.

---

# 32. O que este módulo deliberadamente não faz

O módulo não possui lógica para:

```text
identificar operadores
construir grafo
calcular topologia
alocar slots
extrair pesos
extrair bias
calcular multiplicadores
calcular shifts
calcular Q6
calcular memória
gerar LayerParams
gerar params_blob
gerar WAT
```

Essa separação é importante.

O papel deste arquivo é exclusivamente:

```text
arquivo → Model → SubGraph
```

---

# 33. Ausência de efeitos durante o `import`

Uma decisão importante no código atual é que o modelo não é carregado diretamente no corpo do módulo.

Não fazemos:

```python
MODEL = load_model(
    "model_int8_esp32.tflite"
)
```

ao importar `model_loader.py`.

Em vez disso:

```python
def load_model(...):
```

apenas define a função.

A leitura acontece quando o `main.py` decide executá-la.

Isso evita efeitos colaterais no momento do import.

---

# 34. Por que evitar carregamento automático?

Imagine outro módulo executando:

```python
from extractor.model_loader import (
    load_model
)
```

Se o arquivo fosse lido automaticamente durante o import, simplesmente importar a função já tentaria acessar:

```text
model_int8_esp32.tflite
```

Isso criaria um acoplamento desnecessário.

A implementação atual permite:

```text
importar módulo
      │
      ▼
nenhum arquivo aberto
      │
      ▼
chamar load_model()
      │
      ▼
arquivo efetivamente carregado
```

Essa separação facilita testes e reutilização.

---

# 35. Fluxo completo deste módulo

O comportamento pode ser resumido assim:

```text
MODEL_PATH
    │
    ▼
load_model()
    │
    ├── Path(model_path)
    │
    ├── read_bytes()
    │
    ▼
   buf
    │
    ├── TFLModel.GetRootAsModel?
    │          │
    │          └── sim → parse
    │
    └── TFLModel.Model.GetRootAsModel?
               │
               └── sim → parse
                      │
                      ▼
                    model
                      │
                      ▼
              get_subgraph()
                      │
                      ▼
                 SubGraph 0
```

---

# 36. Relação com o `main.py`

No fluxo principal, a utilização esperada é simples:

```python
model = load_model(
    MODEL_PATH
)

subgraph = get_subgraph(
    model
)
```

Depois disso:

```text
MODEL_PATH
    ↓
model
    ↓
subgraph
```

e o extrator pode iniciar a análise estrutural.

O `main.py` continua responsável pela orquestração, enquanto `model_loader.py` apenas implementa a tarefa específica.

---

# 37. Por que retornar objetos em vez de estruturas próprias?

Neste estágio não há motivo para copiar todo o modelo para uma estrutura Python intermediária.

Por exemplo, não fazemos:

```python
model_data = {
    "operators": ...,
    "tensors": ...,
    "buffers": ...
}
```

A estrutura original já pode ser navegada pelo binding.

Os módulos especializados extraem apenas aquilo de que realmente necessitam.

Isso evita uma transformação intermediária completa e desnecessária.

---

# 38. Responsabilidade arquitetural

A função desse módulo pode ser representada em três camadas:

```text
Sistema de arquivos
      │
      ▼
model_loader.py
      │
      ▼
Binding TFLite
      │
      ▼
Módulos de extração
```

Ele funciona como uma pequena fronteira entre:

```text
representação persistente
```

e:

```text
representação navegável
```

Ou seja:

```text
arquivo binário no disco
           ↓
         bytes
           ↓
      objeto Model
```

---

# 39. Por que isso é importante para o projeto?

O objetivo do projeto não é executar diretamente o modelo através de um runtime TensorFlow Lite.

O modelo TFLite funciona como fonte estruturada de informações necessárias para construir outra representação de execução.

Assim, o fluxo geral não é:

```text
TFLite
  ↓
TFLite Interpreter
  ↓
inferência
```

O fluxo do extrator é:

```text
TFLite
  ↓
leitura estrutural
  ↓
extração dos parâmetros
  ↓
serialização própria
  ↓
WAT
  ↓
WASM
  ↓
runtime WebAssembly
```

Dentro desse processo, `model_loader.py` implementa a primeira ponte.

---

# 40. Relação com a independência posterior do TFLite

Durante a fase de extração, o pipeline depende da estrutura TFLite.

Entretanto, o artefato WAT/WASM final não precisa consultar o arquivo TFLite durante cada inferência.

A transformação conceitual é:

```text
                 FASE DE CONSTRUÇÃO

model.tflite
    │
    ▼
model_loader
    │
    ▼
extrator
    │
    ▼
pesos + parâmetros + código
    │
    ▼
model.wat
    │
    ▼
model.wasm


                 FASE DE EXECUÇÃO

imagem
  │
  ▼
model.wasm
  │
  ▼
inferência
```

Assim, o TFLite participa da construção do artefato, mas não precisa permanecer como runtime de inferência do módulo produzido.

Essa separação é central para a arquitetura deste projeto.

---

# 41. Tratamento atual de múltiplos subgrafos

Embora:

```python
get_subgraph(
    model,
    index=0
)
```

permita informar outro índice, o restante do pipeline foi desenvolvido considerando o subgrafo selecionado como a rede que será integralmente processada.

Portanto, o suporte a modelos que dependam de múltiplos subgrafos inter-relacionados não deve ser presumido apenas porque a função aceita:

```python
index
```

A função permite selecionar um subgrafo.

Isso não significa que o pipeline implemente automaticamente semântica de execução envolvendo vários subgrafos.

Essa distinção é importante.

---

# 42. Validações que ainda não existem

O código atual é propositalmente simples.

Ele não verifica explicitamente:

```text
se model_path possui extensão .tflite
se o arquivo está vazio
se existe pelo menos um subgrafo
se index está dentro do intervalo
se o subgrafo possui operadores
se o subgrafo possui entrada
se o subgrafo possui saída
```

Algumas dessas situações naturalmente causariam erros posteriores.

Caso o extrator futuramente seja utilizado como backend de uma interface gráfica, poderá ser interessante transformar essas condições em validações mais amigáveis.

Por exemplo:

```text
arquivo enviado
    ↓
validação
    ├── modelo válido?
    ├── possui subgrafo?
    ├── operadores suportados?
    └── quantização compatível?
```

Mas isso pertence a uma camada futura de robustez da aplicação.

Não é necessário adicionar complexidade agora apenas para a execução local atual.

---

# 43. Possível evolução futura

Quando o extrator for transformado em backend, a função poderá receber um arquivo selecionado pelo usuário.

O fluxo poderia tornar-se:

```text
Angular
   │
   │ upload .tflite
   ▼
Backend Python
   │
   ▼
load_model()
   │
   ▼
validação
   │
   ▼
extração
   │
   ▼
WAT/WASM
```

A vantagem da implementação atual é que:

```python
load_model(model_path)
```

já não depende diretamente de uma constante global.

Hoje o `main.py` fornece:

```python
MODEL_PATH
```

Amanhã o backend poderá fornecer:

```python
uploaded_model_path
```

sem modificar a função de carregamento.

---

# 44. Decisão de projeto: passagem explícita do caminho

Observe a diferença entre:

```python
def load_model():
    buf = MODEL_PATH.read_bytes()
```

e a implementação escolhida:

```python
def load_model(model_path):
    buf = Path(model_path).read_bytes()
```

A segunda é melhor desacoplada.

`config.py` decide:

```text
qual arquivo usar
```

enquanto:

```text
model_loader.py
```

decide:

```text
como carregar um arquivo TFLite
```

Isso segue a separação:

```text
configuração
     ≠
implementação
```

---

# 45. Resumo das funções

| Função           | Entrada              | Saída      | Responsabilidade                              |
| ---------------- | -------------------- | ---------- | --------------------------------------------- |
| `load_model()`   | Caminho do `.tflite` | `Model`    | Ler o arquivo e criar o objeto raiz TFLite    |
| `get_subgraph()` | `Model` e índice     | `SubGraph` | Selecionar o subgrafo utilizado pelo extrator |

---

# 46. Resumo do módulo

O `model_loader.py` implementa uma etapa simples, porém essencial:

```text
ARQUIVO
   │
   ▼
BYTES
   │
   ▼
MODEL
   │
   ▼
SUBGRAPH
```

Sua principal característica arquitetural é não misturar carregamento com interpretação.

Ele não precisa saber:

```text
o que é uma convolução;
como os pesos serão serializados;
quantos slots existirão;
onde os dados ficarão na memória;
como o WAT executará a rede.
```

Ele precisa saber apenas:

```text
como transformar o arquivo TFLite
em uma estrutura que os próximos módulos consigam navegar.
```

A partir daí, a responsabilidade passa para os módulos especializados.

O fluxo até este ponto do projeto fica:

```text
┌───────────────────────────────┐
│          config.py            │
│                               │
│ MODEL_PATH                    │
│ NUM_SLOTS                     │
│ ALIGN                         │
│ ...                           │
└───────────────┬───────────────┘
                │
                │ MODEL_PATH
                ▼
┌───────────────────────────────┐
│       model_loader.py         │
│                               │
│ load_model()                  │
│ get_subgraph()                │
└───────────────┬───────────────┘
                │
                │ Model + SubGraph
                ▼
┌───────────────────────────────┐
│       extração estrutural     │
│                               │
│ graph.py                      │
│ tflite_utils.py               │
│ weights.py                    │
│ quantization.py               │
│ ...                           │
└───────────────────────────────┘
```

O arquivo é pequeno porque sua responsabilidade também é pequena e bem definida. Isso é desejável: o restante da complexidade do extrator fica dividido entre módulos que possuem conhecimento específico sobre grafo, tensors, quantização, memória e serialização.
