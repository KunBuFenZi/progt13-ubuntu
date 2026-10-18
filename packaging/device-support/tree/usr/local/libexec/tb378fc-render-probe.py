#!/usr/bin/env python3
"""Render a real GLES triangle and verify pixel readback on an explicit EGL device."""
import argparse
import ctypes as C
import json
import os

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--hardware',action='store_true')
args=p.parse_args()
if args.hardware:
    os.environ.pop('LIBGL_ALWAYS_SOFTWARE',None)
    os.environ.pop('GALLIUM_DRIVER',None)
else:
    os.environ['LIBGL_ALWAYS_SOFTWARE']='1'
    os.environ['GALLIUM_DRIVER']='llvmpipe'
egl=C.CDLL('libEGL.so.1')
gl=C.CDLL('libGLESv2.so.2')
V=C.c_void_p; I=C.c_int; U=C.c_uint; B=C.c_ubyte; F=C.c_float
def fn(lib,name,result,*types):
    f=getattr(lib,name);f.restype=result;f.argtypes=list(types);return f
getproc=fn(egl,'eglGetProcAddress',V,C.c_char_p)
getplatform=fn(egl,'eglGetPlatformDisplay',V,U,V,C.POINTER(C.c_ssize_t))
device_name='surfaceless software'
if args.hardware:
    query_devices=C.CFUNCTYPE(U,I,C.POINTER(V),C.POINTER(I))(getproc(b'eglQueryDevicesEXT'))
    query_string=C.CFUNCTYPE(C.c_char_p,V,I)(getproc(b'eglQueryDeviceStringEXT'))
    devices=(V*16)();count=I()
    assert query_devices(16,devices,C.byref(count))
    device=None
    for index in range(count.value):
        name=query_string(devices[index],0x3377)
        if name and name.decode()=='/dev/dri/renderD128':
            device=devices[index];device_name=name.decode();break
    assert device,'No EGL device for renderD128'
    display=getplatform(0x313F,device,None)
else:
    display=getplatform(0x31DD,None,None)
major=I();minor=I()
assert fn(egl,'eglInitialize',U,V,C.POINTER(I),C.POINTER(I))(display,C.byref(major),C.byref(minor))
assert fn(egl,'eglBindAPI',U,U)(0x30A0)
attrs=(I*15)(0x3033,1,0x3040,4,0x3024,8,0x3023,8,0x3022,8,0x3021,8,0x3038,0,0)
config=V();num=I()
assert fn(egl,'eglChooseConfig',U,V,C.POINTER(I),C.POINTER(V),I,C.POINTER(I))(display,attrs,C.byref(config),1,C.byref(num)) and num.value
surface=fn(egl,'eglCreatePbufferSurface',V,V,V,C.POINTER(I))(display,config,(I*5)(0x3057,64,0x3056,64,0x3038))
context=fn(egl,'eglCreateContext',V,V,V,V,C.POINTER(I))(display,config,None,(I*3)(0x3098,2,0x3038))
assert surface and context
assert fn(egl,'eglMakeCurrent',U,V,V,V,V)(display,surface,surface,context)
getstr=fn(gl,'glGetString',C.c_char_p,U)
renderer=getstr(0x1F01).decode()
print(json.dumps({'stage':'context','device':device_name,'renderer':renderer,'version':getstr(0x1F02).decode()}),flush=True)
if args.hardware:
    assert 'adreno' in renderer.lower(),renderer
    assert not any(word in renderer.lower() for word in ('llvmpipe','softpipe','swrast'))
create_shader=fn(gl,'glCreateShader',U,U)
shader_source=fn(gl,'glShaderSource',None,U,I,C.POINTER(C.c_char_p),C.POINTER(I))
shader_compile=fn(gl,'glCompileShader',None,U)
shader_param=fn(gl,'glGetShaderiv',None,U,U,C.POINTER(I))
shaders=[]
for kind,source in [(0x8B31,b'attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}'),
                    (0x8B30,b'precision mediump float; void main(){gl_FragColor=vec4(0.2,0.6,0.9,1.0);}')]:
    shader=create_shader(kind);text=C.c_char_p(source)
    shader_source(shader,1,C.byref(text),None);shader_compile(shader)
    ok=I();shader_param(shader,0x8B81,C.byref(ok));assert ok.value,'shader compile failed'
    shaders.append(shader)
program=fn(gl,'glCreateProgram',U)()
for shader in shaders:fn(gl,'glAttachShader',None,U,U)(program,shader)
fn(gl,'glBindAttribLocation',None,U,U,C.c_char_p)(program,0,b'position')
fn(gl,'glLinkProgram',None,U)(program)
ok=I();fn(gl,'glGetProgramiv',None,U,U,C.POINTER(I))(program,0x8B82,C.byref(ok));assert ok.value
fn(gl,'glUseProgram',None,U)(program)
fn(gl,'glViewport',None,I,I,I,I)(0,0,64,64)
vertices=(F*6)(-1,-1,3,-1,-1,3)
fn(gl,'glVertexAttribPointer',None,U,I,U,B,I,V)(0,2,0x1406,0,0,C.cast(vertices,V))
fn(gl,'glEnableVertexAttribArray',None,U)(0)
fn(gl,'glDrawArrays',None,U,I,I)(4,0,3)
fn(gl,'glFinish',None)()
pixel=(B*4)()
fn(gl,'glReadPixels',None,I,I,I,I,U,U,V)(32,32,1,1,0x1908,0x1401,C.cast(pixel,V))
error=fn(gl,'glGetError',U)()
expected=(51,153,230,255)
assert error==0,hex(error)
assert all(abs(a-b)<=2 for a,b in zip(pixel,expected)),list(pixel)
print(json.dumps({'stage':'triangle_pixel_verified','renderer':renderer,'pixel':list(pixel),'expected':expected,'hardware_requested':args.hardware}),flush=True)
fn(egl,'eglMakeCurrent',U,V,V,V,V)(display,None,None,None)
fn(egl,'eglDestroyContext',U,V,V)(display,context)
fn(egl,'eglDestroySurface',U,V,V)(display,surface)
fn(egl,'eglTerminate',U,V)(display)
