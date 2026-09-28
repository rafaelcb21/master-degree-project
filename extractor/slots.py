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