#!/usr/bin/env python3
"""Use the largest free display IOVA interval, preserving every reservation.

The original handover patch truncated the allocator at the FIRST reservation.
On this device that is the 128MiB MSI window, not the high boot framebuffer.
Three 32MiB desktop buffers fit; rotation's additional buffers fail ENOSPC.
"""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent
path=ROOT/'kernel/drivers/gpu/drm/msm/msm_kms.c'
text=path.read_text()
if 'TB378FC_LARGEST_FREE_IOVA' not in text:
    old='\tu64 va_end = 0x100000000ULL;'
    assert text.count(old)==1
    text=text.replace(old,'\tu64 va_start = 0x1000, va_size = 0, cursor = 0x1000;\n\tconst u64 va_limit = 0x100000000ULL;')
    start=text.index('\t/* TB378FC_DIRECT_REGION_VA_LIMIT:')
    end=text.index('\n\tif (IS_ERR(vm))',start)
    text=text[:start]+'''\t/* TB378FC_LARGEST_FREE_IOVA: reservations need not be sorted.
\t * Keep both the MSI window and inherited scanout outside the allocator.
\t * Truncating at the first reservation left only 128 MiB on TB378FC.
\t */
\tiommu_get_resv_regions(iommu_dev, &regions);
\twhile (cursor < va_limit) {
\t\tu64 next = va_limit, blocked_end = cursor;

\t\tlist_for_each_entry(region, &regions, list) {
\t\t\tu64 end;

\t\t\tif (!region->length || region->start >= va_limit)
\t\t\t\tcontinue;
\t\t\tend = region->start + min_t(u64, region->length,
\t\t\t\t\t\tva_limit - region->start);
\t\t\tif (end <= cursor)
\t\t\t\tcontinue;
\t\t\tif (region->start <= cursor)
\t\t\t\tblocked_end = max(blocked_end, end);
\t\t\telse
\t\t\t\tnext = min_t(u64, next, region->start);
\t\t}
\t\tif (blocked_end > cursor) {
\t\t\tcursor = blocked_end;
\t\t\tcontinue;
\t\t}
\t\tif (next - cursor > va_size) {
\t\t\tva_start = cursor;
\t\t\tva_size = next - cursor;
\t\t}
\t\tcursor = next;
\t}
\tiommu_put_resv_regions(iommu_dev, &regions);
\tif (!va_size) {
\t\tmmu->funcs->destroy(mmu);
\t\treturn ERR_PTR(-ENOSPC);
\t}
\tdrm_info(dev, "KMS IOVA aperture %#llx+%#llx\\n", va_start, va_size);
\tvm = msm_gem_vm_create(dev, mmu, "mdp_kms", va_start, va_size, true);''' + text[end:]
    path.write_text(text)
# Upgrade an already applied first revision without altering its interval logic.
updated=text.replace('if (region->start >= va_limit)',
                     'if (!region->length || region->start >= va_limit)')
updated=updated.replace('end = min_t(u64, va_limit, region->start + region->length);',
    'end = region->start + min_t(u64, region->length,\n\t\t\t\t\t\tva_limit - region->start);')
if updated!=text:path.write_text(updated)
(ROOT/'out/display-iova.patch').write_bytes(subprocess.check_output([
    'git','-C',str(ROOT/'kernel'),'diff','--','drivers/gpu/drm/msm/msm_kms.c']))
print('DISPLAY_IOVA_LARGEST_FREE_INTERVAL_PATCH_INSTALLED')
