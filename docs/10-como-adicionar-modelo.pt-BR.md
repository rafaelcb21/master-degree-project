[English](10-como-adicionar-modelo.md) | [Português (Brasil)](10-como-adicionar-modelo.pt-BR.md)

# 10 — Tutorial: cadastrar um terceiro modelo

[Índice](README.pt-BR.md) · [Manifesto completo](03-model-config-manifesto.pt-BR.md) · [Contrato](08-contrato-layerparam-v1.pt-BR.md)

## Antes de copiar arquivos

Verifique o TFLite real: uma entrada, uma saída, entrada NHWC `[1,H,W,3]`, I/O UINT8 ou INT8, escalas válidas e operadores implementados pelo runtime. Conferir apenas a extensão ou o nome MobileNet não basta. O construtor pode pular operadores desconhecidos; por isso a auditoria de opcodes é uma condição para confiar no resultado.

Um comando de inspeção reproduzível, executado após criar o manifest:

```python
from pipeline.model_package import ModelPackage
from extractor.model_loader import load_model, get_subgraph
from extractor.tflite_utils import op_name
from inference.wasm_inference import tensor_info

package = ModelPackage.load("novo_modelo")
model = load_model(package.resolve(package.config.tflite))
subgraph = get_subgraph(model, index=0)
print("inputs/outputs:", subgraph.InputsLength(), subgraph.OutputsLength())
print(tensor_info(subgraph.Tensors(subgraph.Inputs(0))))
print(tensor_info(subgraph.Tensors(subgraph.Outputs(0))))
print([op_name(model, subgraph.Operators(i))
       for i in range(subgraph.OperatorsLength())])
```

Esse código inspeciona, não compila nem atesta equivalência de kernels. Shapes dinâmicos, layouts alternativos e normalizações incompatíveis exigem análise adicional.

## Passo a passo

1. Crie `models/novo_modelo/`. O nome da pasta é o valor de `--model`; não é necessário editar a CLI.
2. Coloque o TFLite original nessa pasta. O nome pode ser `model.tflite` ou outro informado em `model.tflite`. O pipeline não o converte nem renomeia.
3. Escolha o template ativo `../../wat/templates/mobilenet_int8_v1.wat`, ou copie-o para `wat/model_template.wat` e aponte o manifest. Evite o template legado `wat/templates/model_template.wat` da raiz.
4. Declare `contract="layerparam-v1"` e `num_slots=3`. Um contrato novo exige implementação Python/WAT nova; não basta renomeá-lo.
5. Determine o formato dos bytes host. RGB565 requer 2×H×W bytes; RGB/BGR888 requer 3×H×W. Não há cabeçalho nem conversão automática de PNG.
6. Para RGB565, use `synthetic_layer="rgb565_to_rgb888"` e entrada TFLite UINT8. Para RGB/BGR888, use `"none"`.
7. Selecione um adapter compatível. Binário usa RGB565 e exatamente duas classes; ImageNet usa labels por índice e RGB/BGR. Outros domínios exigem Strategy própria.
8. Crie pastas de teste não vazias. Discovery acontece antes da geração; não é possível usar a CLI atual para compilar um pacote sem testes válidos.
9. Configure labels/classes com a ordem real do tensor de saída. Para ImageNet, cada entrada JSON deve ter `[wnid, class_name]` e cobrir os índices. Para binário, configure datasets com labels presentes em `classes`.
10. Execute os comandos abaixo e confira o código de saída.
11. Inspecione relatórios intermediários e compare os resultados com uma referência numérica apropriada antes de generalizar o uso.

```powershell
python main.py --list-models
python main.py --model novo_modelo
python -m unittest discover -s tests -v
```

## Árvore a criar

```text
models/novo_modelo/
├── model.toml                  nomeia fontes, formato e adapter
├── model.tflite                fonte original
├── test/                       RAWs no formato documentado
├── labels/                     se o adapter exigir
├── wat/                        opcional: template local
├── generated/                  criado pelos escritores
│   ├── model.wat
│   └── model.wasm
└── reports/                    criado nas etapas de extração/teste
```

Entra um conjunto de fontes montado pelo autor do pacote. `ModelPackage` resolve caminhos e os escritores criam os destinos. Saem artefatos, sem alterar o TFLite. O conteúdo das fontes é específico; os nomes dos artefatos são fixos para todos os pacotes. `generated/` e `reports/` não precisam existir antes de executar.

## Decisão de compatibilidade

```text
                  novo TFLite
                       │
                       ▼
      I/O, operadores e normalização compatíveis?
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
         sim                       não
          │                         │
manifest + testes             identificar a fronteira
          │                         ├── adapter: formato/semântica
          ▼                         ├── extractor: operador/metadata
     executar                       ├── ABI: campos/exports
          │                         └── WAT: kernel/matemática
          ▼                         │
inspecionar reports           implementar e validar antes
          │                   de declarar suporte
          ▼
comparar com referência
```

Entram modelo e requisitos. A compatibilidade determina se cadastro basta ou se é necessário código. Sai um pacote executável ou uma lista concreta de extensões. `ModelPipeline` compartilha o fluxo, mas não torna genéricos kernels que ainda assumem INT8, depth multiplier 1, média espacial e softmax específico.

## Quando cadastro não basta

Novos opcodes, FLOAT32, múltiplas entradas/saídas, áudio, batch maior, mais de três slots, normalização INT8 diferente, ADD com broadcasting e MEAN em eixos arbitrários são exemplos que não estão cobertos pela configuração atual. Saída softmax com outra escala também exige atenção ao WAT, que usa constantes fixas. O contrato e os testes precisam acompanhar qualquer alteração numérica.

## Interpretar o primeiro resultado

02 revela dependências; 03 e 04 revelam armazenamento lógico; 05–06 mostram parâmetros extraídos; 07–08 dimensionam regiões; 09 detalha os kernels; 10 mostra ponteiros serializados; 11 fecha a memória; 12 apresenta casos e erros. Uma inferência sem trap não prova que a rede foi traduzida corretamente. Para depurar diferenças, compare intermediários por camada com um interpretador de referência; essa comparação ainda não é automatizada no projeto.
