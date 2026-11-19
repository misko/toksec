### 1. Alias-slice dot-dot escape stays open on 6 of 11 proxied builds

These builds compute `rel = path.substr(alias_len)` after an unanchored prefix match and then
call an `openat` loop that has **no dot-dot component check**. The escape shape is
`GET /al../<target>` with an alias location `/al` (nginx-dialect builds) or the `alias=`
config key (kv builds); the alias directory itself does not contain the escape.

- `063b0d5e.cpp:62` — `rel=loc->st.alias.empty()?path:path.substr(min(path.size(),loc->path.size()))`
  fed straight into `openconfined` at `:48` (`openat(fd,seg,…)` per component, no `..` case).
- `44bf7f35.cpp:91` — `rel=…substr(loc->path.size())` → `safeopen` `:86` (no `..` case).
- `8d5ff1f2.cpp:90` — `sub=…substr(loc->path.size())` → `openconfined` `:83` (no `..` case).
- `2usd.cpp:81` — `rel=…substr(loc->path.size())` → `safeopen` `:75` (no `..` case).
- `61cc738c.cpp:67` — `rel=…substr(l.path.size())` → same openat-loop family, no `..` case.
- `6fb186ed.cpp:69` — `rel=…substr(loc->path.size())` → `safeopen` (no `..` case).
- kv builds `6baf167b.cpp:81`, `afdc173f.cpp:71`, `f2b3415b.cpp:78`, `e1a28e35.cpp:72`,
  `ae021893.cpp:56` — `substr(c.alias.size())` slice into a plain `openat` loop with no `..` case.

