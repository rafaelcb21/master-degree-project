(module
  (memory (export "memory") @@MEM_PAGES@@)

  (global $FLAG_BASE i32 (i32.const 4))  ;; 1 i32 = 4 bytes, endereço 0

  (func $get_flag_base (export "get_flag_base") (result i32)
    global.get $FLAG_BASE
  )

  ;; host/JS consulta o estado
  (func $is_ready_for_image (export "is_ready_for_image") (result i32)
    global.get $FLAG_BASE
    i32.load
    i32.const 0
    i32.eq   ;; retorna 1 se flag == 0 (pronto pra receber imagem)
  )


  ;; --- BASES (no overlap) ---
  (global $PARAMS_BASE i32 (i32.const @@PARAMS_BASE@@))
  (global $LP_SIZE i32 (i32.const @@LP_SIZE@@))
  (global $NUM_LAYERS i32 (i32.const @@NUM_LAYERS@@))

  (global $WEIGHTS_BASE i32 (i32.const @@WEIGHTS_BASE@@))
  (global $BIAS_BASE i32 (i32.const @@BIAS_BASE@@))
  (global $MUL_BASE i32 (i32.const @@MUL_BASE@@))
  (global $SHIFT_BASE i32 (i32.const @@SHIFT_BASE@@))
  (global $Q6_BASE i32 (i32.const @@Q6_BASE@@))

  (global $SLOT0_BASE i32 (i32.const @@SLOT0_BASE@@))
  (global $SLOT1_BASE i32 (i32.const @@SLOT1_BASE@@))
  (global $SLOT2_BASE i32 (i32.const @@SLOT2_BASE@@))

  (func $get_weights_base (export "get_weights_base") (result i32)
    global.get $WEIGHTS_BASE
  )

  (func $get_bias_base (export "get_bias_base") (result i32)
    global.get $BIAS_BASE
  )

  (func $get_mul_base (export "get_mul_base") (result i32)
    global.get $MUL_BASE
  )

  (func $get_shift_base (export "get_shift_base") (result i32)
    global.get $SHIFT_BASE
  )

  (func $get_q6_base (export "get_q6_base") (result i32)
    global.get $Q6_BASE
  )

  (func $get_params_base (export "get_params_base") (result i32)
    global.get $PARAMS_BASE
  )

  (func $get_slot0_base (export "get_slot0_base") (result i32)
    global.get $SLOT0_BASE
  )

  (func $get_slot1_base (export "get_slot1_base") (result i32)
    global.get $SLOT1_BASE
  )

  (func $get_slot2_base (export "get_slot2_base") (result i32)
    global.get $SLOT2_BASE
  )


  (global $RESULT_BASE i32 (i32.const @@RESULT_BASE@@))
  (global $RESULT_COUNT i32 (i32.const @@RESULT_COUNT@@))

  ;; Função auxiliar para obter resultado
  (func $get_result_ptr (export "get_result_ptr") (result i32)
    global.get $RESULT_BASE
  )

  (func $get_result_count (export "get_result_count") (result i32)
    global.get $RESULT_COUNT
  )

  ;; Função para obter o índice da classe com maior probabilidade
  (func $get_top_class (export "get_top_class") (result i32)
    (local $i i32)
    (local $max_val i32)
    (local $max_idx i32)
    (local $val i32)
    (local $ptr i32)

    global.get $RESULT_BASE
    local.set $ptr

    ;; Inicializar com primeiro valor
    local.get $ptr
    i32.load8_s
    local.set $max_val

    i32.const 0
    local.set $max_idx

    i32.const 1
    local.set $i

    (block $exit
      (loop $loop
        local.get $i
        global.get $RESULT_COUNT
        i32.ge_s
        br_if $exit

        local.get $ptr
        local.get $i
        i32.add
        i32.load8_s
        local.set $val

        local.get $val
        local.get $max_val
        i32.gt_s
        (if
          (then
            local.get $val
            local.set $max_val

            local.get $i
            local.set $max_idx
          )
        )

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop
      )
    )

    local.get $max_idx
  )

  ;; Função para obter top-5 classes
  (func $get_top5 (export "get_top5") (param $out_ptr i32)
    (local $i i32)
    (local $j i32)
    (local $k i32)
    (local $val i32)
    (local $idx i32)
    (local $ptr i32)
    (local $temp_val i32)
    (local $temp_idx i32)

    global.get $RESULT_BASE
    local.set $ptr

    ;; Inicializar top5 com -128 (menor valor int8)
    i32.const 0
    local.set $i

    (block $exit_init
      (loop $loop_init
        local.get $i
        i32.const 5
        i32.ge_s
        br_if $exit_init

        ;; out_ptr[i*8 + 0..3] = índice (i32)
        local.get $out_ptr
        local.get $i
        i32.const 3
        i32.shl  ;; * 8
        i32.add
        i32.const -1
        i32.store align=4

        ;; out_ptr[i*8 + 4..7] = valor (i32)
        local.get $out_ptr
        local.get $i
        i32.const 3
        i32.shl
        i32.add
        i32.const 4
        i32.add
        i32.const -128
        i32.store align=4

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop_init
      )
    )

    ;; Para cada classe
    i32.const 0
    local.set $i

    (block $exit_classes
      (loop $loop_classes
        local.get $i
        global.get $RESULT_COUNT
        i32.ge_s
        br_if $exit_classes

        ;; Ler valor da classe atual
        local.get $ptr
        local.get $i
        i32.add
        i32.load8_s
        local.set $val

        ;; Verificar se entra no top5
        i32.const 0
        local.set $j

        (block $exit_top5
          (loop $loop_top5
            local.get $j
            i32.const 5
            i32.ge_s
            br_if $exit_top5

            ;; Ler valor atual do top5[j]
            local.get $out_ptr
            local.get $j
            i32.const 3
            i32.shl
            i32.add
            i32.const 4
            i32.add
            i32.load align=4
            local.set $temp_val

            ;; Se val > temp_val, inserir aqui
            local.get $val
            local.get $temp_val
            i32.gt_s
            (if
              (then
                ;; Deslocar elementos para baixo
                i32.const 4
                local.set $k

                (block $exit_shift
                  (loop $loop_shift
                    local.get $k
                    local.get $j
                    i32.le_s
                    br_if $exit_shift

                    ;; top5[k] = top5[k-1]
                    ;; Copiar índice
                    local.get $out_ptr
                    local.get $k
                    i32.const 3
                    i32.shl
                    i32.add

                    local.get $out_ptr
                    local.get $k
                    i32.const 1
                    i32.sub
                    i32.const 3
                    i32.shl
                    i32.add
                    i32.load align=4

                    i32.store align=4

                    ;; Copiar valor
                    local.get $out_ptr
                    local.get $k
                    i32.const 3
                    i32.shl
                    i32.add
                    i32.const 4
                    i32.add

                    local.get $out_ptr
                    local.get $k
                    i32.const 1
                    i32.sub
                    i32.const 3
                    i32.shl
                    i32.add
                    i32.const 4
                    i32.add
                    i32.load align=4

                    i32.store align=4

                    local.get $k
                    i32.const 1
                    i32.sub
                    local.set $k

                    br $loop_shift
                  )
                )

                ;; Inserir novo valor
                local.get $out_ptr
                local.get $j
                i32.const 3
                i32.shl
                i32.add
                local.get $i
                i32.store align=4

                local.get $out_ptr
                local.get $j
                i32.const 3
                i32.shl
                i32.add
                i32.const 4
                i32.add
                local.get $val
                i32.store align=4

                br $exit_top5
              )
            )

            local.get $j
            i32.const 1
            i32.add
            local.set $j

            br $loop_top5
          )
        )

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop_classes
      )
    )
  )

  ;; ============================================================
  ;; 1. FUNÇÕES DE SUPORTE (REQUANTIZAÇÃO UNIFICADA)
  ;; ============================================================

  (func $saturating_rounding_doubling_high_mul_3 (param $a i32) (param $b i32) (result i32)
    (local $ab i64)
    local.get $a
    i32.const -2147483648
    i32.eq
    local.get $b
    i32.const -2147483648
    i32.eq
    i32.and
    (if
      (then
        i32.const 2147483647
        return
      )
    )
    local.get $a
    i64.extend_i32_s
    local.get $b
    i64.extend_i32_s
    i64.mul
    local.set $ab
    local.get $ab
    i64.const 1073741824 ;; nudge (1 << 30)
    i64.add
    i64.const 31
    i64.shr_s
    i32.wrap_i64
  )

  (func $rounding_divide_by_pot_3 (param $x i32) (param $exponent i32) (result i32)
    (local $nudge i32)
    local.get $exponent
    i32.const 0
    i32.le_s
    (if
      (then
        local.get $x
        return
      )
    )
    i32.const 1
    local.get $exponent
    i32.const 1
    i32.sub
    i32.shl
    local.set $nudge
    local.get $x
    i32.const 0
    i32.ge_s
    (if (result i32)
      (then
        local.get $x
        local.get $nudge
        i32.add
        i32.const 1
        i32.sub
        local.get $exponent
        i32.shr_s
      )
      (else
        local.get $x
        local.get $nudge
        i32.add
        local.get $exponent
        i32.shr_s
      )
    )
  )

  (func $multiply_by_quantized_multiplier_3 (param $x i32) (param $multiplier i32) (param $shift i32) (result i32)
    local.get $shift
    i32.const 0
    i32.gt_s
    (if
      (then
        local.get $x
        local.get $shift
        i32.shl
        local.set $x
      )
    )
    local.get $x
    local.get $multiplier
    call $saturating_rounding_doubling_high_mul_3
    local.set $x
    local.get $shift
    i32.const 0
    i32.lt_s
    (if
      (then
        local.get $x
        i32.const 0
        local.get $shift
        i32.sub
        call $rounding_divide_by_pot_3
        local.set $x
      )
    )
    local.get $x
  )

  ;; ================================================
  ;; INICIO - VERSAO PARA QUANTIZE
  ;; ================================================
  (func $multiply_by_quantized_multiplier_2
    (param $x i32)
    (param $m i32)
    (param $shift i32)  ;; shift -11
    (result i32)

    (local $result i32)


    ;; Se shift > 0 → left shift ANTES
    local.get $shift
    i32.const 0
    i32.gt_s
    (if
      (then
        local.get $x
        i32.const 1
        local.get $shift
        i32.shl
        i32.mul
        local.set $x
      )
    )

    ;; Primeiro high mul (Q31)
    local.get $x
    local.get $m
    call $saturating_rounding_doubling_high_mul_2
    local.set $result


    ;; Se shift < 0 → divide
    local.get $shift
    i32.const 0
    i32.lt_s
    (if
        (then
            local.get $result
            i32.const 0
            local.get $shift    ;;-11
            i32.sub
            call $rounding_divide_by_pot_2
            local.set $result
        )
    )

    local.get $result
  )

  (func $rounding_divide_by_pot_2
    (param $x i32)
    (param $exponent i32)
    (result i32)

    (local $mask i32)
    (local $remainder i32)
    (local $threshold i32)
    (local $result i32)

    ;; mask = (1 << exponent) - 1
    i32.const 1
    local.get $exponent
    i32.shl
    i32.const 1
    i32.sub
    local.set $mask

    ;; remainder = x & mask
    local.get $x
    local.get $mask
    i32.and
    local.set $remainder

    ;; threshold = mask >> 1
    local.get $mask
    i32.const 1
    i32.shr_u
    local.set $threshold

    ;; if x < 0 → threshold++
    local.get $x
    i32.const 0
    i32.lt_s
    (if
      (then
        local.get $threshold
        i32.const 1
        i32.add
        local.set $threshold
      )
    )

    ;; base = x >> exponent
    local.get $x
    local.get $exponent
    i32.shr_s
    local.set $result

    ;; if remainder > threshold → result++
    local.get $remainder
    local.get $threshold
    i32.ge_s
    (if
      (then
        local.get $result
        i32.const 1
        i32.add
        local.set $result
      )
    )

    local.get $result
  )

  (func $saturating_rounding_doubling_high_mul_2 (param $a i32) (param $b i32) (result i32)
    (local $ab i64) ;; a -> x
    (local $nudge i64) ;; b -> m
    (local $result i32)

    ;; Caso especial INT32_MIN * INT32_MIN
    local.get $a
    i32.const -2147483648
    i32.eq
    local.get $b
    i32.const -2147483648
    i32.eq
    i32.and
    (if
      (then
        i32.const 2147483647
        return
      )
    )

    ;; ab = (int64)a * b
    local.get $a
    i64.extend_i32_s
    local.get $b
    i64.extend_i32_s
    i64.mul
    local.set $ab

    i64.const 1073741824
    local.set $nudge

    ;; (ab + nudge) >> 31
    local.get $ab
    local.get $nudge
    i64.add
    i64.const 31
    i64.shr_s
    i32.wrap_i64
    local.set $result

    local.get $result

  )

  ;; ============================================================
  ;; saturating_rounding_doubling_high_mul
  ;; ============================================================
  (func $saturating_rounding_doubling_high_mul
    (export "saturating_rounding_doubling_high_mul")
    (param $a i32)
    (param $b i32)
    (result i32)

    (local $ab i64)

    ;; ------------------------------------------------------------
    ;; Caso especial: INT32_MIN * INT32_MIN
    ;; ------------------------------------------------------------

    local.get $a
    i32.const -2147483648
    i32.eq

    local.get $b
    i32.const -2147483648
    i32.eq

    i32.and
    if
      i32.const 2147483647
      return
    end

    ;; ------------------------------------------------------------
    ;; ab = (i64)a * (i64)b
    ;; ------------------------------------------------------------

    local.get $a
    i64.extend_i32_s

    local.get $b
    i64.extend_i32_s

    i64.mul
    local.set $ab

    ;; ------------------------------------------------------------
    ;; (ab + (1<<30)) >> 31
    ;; ------------------------------------------------------------

    local.get $ab
    i64.const 1073741824   ;; 1 << 30
    i64.add

    i64.const 31
    i64.shr_s

    i32.wrap_i64
  )

  ;; ============================================================
  ;; rounding_divide_by_pot
  ;; ============================================================
  (func $rounding_divide_by_pot
    (export "rounding_divide_by_pot")
    (param $x i32)
    (param $exponent i32)
    (result i32)

    (local $nudge i32)

    ;; if exponent <= 0 return x

    local.get $exponent
    i32.const 0
    i32.le_s
    if
      local.get $x
      return
    end

    ;; nudge = 1 << (exponent - 1)

    i32.const 1
    local.get $exponent
    i32.const 1
    i32.sub
    i32.shl
    local.set $nudge

    ;; if x >= 0

    local.get $x
    i32.const 0
    i32.ge_s
    if
      ;; (x + nudge - 1) >> exponent

      local.get $x
      local.get $nudge
      i32.add
      i32.const 1
      i32.sub

      local.get $exponent
      i32.shr_s

      return
    end

    ;; else (x + nudge) >> exponent

    local.get $x
    local.get $nudge
    i32.add

    local.get $exponent
    i32.shr_s
  )

  ;; ============================================================
  ;; multiply_by_quantized_multiplier
  ;; ============================================================
  (func $multiply_by_quantized_multiplier
    (export "multiply_by_quantized_multiplier")
    (param $x i32)
    (param $multiplier i32)
    (param $shift i32)
    (result i32)

    (local $tmp i32)

    ;; tmp = SRDHM(x, multiplier)

    local.get $x
    local.get $multiplier
    call $saturating_rounding_doubling_high_mul
    local.set $tmp

    ;; return rounding_divide_by_pot(tmp, -shift)

    local.get $tmp

    i32.const 0
    local.get $shift
    i32.sub

    call $rounding_divide_by_pot
  )

  (func $multiply_by_quantized_multiplier_softmax
    (param $x i32)
    (param $multiplier i32)
    (param $shift i32)
    (result i32)

    (local $result i32)
    (local $right_shift i32)

    ;; High mul
    local.get $x
    local.get $multiplier
    call $saturating_rounding_doubling_high_mul_3
    local.set $result

    ;; right_shift = -shift
    i32.const 0
    local.get $shift
    i32.sub
    local.set $right_shift

    ;; Rounding divide
    local.get $result
    local.get $right_shift
    call $rounding_divide_by_pot_3
  )

  (func $exp_q15 (param $x i32) (result i32)
    ;; x já está arredondado em [-11..0]

    local.get $x
    i32.const -11
    i32.lt_s
    (if
      (then
        i32.const 0
        return
      )
    )

    local.get $x
    i32.const 0
    i32.gt_s
    (if
      (then
        i32.const 0
        local.set $x
      )
    )

    ;; switch manual via br_table com blocos aninhados
    (block $c11
    (block $c10
    (block $c9
    (block $c8
    (block $c7
    (block $c6
    (block $c5
    (block $c4
    (block $c3
    (block $c2
    (block $c1
    (block $c0
      local.get $x
      i32.const 11
      i32.add      ;; transforma -11..0 → 0..11
      br_table $c0 $c1 $c2 $c3 $c4 $c5 $c6 $c7 $c8 $c9 $c10 $c11
    )
    i32.const 1   return) ;; $c0  (x = -11)
    i32.const 1   return) ;; $c1  (x = -10)
    i32.const 4   return) ;; $c2
    i32.const 11  return) ;; $c3
    i32.const 30  return) ;; $c4
    i32.const 81  return) ;; $c5
    i32.const 221 return) ;; $c6
    i32.const 600 return) ;; $c7
    i32.const 1631  return) ;; $c8
    i32.const 4435  return) ;; $c9
    i32.const 12055 return) ;; $c10
    i32.const 32768          ;; $c11 (x = 0) — cai aqui e retorna normalmente
  )


  ;; ============================================================
  ;; LayerParam reader (29x i32) + loader to locals
  ;; ============================================================


  (func $layerparam_base (param $layer_idx i32) (result i32)
    global.get $PARAMS_BASE
    local.get $layer_idx    ;; Índice da camada (0 a 66)
    global.get $LP_SIZE     ;; 116
    i32.mul                 ;; 0 * 116 , 1 * 116, 2 * 116 ...
    i32.add
  )

  (func $depthwise_conv2d (export "depthwise_conv2d") (param $layer_idx i32)
    (local $base     i32)

    (local $op_type   i32)
    (local $act       i32)
    (local $flags     i32)
    (local $in_ptr    i32)
    (local $out_ptr   i32)
    (local $in_h      i32)
    (local $in_w      i32)
    (local $cin       i32)
    (local $cout      i32)
    (local $kh        i32)
    (local $kw        i32)
    (local $stride_h  i32)
    (local $stride_w  i32)
    (local $dil_h     i32)
    (local $dil_w     i32)
    (local $pad_t     i32)
    (local $pad_b     i32)
    (local $pad_l     i32)
    (local $pad_r     i32)
    (local $wptr      i32)
    (local $bias_ptr  i32)
    (local $shift_ptr i32)
    (local $mul_ptr   i32)
    (local $q6_ptr    i32)
    (local $zx        i32)
    (local $zw        i32)
    (local $zy        i32)
    (local $out_h     i32)
    (local $out_w     i32)

    (local $bottom    i32)
    (local $right     i32)
    (local $plane_out i32)
    (local $w_per_oc  i32)

    (local $oc        i32)
    (local $i_out     i32)
    (local $j_out     i32)
    (local $ki        i32)
    (local $kj        i32)

    (local $baseOutOC i32)
    (local $baseWoc   i32)

    (local $b         i32)
    (local $m         i32)
    (local $q6        i32)

    (local $i         i32)
    (local $j         i32)

    (local $acc       i32)

    (local $row       i32)
    (local $col       i32)

    (local $row_img   i32)
    (local $row_base  i32)
    (local $col_img   i32)
    (local $idx       i32)

    (local $pos       i32)
    (local $baseW_kikj i32)

    (local $outIdx    i32)

    (local $tmp i32)
    (local $w0  i32)

    (local $y   i32)
    (local $hi  i32)
    (local $lo  i32)
    (local $p   i64)
    (local $nudge i64)

    ;; base = PARAMS_BASE + layer_idx * LP_SIZE
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; -------------------------
    ;; helpers inline:
    ;; load_i32(field_idx) = i32.load(base + field_idx*4)
    ;; -------------------------

    ;; op_type (0)
    local.get $base
    i32.const 0
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $op_type

    ;; act (1)
    local.get $base
    i32.const 1
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $act

    ;; flags (2)
    local.get $base
    i32.const 2
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $flags

    ;; in_ptr (3)
    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_ptr

    ;; out_ptr (4)
    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_ptr

    ;; in_h (5)
    local.get $base
    i32.const 5
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_h

    ;; in_w (6)
    local.get $base
    i32.const 6
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_w

    ;; cin (7)
    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cin

    ;; cout (8)
    local.get $base
    i32.const 8
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cout

    ;; kh (9)
    local.get $base
    i32.const 9
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $kh

    ;; kw (10)
    local.get $base
    i32.const 10
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $kw

    ;; stride_h (11)
    local.get $base
    i32.const 11
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $stride_h

    ;; stride_w (12)
    local.get $base
    i32.const 12
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $stride_w

    ;; dil_h (13)
    local.get $base
    i32.const 13
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $dil_h

    ;; dil_w (14)
    local.get $base
    i32.const 14
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $dil_w

    ;; pad_t (15)
    local.get $base
    i32.const 15
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_t

    ;; pad_b (16)
    local.get $base
    i32.const 16
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_b

    ;; pad_l (17)
    local.get $base
    i32.const 17
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_l

    ;; pad_r (18)
    local.get $base
    i32.const 18
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_r

    ;; wptr (19)
    local.get $base
    i32.const 19
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $wptr

    ;; bias_ptr (20)
    local.get $base
    i32.const 20
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $bias_ptr

    ;; mul_ptr (21)
    local.get $base
    i32.const 21
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $mul_ptr

    ;; shift_ptr (22)
    local.get $base
    i32.const 22
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set
    $shift_ptr

    ;; q6_ptr (23)
    local.get $base
    i32.const 23
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $q6_ptr

    ;; zx (24)
    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zx

    ;; zw (25)
    local.get $base
    i32.const 25
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zw

    ;; zy (26)
    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zy

    ;; out_h (27)
    local.get $base
    i32.const 27
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_h

    ;; out_w (28)
    local.get $base
    i32.const 28
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_w

    ;; =========================


    ;; bottom = pad_t + in_h;
    local.get $pad_t
    local.get $in_h
    i32.add
    local.set $bottom

    ;; right = pad_l + in_w;
    local.get $pad_l
    local.get $in_w
    i32.add
    local.set $right

    ;; plane_out = out_h * out_w;
    local.get $out_h
    local.get $out_w
    i32.mul
    local.set $plane_out

    ;; bytes por oc (depthwise): kh * kw = 9
    local.get $kh
    local.get $kw
    i32.mul
    local.set $w_per_oc

    ;; =========================
    ;; loops: oc / i_out / j_out / ki / kj
    ;; com dilatação: row = i + ki*dil_h, col = j + kj*dil_w
    ;; =========================

    ;; --- INÍCIO DOS LOOPS NHWC ---

    i32.const 0 local.set $i_out
    (block $exit_i
      (loop $loop_i
        ;; if (i_out >= out_h) break;
        local.get $i_out
        local.get $out_h
        i32.ge_s
        br_if $exit_i

        i32.const 0 local.set $j_out
        (block $exit_j
          (loop $loop_j
            ;; if (j_out >= out_w) break;
            local.get $j_out
            local.get $out_w
            i32.ge_s
            br_if $exit_j

            i32.const 0 local.set $oc
            (block $exit_oc
              (loop $loop_oc
                ;; if (oc >= cout) break;
                local.get $oc
                local.get $cout
                i32.ge_s
                br_if $exit_oc

                ;; --- Lógica de Acumulação ---
                local.get $bias_ptr local.get $oc i32.const 2 i32.shl i32.add i32.load local.set $acc

                i32.const 0 local.set $ki
                (block $exit_ki
                  (loop $loop_ki
                    local.get $ki
                    local.get $kh
                    i32.ge_s
                    br_if $exit_ki

                    local.get $i_out local.get $stride_h i32.mul local.get $ki local.get $dil_h i32.mul i32.add local.set $row

                    ;; Boundary Check Altura (se fora, pula para o próximo ki)
                    (block $continue_ki
                        local.get $row local.get $pad_t i32.lt_s br_if $continue_ki
                        local.get $row local.get $pad_t local.get $in_h i32.add i32.ge_s br_if $continue_ki

                        i32.const 0 local.set $kj
                        (block $exit_kj
                          (loop $loop_kj
                            local.get $kj local.get $kw i32.ge_s br_if $exit_kj

                            local.get $j_out local.get $stride_w i32.mul local.get $kj local.get $dil_w i32.mul i32.add local.set $col

                            ;; Boundary Check Largura
                            (block $continue_kj
                                local.get $col local.get $pad_l i32.lt_s br_if $continue_kj
                                local.get $col local.get $pad_l local.get $in_w i32.add i32.ge_s br_if $continue_kj

                                ;; INDEXAÇÃO NHWC INPUT
                                local.get $row local.get $pad_t i32.sub local.get $in_w i32.mul
                                local.get $col local.get $pad_l i32.sub i32.add
                                local.get $cin i32.mul
                                local.get $oc i32.add
                                local.get $in_ptr i32.add i32.load8_s local.set $tmp

                                ;; INDEXAÇÃO KERNEL (Depthwise)
                                local.get $ki local.get $kw i32.mul local.get $kj i32.add
                                local.get $cout i32.mul
                                local.get $oc i32.add
                                local.get $wptr i32.add i32.load8_s local.set $w0

                                ;; acc += (input - zx) * (w - zw)
                                local.get $tmp local.get $zx i32.sub
                                local.get $w0 local.get $zw i32.sub
                                i32.mul
                                local.get $acc i32.add local.set $acc
                            ) ;; fim continue_kj

                            local.get $kj i32.const 1 i32.add local.set $kj
                            br $loop_kj
                          )
                        )
                    ) ;; fim continue_ki

                    local.get $ki i32.const 1 i32.add local.set $ki
                    br $loop_ki
                  )
                )

                ;; --- REQUANTIZAÇÃO E STORE (NHWC) ---
                local.get $acc
                local.get $mul_ptr local.get $oc i32.const 2 i32.shl i32.add i32.load ;; Multiplier
                local.get $shift_ptr local.get $oc i32.const 2 i32.shl i32.add i32.load ;; Shift
                call $multiply_by_quantized_multiplier_3
                local.get $zy i32.add local.set $y

                ;; ReLU / ReLU6
                local.get $act i32.const 1 i32.eq (if (then local.get $y local.get $zy i32.lt_s (if (then local.get $zy local.set $y))))
                local.get $act i32.const 3 i32.eq (if (then
                  local.get $q6_ptr local.get $oc i32.const 2 i32.shl i32.add i32.load local.set $q6
                  local.get $y local.get $q6 i32.gt_s (if (then local.get $q6 local.set $y))
                  local.get $y local.get $zy i32.lt_s (if (then local.get $zy local.set $y))
                ))

                ;; Final Clamp i8
                local.get $y i32.const 127 i32.gt_s (if (then i32.const 127 local.set $y))
                local.get $y i32.const -128 i32.lt_s (if (then i32.const -128 local.set $y))

                ;; --- STORE NHWC OUTPUT ---
                ;; idx = (i_out*out_w + j_out)*cout + oc
                local.get $i_out local.get $out_w i32.mul local.get $j_out i32.add
                local.get $cout i32.mul local.get $oc i32.add local.set $idx

                local.get $out_ptr local.get $idx i32.add
                local.get $y i32.store8

                ;;local.get $layer_idx
                ;;i32.const 3
                ;;i32.eq
                ;;if
                ;;  local.get $y
                ;;end

                local.get $oc i32.const 1 i32.add local.set $oc
                br $loop_oc
              )
            ) ;; fim exit_oc

            local.get $j_out i32.const 1 i32.add local.set $j_out
            br $loop_j
          )
        ) ;; fim exit_j

        local.get $i_out i32.const 1 i32.add local.set $i_out
        br $loop_i
      )
    ) ;; fim exit_i
  )

  (func $conv2d (export "conv2d") (param $layer_idx i32)
    (local $base     i32)

    (local $op_type   i32)
    (local $act       i32)
    (local $flags     i32)
    (local $in_ptr    i32)
    (local $out_ptr   i32)
    (local $in_h      i32)
    (local $in_w      i32)
    (local $cin       i32)
    (local $cout      i32)
    (local $kh        i32)
    (local $kw        i32)
    (local $stride_h  i32)
    (local $stride_w  i32)
    (local $dil_h     i32)
    (local $dil_w     i32)
    (local $pad_t     i32)
    (local $pad_b     i32)
    (local $pad_l     i32)
    (local $pad_r     i32)
    (local $wptr      i32)
    (local $bias_ptr  i32)
    (local $mul_ptr   i32)
    (local $shift_ptr i32)
    (local $q6_ptr    i32)
    (local $zx        i32)
    (local $zw        i32)
    (local $zy        i32)
    (local $out_h     i32)
    (local $out_w     i32)

    (local $bottom    i32)
    (local $right     i32)
    (local $plane_out i32)
    (local $w_per_oc  i32)

    (local $oc        i32)
    (local $i_out     i32)
    (local $j_out     i32)
    (local $ki        i32)
    (local $kj        i32)

    (local $baseOutOC i32)
    (local $baseWoc   i32)

    (local $b         i32)
    (local $m         i32)
    (local $q6        i32)
    (local $shift     i32)

    (local $i         i32)
    (local $j         i32)

    (local $acc       i32)

    (local $row       i32)
    (local $col       i32)

    (local $row_img   i32)
    (local $row_base  i32)
    (local $col_img   i32)
    (local $idx       i32)

    (local $pos       i32)
    (local $baseW_kikj i32)

    (local $outIdx    i32)

    (local $tmp i32)
    (local $w0  i32)

    (local $y   i32)
    (local $hi  i32)
    (local $lo  i32)
    (local $p   i64)
    (local $nudge i64)

    (local $c i32)

    (local $dbg_i i32)

    ;; base = PARAMS_BASE + layer_idx * LP_SIZE
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; -------------------------
    ;; helpers inline:
    ;; load_i32(field_idx) = i32.load(base + field_idx*4)
    ;; -------------------------

    ;; op_type (0)
    local.get $base
    i32.const 0
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $op_type

    ;; act (1)
    local.get $base
    i32.const 1
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $act

    ;; flags (2)
    local.get $base
    i32.const 2
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $flags

    ;; in_ptr (3)
    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_ptr

    ;; out_ptr (4)
    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_ptr

    ;; in_h (5)
    local.get $base
    i32.const 5
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_h

    ;; in_w (6)
    local.get $base
    i32.const 6
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_w

    ;; cin (7)
    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cin

    ;; cout (8)
    local.get $base
    i32.const 8
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cout

    ;; kh (9)
    local.get $base
    i32.const 9
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $kh

    ;; kw (10)
    local.get $base
    i32.const 10
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $kw

    ;; stride_h (11)
    local.get $base
    i32.const 11
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $stride_h

    ;; stride_w (12)
    local.get $base
    i32.const 12
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $stride_w

    ;; dil_h (13)
    local.get $base
    i32.const 13
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $dil_h

    ;; dil_w (14)
    local.get $base
    i32.const 14
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $dil_w

    ;; pad_t (15)
    local.get $base
    i32.const 15
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_t

    ;; pad_b (16)
    local.get $base
    i32.const 16
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_b

    ;; pad_l (17)
    local.get $base
    i32.const 17
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_l

    ;; pad_r (18)
    local.get $base
    i32.const 18
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $pad_r

    ;; wptr (19)
    local.get $base
    i32.const 19
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $wptr

    ;; bias_ptr (20)
    local.get $base
    i32.const 20
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $bias_ptr

    ;; mul_ptr (21)
    local.get $base
    i32.const 21
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $mul_ptr

    ;; shift_ptr (22)
    local.get $base
    i32.const 22
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $shift_ptr

    ;; q6_ptr (23)
    local.get $base
    i32.const 23
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $q6_ptr

    ;; zx (24)
    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zx

    ;; zw (25)
    local.get $base
    i32.const 25
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zw

    ;; zy (26)
    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zy

    ;; out_h (27)
    local.get $base
    i32.const 27
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_h

    ;; out_w (28)
    local.get $base
    i32.const 28
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_w

    ;; bottom = pad_t + in_h;
    local.get $pad_t
    local.get $in_h
    i32.add
    local.set $bottom

    ;; right = pad_l + in_w;
    local.get $pad_l
    local.get $in_w
    i32.add
    local.set $right

    ;; plane_out = out_h * out_w;
    local.get $out_h
    local.get $out_w
    i32.mul
    local.set $plane_out

    ;; // bytes por oc: kh*kw*cin = 9*3 = 27
    local.get $kh
    local.get $kw
    local.get $cin
    i32.mul
    i32.mul
    local.set $w_per_oc ;; quantidade de pesos por canal 3x3x3 = 27

    ;; =========================
    ;; loops: oc / i_out / j_out / ki / kj
    ;; com dilatação: row = i + ki*dil_h, col = j + kj*dil_w
    ;; =========================

    ;; i_out = 0
    i32.const 0
    local.set $i_out

    (block $exit_i
      (loop $loop_i

        ;; if (i_out >= out_h) break;
        local.get $i_out
        local.get $out_h
        i32.ge_s
        br_if $exit_i

        ;; i = i_out * stride_h
        local.get $i_out
        local.get $stride_h
        i32.mul
        local.set $i

        ;; j_out = 0
        i32.const 0
        local.set $j_out

        (block $exit_j
          (loop $loop_j

            ;; if (j_out >= out_w) break;
            local.get $j_out
            local.get $out_w
            i32.ge_s
            br_if $exit_j

            ;; j = j_out * stride_w
            local.get $j_out
            local.get $stride_w
            i32.mul
            local.set $j

            ;; oc = 0
            i32.const 0
            local.set $oc

            (block $exit_oc
              (loop $loop_oc

                ;; if (oc >= cout) break;
                local.get $oc
                local.get $cout
                i32.ge_s
                br_if $exit_oc

                ;; out_index = ((i_out * out_w) + j_out) * cout + oc

                local.get $i_out
                local.get $out_w
                i32.mul

                local.get $j_out
                i32.add

                local.get $cout
                i32.mul

                local.get $oc
                i32.add

                local.set $outIdx

                ;; b = load<i32>(bias_ptr + oc*4)
                local.get $bias_ptr
                local.get $oc
                i32.const 2
                i32.shl
                i32.add
                i32.load align=4
                local.set $b

                ;; m = load<i32>(mul_ptr + oc*4)
                local.get $mul_ptr
                local.get $oc
                i32.const 2
                i32.shl
                i32.add
                i32.load align=4
                local.set $m

                ;; shift = load<i32>(shift_ptr + oc*4)
                local.get $shift_ptr
                local.get $oc
                i32.const 2
                i32.shl
                i32.add
                i32.load align=4
                local.set $shift

                ;; q6 = (q6_ptr != 0) ? load<i32>(q6_ptr + oc*4) : 0
                local.get $q6_ptr
                i32.eqz
                (if (result i32)
                  (then
                    i32.const 0
                  )
                  (else
                    local.get $q6_ptr
                    local.get $oc
                    i32.const 2
                    i32.shl
                    i32.add
                    i32.load align=4
                  )
                )
                local.set $q6

                ;; baseWoc = wptr + oc * w_per_oc ;; base dos pesos onde eles estao
                local.get $wptr
                local.get $oc
                local.get $w_per_oc
                i32.mul
                i32.add
                local.set $baseWoc

                local.get $b
                local.set $acc

                i32.const 0
                local.set $ki

                (block $exit_ki
                  (loop $loop_ki

                    ;; if (ki >= kh) break;
                    local.get $ki
                    local.get $kh
                    i32.ge_s
                    br_if $exit_ki

                    ;; ---- alvo do "continue" do ki ----
                    (block $inc_ki

                      ;; row = i + ki*dil_h   (DILATAÇÃO AQUI)
                      local.get $i
                      local.get $ki
                      local.get $dil_h
                      i32.mul
                      i32.add
                      local.set $row

                      ;; if (row < pad_t) continue;
                      local.get $row
                      local.get $pad_t
                      i32.lt_s
                      br_if $inc_ki

                      ;; if (row >= bottom) break;
                      local.get $row
                      local.get $bottom
                      i32.ge_s
                      br_if $exit_ki

                      ;; row_img  = row - pad_t
                      local.get $row
                      local.get $pad_t
                      i32.sub
                      local.set $row_img

                      ;; if (row_img < 0 || row_img >= in_h) continue;
                      local.get $row_img
                      i32.const 0
                      i32.lt_s
                      br_if $inc_ki

                      ;; row_img >= in_h
                      local.get $row_img
                      local.get $in_h
                      i32.ge_s
                      br_if $inc_ki

                      ;; row_base = row_img * in_w
                      local.get $row_img
                      local.get $in_w
                      i32.mul
                      local.set $row_base

                      ;; kj = 0
                      i32.const 0
                      local.set $kj

                      (block $exit_kj
                        (loop $loop_kj

                          ;; if (kj >= kw) break;
                          local.get $kj
                          local.get $kw
                          i32.ge_s
                          br_if $exit_kj

                          ;; ---- alvo do "continue" do kj ----
                          (block $inc_kj

                            ;; col = j + kj*dil_w   (DILATAÇÃO AQUI)
                            local.get $j
                            local.get $kj
                            local.get $dil_w
                            i32.mul
                            i32.add
                            local.set $col

                            ;; if (col < pad_l) continue;
                            local.get $col
                            local.get $pad_l
                            i32.lt_s
                            br_if $inc_kj

                            ;; if (col >= right) break;
                            local.get $col
                            local.get $right
                            i32.ge_s
                            br_if $exit_kj

                            ;; col_img = col - pad_l
                            local.get $col
                            local.get $pad_l
                            i32.sub
                            local.set $col_img

                            ;; if (col_img < 0 || col_img >= in_w) continue;
                            local.get $col_img
                            i32.const 0
                            i32.lt_s
                            br_if $inc_kj

                            local.get $col_img
                            local.get $in_w
                            i32.ge_s
                            br_if $inc_kj

                            ;; for c in [0..cin)
                            i32.const 0
                            local.set $c

                            (block $exit_c
                              (loop $loop_c

                                ;; if (c >= cin) break
                                local.get $c
                                local.get $cin
                                i32.ge_s
                                br_if $exit_c

                                ;; input_idx = (row_base + col_img) * cin + c
                                local.get $row_base
                                local.get $col_img
                                i32.add
                                local.get $cin
                                i32.mul
                                local.get $c
                                i32.add
                                local.set $idx

                                ;; tmp = load<i8>(in_ptr + idx)
                                local.get $in_ptr
                                local.get $idx
                                i32.add
                                i32.load8_s
                                local.set $tmp

                                ;; pos = ((ki*kw + kj) * cin) + c
                                local.get $ki
                                local.get $kw
                                i32.mul
                                local.get $kj
                                i32.add
                                local.get $cin
                                i32.mul
                                local.get $c
                                i32.add
                                local.set $pos

                                ;; w0 = load<i8>(baseWoc + pos)
                                local.get $baseWoc
                                local.get $pos
                                i32.add
                                i32.load8_s
                                local.set $w0

                                ;; acc += (tmp - zx) * (w0 - zw)
                                local.get $acc
                                local.get $tmp
                                local.get $zx
                                i32.sub
                                local.get $w0
                                local.get $zw
                                i32.sub
                                i32.mul
                                i32.add
                                local.set $acc

                                ;; c++
                                local.get $c
                                i32.const 1
                                i32.add
                                local.set $c

                                br $loop_c
                              )
                            )

                            ;; kj++
                            local.get $kj
                            i32.const 1
                            i32.add
                            local.set $kj

                            br $loop_kj
                          )
                        )
                      )
                    )

                    ;; ki++
                    local.get $ki
                    i32.const 1
                    i32.add
                    local.set $ki
                    br $loop_ki
                  )
                )

                ;; 1. Cálculo base (Requantização)
                local.get $acc
                local.get $m
                local.get $shift
                call $multiply_by_quantized_multiplier_3
                local.get $zy
                i32.add
                local.set $y

                ;; --- INÍCIO DAS ATIVAÇÕES ---

                ;; act == 1: RELU (y = max(y, zy))
                local.get $act
                i32.const 1
                i32.eq
                if
                  local.get $y
                  local.get $zy
                  i32.lt_s
                  if
                    local.get $zy
                    local.set $y
                  end
                end

                ;; act == 3: RELU6 (Clamp entre lo e hi)
                local.get $act
                i32.const 3
                i32.eq
                if
                  ;; Configurar limites iniciais
                  local.get $zy
                  local.set $lo
                  local.get $q6
                  local.set $hi

                  ;; if hi < lo: hi = lo
                  local.get $hi
                  local.get $lo
                  i32.lt_s
                  if
                    local.get $lo
                    local.set $hi
                  end

                  ;; Clamp hi a 127
                  local.get $hi
                  i32.const 127
                  i32.gt_s
                  if
                    i32.const 127
                    local.set $hi
                  end

                  ;; Clamp lo a -128
                  local.get $lo
                  i32.const -128
                  i32.lt_s
                  if
                    i32.const -128
                    local.set $lo
                  end

                  ;; Aplica o Clamp no valor y: max(lo, min(y, hi))
                  local.get $y
                  local.get $hi
                  i32.gt_s
                  if
                    local.get $hi
                    local.set $y
                  end

                  local.get $y
                  local.get $lo
                  i32.lt_s
                  if
                    local.get $lo
                    local.set $y
                  end
                end

                ;; --- FINAL CLAMP GLOBAL [-128, 127] ---
                ;; Essencial para evitar overflow ao converter para i8 (byte)
                local.get $y
                i32.const 127
                i32.gt_s
                if
                  i32.const 127
                  local.set $y
                end

                local.get $y
                i32.const -128
                i32.lt_s
                if
                  i32.const -128
                  local.set $y
                end

                ;; store8(out_ptr + outIdx)

                local.get $out_ptr
                local.get $outIdx
                i32.add

                local.get $y
                i32.store8

                ;; oc++
                local.get $oc
                i32.const 1
                i32.add
                local.set $oc

                br $loop_oc
              )
            )

            ;; j_out++
            local.get $j_out
            i32.const 1
            i32.add
            local.set $j_out

            br $loop_j
          )
        )

        ;; i_out++
        local.get $i_out
        i32.const 1
        i32.add
        local.set $i_out

        br $loop_i
      )
    )
  )

  (func $quantize (export "quantize") (param $layer_idx i32)
    (local $base i32)
    (local $flags i32)
    (local $in_ptr i32)
    (local $out_ptr i32)
    (local $total i32)
    (local $mul i32)
    (local $shift i32)
    (local $zp_in i32)
    (local $zp_out i32)
    (local $i i32)
    (local $val i32)
    (local $result i32)

    (local $dbg_i i32)
    ;; base
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; flags (2)
    local.get $base
    i32.const 2
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $flags ;; 1 ou 0

    ;; in_ptr (3)
    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $in_ptr

    ;; out_ptr (4)
    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $out_ptr

    ;; total = out_h * out_w * cout
    local.get $base
    i32.const 27
    i32.const 2
    i32.shl
    i32.add
    i32.load ;; 1

    local.get $base
    i32.const 28
    i32.const 2
    i32.shl
    i32.add
    i32.load
    i32.mul ;; 1 * 1

    local.get $base
    i32.const 8
    i32.const 2
    i32.shl
    i32.add
    i32.load
    i32.mul

    local.set $total

    ;; mul = kh (9)
    local.get $base
    i32.const 9
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $mul

    ;; shift = kw (10)
    local.get $base
    i32.const 10
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $shift

    ;; zp_in (24)
    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $zp_in

    ;; zp_out (26)
    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $zp_out

    i32.const 0
    local.set $i

    (block $exit
      (loop $loop

        local.get $i
        local.get $total
        i32.ge_u
        br_if $exit

        ;; load value
        local.get $flags
        i32.const 1
        i32.and
        i32.eqz
        (if
          (then
            ;; uint8
            local.get $in_ptr
            local.get $i
            i32.add
            i32.load8_u
            local.set $val
          )
          (else
            ;; int8
            local.get $in_ptr
            local.get $i
            i32.add
            i32.load8_s
            local.set $val
          )
        )

        ;; val -= zp_in
        local.get $val
        local.get $zp_in
        i32.sub
        local.set $val

        ;; multiply
        local.get $val
        local.get $mul
        local.get $shift
        call $multiply_by_quantized_multiplier_3
        local.set $result ;; <= O VALOR JÁ ESTA CERTO AQUI

        ;;result += zp_out
        local.get $result
        local.get $zp_out
        i32.add
        local.set $result

        ;; clamp: depende da camada
        local.get $flags
        i32.const 2
        i32.and
        (if
          (then
            ;; última camada: uint8 [0, 255]
            local.get $result
            i32.const 255
            i32.gt_s
            (if (then i32.const 255 local.set $result))

            local.get $result
            i32.const 0
            i32.lt_s
            (if (then i32.const 0 local.set $result))
          )
          (else
            ;; demais camadas: int8 [-128, 127]
            local.get $result
            i32.const 127
            i32.gt_s
            (if (then i32.const 127 local.set $result))

            local.get $result
            i32.const -128
            i32.lt_s
            (if (then i32.const -128 local.set $result))
          )
        )

        ;; store
        local.get $out_ptr
        local.get $i
        i32.add
        local.get $result
        i32.store8

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop
      )
    )
  )

  ;; ============================================================
  ;; ADD Layer - CORRIGIDO com Quantização Q31 Completa
  ;; Campos usados:
  ;;   kh = mul0 (Q31), kw = shift0
  ;;   stride_h = mul1 (Q31), stride_w = shift1
  ;;   dil_h = out_mul (Q31), dil_w = out_shift
  ;;   pad_t = input_ptr[0], pad_b = input_ptr[1]
  ;;   pad_l = zA, pad_r = zB
  ;;   zx = zA, zw = zB, zy = zY
  ;; ============================================================
  (func $add (export "add") (param $layer_idx i32)
    (local $base     i32)
    (local $in_ptr_0 i32)  ;; de pad_t
    (local $in_ptr_1 i32)  ;; de pad_b
    (local $out_ptr  i32)
    (local $in_h     i32)
    (local $in_w     i32)
    (local $cin      i32)

    ;; Parâmetros de quantização
    (local $mul0     i32)  ;; de kh
    (local $shift0   i32)  ;; de kw
    (local $mul1     i32)  ;; de stride_h
    (local $shift1   i32)  ;; de stride_w
    (local $out_mul  i32)  ;; de dil_h
    (local $out_shift i32) ;; de dil_w
    (local $zA       i32)  ;; de pad_l
    (local $zB       i32)  ;; de pad_r
    (local $zY       i32)  ;; de zy

    (local $total    i32)
    (local $idx      i32)
    (local $val0     i32)
    (local $val1     i32)
    (local $acc0     i32)
    (local $acc1     i32)
    (local $sum      i32)
    (local $result   i32)

    ;;local.get $layer_idx

    ;; Carregar base
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; pad_t (15) = in_ptr_0
    local.get $base
    i32.const 15
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_ptr_0

    ;; pad_b (16) = in_ptr_1
    local.get $base
    i32.const 16
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_ptr_1

    ;; out_ptr (4)
    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_ptr

    ;; in_h (5)
    local.get $base
    i32.const 5
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_h

    ;; in_w (6)
    local.get $base
    i32.const 6
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_w

    ;; cin (7)
    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cin

    ;; kh (9) = mul0
    local.get $base
    i32.const 9
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $mul0

    ;; kw (10) = shift0
    local.get $base
    i32.const 10
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $shift0

    ;; stride_h (11) = mul1
    local.get $base
    i32.const 11
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $mul1

    ;; stride_w (12) = shift1
    local.get $base
    i32.const 12
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $shift1

    ;; dil_h (13) = out_mul
    local.get $base
    i32.const 13
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_mul

    ;; dil_w (14) = out_shift
    local.get $base
    i32.const 14
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_shift

    ;; pad_l (17) = zA
    local.get $base
    i32.const 17
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zA

    ;; pad_r (18) = zB
    local.get $base
    i32.const 18
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zB

    ;; zy (26) = zY
    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zY

    ;; total = in_h * in_w * cin
    local.get $in_h
    local.get $in_w
    i32.mul
    local.get $cin
    i32.mul
    local.set $total

    ;; Loop através de todos os elementos
    i32.const 0
    local.set $idx

    (block $exit_loop
      (loop $loop
        ;; if (idx >= total) break
        local.get $idx
        local.get $total
        i32.ge_s
        br_if $exit_loop

        ;; val0 = load<i8>(in_ptr_0 + idx) - zA
        local.get $in_ptr_0
        local.get $idx
        i32.add
        i32.load8_s
        local.get $zA
        i32.sub
        local.set $val0

        ;; val1 = load<i8>(in_ptr_1 + idx) - zB
        local.get $in_ptr_1
        local.get $idx
        i32.add
        i32.load8_s
        local.get $zB
        i32.sub
        local.set $val1

        ;; acc0 = multiply_by_quantized_multiplier(val0, mul0, shift0)
        local.get $val0
        local.get $mul0
        local.get $shift0
        call $multiply_by_quantized_multiplier_3
        local.set $acc0

        ;; acc1 = multiply_by_quantized_multiplier(val1, mul1, shift1)
        local.get $val1
        local.get $mul1
        local.get $shift1
        call $multiply_by_quantized_multiplier_3
        local.set $acc1

        ;; sum = acc0 + acc1
        local.get $acc0
        local.get $acc1
        i32.add
        local.set $sum

        ;; result = multiply_by_quantized_multiplier(sum, out_mul, out_shift)
        local.get $sum
        local.get $out_mul
        local.get $out_shift
        call $multiply_by_quantized_multiplier_3
        local.set $result

        ;; result += zY
        local.get $result
        local.get $zY
        i32.add
        local.set $result

        ;; Clamp [-128, 127]
        local.get $result
        i32.const 127
        i32.gt_s
        (if
          (then
            i32.const 127
            local.set $result
          )
        )

        local.get $result
        i32.const -128
        i32.lt_s
        (if
          (then
            i32.const -128
            local.set $result
          )
        )

        ;; store<i8>(out_ptr + idx) = result
        local.get $out_ptr
        local.get $idx
        i32.add
        local.get $result
        i32.store8

        ;; idx++
        local.get $idx
        i32.const 1
        i32.add
        local.set $idx

        br $loop
      )
    )
  )

  ;; ============================================================
  ;; MEAN Layer - CORRIGIDO com Quantização
  ;; Campos usados:
  ;;   kh = mul (Q31), kw = shift
  ;;   stride_h = spatial_size (in_h * in_w)
  ;;   pad_t = input_ptr
  ;;   zx, zy para zero points
  ;; ============================================================
  (func $mean (export "mean") (param $layer_idx i32)

    (local $base i32)
    (local $in_ptr i32)
    (local $out_ptr i32)
    (local $in_h i32)
    (local $in_w i32)
    (local $cin i32)

    (local $mul i32)
    (local $shift i32)
    (local $zX i32)
    (local $zY i32)
    (local $spatial_size i32)

    (local $c i32)
    (local $idx i32)
    (local $sum i32)
    (local $val i32)
    (local $scaled i32)

    ;; =========================
    ;; Load base
    ;; =========================
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; in_ptr (3)
    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $in_ptr

    ;; out_ptr (4)
    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $out_ptr

    ;; in_h (5)
    local.get $base
    i32.const 5
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $in_h

    ;; in_w (6)
    local.get $base
    i32.const 6
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $in_w

    ;; cin (7)
    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $cin

    ;; kh (9) = mul
    local.get $base
    i32.const 9
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $mul

    ;; kw (10) = shift
    local.get $base
    i32.const 10
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $shift

    ;; zx (24)
    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $zX

    ;; zy (26)
    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load
    local.set $zY

    ;; spatial_size = in_h * in_w
    local.get $in_h
    local.get $in_w
    i32.mul
    local.set $spatial_size

    ;; =========================
    ;; Loop canais
    ;; =========================
    i32.const 0
    local.set $c

    (block $exit_c
      (loop $loop_c

        local.get $c
        local.get $cin
        i32.ge_s
        br_if $exit_c

        ;; sum = 0
        i32.const 0
        local.set $sum

        ;; idx = 0
        i32.const 0
        local.set $idx

        (block $exit_spatial
          (loop $loop_spatial

            local.get $idx
            local.get $spatial_size
            i32.ge_s
            br_if $exit_spatial

            ;; val = load<i8>(in_ptr + idx*cin + c)
            local.get $in_ptr
            local.get $idx
            local.get $cin
            i32.mul
            local.get $c
            i32.add
            i32.add
            i32.load8_s
            local.set $val

            ;; sum += (val - zX)
            local.get $sum
            local.get $val
            local.get $zX
            i32.sub
            i32.add
            local.set $sum

            ;; idx++
            local.get $idx
            i32.const 1
            i32.add
            local.set $idx

            br $loop_spatial
          )
        )

        ;; mean = sum / spatial_size
        local.get $sum
        local.get $spatial_size
        i32.div_s
        local.set $val  ;; reutilizando $val como mean temporário

        ;; scaled = multiply_by_quantized_multiplier(mean, mul, shift)
        local.get $val
        local.get $mul
        local.get $shift
        call $multiply_by_quantized_multiplier_3
        local.set $scaled

        ;; scaled += zY
        local.get $scaled
        local.get $zY
        i32.add
        local.set $scaled

        ;; clamp [-128,127]
        local.get $scaled
        i32.const 127
        i32.gt_s
        (if (then i32.const 127 local.set $scaled))

        local.get $scaled
        i32.const -128
        i32.lt_s
        (if (then i32.const -128 local.set $scaled))

        ;; store
        local.get $out_ptr
        local.get $c
        i32.add
        local.get $scaled
        i32.store8

        ;; c++
        local.get $c
        i32.const 1
        i32.add
        local.set $c

        br $loop_c
      )
    )
  )

  (func $div_round_nearest (param $x i32) (param $d i32) (result i32)
    local.get $x
    i32.const 0
    i32.ge_s

    (if (result i32)
      (then
        local.get $x
        local.get $d
        i32.const 2
        i32.div_s
        i32.add

        local.get $d
        i32.div_s
      )
      (else
        local.get $x
        local.get $d
        i32.const 2
        i32.div_s
        i32.sub

        local.get $d
        i32.div_s
      )
    )
  )

  ;; ============================================================
  ;; FULLY_CONNECTED Layer - CORRIGIDO
  ;; ============================================================
  (func $fully_connected (export "fully_connected") (param $layer_idx i32)
    (local $base     i32)
    (local $in_ptr   i32)
    (local $out_ptr  i32)
    (local $cin      i32)
    (local $cout     i32)
    (local $wptr     i32)
    (local $bias_ptr i32)
    (local $mul_ptr  i32)
    (local $shift_ptr i32)
    (local $zx       i32)
    (local $zw       i32)
    (local $zy       i32)

    (local $oc       i32)
    (local $ic       i32)
    (local $acc      i32)
    (local $b        i32)
    (local $m        i32)
    (local $shift    i32)
    (local $input_val i32)
    (local $weight_val i32)
    (local $y        i32)

    ;; Carregar parâmetros
    local.get $layer_idx
    call $layerparam_base
    local.set $base  ;; 1800160

    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $in_ptr

    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_ptr

    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cin

    local.get $base
    i32.const 8
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cout

    local.get $base
    i32.const 19
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $wptr

    local.get $base
    i32.const 20
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $bias_ptr

    local.get $base
    i32.const 21
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $mul_ptr

    local.get $base
    i32.const 22
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $shift_ptr

    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zx

    local.get $base
    i32.const 25
    i32.const 2
    i32.shl
    i32.add
    i32.load
    align=4
    local.set $zw

    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zy

    ;; Loop por cada saída
    i32.const 0
    local.set $oc

    (block $exit_oc
      (loop $loop_oc
        local.get $oc
        local.get $cout
        i32.ge_s
        br_if $exit_oc

        ;; Carregar bias, multiplier e shift para este canal
        local.get $bias_ptr
        local.get $oc       ;; 0
        i32.const 2
        i32.shl
        i32.add
        i32.load align=4
        local.set $b

        local.get $mul_ptr
        local.get $oc       ;; 0
        i32.const 2
        i32.shl
        i32.add
        i32.load align=4
        local.set $m

        local.get $shift_ptr
        local.get $oc        ;; 0
        i32.const 2 i32.shl
        i32.add
        i32.load align=4
        local.set $shift

        ;; Acumulador começa com bias
        local.get $b
        local.set $acc        ;; -12122

        ;; Loop por cada entrada
        i32.const 0
        local.set $ic

        (block $exit_ic   ;; faz o acc de uma coluna inteira da matrix de pesos (1280 linhas)
          (loop $loop_ic  ;; for i in range(0, 1280)
            local.get $ic
            local.get $cin ;; 1280
            i32.ge_s
            br_if $exit_ic

            ;; Carregar input
            local.get $in_ptr
            local.get $ic     ;; 0
            i32.add
            i32.load8_s
            local.set $input_val ;; armazena 1280 valores de input ???

            ;; Carregar weight
            local.get $wptr
            local.get $oc   ;; 0
            local.get $cin  ;; 1280
            i32.mul
            local.get $ic
            i32.add
            i32.add
            i32.load8_s
            local.set $weight_val ;; -22 -19

            ;; acc += (input - zx) * (weight - zw)
            local.get $acc        ;; -12122
            local.get $input_val
            local.get $zx         ;; -128
            i32.sub               ;; SLOT01 - (-128) $input_val - $zx
            local.get $weight_val ;; -22
            local.get $zw         ;; 0
            i32.sub               ;; -22 - 0 $weight_val - $zw
            i32.mul               ;; (input - zx) * (weight - zw)
            i32.add               ;; acc + (input - zx) * (weight - zw)
            local.set $acc

            local.get $ic
            i32.const 1
            i32.add
            local.set $ic

            br $loop_ic
          )
        )

        local.get $acc
        local.get $m
        local.get $shift  ;; -11
        call $multiply_by_quantized_multiplier_3
        local.set $y      ;; 0

        ;; Adicionar zero point de saída
        local.get $y
        local.get $zy
        i32.add
        local.set $y

        ;; Clamp para int8 [-128, 127]
        local.get $y ;; -48
        i32.const 127
        i32.gt_s      ;; -48 > 127? false
        (if (then i32.const 127 local.set $y))

        local.get $y
        i32.const -128
        i32.lt_s
        (if (then i32.const -128 local.set $y))

        ;; Armazenar resultado
        local.get $out_ptr
        local.get $oc
        i32.add
        local.get $y
        i32.store8          ;; -48

        local.get $oc
        i32.const 1
        i32.add
        local.set $oc

        br $loop_oc
      )
    )
  )

  ;; ============================================================
  ;; SOFTMAX Layer - Implementação Melhorada
  ;; ============================================================
  (func $softmax (export "softmax") (param $layer_idx i32)
    (local $base     i32)
    (local $in_ptr   i32)
    (local $out_ptr  i32)
    (local $cin      i32)
    (local $zX       i32)
    (local $zY       i32)

    (local $i        i32)
    (local $max_val  i32)
    (local $val      i32)
    (local $sum      i32)
    (local $norm_val i32)

    (local $diff     i32)
    (local $exp_val  i32)
    (local $exp_val_acc  i32)

    i32.const 0
    local.set $exp_val_acc

    ;; Carregar parâmetros
    local.get $layer_idx
    call $layerparam_base
    local.set $base   ;; 1800276

    local.get $base
    i32.const 3
    i32.const 2
    i32.shl
    i32.add           ;; 1800276 + 3 * [4](2^2) = 1800288
    i32.load align=4  ;; carrega os indices 1800288 1800289 1800290 1800291
    local.set $in_ptr

    local.get $base
    i32.const 4
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $out_ptr ;; 1800512 -> SLOT0_BASE

    local.get $base
    i32.const 7
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $cin    ;; 1000

    local.get $base
    i32.const 24
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zX   ;; -45

    local.get $base
    i32.const 26
    i32.const 2
    i32.shl
    i32.add
    i32.load align=4
    local.set $zY  ;; -128

    ;; Encontrar valor máximo (para estabilidade numérica)
    i32.const -128
    local.set $max_val

    i32.const 0
    local.set $i

    (block $exit_max
      (loop $loop_max
        local.get $i    ;; 0...999
        local.get $cin  ;; 1000
        i32.ge_s
        br_if $exit_max

        local.get $in_ptr
        local.get $i      ;; 0
        i32.add
        i32.load8_s
        local.set $val    ;; pega os logits que estao na memoria

        local.get $val
        local.get $max_val ;; val > max_val
        i32.gt_s
        (if
          (then
            local.get $val
            local.set $max_val
          )
        )

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop_max
      )
    )

    i32.const 0
    local.set $i

    (block $exit_sum
      (loop $loop_sum

        local.get $i
        local.get $cin
        i32.ge_s
        br_if $exit_sum

        ;; carregar logit int8
        local.get $in_ptr
        local.get $i
        i32.add
        i32.load8_s
        local.set $val

        local.get $val
        local.get $max_val
        i32.sub            ;; Ex: -22
        i32.const 7877     ;; Nosso multiplicador fixo (equivale ao scale 0.12)
        i32.mul            ;; -22 * 7877 = -173294
        i32.const 16
        i32.shr_s          ;; Divide por 65536 -> -173294 >> 16 = -2.64... -> -2
        local.set $diff    ;; Agora o diff é -2, que sua tabela aceita!

        local.get $diff
        call $exp_q15
        local.set $exp_val

        ;; acumular soma
        local.get $exp_val_acc
        local.get $exp_val
        i32.add
        local.set $exp_val_acc

        ;; i++
        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop_sum
      )
    )

    i32.const 0
    local.set $i

    (block $exit_norm
      (loop $loop_norm

        local.get $i
        local.get $cin
        i32.ge_s
        br_if $exit_norm

        ;; repetir cálculo do diff
        local.get $in_ptr
        local.get $i
        i32.add
        i32.load8_s
        local.set $val

        local.get $val
        local.get $max_val
        i32.sub            ;; Ex: -22
        i32.const 7877     ;; Nosso multiplicador fixo (equivale ao scale 0.12)
        i32.mul            ;; -22 * 7877 = -173294
        i32.const 16
        i32.shr_s          ;; Divide por 65536 -> -173294 >> 16 = -2.64... -> -2
        local.set $diff    ;; Agora o diff é -2, que sua tabela aceita!

        local.get $diff
        call $exp_q15
        local.set $exp_val

        ;; q = (exp_val * 256) / sum
        local.get $exp_val
        i32.const 256
        i32.mul
        local.get $exp_val_acc
        i32.div_u
        local.set $norm_val

        ;; adicionar zero_point de saída
        local.get $norm_val
        local.get $zY
        i32.add
        local.set $norm_val

        ;; CLAMP INT8 [-128, 127]
        local.get $norm_val
        i32.const 127
        i32.gt_s
        (if
          (then
            i32.const 127
            local.set $norm_val
          )
        )

        local.get $norm_val
        i32.const -128
        i32.lt_s
        (if
          (then
            i32.const -128
            local.set $norm_val
          )
        )

        ;; armazenar
        local.get $out_ptr
        local.get $i
        i32.add
        local.get $norm_val
        i32.store8

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop_norm
      )
    )
  )

  (func $rgb565_to_rgb888 (export "rgb565_to_rgb888") (param $layer_idx i32)
    (local $base     i32)
    (local $in_ptr   i32)
    (local $out_ptr  i32)
    (local $total    i32)    ;; in_h * in_w (número de pixels)
    (local $fmt_addr i32)    ;; endereço onde host escreveu o formato
    (local $sentinel i32)    ;; valor sentinela (kh = 65 para RGB565)
    (local $i        i32)    ;; índice do pixel atual
    (local $src      i32)    ;; endereço do pixel de entrada
    (local $dst      i32)    ;; endereço do pixel de saída
    (local $pixel    i32)    ;; valor RGB565 lido (16 bits)
    (local $r        i32)
    (local $g        i32)
    (local $b        i32)

    local.get $layer_idx
    call $layerparam_base
    local.set $base

    ;; in_ptr = campo [3]
    local.get $base
    i32.const 12        ;; 3 * 4
    i32.add
    i32.load
    local.set $in_ptr

    ;; out_ptr = campo [4]
    local.get $base
    i32.const 16        ;; 4 * 4
    i32.add
    i32.load
    local.set $out_ptr

    ;; total = in_h * in_w  (campos [5] e [6])
    local.get $base
    i32.const 20        ;; 5 * 4
    i32.add
    i32.load
    local.get $base
    i32.const 24        ;; 6 * 4
    i32.add
    i32.load
    i32.mul
    local.set $total

    ;; fmt_addr = flags = campo [2]
    local.get $base
    i32.const 8         ;; 2 * 4
    i32.add
    i32.load
    local.set $fmt_addr

    ;; sentinel = kh = campo [9]
    local.get $base
    i32.const 36        ;; 9 * 4
    i32.add
    i32.load
    local.set $sentinel

    ;; i = 0
    i32.const 0
    local.set $i

    ;; if mem[fmt_addr] == sentinel → converte RGB565; senão copia RGB888
    local.get $fmt_addr
    i32.load8_u
    local.get $sentinel
    i32.eq
    (if
      (then
        ;; ── caminho RGB565 → RGB888 ──
        (block $break_rgb565
          (loop $loop_rgb565
            local.get $i
            local.get $total
            i32.ge_u
            br_if $break_rgb565

            ;; src = in_ptr + i * 2   (RGB565: 2 bytes/pixel)
            local.get $in_ptr
            local.get $i
            i32.const 2
            i32.mul
            i32.add
            local.set $src

            ;; dst = out_ptr + i * 3  (RGB888: 3 bytes/pixel)
            local.get $out_ptr
            local.get $i
            i32.const 3
            i32.mul
            i32.add
            local.set $dst

            ;; pixel = mem16[src]
            local.get $src
            i32.load16_u
            local.set $pixel

            ;; R5 → R8:  r = (pixel >> 11) & 0x1F → escala para 8 bits
            ;; R8 = (R5 << 3) | (R5 >> 2)
            local.get $pixel
            i32.const 11
            i32.shr_u
            i32.const 0x1F
            i32.and
            local.tee $r
            i32.const 3
            i32.shl
            local.get $r
            i32.const 2
            i32.shr_u
            i32.or
            local.set $r

            ;; G6 → G8:  g = (pixel >> 5) & 0x3F → escala para 8 bits
            ;; G8 = (G6 << 2) | (G6 >> 4)
            local.get $pixel
            i32.const 5
            i32.shr_u
            i32.const 0x3F
            i32.and
            local.tee $g
            i32.const 2
            i32.shl
            local.get $g
            i32.const 4
            i32.shr_u
            i32.or
            local.set $g

            ;; B5 → B8:  b = pixel & 0x1F → escala para 8 bits
            ;; B8 = (B5 << 3) | (B5 >> 2)
            local.get $pixel
            i32.const 0x1F
            i32.and
            local.tee $b
            i32.const 3
            i32.shl
            local.get $b
            i32.const 2
            i32.shr_u
            i32.or
            local.set $b

            ;; mem8[dst+0] = r
            local.get $dst
            local.get $r
            i32.store8

            ;; mem8[dst+1] = g
            local.get $dst
            i32.const 1
            i32.add
            local.get $g
            i32.store8

            ;; mem8[dst+2] = b
            local.get $dst
            i32.const 2
            i32.add
            local.get $b
            i32.store8

            ;; i++
            local.get $i
            i32.const 1
            i32.add
            local.set $i

            br $loop_rgb565
          )
        )
      )
      (else
        ;; ── caminho RGB888: copia SLOT0 → SLOT1 (total * 3 bytes) ──
        (block $break_copy
          (loop $loop_copy
            local.get $i
            local.get $total
            i32.const 3
            i32.mul
            i32.ge_u
            br_if $break_copy

            local.get $out_ptr
            local.get $i
            i32.add
            local.get $in_ptr
            local.get $i
            i32.add
            i32.load8_u
            i32.store8

            local.get $i
            i32.const 1
            i32.add
            local.set $i

            br $loop_copy
          )
        )
      )
    )
  )

  ;; ============================================================
  ;; Dispatcher - Executa a camada correta baseado no layer_idx
  ;; ============================================================
  (func $run_layer (export "run_layer") (param $layer_idx i32)
    (local $base i32)
    (local $op_type i32)

    ;; =========================================
    ;; Carregar op_type da LayerParam
    ;; =========================================
    local.get $layer_idx
    call $layerparam_base
    local.set $base

    local.get $base
    i32.load align=4
    local.set $op_type

    ;; =========================================
    ;; 1 = CONV2D
    ;; =========================================
    local.get $op_type
    i32.const 1
    i32.eq
    (if
      (then
        ;;local.get $layer_idx
        local.get $layer_idx
        call $conv2d
        return
      )
    )

    ;; =========================================
    ;; 2 = DEPTHWISE
    ;; =========================================
    local.get $op_type
    i32.const 2
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $depthwise_conv2d
        return
      )
    )

    ;; =========================================
    ;; 3 = FULLY_CONNECTED
    ;; =========================================
    local.get $op_type
    i32.const 3
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $fully_connected
        return
      )
    )

    ;; =========================================
    ;; 4 = ADD
    ;; =========================================
    local.get $op_type
    i32.const 4
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $add
        return
      )
    )

    ;; =========================================
    ;; 5 = MEAN
    ;; =========================================
    local.get $op_type
    i32.const 5
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $mean
        return
      )
    )

    ;; =========================================
    ;; 6 = SOFTMAX
    ;; =========================================
    local.get $op_type
    i32.const 6
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $softmax
        return
      )
    )

    ;; =========================================
    ;; 7 = QUANTIZE
    ;; =========================================
    local.get $op_type
    i32.const 7
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $quantize
        return
      )
    )

    ;; =========================================
    ;; 8 = RGB565_TO_RGB888
    ;; =========================================
    local.get $op_type
    i32.const 8
    i32.eq
    (if
      (then
        local.get $layer_idx
        call $rgb565_to_rgb888
        return
      )
    )
  )

  ;; ============================================================
  ;; Executa toda a rede MobileNetV2
  ;; ============================================================
  (func $run_mobilenetv2 (export "run_mobilenetv2") (result i32)
    (local $i i32)

    ;; sinaliza: "não escreva imagem agora, estou processando"
    global.get $FLAG_BASE
    i32.const 1
    i32.store

    i32.const 0
    local.set $i

    (block $exit
      (loop $loop

        local.get $i
        global.get $NUM_LAYERS
        i32.ge_s
        br_if $exit

        local.get $i
        call $run_layer

        local.get $i
        i32.const 1
        i32.add
        local.set $i

        br $loop
      )
    )

    ;; sinaliza: "terminei, pode escrever nova imagem"
    global.get $FLAG_BASE
    i32.const 0
    i32.store

    i32.const 0
  )

  ;; Função de debug para verificar memória
(func $debug_memory (export "debug_memory") (param $ptr i32) (param $size i32) (result i32)
  (local $i i32)
  (local $sum i32)
  (local $val i32)

  i32.const 0
  local.set $sum

  i32.const 0
  local.set $i

  (block $exit
    (loop $loop
      local.get $i
      local.get $size
      i32.ge_s
      br_if $exit

      local.get $ptr
      local.get $i
      i32.add
      i32.load8_s
      local.set $val

      local.get $sum
      local.get $val
      local.get $val
      i32.mul
      i32.add
      local.set $sum

      local.get $i
      i32.const 1
      i32.add
      local.set $i

      br $loop
    )
  )

  local.get $sum
)


  @@DATA_SEGMENTS@@

)
