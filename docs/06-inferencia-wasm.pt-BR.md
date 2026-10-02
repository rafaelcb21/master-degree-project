[English](06-inferencia-wasm.md) | [Português (Brasil)](06-inferencia-wasm.pt-BR.md)

# 06 — Host de inferência Wasmtime

[Índice](README.pt-BR.md) · Fonte: [inference/wasm_inference.py](../inference/wasm_inference.py)

## Responsabilidade e dependências

O módulo é a ponte entre bytes Python e memória linear WebAssembly. Depende de `pathlib`, `math`, classes Wasmtime, constantes de formato em `layer_params` e helpers de tensores. Não existe mais `extractor/wasm_inference.py`. A pasta `inference/` não contém `__init__.py`; é importável como namespace package na execução pela raiz.

## _instantiate_wasm(wasm_path)

Converte o caminho em `Path`, exige arquivo existente, lê bytes, cria `Store()`, compila `Module(store.engine, wasm_bytes)` e resolve imports na ordem declarada. Admite somente funções `env.log`, `env.logf` e `env.log64`, com callbacks `lambda *args: None`. Qualquer outro import levanta `RuntimeError`. O callback pressupõe assinatura compatível com retorno `None`; não implementa retornos numéricos arbitrários.

Cria `Instance`, consulta exports e exige `memory`, `run_mobilenetv2` e `get_result_ptr`. Verifica que `memory` é `wasmtime.Memory`; não valida antecipadamente as assinaturas das duas funções. Retorna um dict com `store`, `instance`, `memory`, `run`, `get_result_ptr`. Erros de validação binária, instanciação e assinatura podem vir de Wasmtime.

## tensor_info(tensor)

Aceita tipo TFLite 3 (UINT8) ou 9 (INT8); outros tipos causam `ValueError`. Obtém escala e zero point pelos helpers escalares. Rejeita `scale <= 0`, mas não testa `isfinite`. Retorna `shape`, `elements=math.prod(shape)`, `scale`, `zero_point`, `dtype`. Como os helpers têm defaults, quantização ausente pode aparecer como scale 1 e zp 0; o método não comprova que o tensor possui quantização explícita. Não valida dimensões positivas, canais ou batch: parte dessas verificações fica no pipeline.

## run_wasm_inference: parâmetros

Todos são keyword-only: `wasm_path`, `adapter`, `cases`, `input_info`, `output_info`, `input_ptr`, `slot_bytes`. `cases` deve permitir iteração e `len`, como a lista criada pelo pipeline. A instância é criada uma única vez para todos os casos.

Entrada esperada:

```text
synthetic_layer_count = 1          synthetic_layer_count = 0
input_info.elements / 3 × 2        input_info.elements
           │                                  │
           ▼                                  ▼
      bytes RGB565                     bytes RGB888/INT8
           └────────────────┬─────────────────┘
                            ▼
            expected <= slot_bytes e fim <= memória
```

Entram a geometria do modelo e o modo sintético; o runner calcula quantos bytes deve escrever. Sai o comprimento aceito. As dimensões são do modelo; a regra 2 ou 3 bytes por pixel pertence aos formatos de imagem atualmente suportados. A divisão inteira `//3` pressupõe a validação prévia de três canais.

## Ciclo por caso

```text
                  instância única
                        │
TestCase ──► adapter.prepare_input
                        │ valida len(data)
                        ▼
         memory.write(data, input_ptr)
                        │
         com sintética: memory[0] = 65
                        ▼
              run_mobilenetv2(store)
                        │ retorno ignorado
                        ▼
               get_result_ptr(store)
                        │ valida [ptr, ptr+elements)
                        ▼
                 memory.read → bytes
                        ▼
              adapter.evaluate_output
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        records.append       errors.append
                             file + str(exc)
```

Entram os bytes preparados; o runner escreve na memória, chama o runtime e lê uma saída de 8 bits. Saem registros do adapter ou erros por arquivo. O endereço do slot é calculado pelo extrator; o protocolo dos exports é comum. Labels e ranking não entram no host.

Antes dos casos, valida `expected <= slot_bytes`, `input_ptr >= 0` e fim da entrada dentro da memória. Em cada caso verifica tamanho exato e faixa da saída. Não limpa os slots entre imagens, não reinstancia após exceção e não verifica que a saída está em uma região de slot específica: basta estar dentro da memória. O grafo deve sobrescrever os dados que lê a cada execução. Um erro de kernel que deixe memória parcialmente escrita pode influenciar casos seguintes; não há isolamento por caso.

O `try` por caso captura `Exception` de leitura, preparação, execução e avaliação. O erro da própria instanciação ocorre antes desse bloco e interrompe tudo. Não captura `KeyboardInterrupt`. A cada 100 casos tentados imprime progresso, incluindo os que falharam. Retorna `records`, `errors` e `processed=len(records)`, não acurácia.

## Formato e sincronização

O marcador de formato é o byte 65 no endereço 0 quando há sintética. O WAT possui outra flag em endereço 4, usada por `is_ready_for_image` e por `run_mobilenetv2`; o host síncrono não a consulta. Não confunda essas flags com os bits de dtype dentro de uma LayerParam. Não há threads, fila de imagens, timeout ou limite de combustível configurado.

## Limites de generalização

O arquivo é genérico quanto ao adapter, mas ainda exige nome de export `run_mobilenetv2`, saída de um byte por elemento e protocolo de imagem. O código não usa `get_top_class`, `get_top5` nem `get_result_count`; o ranking é Python e a contagem vem do TFLite/gerador. O resultado não é comparado automaticamente com TensorFlow Lite.
