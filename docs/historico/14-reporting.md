[English](14-reporting.md) | [Português (Brasil)](14-relatorios.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in the Portuguese edition.

# 14 — Saving reports (`reporting.py`)

## 1. Module purpose

`extractor/reporting.py` has a single responsibility:

```text
receive prepared text
        ↓
ensure the destination directory exists
        ↓
save that text to a UTF-8 file
```

Its code is:

```python
from pathlib import Path


def save_report(
    path: Path,
    content: str,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )
```

Despite its small size, this module maintains an important separation:

```text
extraction/calculation modules
        ↓
produce structured data

*_to_text() functions
        ↓
produce text

reporting.py
        ↓
save text to disk
```

---

# 2. Exact responsibility

`reporting.py` does not decide:

```text
what the report should contain

how to format weights

how to show quantization

how to describe memory

how to present LayerParams
```

Those decisions belong to the individual modules.

For example:

```text
weights.py
    ↓
weights_bias_to_text()

quantization.py
    ↓
quantization_to_text()

memory.py
    ↓
slot_memory_to_text()
    ↓
parameter_layout_to_text()
    ↓
final_memory_layout_to_text()

layer_params.py
    ↓
layer_params_to_text()

params_blob.py
    ↓
params_blob_to_text()
```

`reporting.py` receives only the final results of these functions.

---

# 3. Architectural separation

The adopted architecture is:

```text
DATA
  ↓
Python structure

PRESENTATION
  ↓
string

PERSISTENCE
  ↓
file
```

More concretely:

```text
extract_weights_and_bias()
        ↓
dict
        ↓
weights_bias_to_text()
        ↓
str
        ↓
save_report()
        ↓
.txt file
```

This avoids mixing:

```text
calculation
formatting
I/O
```

in the same function.

---

# 4. Importing `Path`

The module imports:

```python
from pathlib import Path
```

`Path` belongs to Python's standard library.

It provides an object-oriented abstraction for file and directory paths.

---

# 5. Why use `Path`?

Instead of manipulating paths as strings:

```python
"reports/weights.txt"
```

we can work with:

```python
Path("reports/weights.txt")
```

This allows operations such as:

```python
path.parent
```

and:

```python
path.write_text(...)
```

directly.

---

# 6. Example

For:

```python
path = Path(
    "reports/weights.txt"
)
```

we have:

```python
path.parent
```

equal to:

```text
reports
```

---

# 7. Signature of `save_report()`

The function is declared as:

```python
def save_report(
    path: Path,
    content: str,
):
```

It receives two arguments.

---

# 8. `path`

The first parameter represents:

```text
file path
that will be created or overwritten
```

Example:

```python
Path(
    "reports/quantization.txt"
)
```

---

# 9. `content`

The second parameter contains:

```text
the complete text
to be written to the file
```

Its type hint is:

```python
str
```

The function therefore expects textual content.

---

# 10. Call example

```python
save_report(
    Path("reports/weights.txt"),
    weights_bias_to_text(
        weights_bias
    ),
)
```

The flow is:

```text
weights_bias
     ↓
weights_bias_to_text()
     ↓
string
     ↓
save_report()
     ↓
reports/weights.txt
```

---

# 11. First operation: parent directory

The function starts with:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

---

# 12. `path.parent`

This attribute returns the directory where the file will be saved.

Example:

```python
path = Path(
    "reports/memory/final.txt"
)
```

Then:

```python
path.parent
```

represents:

```text
reports/memory
```

---

# 13. `mkdir()`

The method:

```python
mkdir()
```

creates a directory.

Here it is called on the file's parent directory.

---

# 14. Why create the directory?

Without this step, attempting to write:

```text
reports/memory/final.txt
```

would fail if:

```text
reports/memory/
```

did not already exist.

---

# 15. `parents=True`

The option:

```python
parents=True
```

also allows creating intermediate directories.

---

# 16. Example

Consider:

```python
Path(
    "reports/memory/final.txt"
)
```

and suppose neither directory exists:

```text
reports/
reports/memory/
```

With:

```python
parents=True
```

Python can create:

```text
reports/
    └── memory/
```

automatically.

---

# 17. Without `parents=True`

If only:

```text
reports/
```

were absent, directly attempting to create:

```text
reports/memory/
```

could fail because its parent directory would also be missing.

This option handles that chain.

---

# 18. `exist_ok=True`

The second option is:

```python
exist_ok=True
```

This means:

```text
if the directory already exists,
do not treat that as an error
```

---

# 19. Example

On the first run:

```text
reports/
```

may be created.

On the second run:

```text
reports/
```

already exists.

Even so:

```python
mkdir(
    parents=True,
    exist_ok=True,
)
```

continues normally.

---

# 20. Idempotent directory creation

This part of the function can run repeatedly without requiring the caller to know in advance:

```text
does the directory exist?
```

The helper handles this itself.

---

# 21. Second operation: `write_text()`

Then:

```python
path.write_text(
    content,
    encoding="utf-8",
)
```

is used to write the contents.

---

# 22. What does `write_text()` do?

The method writes a string into a text file.

Conceptually:

```text
content
   ↓
UTF-8 encoding
   ↓
bytes
   ↓
file on disk
```

---

# 23. `encoding="utf-8"`

Encoding is explicitly set:

```python
encoding="utf-8"
```

This avoids depending on the operating system's default encoding.

---

# 24. Why does this matter?

Reports use Portuguese text and may contain characters such as:

```text
á
ã
ç
é
ó
```

With UTF-8, these characters have a predictable representation.

---

# 25. Example

A line such as:

```text
Quantidade de parâmetros de quantização
```

can be saved correctly regardless of the machine's regional settings.

---

# 26. Operating system independence

Without explicit encoding, behavior could depend on environment defaults.

With:

```python
encoding="utf-8"
```

the project explicitly defines its text format.

---

# 27. Existing file

`write_text()` opens the file for writing.

If the file already exists, its previous contents are replaced.

---

# 28. Consequence

Running again:

```python
save_report(
    Path("reports/weights.txt"),
    novo_conteudo,
)
```

updates the report.

The function does not:

```text
append to the previous file
```

It writes the supplied content as the report's current contents.

---

# 29. Why this suits generated reports

Files in:

```text
reports/
```

represent the current extractor run's state.

It therefore makes sense that:

```text
new run
    ↓
new report
    ↓
replaces previous report
```

---

# 30. The function does not add a newline

`save_report()` writes exactly:

```python
content
```

It does not automatically append:

```text
\n
```

at the end.

---

# 31. Consequence

If a report should end in a newline, that decision belongs to:

```text
*_to_text()
```

or to the supplied content.

---

# 32. The function does not modify text

It does not perform:

```text
strip()

replace()

formatting

line conversion

indentation
```

The received text is passed directly to:

```python
write_text()
```

---

# 33. This preserves the separation of responsibilities

The function does not need to understand the contents.

To it, these strings are equivalent:

```text
weight report

memory report

quantization report

any other text
```

---

# 34. It does not know the model

`save_report()` does not receive:

```text
model

subgraph

tensor

operator
```

It therefore has no TFLite dependency.

---

# 35. It does not know the data structure

It also does not receive:

```text
weight_records

layer_params

regions

mul_vals
```

These structures have already been converted into text.

---

# 36. Weight example

```text
weights.py
    ↓
extract_weights_and_bias()
    ↓
dict

weights_bias_to_text()
    ↓
str

reporting.py
    ↓
file
```

---

# 37. Quantization example

```text
quantization.py
    ↓
extract_quantization_parameters()
    ↓
dict

quantization_to_text()
    ↓
str

reporting.py
    ↓
file
```

---

# 38. Memory example

```text
memory.py
    ↓
calculate_final_memory_layout()
    ↓
dict

final_memory_layout_to_text()
    ↓
str

reporting.py
    ↓
file
```

---

# 39. `LayerParam` example

```text
layer_params.py
    ↓
build_layer_params()
    ↓
list[dict]

layer_params_to_text()
    ↓
str

reporting.py
    ↓
file
```

---

# 40. `params_blob` example

```text
params_blob.py
    ↓
build_params_blob()
    ↓
dict

params_blob_to_text()
    ↓
str

reporting.py
    ↓
file
```

---

# 41. Role of `main.py`

These parts are normally combined by:

```text
main.py
```

For example, conceptually:

```python
report = weights_bias_to_text(
    weights_bias
)

save_report(
    REPORTS_DIR / "weights.txt",
    report,
)
```

---

# 42. Responsibility of `main.py`

`main.py` decides:

```text
which report to generate

which filename to use

when to save it
```

`reporting.py` only performs persistence.

---

# 43. Relationship with `config.py`

`config.py` has:

```python
REPORTS_DIR = Path(
    "reports"
)
```

This configuration can be combined with specific names.

Example:

```python
REPORTS_DIR / "weights.txt"
```

results in:

```text
reports/weights.txt
```

---

# 44. The module does not import `REPORTS_DIR`

This is an important decision.

`reporting.py` does not do:

```python
from extractor.config import (
    REPORTS_DIR,
)
```

---

# 45. Why is this useful?

Because the function is not tied to:

```text
reports/
```

It can save to any path supplied by the caller.

---

# 46. Example

The same function can receive:

```python
Path(
    "reports/weights.txt"
)
```

or:

```python
Path(
    "debug/current-run.txt"
)
```

or:

```python
Path(
    "/tmp/model-report.txt"
)
```

provided the environment allows writing.

---

# 47. Configuration outside the helper

Therefore:

```text
where to save?
    ↓
caller's decision

how to save?
    ↓
reporting.py
```

---

# 48. Single responsibility principle

This module clearly illustrates the principle:

```text
one function
    ↓
one responsibility
```

The function performs exactly two operations needed to save a report:

```text
1. create directory

2. write file
```

---

# 49. Why do these two operations belong together?

Saving a file to an arbitrary path normally requires its directory to exist.

Thus:

```text
ensure destination exists
+
write file
```

form one conceptual operation:

```text
save report
```

---

# 50. What should not go here?

It would be inappropriate to add things such as:

```text
calculate total weights

format quantization table

find largest tensor

calculate MEM_PAGES

convert parameter bytes
```

These functions belong to the domain modules.

---

# 51. It should not generate WAT either

The module has no relationship with:

```text
wat_generator.py
```

except that both perform file I/O.

Their contents and responsibilities differ.

---

# 52. Comparison with `wat_generator.py`

`wat_generator.py`:

```text
receives template
replaces placeholders
inserts blobs
generates WAT contents
saves artifact
```

`reporting.py`:

```text
receives prepared text
saves text
```

---

# 53. Why not use `print()` for everything?

The project separates:

```text
brief execution output
    ↓
print()
```

from:

```text
detailed diagnostic information
    ↓
reports/
```

This avoids filling the terminal with hundreds or thousands of lines.

---

# 54. Example

The terminal may show only:

```text
Modelo carregado.
68 camadas processadas.
WAT gerado com sucesso.
```

While files may contain:

```text
all tensors
all weights
all multipliers
all offsets
all LayerParams
```

---

# 55. Benefit for the project

This division makes execution:

```text
readable
```

without losing:

```text
detailed traceability
```

---

# 56. Reports as diagnostic artifacts

Files saved by this module are not directly part of inference.

The runtime does not read:

```text
reports/*.txt
```

---

# 57. Consequence

Deleting reports after generation does not change:

```text
weights_raw

params_blob

model.wat

model.wasm
```

They are inspection aids.

---

# 58. They remain important for validation

They answer:

```text
which tensor determined SLOT_BYTES?

which weight started at a given offset?

which multiplier was calculated?

which LayerParam received a given pointer?

which memory region starts at a given address?
```

Without inserting debug information into WAT.

---

# 59. This separation improved WAT

One refactoring principle is to avoid turning:

```text
generated/model.wat
```

into a mixture of:

```text
code
+
debug dump
+
report
```

---

# 60. Desired structure

```text
generated/model.wat
    ↓
executable/textual artifact


reports/
    ↓
diagnostic artifacts


docs/
    ↓
architecture explanation
```

---

# 61. Three artifact types

It is important to distinguish:

### `docs/`

Explains:

```text
how the code works
```

---

### `reports/`

It shows:

```text
what happened
in a particular run
with a particular model
```

---

### `generated/`

Contains:

```text
generated artifact
for execution/compilation
```

---

# 62. Example of the difference

`docs/09-memory-layout.md` explains:

```text
how MEM_PAGES is calculated
```

A report could show:

```text
MEM_PAGES = 17
```

for a concrete model.

---

# 63. Another example

`docs/08-quantization.md` explains:

```text
how multiplier and shift are calculated
```

While:

```text
reports/quantization.txt
```

may show:

```text
op 12:
multiplier = ...
shift = ...
```

from the current run.

---

# 64. `reporting.py` does not mix these layers

It only knows:

```text
I have a string

I have a destination

I will save it
```

---

# 65. Error handling

The function has no:

```python
try:
    ...
except:
    ...
```

---

# 66. Consequence

Filesystem errors propagate naturally to the caller.

Examples:

```text
no write permission

invalid path

disk full

incompatible destination
```

---

# 67. Why is this reasonable?

If a requested report cannot be saved, hiding the error would hinder diagnosis.

The current implementation prefers:

```text
actual error
    ↓
exception
    ↓
caller notices
```

---

# 68. No silent fallback

The function does not do:

```text
failed to save
    ↓
ignore
```

or:

```text
failed
    ↓
print and continue
```

The I/O error remains visible.

---

# 69. Function return value

There is no:

```python
return ...
```

explicitly.

Thus, in Python, the return value is:

```python
None
```

---

# 70. Why not return the path?

The current implementation does not need it.

The caller already knows:

```python
path
```

because it supplied the argument.

---

# 71. Why not return the byte count?

The current flow does not require it either.

It could be added if useful later, but the function remains minimal for now.

---

# 72. Type hints

The signature uses:

```python
path: Path
```

and:

```python
content: str
```

These type hints document the expected interface.

---

# 73. A type hint is not runtime validation

Python does not automatically prevent:

```python
save_report(
    "reports/a.txt",
    "abc",
)
```

just because the type hint says:

```python
Path
```

---

# 74. Practical consequence

The implementation accesses:

```python
path.parent
```

An ordinary string:

```python
"reports/a.txt"
```

does not have this interface.

Current usage expects the caller to provide a `Path`.

---

# 75. Possible future generalization

Internal normalization would be possible:

```python
path = Path(path)
```

as `wat_generator.py` does.

That is not the current implementation.

---

# 76. The current interface is deliberately simple

```text
input:
Path + str

output:
file
```

---

# 77. Complete example

Suppose:

```python
report_path = Path(
    "reports/memory.txt"
)

report_content = (
    "MEM_END = 1097072\n"
    "MEM_PAGES = 17"
)
```

The call:

```python
save_report(
    report_path,
    report_content,
)
```

executes:

```text
reports/
    ↓
create if needed

reports/memory.txt
    ↓
write UTF-8
```

---

# 78. Conceptual result

```text
reports/
└── memory.txt
```

with:

```text
MEM_END = 1097072
MEM_PAGES = 17
```

These values are only example contents.

---

# 79. Running again

If the file already contains:

```text
MEM_PAGES = 16
```

and the function is called again with:

```text
MEM_PAGES = 17
```

the file is replaced.

---

# 80. No automatic history

The function does not create:

```text
memory-1.txt

memory-2.txt

memory-2026-09-27.txt
```

automatically.

If reports need versioning, the caller must decide the filename.

---

# 81. This keeps the helper neutral

The function does not need to know:

```text
dates

model names

versions

runs
```

These decisions remain outside it.

---

# 82. Relationship with reproducibility

Because each module produces text from calculated structures and `save_report()` writes it unchanged, reports can be used to compare runs.

For example:

```text
run A
    ↓
quantization.txt

run B
    ↓
quantization.txt
```

and then compare:

```text
offsets
multipliers
shifts
Q6
```

---

# 83. The module does not perform comparison

That activity is outside its responsibility.

`reporting.py` only saves results.

---

# 84. Relationship with tests

This helper is simple enough to describe through three main cases:

```text
1. directory does not exist
    → create and write

2. directory exists
    → just write

3. file exists
    → overwrite
```

---

# 85. Possible test 1

```text
reports_test/
does not exist

save_report(
    reports_test/a.txt,
    "abc"
)

expected result:
directory created
file created
contents = "abc"
```

---

# 86. Possible test 2

```text
directory already exists

save_report(...)

Result:
no mkdir error
```

thanks to:

```python
exist_ok=True
```

---

# 87. Possible test 3

Previous file:

```text
abc
```

New call:

```text
xyz
```

Result:

```text
xyz
```

rather than:

```text
abcxyz
```

---

# 88. No need to test domain logic here

It would not make sense to test:

```text
correct multiplier

correct SLOT_BYTES

correct offset
```

in `reporting.py`.

Those checks belong to the respective modules.

---

# 89. A small function is desirable

There is nothing wrong with a file containing only:

```text
one function
```

when it represents a distinct architectural responsibility.

---

# 90. Avoiding excessive abstraction

There is currently no need to create:

```text
ReportManager

ReportWriter

ReportFactory

BaseReport
```

The required operation is very simple.

The function:

```python
save_report()
```

solves the problem directly.

---

# 91. Why not place this in `main.py`?

One could repeat:

```python
path.parent.mkdir(...)
path.write_text(...)
```

for every report.

That would introduce duplication.

---

# 92. Problem example

Without the helper:

```python
weights_path.parent.mkdir(...)
weights_path.write_text(...)

memory_path.parent.mkdir(...)
memory_path.write_text(...)

quant_path.parent.mkdir(...)
quant_path.write_text(...)
```

---

# 93. With `save_report()`

The orchestrator code becomes:

```python
save_report(
    weights_path,
    weights_text,
)

save_report(
    memory_path,
    memory_text,
)

save_report(
    quant_path,
    quant_text,
)
```

---

# 94. Benefit

The policy:

```text
create directory automatically
+
UTF-8
```

is defined in one place.

---

# 95. If the policy changes

Suppose all reports need a different persistence rule in the future.

The change can be centralized in:

```text
reporting.py
```

without editing each module.

---

# 96. Formatting remains decentralized

This is important.

Centralizing persistence does not mean centralizing every report.

We still have:

```text
weights_bias_to_text()
quantization_to_text()
layer_params_to_text()
...
```

alongside the modules that understand their own data.

---

# 97. Why is this division useful?

Who best understands:

```text
weight_records
```

is:

```text
weights.py
```

Who best understands:

```text
regions
MEM_END
MEM_PAGES
```

is:

```text
memory.py
```

Who best understands:

```text
LayerParams
```

is:

```text
layer_params.py
```

None of them needs to know repetitive persistence details.

---

# 98. Report architecture flow

```text
┌───────────────────────────┐
│       graph.py            │
│       graph_to_text()     │
└─────────────┬─────────────┘
              │
              │
┌─────────────▼─────────────┐
│       slots.py            │
│ slot_allocation_to_text() │
└─────────────┬─────────────┘
              │
              │
┌─────────────▼─────────────┐
│      weights.py           │
│ weights_bias_to_text()    │
└─────────────┬─────────────┘
              │
              │
           ... etc.
              │
              ▼
┌───────────────────────────┐
│      reporting.py         │
│                           │
│      save_report()        │
└─────────────┬─────────────┘
              │
              ▼
          reports/
```

---

# 99. Relationship with project structure

```text
master-degree-project/
│
├── extractor/
│   ├── reporting.py
│   └── ...
│
├── docs/
│   └── documentation
│
├── reports/
│   └── textual results
│
└── generated/
    └── generated artifacts
```

`reporting.py` is the simple interface between:

```text
extractor/
```

and:

```text
reports/
```

---

# 100. Central principle

The adopted design can be summarized as:

```text
structured data are the source of truth
```

rather than:

```text
report text is the source of truth
```

---

# 101. Consequence

No subsequent stage should:

```text
open report.txt
    ↓
parse text
    ↓
recover offsets
```

---

# 102. Correct flow

```text
Python dict
   │
   ├──→ next pipeline stage
   │
   └──→ *_to_text()
            │
            ▼
       save_report()
```

---

# 103. Incorrect flow

```text
dict
 ↓
text
 ↓
file
 ↓
read file
 ↓
parse text
 ↓
continue pipeline
```

This would turn a human-readable representation into an internal protocol, which is undesirable.

---

# 104. A report is a side output

We can represent it as:

```text
                  ┌──→ report
                  │
structured data   │
                  └──→ next stage
```

The report is an auxiliary output.

It is outside the calculation path.

---

# 105. Example

```text
weights_bias
      │
      ├──────────────→ memory.py
      │
      └→ to_text()
          ↓
       report
```

`memory.py` receives:

```text
weights_bias
```

directly.

It never reads:

```text
weights.txt
```

---

# 106. This improves robustness

Report formats may change:

```text
spacing

headers

names

visual alignment
```

without breaking the pipeline.

---

# 107. Example

We can change:

```text
Total de bytes de pesos: 1234
```

to:

```text
Pesos totais = 1234 bytes
```

without affecting any calculation stage.

---

# 108. This confirms the role of reports

They exist for:

```text
humans
```

not for:

```text
internal communication between modules
```

---

# 109. `save_report()` as the last step of the branch

The sequence is:

```text
data
 ↓
to_text()
 ↓
save_report()
 ↓
end
```

No pipeline stage depends on the return value.

---

# 110. Minimal dependencies

`reporting.py` depends only on:

```text
pathlib
```

It does not depend on:

```text
tflite

numpy

struct

re

other extractor modules
```

---

# 111. Benefit

This makes the helper:

```text
simple

isolated

reusable

easy to test
```

---

# 112. No global state

There are no:

```text
mutable global variables

cache

permanently open file

singleton
```

Each call works independently.

---

# 113. No open handles retained

`Path.write_text()` handles opening and closing the file internally.

The module does not need to do this manually:

```python
open(...)
close()
```

---

# 114. Conceptually equivalent version

The code could be written approximately as:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with path.open(
    "w",
    encoding="utf-8",
) as file:
    file.write(content)
```

`write_text()` simply provides a shorter form for this case.

---

# 115. Why is the current version better?

For such a simple function:

```python
path.write_text(...)
```

makes the intention immediate:

```text
write this text to this path
```

without unnecessary boilerplate.

---

# 116. No append

It is also clear that the objective is to write a complete file, rather than progressively add fragments.

---

# 117. Report sizes

Even if some reports are large, the function receives:

```text
content
```

as a complete string and then writes everything.

---

# 118. Consequence

The current design assumes reports are small enough to exist in memory as complete strings.

For this project's reports, that is consistent with the current implementation.

---

# 119. It is not a logger

`save_report()` should not be confused with:

```text
logging
```

---

# 120. Difference

A logger normally handles:

```text
incremental messages

levels:
INFO
DEBUG
WARNING
ERROR

timestamps

handlers
```

`save_report()` handles:

```text
a complete document
```

---

# 121. Example

It is not intended to use:

```python
save_report(
    path,
    "Processando layer 1..."
)
```

repeatedly during the loop.

That would overwrite the file on every call.

---

# 122. Intended use

The correct pattern is:

```text
process everything
    ↓
assemble the complete report
    ↓
save once
```

---

# 123. Relationship with `print()`

We can simultaneously have:

```python
print(
    "WAT gerado com sucesso."
)
```

and:

```python
save_report(
    report_path,
    report_content,
)
```

The two outputs have different audiences and levels of detail.

---

# 124. Terminal

Ideal for:

```text
operational summary
```

---

# 125. Reports

Ideal for:

```text
technical details

auditing

comparison

debug

execution documentation
```

---

# 126. There is no conflict between them

The existence of `reports/` does not prevent `main.py` from printing a short summary.

The principle is simply to avoid:

```text
hundreds of lines
```

in the terminal.

---

# 127. Directory handling

The call:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

also makes each report independent.

`main.py` does not need to perform:

```python
REPORTS_DIR.mkdir(...)
```

for all reports in advance.

---

# 128. `main.py` could still do so

But it would be redundant.

Each `save_report()` call already ensures its own directory precondition.

---

# 129. Example with future subdirectories

If the project later wants:

```text
reports/
├── graph/
├── quantization/
└── memory/
```

the function continues working without changes.

---

# 130. Example

```python
save_report(
    Path(
        "reports/quantization/"
        "parameters.txt"
    ),
    content,
)
```

automatically creates:

```text
reports/quantization/
```

if needed.

---

# 131. This flexibility comes from `parents=True`

The helper is therefore not limited to a single directory level.

---

# 132. Possible future improvement: return the path

It might be useful to do:

```python
return path
```

to allow:

```python
saved_path = save_report(...)
```

This is not currently needed because the caller already has that value.

---

# 133. Possible future improvement: normalize `Path`

It could also start with:

```python
path = Path(path)
```

allowing it to accept:

```text
Path

or a string
```

The current signature explicitly requests:

```text
Path
```

and the implementation follows that expectation.

---

# 134. Possible future improvement: atomic writing

For more critical scenarios, one could:

```text
write temporary file
        ↓
atomic rename
        ↓
final file
```

This would prevent partially written files if interrupted.

---

# 135. Is that needed here?

For current diagnostic reports, it would probably add unnecessary complexity.

The current function serves its simple role well.

---

# 136. Possible future improvement: return metadata

It could also return:

```text
path

bytes written
```

Again, the current pipeline does not require it.

---

# 137. Possible future improvement: different formats

If the project later generates:

```text
JSON

CSV

Markdown
```

`save_report()` could still save any of them, provided the content arrives as:

```text
str
```

---

# 138. Markdown example

```python
save_report(
    Path(
        "reports/memory.md"
    ),
    markdown_text,
)
```

would work unchanged.

---

# 139. CSV example

```python
save_report(
    Path(
        "reports/layers.csv"
    ),
    csv_text,
)
```

as well.

---

# 140. The extension is not interpreted

The function does not check:

```text
.txt

.md

.csv
```

Contents and extension are the caller's responsibility.

---

# 141. This keeps the helper generic

Its contract remains:

```text
Path + text
    ↓
UTF-8 file
```

---

# 142. Expected invariants

Before the call:

```text
path is a usable Path

content is a string
```

---

# 143. After a successful call

We should have:

```text
path.parent exists

path exists

file contents
match content
```

encoded in UTF-8.

---

# 144. What does the function not guarantee?

It does not guarantee:

```text
contents are correct

the report is complete

calculated values are correct

the file follows a particular format
```

Those properties belong to the functions producing `content`.

---

# 145. Content errors versus persistence errors

It is important to separate:

```text
incorrect multiplier in the report
    ↓
problem in quantization.py
```

from:

```text
unable to create quantization.txt
    ↓
I/O/reporting problem
```

---

# 146. This helps diagnosis

Each module has a clear responsibility.

---

# 147. Complete reporting flow

```text
                       DATA
                         │
                         ▼
              processing function
                         │
                         ▼
                Python structure
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
      next pipeline             *_to_text()
      stage                          │
                                     ▼
                                  string
                                     │
                                     ▼
                              save_report()
                                     │
                                     ▼
                                  reports/
```

---

# 148. Relationship with the project's general approach

Refactoring follows the principle:

```text
calculate
    ↓
return structure
    ↓
validate
    ↓
serialize
    ↓
generate artifact
```

Reports accompany this flow without controlling it.

---

# 149. Reports do not become a data source

This is an important architectural rule:

```text
never parse reports
to retrieve pipeline data
```

The source of truth remains:

```text
dictionaries

lists

bytes

structured objects
```

---

# 150. Maintenance consequence

We can change the human-facing presentation without risking changes to inference behavior.

This allows freely improving reports.

---

# 151. Example

Today:

```text
Total de tensors de pesos: 54
```

tomorrow it could be:

```text
Pesos extraídos: 54 tensors
```

without any impact on WAT.

---

# 152. This also helps documentation

Files in:

```text
docs/
```

can explain report meanings.

Whereas:

```text
reports/
```

show concrete values.

---

# 153. Final project structure

```text
master-degree-project/
│
├── extractor/
│   │
│   ├── graph.py
│   ├── slots.py
│   ├── weights.py
│   ├── quantization.py
│   ├── memory.py
│   ├── layer_params.py
│   ├── params_blob.py
│   ├── wat_generator.py
│   └── reporting.py
│
├── wat/
│   └── model_template.wat
│
├── generated/
│   └── model.wat
│
├── reports/
│   └── *.txt
│
└── docs/
    └── *.md
```

---

# 154. Role of each output

```text
docs/
    ↓
explains the system


reports/
    ↓
explains a run


generated/
    ↓
contains the generated artifact
```

---

# 155. Even the simplest module helps the architecture

Despite containing only:

```text
one short function
```

`reporting.py` removes duplication and prevents filesystem logic from spreading across domain modules.

---

# 156. Summary

`reporting.py` has a small, well-defined responsibility:

```text
save textual content
to a file
predictably
```

The function:

```python
save_report()
```

receives:

```text
Path
+
str
```

ensures the parent directory exists through:

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

and writes the contents using:

```python
path.write_text(
    content,
    encoding="utf-8",
)
```

It does not generate reports, modify contents, interpret model data, or interfere with the inference pipeline.

It keeps three responsibilities separate:

```text
PROCESSING
    ↓
domain modules


FORMATTING
    ↓
*_to_text() functions


PERSISTENCE
    ↓
reporting.save_report()
```

This separation reinforces an important architectural rule:

```text
structured data are
the source of truth

reports are
auxiliary human-readable representations
```

`reporting.py` thus serves as the final step of a diagnostic branch of the pipeline, without creating a dependency between text reports and generation of the WebAssembly artifact.
