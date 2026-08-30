; boot.asm - minimal x86 real-mode boot sector.
;
; This is stage 0 of Bolt's freestanding roadmap: proof that the actual
; toolchain (assemble -> flat binary -> boot in an emulator) works end
; to end on this machine, with zero OS underneath it. No BIOS calls
; beyond the teletype interrupt used to prove it's alive; no libc; no
; host OS involved once it's loaded - this code IS what runs first.
;
; Assemble:  nasm -f bin boot.asm -o boot.bin
; Run:       qemu-system-x86_64 -fda boot.bin
;
; A real BIOS loads sector 0 of the boot device to 0x7C00 and jumps to
; it whenever the last two bytes are the 0x55 0xAA boot signature -
; this is the actual mechanism every x86 OS bootloader (including
; Linux's, Windows's, and GRUB's) relies on to get control before any
; OS exists.

[org 0x7C00]
[bits 16]

start:
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00

    mov si, msg
.print_vga:
    lodsb
    or al, al
    jz .print_serial_start
    mov ah, 0x0E        ; BIOS teletype output (int 10h) - visible on a real screen
    mov bh, 0x00
    int 0x10
    jmp .print_vga

.print_serial_start:
    mov si, msg
.print_serial:
    lodsb
    or al, al
    jz .done
    mov dx, 0x3F8       ; COM1 data register - written directly, no OS driver involved
    out dx, al
    jmp .print_serial

.done:
    cli
.hang:
    hlt
    jmp .hang

msg db "BOLT FREESTANDING: no OS, no libc, boots on bare x86.", 0

times 510-($-$$) db 0
dw 0xAA55
