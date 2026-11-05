# Pages that compute (no code, works offline)

A page can hold an image and a little form. The publisher ships text; your computer does the arithmetic,
and what you type never leaves your machine.

![the Alternet ring](logo.png)

## Split a bill

:input total "Bill total"
:input people "People"
:input tip "Tip %"
:check round "Round up (just look at the result)"
:calc each "Each pays" = (total + total * tip / 100) / max(people, 1)

Press f to edit the fields, Tab to move, Enter when done. Everything stays on this machine, and the
page works exactly the same with no network.
