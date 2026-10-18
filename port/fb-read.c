/* Read-only capture of the active linear KMS scanout for port diagnostics. */
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include <drm/drm_fourcc.h>

#define CHECK(x) do { if (!(x)) { perror(#x); return 1; } } while (0)
int main(int argc, char **argv)
{
    uint32_t ids[32]={0};
    struct drm_mode_card_res res={0};
    struct drm_mode_crtc crtc={0};
    struct drm_mode_fb_cmd2 fb={0};
    struct drm_mode_map_dumb map={0};
    int fd=open("/dev/dri/card0",O_RDWR|O_CLOEXEC);
    CHECK(fd>=0 && argc==2);
    res.crtc_id_ptr=(uintptr_t)ids;res.count_crtcs=32;
    CHECK(ioctl(fd,DRM_IOCTL_MODE_GETRESOURCES,&res)==0 && res.count_crtcs<=32);
    for (unsigned i=0;i<res.count_crtcs;i++) {
        crtc.crtc_id=ids[i];
        CHECK(ioctl(fd,DRM_IOCTL_MODE_GETCRTC,&crtc)==0);
        if (crtc.fb_id)break;
    }
    CHECK(crtc.fb_id!=0);
    fb.fb_id=crtc.fb_id;
    CHECK(ioctl(fd,DRM_IOCTL_MODE_GETFB2,&fb)==0);
    fprintf(stderr,"FB_READ id=%u size=%ux%u format=%08x pitch=%u modifier=%"PRIx64" handle=%u\n",
            fb.fb_id,fb.width,fb.height,fb.pixel_format,fb.pitches[0],(uint64_t)fb.modifier[0],fb.handles[0]);
    CHECK(fb.handles[0] && fb.width && fb.width<=8192 && fb.height && fb.height<=8192);
    CHECK(fb.modifier[0]==DRM_FORMAT_MOD_LINEAR);
    CHECK(fb.pixel_format==DRM_FORMAT_XRGB8888 || fb.pixel_format==DRM_FORMAT_ARGB8888 ||
          fb.pixel_format==DRM_FORMAT_XRGB2101010 || fb.pixel_format==DRM_FORMAT_ARGB2101010);
    map.handle=fb.handles[0];
    CHECK(ioctl(fd,DRM_IOCTL_MODE_MAP_DUMB,&map)==0);
    size_t bytes=(size_t)fb.pitches[0]*fb.height+fb.offsets[0];
    uint8_t *data=mmap(NULL,bytes,PROT_READ,MAP_SHARED,fd,map.offset);
    CHECK(data!=MAP_FAILED);
    FILE *out=fopen(argv[1],"wb");CHECK(out!=NULL);
    unsigned scale=(fb.width+1199)/1200;
    unsigned w=(fb.width+scale-1)/scale,h=(fb.height+scale-1)/scale;
    fprintf(out,"P6\n%u %u\n255\n",w,h);
    for(unsigned y=0;y<fb.height;y+=scale)for(unsigned x=0;x<fb.width;x+=scale) {
        uint32_t p=*(uint32_t*)(data+fb.offsets[0]+(size_t)y*fb.pitches[0]+x*4);
        uint8_t rgb[3];
        if(fb.pixel_format==DRM_FORMAT_XRGB2101010 || fb.pixel_format==DRM_FORMAT_ARGB2101010) {
            rgb[0]=(p>>22)&255;rgb[1]=(p>>12)&255;rgb[2]=(p>>2)&255;
        } else {rgb[0]=(p>>16)&255;rgb[1]=(p>>8)&255;rgb[2]=p&255;}
        CHECK(fwrite(rgb,1,3,out)==3);
    }
    CHECK(fclose(out)==0);
    munmap(data,bytes);close(fd);return 0;
}
