#!/usr/bin/env python3
"""Build a removable APR variant that respects disabled service nodes."""
from pathlib import Path

source = Path('kernel/drivers/soc/qcom/apr.c').read_text()
old1 = 'for_each_child_of_node_scoped(dev->of_node, node) {'
old2 = 'for_each_child_of_node(dev->of_node, node) {'
assert source.count(old1) == 1 and source.count(old2) == 1
source = source.replace(old1, 'for_each_available_child_of_node_scoped(dev->of_node, node) {')
source = source.replace(old2, 'for_each_available_child_of_node(dev->of_node, node) {')
out = Path('out/live-apr65')
out.mkdir(exist_ok=True)
(out / 'apr.c').write_text(source)
(out / 'Makefile').write_text('obj-m += apr.o\n')
