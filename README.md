# Pacotes de modelo TFLite → WebAssembly

Requer Python 3.10+ e as dependências de `requirements.txt`.

```powershell
python -m pip install -r requirements.txt
python main.py --list-models
python main.py
python main.py --model drowsiness
python main.py --model mobilenetv2_alpha035
```

Nesta máquina, a validação usou `.venv-models/Scripts/python.exe`; o ambiente
`.venv` antigo aponta para uma instalação de Python ausente.

## Organização

Cada pasta em `models/` tem um `model.toml`, o TFLite original, testes e,
após a execução, `generated/model.wat`, `generated/model.wasm` e `reports/`.
Todos os caminhos do manifesto são relativos ao pacote, independentemente
do diretório em que o comando é executado. O TFLite e o template são fontes;
o pipeline escreve apenas os artefatos e relatórios.

`main.py` seleciona o `ModelPackage`; `ModelPipeline` compartilha extração,
memória, geração e compilação. O registry em `adapters/registry.py` seleciona
o adapter pelo campo `test.adapter`.

- `binary-folders`: RAW RGB565, datasets com labels e duas classes na ordem
  dos índices da saída. Relata acertos, empates e acurácia entre os casos processados.
- `imagenet-topk`: RAW BGR888/RGB888 com dimensões do tensor de entrada;
  converte BGR para RGB, interpreta a saída com tipo, escala e zero point
  do TFLite e ordena os scores. Empates usam a ordem dos índices.
  Para entrada INT8, aplica a normalização MobileNet `pixel / 127.5 - 1`
  antes de quantizar; entrada UINT8 recebe os pixels diretamente.

O pacote ImageNet usa o RAW de avião que estava em `img_mobilenetv2/`.
O arquivo `a0397.raw`, de 32.768 bytes, foi preservado em `test/incompatible/`:
não tem o tamanho necessário para a entrada 224×224×3 desse modelo.
Os labels foram obtidos de
https://storage.googleapis.com/download.tensorflow.org/data/imagenet_class_index.json.

## Adicionar um modelo

1. Crie `models/<nome>/model.toml`, usando um dos manifests como referência.
2. Defina `model.tflite` e `runtime.wat_template`. O template pode ser
   compartilhado (`../../wat/templates/mobilenet_int8_v1.wat`) ou local.
3. Configure o formato, a camada sintética e os testes.
4. Execute `python main.py --model <nome>`.

Um novo protocolo exige suporte no código: contratos diferentes de
`layerparam-v1` são rejeitados. Esse contrato usa 29 inteiros de 32 bits por
LayerParam (116 bytes), três slots e os exports `memory`, `run_mobilenetv2`
e `get_result_ptr`. O pipeline atual aceita uma entrada e uma saída de 8 bits
e as operações já suportadas pelo extrator; cadastrar um pacote não adiciona
novos operadores ao runtime.

Em `QUANTIZE`, o bit 0 de `flags` indica entrada INT8 e o bit 1 indica saída
UINT8. Os templates dos pacotes usam esses bits para carregar e limitar os
valores, sem depender de um índice fixo de camada. Templates personalizados
precisam respeitar essa convenção; o tamanho do LayerParam permanece 116 bytes.

`input.synthetic_layer = "rgb565_to_rgb888"` acrescenta uma camada e desloca
o mapeamento de slots em 1. Com `"none"`, ambos são zero.
Pastas ausentes, RAW inválido e falhas de inferência produzem erro;
falhas por caso ficam registradas em `12-inferencia-wasm.txt`.

Os documentos numerados em `docs/` detalham o extrator original. Para a seleção
de modelo e a configuração de caminhos, use os manifests e este README.

## Verificação

```powershell
python -m unittest discover -s tests -v
```
