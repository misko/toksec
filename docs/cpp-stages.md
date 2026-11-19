# C++ Stages 1 and 2

The C++ variants use the same English HTTP contracts, smoke selection, independent
API cases, workload matrices, resource limits, tag policy and spending controls as
Rust. Language is an explicit run property, not an inferred source extension.
No starter or previous implementation is sent to the builder.

The source is main.cpp. Production builds use g++ -std=c++20 -O3 -DNDEBUG -pthread.
Standalone test programs use the same options without -DNDEBUG, so assertions work.
Compilation, execution, tests and Git operations all use the existing sandboxes.
C++ standard headers, C standard headers and POSIX/Linux OS headers are allowed.
Third-party HTTP, crypto/TLS, compression and networking libraries are prohibited.
Header dependencies must belong to the installed libc/kernel/GCC/C++ development
packages. The harness also checks linked dependencies and rejects ordinary runtime
library-loading symbols. These checks supplement the language contract; they are
not a proof against a deliberately evasive implementation.

Stage 1 has one visible GET smoke check; Stage 2 has GET, HEAD and sequential
persistent GET smoke checks. Full API feedback remains withheld until the run ends.
Tag source, checkpoint recovery, standalone evaluation and post-run plots all use
the run's selected language. The C++ variants currently support only Stages 1 and 2.
They are plaintext HTTP; encryption is outside their requirements.

```sh
python3 -m toksec publish --language cpp --output tasks/v7/cpp
python3 -m toksec init --campaign .runs/cpp-stage1 --budget-usd 3
python3 -m toksec prepare --campaign .runs/cpp-stage1 --level 1 --language cpp --model gpt-6.1-terra --wall-seconds 7200
./evaluate.py --section api --level 1 --language cpp --source /path/to/main.cpp
./evaluate.py --section performance --level 2 --language cpp --source /path/to/main.cpp
```

Each requested C++ run has its own fresh $3 campaign and two-hour builder ceiling.
Both use Terra medium and service_tier=default. They run sequentially on CPUs 5–9,
separate from the existing Rust benchmark's CPUs 0–4. The queued run's two-hour
clock starts when its model loop starts, not while waiting. CPU affinity is recorded
in each manifest. Post-run grading and plotting make no additional model calls.
The strict $2.745 next-call reservation may stop a run well below $3 settled spend.
