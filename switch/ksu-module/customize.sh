#!/system/bin/sh
ui_print "TB378FC Ubuntu switch; Ubuntu must already be installed"
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/tb378fc-switch" 0 0 0755
set_perm "$MODPATH/device.conf" 0 0 0600
