echo Sourcing gdbinit file \n
set history save
set list 40
source ~/.gdb_stl
define vgbits
  eval "monitor get_vbits %p %d", &$arg0, sizeof($arg0)
end
