; synthetic sliced gcode — 3-color, no-AMS / M400 U1 preset
; HEADER BLOCK (slicer chatter the parser must ignore)
M73 P0 R10
M201 X20000 Y20000 Z500 E5000
M204 S10000
G90
M83
M104 S220
M109 S220
G28 ; home all axes
; ---- print filament 1 (the starting color, no change) ----
G1 Z0.2 F600
G1 X10 Y10 E1.0 F1800
G1 X90 Y10 E5.0
; layer 12 — change #1 to filament 2
M1020 S1            ; select project filament 2  (S1 = filament #2)
M400 U1             ; pause for manual swap
G1 X10 Y90 E5.0
G1 X90 Y90 E5.0
; some noise: a bare M400 with no U1 must NOT count as a change
M400
; layer 30 — change #2 to filament 5
M1020 S4 ; select project filament 5 (S4 = filament #5)
   M400 U1   ; indented + trailing comment, still a pause
G1 X10 Y10 E5.0
; an M1020 that gets superseded before the next pause
M1020 S2
M1020 S0            ; final selection wins -> change #3 is filament 1
M400 U1
G1 X50 Y50 E2.0
M104 S0
M84
; end of print
