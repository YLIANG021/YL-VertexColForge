# YL VertexColForge

- **YL VertexColForge**是一个用于 Blender 顶点色 / Color Attribute 的通道编辑工具。它为 RGB / R / G / B / A 通道提供更直接的预览、绘制、选择、渐变、随机、转换和打包流程，减少单通道编辑，也覆盖在常规顶点绘制流程中操作较繁琐的 A 通道

- 插件支持 Face Corner 与 Vertex / Point 两种颜色属性域。无论当前目标通道是 RGB、R、G、B 还是 A，填充、笔刷、渐变、随机和转换都会准确写入目标通道，不影响其他通道。

- 它适合制作游戏资产、材质遮罩、顶点色权重、通道打包数据和 Alpha 通道预览。你可以在 Blender 内完成从通道生成、编辑、整理到导出前检查的完整流程。

---

## 多语言支持

- 支持英语、简体中文、繁体中文、日语、韩语、德语、法语、西班牙语、意大利语、波兰语、葡萄牙语、俄语和越南语。

---

## 核心功能

### 1. 👁️顶点色单通道预览与编辑

- 在视口中查看完整 RGB，或单独查看 R、G、B、A 任意通道的灰度预览。单通道预览基于几何节点，非破坏性。（导出前请切回 **RGB** 预览或关闭单通道预览，避免将单通道预览修改器一并导出。）

- 预览通道与写入通道保持一致：切到 R 就查看并编辑 R，切到 A 就查看并编辑 A。填充、笔刷、渐变、随机和转换都会写入当前目标通道，不影响其他通道。

<img width="812" height="540" alt="通道预览与编辑" src="https://github.com/user-attachments/assets/d58aa3dc-12b4-4a95-9bc4-ce19ffad3360" />

### 2. 🎨顶点色通道填充与通道笔刷

- 无需切换到顶点绘制模式，也可以在对象模式或编辑模式下快速写入当前通道。填充和笔刷都支持选区限制，只修改需要的区域。


- 通道笔刷支持直接绘制单通道，也覆盖在常规顶点绘制流程中操作较繁琐的 A 通道。配合单通道预览，你可以一边查看 Alpha 灰度结果，一边实时把笔刷写入 A 通道，而不影响其他通道。

<img width="812" height="540" alt="填充和笔刷工具" src="https://github.com/user-attachments/assets/014e7aec-c834-4df2-9002-ff1433ac1531" />

### 3. ⚡顶点色交互式通道选择

- 点击模型表面即可采样当前通道颜色，拖动鼠标实时调整容差，松开后完成选择，过程直观快速

- 选择逻辑跟随当前通道：在 R 通道中按 R 值选择，在 A 通道中按 Alpha 值选择，避免 RGB 混合判断带来的干扰。

<img width="812" height="540" alt="选择" src="https://github.com/user-attachments/assets/f1f657c9-7eab-40a5-bcc4-a78f852f5b72" />

### 4. 🌈顶点色实时渐变与 Light Mask

- 使用 ColorRamp 控制颜色和过渡，并在 3D 视口中拖拽生成线性渐变、径向渐变或方向 Light Mask。支持实时预览，并可写入 RGB 或任意单通道。

- 适合制作角色、场景和道具上的光照遮罩、方向遮罩、渐变权重或风格化顶点色过渡。

<img width="812" height="540" alt="实时渐变与 Light Mask" src="https://github.com/user-attachments/assets/a0c804c6-2da5-4b68-acf1-1258edd88425" />

### 5. 🗺️UV 空间渐变

- UV Gradient 可在 UV Editor 中按 UV 空间绘制渐变，并将结果写入当前任意通道

<img width="640" height="480" alt="uv" src="https://github.com/user-attachments/assets/5dc371a9-8540-4443-b899-55428124c664" />

### 6. 📦通道打包与通道操作

- 提供通道复制、通道交换、当前通道反相和归一化工具。你可以快速整理 R / G / B / A 数据，把不同来源的遮罩打包到同一个 Vertex Color / Color Attribute 中。

- 适合导出到游戏引擎、材质系统或后续贴图转换流程中使用。

<img width="812" height="540" alt="通道打包与通道操作" src="https://github.com/user-attachments/assets/52e7b3c2-62d6-4203-a828-97732cb836d6" />

### 7. 🎲随机通道

- 将随机值写入当前 RGB / R / G / B / A 通道，并支持按 Connected Mesh、UV Island、Material、Sharp Edge 和 Angle Island 分组随机。

- 适合快速生成区域变化、材质 ID、遮罩扰动、风格化颜色变化或后续材质随机化数据。

<img width="812" height="540" alt="随机" src="https://github.com/user-attachments/assets/3b4b0e41-2e85-4020-968d-7b2be5b41afd" />

### 8. 🔁Image / Weight / Channel 转换

- 在 Image、Vertex Group Weights 和 Vertex Color 通道之间双向转换数据。可以读取或写出 RGB / R / G / B / A，作为图片、权重和顶点色通道之间的数据中转工具。

---

## 使用指南

- 安装并启用 `YL VertexColForge`。
- 在 3D 视口中选择一个网格对象，按 `N` 打开侧边栏。
- 进入 `YL VertexColForge` 面板，开启通道预览后开始编辑。

---

## 许可协议

- 插件遵循 `GPL-3.0-or-later` 许可协议。
- 捆绑资源遵循对应资源文件声明的许可协议。
