[English](11-testes.md) | [Português (Brasil)](11-testes.pt-BR.md)

# 11 — Testes e alcance da validação

[Índice](README.pt-BR.md) · Fonte: [tests/test_model_packages.py](../tests/test_model_packages.py)

## Execução e organização

```powershell
python -m unittest discover -s tests -v
```

Há uma classe `ModelPackagesTests(unittest.TestCase)` com sete métodos. Depende de `tempfile`, `re`, `struct`, `Path`, `SimpleNamespace`, `unittest.mock.patch`, dos adapters e do extrator; um teste importa Wasmtime. Não requer pytest. `if __name__ == "__main__": unittest.main()` também permite execução direta, desde que o repositório esteja no caminho de importação.

| Método | Grupo | Intenção, execução e regressão protegida |
|---|---|---|
| `test_wasm_quantize_uses_output_type_at_any_layer_index` | ABI/QUANTIZE/dtypes | Lê o template ativo de drowsiness, substitui placeholders para um módulo de uma página, grava um WASM temporário e escreve manualmente 29 int32 na memória. Chama o export `quantize` no índice 0 com flags 3: entrada bytes `[128,0,127]` como INT8 deve virar UINT8 `[0,128,255]`. Depois usa flags 0 e converte UINT8 `[0,128,255]` para INT8 representado por bytes `[128,0,127]`. Evita voltar à dependência do índice fixo 67. |
| `test_paths_are_relative_to_package` | Paths/fontes | Carrega todos os pacotes, valida fontes, verifica que o WAT gerado fica em `root/generated` e difere do template. Protege convenção de destinos, mas não muda cwd nem testa confinamento de paths. |
| `test_unknown_contract_rejected` | Manifesto/ABI | Copia o manifest de sonolência para diretório temporário e troca v1 por v2; exige `ValueError` contendo “Contrato”. Evita aceitação silenciosa de versão não implementada. |
| `test_synthetic_layer_optional` | Sintética | Usa subgrafo sem operadores e mock de `build_rgb565_layer`. Com `none`, lista vazia e helper não chamado; com default, uma camada. Não executa o kernel RGB565. |
| `test_bgr_conversion_and_invalid_size` | Entrada | RAW temporário de um pixel `[10,20,30]`; exige bytes `[30,20,10]`. Depois exige erro quando metadados pedem seis elementos. Protege ordem de canais e tamanho. |
| `test_signed_output_and_stable_topk` | Saída/Top-K | Decodifica bytes `[128,255,127]` como `[-128,-1,127]`, verifica scores e ranking estável em empate. Fixtures de labels usam `[wnid,nome]`. Não compara o texto inteiro do relatório. |
| `test_binary_class_order_and_ties` | Classificação | Confirma acerto para `[200,55]` no label 1, invalidação de empate `[100,100]` e vetor zero. Protege ordem das classes e critério de invalidez. |

## O teste binário de ABI

```text
template WAT ativo
        │ placeholders mínimos
        ▼
wasmtime.wat2wasm ──► arquivo temporário
                              │
                              ▼
                       Store / Instance
                              │
struct.pack("<29i") ──► memory[1024:1140]
bytes de entrada ─────► memory[4096:4099]
                              │
                              ▼
                    export quantize(store, 0)
                              │
                              ▼
                    memory[8192:8195] → assert
```

Entram um template e parâmetros artificiais, não um TFLite. O teste exercita o kernel real e compara bytes. Sai uma assertiva sobre flags e quantização no índice 0. Os ponteiros e valores são dados do teste; layout de registro e assinatura do export são do runtime. A cobertura é mais forte que apenas testar uma função Python que monta flags, mas não cobre a rede inteira.

## Resultados e lacunas

Os sete testes foram executados durante esta revisão documental. O resultado detalhado está em [verificação](98-verificacao-documental.pt-BR.md). Os relatórios dos pacotes existentes fornecem evidência adicional, mas não são assertions desta suíte.

Não há testes atuais de equivalência completa TFLite/WASM, de todos os kernels isolados, de liveness em grafos arbitrários, de trap seguido de nova imagem, de JSON malformado, de broadcast ADD, de axis MEAN, de softmax com diferentes escalas ou de normalização INT8 do adapter. Não documente essas coberturas como existentes. Também não há testes de licença/proveniência ou avaliação estatística do dataset.

## Possíveis evoluções

Adicionar casos diferenciais contra uma referência TFLite, cobrindo tensores intermediários e arredondamento, permitiria distinguir regressão de integração de divergência numérica já presente. Ampliar casos para formatos inválidos e validação de manifests melhoraria mensagens de erro. Essas propostas não fazem parte da suíte atual e não foram implementadas nesta tarefa.
