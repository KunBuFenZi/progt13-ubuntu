# 固件与设备输入

这里仅记录最终安装版的固件路径、大小和SHA256，不分发原厂二进制或设备校准。`installed-manifest.json`为最终Ubuntu可写层内的142个固件文件标识；早期initramfs还含GPU、ADSP及触控固件。

需要从自己的匹配ColorOS/联想固件中提取：

| 用途 | 本机原路径 / 类型 |
|---|---|
| 触控 | `/vendor/firmware/novatek_ts_fw.bin`；本次长度253952字节 |
| GPU | `/vendor/firmware/gen80000_{aqe,sqe}.fw`、`gen80000_gmu.bin`、`gen80000_zap.mbn` |
| ADSP/传感器 | `/vendor/firmware_mnt/image/adsp.*`、本机registry/config及RPC所需文件 |
| Wi-Fi | WCN7860对应的固件、board/校准及运行参数；不能使用别台设备的地址或校准 |
| 蓝牙 | WCN7860匹配的patch/NVM，路径在固件清单中 |
| 功放 | 本机AW88480配置输入，用于生成ACF/寄存器配置 |
| 启动封装 | 同设备同固件的base DTB身份、dtbo符号，以及已有boot/init_boot/vendor_boot备份的容量和rollback |

使用原始`port/build-initramfs.py`时，其固定摘要只接受本次已核对版本。其他固件不要直接删掉摘要检查，应先核对硬件与固件适配，再更新自己的输入清单。

机主已在本地保存最终Ubuntu驱动/运行配置提取归档及初期固件输入；公开仓库不需要把个人根系统或分区备份传到GitHub。禁止把私钥、Wi-Fi密码、SSH主机/登录密钥、蓝牙配对库和用户媒体加入固件目录。
