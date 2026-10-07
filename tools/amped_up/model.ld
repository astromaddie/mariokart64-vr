OUTPUT_FORMAT("elf32-tradbigmips")
OUTPUT_ARCH(mips)
ENTRY(render_kart)

SECTIONS
{
    . = 0x81000000;
    .recomp_force_patch : { KEEP(*(.recomp_force_patch)) }
    .text.amped_up : { *(.text.amped_up) }
    .recomp_callback.*:recomp_on_init : { KEEP(*(.recomp_callback.*:recomp_on_init)) }
    .data.amped_up : { *(.data.amped_up) }

    .rel 0 : { *(.rel*) }
    .rela 0 : { *(.rela*) }
    .symtab 0 : { *(.symtab) }
    .strtab 0 : { *(.strtab) }
    .shstrtab 0 : { *(.shstrtab) }
}
