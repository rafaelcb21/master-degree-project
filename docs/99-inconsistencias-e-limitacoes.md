# 99 — Inconsistências, limitações e informações não determinadas

[Índice](README.md) · Revisão do estado local em 28/09/2026.

## Método e alcance

Os itens abaixo resultam da leitura do código, manifests, templates, testes e artefatos existentes. A tarefa alterou documentação, não kernels ou regras funcionais. “Recomendação” descreve possível evolução, não uma capacidade implementada. Um risco identificado por inspeção não significa que os modelos atuais tenham disparado todos esses casos.

## Comportamento atual e divergências verificadas

| ID | Arquivo / conceito | Comportamento atual | Divergência ou limitação | Recomendação |
|---|---|---|---|---|
| 01 | `wat/templates/model_template.wat`, QUANTIZE | Template legado usa `layer_idx==67` para escolher UINT8 | Não segue as flags de saída atuais; nenhum manifest o seleciona | Usar os templates ativos; remover/deprecar o legado em tarefa funcional separada |
| 02 | Templates ativos, SOFTMAX | Multiplica diferenças de logits por 7877, shift 16, tabela Q15 e fator 256 | Python calcula parâmetros por modelo que o kernel não usa; comentários sugerem scale fixa 0.12 | Implementar uso dos parâmetros e comparar numericamente com referência |
| 03 | Templates ativos, `FLAG_BASE` | Constante tem valor 4 | Comentário diz endereço 0; host escreve marcador de formato em 0 | Distinguir formato em 0 de busy em 4; corrigir comentário em revisão apropriada |
| 04 | `layer_params.py` e kernel depthwise | Python registra depth_mult; WAT usa canal oc diretamente na entrada | depth_mult não está nos 29 campos e valor >1 não é corretamente generalizado | Rejeitar casos não suportados ou implementar correspondência de canais |
| 05 | `operator_options.py`, ADD/FC | Ativação é extraída e registrada | Kernels ADD/FC não aplicam act | Implementar ou rejeitar ativação diferente de NONE nesses kernels |
| 06 | MEAN builder/runtime | Média espacial H×W por canal | Não lê axis/keep_dims; usa divisão truncada | Declarar/restringir o caso suportado e validar arredondamento |
| 07 | `_build_softmax_params` | Beta fixo 1 e parâmetros derivados | Não lê beta real de SoftmaxOptions | Validar beta do modelo ou implementá-lo |
| 08 | `build_layer_params` | Tipos desconhecidos e operadores sem output podem ser pulados | Não há falha global obrigatória por opcode incompatível | Adicionar validação de cobertura completa antes da geração |
| 09 | `graph.py` versus `layer_params.py` | Slots usam ordem topológica; camadas serializadas usam ordem original | As ordens não são explicitamente comparadas | Validar invariantes de ordenação/identidade dos outputs |
| 10 | `slots.py`, QUANTIZE | Usa mesmo slot e executa continue | Não atualiza contagem de leitores nesse ramo | Testar liveness em ramificações com QUANTIZE intermediário |
| 11 | `tensor_mapping.py` | Propaga primeiro slot encontrado por produtor; múltiplos outputs recebem mesmo slot | Não demonstra equivalência semântica do alias | Restringir aliases válidos e validar grafos com múltiplas saídas |
| 12 | Mapa lógico versus runtime | Runtime reconstrói somente inputs/outputs de alocação | Resoluções recursivas do mapa lógico não são reaproveitadas | Verificar consistência dos dois mapas em modelos novos |
| 13 | Pesos/bias e builders | Ausências podem ser puladas; w_off default 0; ponteiros ausentes 0 | Alguns kernels fazem load de bias/quantização sem checar zero | Falhar cedo para parâmetros obrigatórios ausentes |
| 14 | Quantização por canal | Usa primeiro scale de I/O e completa scales de pesos repetindo a última | qdim é relatado, mas não controla genericamente o eixo de quantização | Validar número/eixo de escalas |
| 15 | `operator_options.py` | Captura exceções e usa defaults | Opções incompatíveis podem virar stride 1/VALID/NONE silenciosamente | Distinguir opção ausente de falha de parsing |
| 16 | `tflite_utils.py` | Scale ausente→1; zp ausente→0; reshape malsucedido é ignorado | Valores neutros não comprovam validade do tensor | Validar schema/shape/quantização nos consumidores |
| 17 | `ModelConfig` | Validação parcial; campos desconhecidos ignorados | Tipos anotados não são impostos; num_slots=3.0 e top_k=true são casos problemáticos | Introduzir validação explícita de tipos |
| 18 | `ModelPackage.resolve` | Permite `..` e paths absolutos | README anterior dizia todos os paths relativos como regra absoluta | Documentação atual distingue convenção de restrição |
| 19 | `main.py` | Captura OSError, ValueError, RuntimeError | Nem todo erro vira mensagem sem traceback | Documentar classes que propagam; melhorar fronteira de erros se necessário |
| 20 | Runner | Uma instância por lote, memória não limpa, continua após erro por caso | Trap pode deixar estado parcial; não há isolamento ou timeout | Testar falha seguida de inferência e definir política de reinicialização |
| 21 | WAT ranking | get_top_class/get_top5 leem INT8 | Saídas dos dois TFLite atuais são UINT8 | Manter ranking no adapter; generalizar exports se usados externamente |
| 22 | Helpers WAT duplicados | Variantes `_2`, `_3` e exportadas têm diferenças | Função exportada sem sufixo não faz o mesmo left shift de `_3` | Consolidar ou documentar ABI numérico de cada helper |
| 23 | Runtime e host | Nome obrigatório `run_mobilenetv2`, imagens NHWC RGB e I/O 8 bits | Parte da infraestrutura ainda é específica deste domínio | Separar contrato de execução ao suportar áudio/outros formatos |
| 24 | ImageNet INT8 | Normaliza pixel/127.5−1 antes de quantizar | Não é pré-processamento configurável para qualquer rede | Tornar a normalização explícita em futura configuração |
| 25 | Template compartilhado/local | Dois arquivos ativos têm o mesmo conteúdo | Não há vínculo de sincronização; podem divergir | Versionar e testar cada template selecionado |
| 26 | Pacote drowsiness | Template fica fora de sua pasta | Não é autocontido para distribuição isolada | Incluir template compartilhado ou usar cópia local ao distribuir |
| 27 | `README.md` anterior | Citava `test/incompatible/a0397.raw` | Caminho não existe no estado atual; destino não pode ser determinado | Referência operacional removida; nenhum arquivo de dados foi criado para sustentá-la |
| 28 | `img_mobilenetv2/aviao_uint8.raw` | Existe cópia externa ao pacote | Manifest só lê o arquivo em models/.../test/img | Documentar a cópia como não usada pela execução atual |
| 29 | Docs antigos | Contêm centenas de exemplos sobre extrator e arquitetura anterior | main.py orquestrador, globals de paths e sintética obrigatória ficaram obsoletos | Corpos preservados em historico; capítulos atuais 00–33 são a referência |
| 30 | `inference/wasm_inference.py` | Imports de constantes repetidos; string descritiva no meio do arquivo | Essa string não é docstring do módulo | Limpeza editorial em tarefa separada, sem efeito funcional necessário aqui |
| 31 | Artefatos/reports | Escrita incremental e sobrescrita direta | Execução interrompida pode misturar versões; sem timestamps/checksums | Conferir código de saída; considerar metadados e escrita atômica |
| 32 | `wat_generator.py` | Saída vem da última LayerParam; regex verifica tokens remanescentes | Não garante identidade do tensor final nem presença de todos os placeholders | Validar identidade e interface do template |
| 33 | `memory.py` | Alinhamento por bitmask; dimensionamento com defaults para negativos | Sem checagem de potência de dois/overlap/shapes dinâmicos completos | Validar invariantes do layout |
| 34 | `setup_env.ps1` | Reutiliza .venv existente e chama python/pip | Não valida se o interpretador da venv ainda existe; ambiente local antigo está quebrado | Criar ambiente válido explicitamente; não tratar sucesso impresso como teste de execução |
| 35 | Testes atuais | Sete testes direcionados | Não há equivalência completa TFLite/WASM nem cobertura de todos os kernels | Adicionar referência diferencial por operador/tensor |
| 36 | Histórico de flags | Texto antigo “flags 0 uint8, 1 int8” era incompleto | Código atual já descreve bits de entrada e saída; relatórios antigos podem conservar o texto anterior | Regenerar relatórios numa execução funcional quando necessário; esta tarefa não os altera |

## Limites que o código rejeita explicitamente

O manifest aceita somente `layerparam-v1`, três slots e os três pares formato/camada documentados. O pipeline exige uma entrada/saída, dtype de I/O UINT8 ou INT8, shape de entrada rank 4, batch 1, canais 3, e entrada UINT8 para sintética RGB565. O runner exige tamanho exato do RAW e acesso dentro da memória. Adapters rejeitam pastas sem casos; ImageNet rejeita labels estruturalmente inválidos e binário exige duas classes.

## Informações que não podem ser determinadas aqui

Não estão documentadas de forma recuperável no fluxo atual a procedência completa de treinamento, origem/licenças de todos os RAWs, divisão treino/teste, cadeia de conversão dos modelos, configuração original do Colab, calibração de probabilidades ou desempenho em hardware ESP32. Os nomes dos arquivos e comentários não bastam como evidência. O objetivo indicado pelos manifests pode ser descrito, mas não esses detalhes ausentes.

## Possíveis evoluções

A prioridade técnica sugerida é validação de cobertura de operadores e comparação numérica por camada, seguida da remoção de constantes de softmax e de validação rigorosa de opções/dtypes. Depois podem ser generalizados formatos, número de entradas/saídas e contratos. Essas são propostas documentadas; a tarefa não as implementou nem alterou resultados existentes.
