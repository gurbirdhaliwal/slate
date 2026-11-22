# Third-party notices

Slate has zero runtime dependencies — the installed package is the Python
standard library plus the `git` binary (see `pyproject.toml`). This file covers
third-party material **redistributed inside this repository**, which is
confined to the benchmark evidence.

---

## Flask (Pallets) — BSD-3-Clause

`benchmarks/repairbench/` and `benchmarks/agentbench/` run their trials against
a checkout of [Flask](https://github.com/pallets/flask). The committed agent
transcripts under `benchmarks/*/runs/*.jsonl.gz` are verbatim session logs, so
they contain **substantial excerpts of Flask source code** as it appeared in
tool output — `src/flask/app.py`, `src/flask/sessions.py`, the project's
`pyproject.toml`, and others — along with pytest output quoting those files.

The corpus definitions (`corpus_rev2.json`, `corpus_controls.json`,
`corpus_repairs.json`) reference Flask commits by SHA and contain no Flask
source; `corpus.py` clones Flask at run time and the clone is git-ignored.

Flask is distributed under the BSD 3-Clause License, reproduced in full below.
This redistribution retains that notice as the license requires. Flask is not
affiliated with, and does not endorse, Slate.

```
Copyright 2010 Pallets

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1.  Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.

2.  Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

3.  Neither the name of the copyright holder nor the names of its
    contributors may be used to endorse or promote products derived from
    this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
