# Host ESP32 para benchmarks WASM/AOT

Este projeto e independente do Python. O host baixa arquivos RAW do
Cloudinary, copia a entrada para a memoria do modulo, executa a inferencia
e registra os resultados e as medicoes.

## Arquivos para editar

- `main/host_config.h`: Wi-Fi, dimensoes e tamanho da entrada, flag de formato,
  exports WASM, handshake, tipo e quantidade de saidas, rotulos, timeouts,
  tamanhos de pilha e endereco HTTP do relatorio.
- `main/image_list.h`: uma lista de URLs Cloudinary e rotulos, na ordem de
  execucao. As 2.000 entradas anteriores foram preservadas. Use `-1` como
  rotulo quando quiser apenas executar e medir, sem avaliar acuracia.

As credenciais Wi-Fi sao placeholders: preencha-as em `host_config.h`.
Alteracoes nesses arquivos exigem recompilar e gravar o firmware.

Exemplo de entrada na lista:

```c
{ "https://res.cloudinary.com/SEU_CLOUD/raw/upload/imagem.raw", 0 },
```

`CLASS_LABELS` mapeia a ordem do tensor de saida para os rotulos da lista.
O valor inicial `{ 1, 0 }` preserva a associacao do modelo anterior.
Para um modelo com tres classes rotuladas de 0 a 2, use `NUM_CLASSES 3`
e `CLASS_LABELS { 0, 1, 2 }`.

## Contrato do modulo

O host suporta modulos que respeitem esta interface; os nomes dos exports
sao configuraveis, mas suas assinaturas devem ser `() -> i32`:

| Configuracao | Retorno esperado |
|---|---|
| `WASM_READY_EXPORT` | 1 quando pode receber uma imagem; 0 quando ocupado |
| `WASM_INPUT_PTR_EXPORT` | Offset do buffer de entrada |
| `WASM_RUN_EXPORT` | `INFERENCE_SUCCESS_CODE` quando termina com sucesso |
| `WASM_OUTPUT_PTR_EXPORT` | Offset do tensor de saida contiguo |

Os nomes iniciais preservam os exports dos modulos existentes, incluindo
`run_mobilenetv2`. Esse nome nao determina o modelo executado pelo host.
`USE_READY_HANDSHAKE 0` permite modulos sem o export de prontidao.
A execucao e sequencial e sincrona. Timeout ou erro aborta aquela imagem.
Uma falha interna pode deixar o modulo indisponivel para as proximas imagens;
o host nao limpa a flag nem forca uma recuperacao do estado do modelo.

O RAW deve conter exatamente `INPUT_BYTES` bytes, na ordem e codificacao
esperadas pelo modulo. O host nao redimensiona, normaliza nem troca canais.
O valor inicial usa 128 x 128 pixels RGB565 (32.768 bytes).
Para RGB888/BGR888, ajuste `INPUT_BYTES_PER_PIXEL` para 3 e configure
`WRITE_FORMAT_FLAG` conforme o contrato do modulo. Desative essa escrita
quando o modulo nao usar a flag de formato.

A saida pode ser `OUTPUT_UINT8`, `OUTPUT_INT8` ou `OUTPUT_FLOAT32`.
`NUM_CLASSES` deve corresponder ao numero de elementos da saida. O host
valida os limites da memoria linear, mas nao consegue deduzir a capacidade
dos tensores: tamanhos e formato precisam corresponder ao modulo.
O resultado e o rotulo do maior elemento; empate produz `-1`.
Para saidas quantizadas, essa comparacao pressupoe escala positiva e
zero point comuns as classes. Os valores brutos nao sao convertidos em
porcentagens. Modelos com varias saidas, deteccao ou outro pos-processamento
precisam de adaptacao desse contrato.

## Modulo incorporado

Coloque `main.aot` ou `main.wasm` em `main/`. A regra existente do CMake
continua priorizando `main.aot` quando presente; para usar o interpretado,
retire esse AOT da pasta antes de reconfigurar/compilar o projeto.
O host nao gera esses arquivos. O AOT deve corresponder ao alvo e ao WAMR
usados no firmware.

## Medicoes e CSV

Depois do benchmark, o servidor disponibiliza o CSV em
`http://<ip-do-esp32>:80/report` (porta e caminho configuraveis).
Ele inicia depois da coleta para servir um relatorio completo e imutavel.

Cada imagem gera `ok`, `class_0_raw` ate `class_N_raw`, resultado, rotulo,
acerto, tempo de download, tempo de inferencia, heap e PSRAM antes/depois,
diferencas de memoria e menor espaco livre observado na pilha da tarefa.
`right=-1` significa sem avaliacao (falha ou rotulo desconhecido).
Em falhas, as saidas ficam vazias; medicoes nao realizadas ficam em zero.
As medias de tempo e a acuracia consideram apenas imagens processadas com
sucesso; a acuracia exclui imagens sem rotulo. Empates contam como erro de
classificacao para imagens rotuladas.

O tempo de inferencia mede a chamada ao export, incluindo lookup e entrada
no WAMR; download e copia de entrada ficam fora dessa janela. As diferencas
de heap/PSRAM nao representam o pico de memoria durante uma inferencia.
Os minimos historicos do resumo incluem outras tarefas e a inicializacao.

O CSV acumulado fica na PSRAM; muitas imagens/classes podem esgotar esse
espaco. Nesse caso o host registra a falha e o endpoint retorna erro HTTP,
sem apresentar o CSV parcial como completo. Ha apenas um buffer de imagem
e uma estrutura de resultado reutilizados durante o benchmark.
