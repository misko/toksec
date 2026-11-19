### 5. Upgrade/h2c: stripped as hop-by-hop; no protocol switch exists

`h2c` does not appear in any source; `upgrade` appears only inside hop-by-hop strip lists.
No build can switch protocols, so no h2c smuggling pipe exists in this corpus. Hop-strip
cites: 063b0d5e:59, 29d05850:50, 44bf7f35:87, 6baf167b:59.

