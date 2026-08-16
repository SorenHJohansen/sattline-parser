#!/bin/bash -eu

# Build and install the project (explicit Python 3.13)
/usr/local/bin/python3.13 -m pip install .

CORPUS_SRC="$SRC/sattline-parser/tests/fixtures/corpus"

# Build fuzzers into $OUT from repo-owned source harnesses only.
for fuzzer in $(find "$SRC/sattline-parser/src" -name '*_fuzzer.py'); do
  fuzzer_basename=$(basename -s .py "$fuzzer")
  fuzzer_package=${fuzzer_basename}.pkg

  /usr/local/bin/python3.13 -m PyInstaller \
    --distpath "$OUT" \
    --onefile \
    --name "$fuzzer_package" \
    --collect-data=sattline_parser \
    --hidden-import=sattline_parser.models._ast_model_support \
    "$fuzzer"

  echo "#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
this_dir=\$(dirname \"\$0\")
LD_PRELOAD=\$this_dir/sanitizer_with_fuzzer.so \
ASAN_OPTIONS=\$ASAN_OPTIONS:symbolize=1:external_symbolizer_path=\$this_dir/llvm-symbolizer:detect_leaks=0 \
\$this_dir/$fuzzer_package \$@" > "$OUT/$fuzzer_basename"
  chmod +x "$OUT/$fuzzer_basename"

  # Seed each fuzzer with the repository corpus so libFuzzer starts from real
  # SattLine inputs instead of an empty corpus (which yields no coverage and no
  # mutation guidance).
  seed_dir="$OUT/${fuzzer_basename}_seed_corpus"
  mkdir -p "$seed_dir"
  if [ -d "$CORPUS_SRC" ]; then
    find "$CORPUS_SRC" -name '*.s' -type f -exec cp {} "$seed_dir/" \;
  fi
  echo "Seeded $fuzzer_basename with $(ls -1 "$seed_dir" | wc -l) corpus files"
done

# Make python3 resolve to Python 3.13 for any post-build checks
rm -f /usr/local/bin/python3
ln -s /usr/local/bin/python3.13 /usr/local/bin/python3
