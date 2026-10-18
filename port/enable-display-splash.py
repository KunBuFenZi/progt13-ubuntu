#!/usr/bin/env python3
"""Preserve DT direct regions in MSM's private paging domain during handover.

The IOMMU core installs reserved direct mappings only in DMA domains. MSM uses
its own paging domain and must map these before enabling display DMA, and exclude
them from its GEM allocator. SMMUv2 initializes page tables at attach, so mapping
must follow attach. No framebuffer address is hardcoded in this patch.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / 'kernel/drivers/gpu/drm/msm'
path = src / 'msm_iommu.c'
text = path.read_text()
helper = '''/* TB378FC_DIRECT_REGION_HANDOVER: preserve firmware's active scanout. */
static int msm_iommu_map_direct_regions(struct iommu_domain *domain,
				       struct device *dev)
{
	struct iommu_resv_region *region;
	LIST_HEAD(regions);
	int ret = 0;

	iommu_get_resv_regions(dev, &regions);
	list_for_each_entry(region, &regions, list) {
		if (region->type != IOMMU_RESV_DIRECT &&
		    region->type != IOMMU_RESV_DIRECT_RELAXABLE)
			continue;
		ret = iommu_map(domain, region->start, region->start,
				region->length, region->prot, GFP_KERNEL);
		if (ret)
			break;
		dev_info(dev, "preserved direct scanout IOVA %pa size %zu\\n",
			 &region->start, region->length);
	}
	iommu_put_resv_regions(dev, &regions);
	return ret;
}

'''
attach = '''\tret = iommu_attach_device(iommu->domain, dev);
	if (!ret) {
		ret = msm_iommu_map_direct_regions(iommu->domain, dev);
		if (ret)
			iommu_detach_device(iommu->domain, dev);
	}'''
if 'TB378FC_DIRECT_REGION_HANDOVER' not in text:
    anchor = 'struct msm_mmu *msm_iommu_new(struct device *dev, unsigned long quirks)'
    assert text.count(anchor) == 1
    text = text.replace(anchor, helper + anchor)
    anchor = '\tret = iommu_attach_device(iommu->domain, dev);'
    assert text.count(anchor) == 1
    text = text.replace(anchor, attach)
    path.write_text(text)

# Upgrade the first offline patch revision; it was never booted on hardware.
old = '''\tret = msm_iommu_map_direct_regions(iommu->domain, dev);
	if (!ret)
		ret = iommu_attach_device(iommu->domain, dev);'''
if old in text:
    text = text.replace(old, attach)
    path.write_text(text)

path = src / 'msm_kms.c'
text = path.read_text()
if 'TB378FC_DIRECT_REGION_VA_LIMIT' not in text and 'TB378FC_LARGEST_FREE_IOVA' not in text:
    anchor = '\tstruct device *iommu_dev;'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''\tstruct device *iommu_dev;
	struct iommu_resv_region *region;
	LIST_HEAD(regions);
	u64 va_end = 0x100000000ULL;''')
    anchor = '''\tvm = msm_gem_vm_create(dev, mmu, "mdp_kms",
			       0x1000, 0x100000000 - 0x1000, true);'''
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''\t/* TB378FC_DIRECT_REGION_VA_LIMIT: keep GEM away from boot mappings.
	 * Use the free range below the first reservation for this bring-up.
	 */
	iommu_get_resv_regions(iommu_dev, &regions);
	list_for_each_entry(region, &regions, list) {
		if (region->start >= 0x1000 && region->start < va_end)
			va_end = region->start;
	}
	iommu_put_resv_regions(iommu_dev, &regions);
	vm = msm_gem_vm_create(dev, mmu, "mdp_kms",
			       0x1000, va_end - 0x1000, true);''')
    path.write_text(text)

subprocess.run([sys.executable,str(ROOT/'port/fix-display-iova.py')],check=True)
patch = subprocess.check_output(['git', '-C', str(ROOT / 'kernel'), 'diff', '--',
                                'drivers/gpu/drm/msm/msm_iommu.c',
                                'drivers/gpu/drm/msm/msm_kms.c'])
(ROOT / 'out/display-splash.patch').write_bytes(patch)
print('DISPLAY_DIRECT_REGION_PATCH_INSTALLED')
