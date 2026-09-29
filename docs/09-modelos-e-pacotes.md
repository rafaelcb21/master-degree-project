# 09 — Modelos e pacotes presentes

[Índice](README.md) · [Sonolência](../models/drowsiness/README.md) · [ImageNet](../models/mobilenetv2_alpha035/README.md)

## Comparação extraída dos arquivos

| Característica | drowsiness | mobilenetv2_alpha035 |
|---|---|---|
| Nome no manifest | Drowsiness MobileNetV2 | MobileNetV2 Alpha 0.35 ImageNet |
| Arquivo original | `model_int8_esp32.tflite` | `mobilenetv2_alpha035_quant.tflite` |
| Bytes do TFLite | 618376 | 1925904 |
| Subgrafos/tensores | 1 / 175 | 1 / 175 |
| Entrada | `[1,128,128,3]` UINT8 | `[1,224,224,3]` UINT8 |
| Scale / zero point de entrada | 0.003921508323401213 / 0 | 0.007843137718737125 / 127 |
| Saída | `[1,2]` UINT8 | `[1,1000]` UINT8 |
| Scale / zero point de saída | 0.00390625 / 0 | 0.00390625 / 0 |
| RAW do host | RGB565 little-endian, 32768 bytes | BGR888, 150528 bytes |
| Sintética / shift | RGB565_TO_RGB888 / 1 | nenhuma / 0 |
| Adapter | binary-folders | imagenet-topk |
| Casos encontrados | 1000 + 1000 | 1 |
| Camadas TFLite / runtime | 67 / 68 | 67 / 67 |
| Páginas WASM nos relatórios | 17 | 56 |

Os dois modelos têm 35 CONV_2D, 17 DEPTHWISE_CONV_2D, 10 ADD, 2 QUANTIZE, 1 MEAN, 1 FULLY_CONNECTED e 1 SOFTMAX. O nome `int8` no arquivo ou template não define o dtype de I/O: os dois FlatBuffers expõem UINT8, com operações internas quantizadas e QUANTIZE nas extremidades.

## Variantes de entrada

```text
COM SINTÉTICA — drowsiness           SEM SINTÉTICA — ImageNet

arquivo RAW RGB565                  arquivo RAW BGR888
        │                                   │
        ▼                                   ▼
BinaryFoldersAdapter                ImageNetTopKAdapter
        │ lê bytes                           │ BGR → RGB
        ▼                                   ▼
      SLOT0                                SLOT0
        │                                   │
        ▼                                   │
┌────────────────────────┐                  │
│ camada SINTÉTICA       │                  │
│ RGB565_TO_RGB888       │                  │
└───────────┬────────────┘                  │
            ▼                              │
          SLOT1                            │
            │                              │
            ▼                              ▼
 primeira operação REAL             primeira operação REAL
 do TFLite: QUANTIZE                do TFLite: QUANTIZE
```

Entram formatos host diferentes. No primeiro, o adapter apenas lê e o WAT expande RGB565 para RGB888; no segundo, Python inverte B/R e escreve RGB diretamente. Sai a entrada lógica para a primeira operação real. O formato é específico do pacote; o runner e os slots obedecem ao protocolo compartilhado. A sintética não pertence ao grafo TFLite original.

## O que os resultados permitem concluir

O relatório de sonolência contém 2000 registros, 1965 acertos, cinco inválidos/empates e acurácia 98,25%, sem erros. O relatório ImageNet traz `airliner`, índice 404, q=226 e score=0,8828125 em primeiro lugar para o único RAW atual. São resultados de execução do runtime existente. Não há no conjunto de testes uma comparação completa contra TensorFlow Lite nem prova de acurácia fora desses dados.

Os manifests e nomes indicam os objetivos das redes; o repositório não fornece neste fluxo a procedência completa de treinamento, divisão treino/validação, licenças dos datasets, hiperparâmetros ou checkpoint de origem. Não é possível reconstruir esses fatos apenas a partir dos nomes dos arquivos. Não se deve inferir segurança de uso em monitoramento real de motoristas.

## Fontes compartilhadas e autonomia do pacote

Sonolência depende de um template fora de sua pasta. ImageNet aponta para uma cópia local cujo hash coincide com o template ativo compartilhado na inspeção atual. Os arquivos podem divergir no futuro; não existe sincronização automática. A cópia `img_mobilenetv2/aviao_uint8.raw` fora do pacote não participa da execução configurada.

O README anterior citava `test/incompatible/a0397.raw`; essa pasta/arquivo não foi encontrada na árvore atual. A referência foi retirada da documentação operacional e registrada no capítulo 99. Não é possível afirmar o destino desse arquivo a partir do estado atual.
