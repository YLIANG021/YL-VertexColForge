# YL VertexColForge

YL VertexColForge 是一个专注于 **Blender Vertex Color 通道工作流** 的插件。它为 Blender Vertex Color 补充了更直观的单通道查看与编辑流程，让 RGB / R / G / B / A，尤其是 A 通道的绘制、选择、渐变、随机和转换更加直接，并把填充、笔刷、渐变、选择、随机和数据转换结果准确写入目标通道。

插件同时支持 Blender 的两种 Vertex Color 域：

- Face Corner
- Vertex / Point

它特别适合制作和整理 **顶点色通道**：你可以将不同来源的遮罩、选择结果、渐变、权重或图片数据分别写入 R / G / B / A 通道，尤其适合需要单独查看、绘制或打包 Alpha / A 通道的工作流，并在 Blender 内完成预览、编辑与通道打包。最终可导出到游戏引擎或材质系统中使用。

---

## 多语言支持

支持简体中文、繁体中文、英语、日语、韩语、德语、法语、西班牙语、意大利语、波兰语、葡萄牙语、俄语和越南语。

---

## 核心功能

### 1. 👁️顶点色单通道预览与编辑

在视口中查看完整 RGB，或单独查看 R、G、B、A 任意通道的灰度预览。单通道预览基于几何节点，非破坏性。（导出前请切回 **RGB** 预览或关闭单通道预览，避免将单通道预览修改器一并导出。）

预览通道与写入通道保持一致：切到 R 就查看并编辑 R，切到 A 就查看并编辑 A。填充、笔刷、渐变、随机和转换都会写入当前目标通道，不影响其他通道。

<img width="812" height="540" alt="通道预览与编辑" src="https://github.com/user-attachments/assets/d58aa3dc-12b4-4a95-9bc4-ce19ffad3360" />

### 2. 🎨顶点色通道填充与通道笔刷

填充和笔刷工具可直接在对象模式或编辑模式下操作，无需切换到顶点绘制模式。两个工具可以快速写入单通道，并可配合选区限制，只修改需要的区域。


通道笔刷支持直接绘制当前通道，包括 Blender 原生顶点绘制很难处理的 A 通道。配合单通道预览，你可以一边查看 Alpha 灰度结果，一边实时把笔刷写入 A 通道，而不影响其他通道

<img width="812" height="540" alt="填充和笔刷工具" src="https://github.com/user-attachments/assets/014e7aec-c834-4df2-9002-ff1433ac1531" />

### 3. ⚡顶点色交互式通道选择

点击模型表面即可采样当前通道颜色，拖动鼠标实时调整容差，松开后完成选择，过程直观快速

<img width="812" height="540" alt="选择" src="https://github.com/user-attachments/assets/f1f657c9-7eab-40a5-bcc4-a78f852f5b72" />

### 4. 🌈顶点色实时渐变与 Light Mask

使用 ColorRamp 控制颜色和过渡，并在 3D 视口中拖拽生成线性渐变、径向渐变或方向 Light Mask。支持实时预览，并可写入 RGB 或任意单通道。

<img width="812" height="540" alt="实时渐变与 Light Mask" src="https://github.com/user-attachments/assets/a0c804c6-2da5-4b68-acf1-1258edd88425" />

### 5. 🗺️UV 空间渐变

UV Gradient 可在 UV Editor 中按 UV 空间绘制渐变，并将结果写入当前任意通道

<img width="640" height="480" alt="uv" src="https://github.com/user-attachments/assets/5dc371a9-8540-4443-b899-55428124c664" />

### 6. 📦通道打包与通道操作

支持通道复制、通道交换、当前通道反相和归一化。你可以快速整理通道数据，把不同遮罩打包到同一个 Vertex Color 中。

<img width="812" height="540" alt="通道打包与通道操作" src="https://github.com/user-attachments/assets/52e7b3c2-62d6-4203-a828-97732cb836d6" />

### 7. 🎲随机通道

随机工具可将随机值写入当前 RGB / R / G / B / A 通道，并支持按 Connected Mesh、UV Island、Material、Sharp Edge 和 Angle Island 分组随机。

<img width="812" height="540" alt="随机" src="https://github.com/user-attachments/assets/3b4b0e41-2e85-4020-968d-7b2be5b41afd" />

### 8. 🔁Image / Weight / Channel 转换

Convert 工具支持 Image、Vertex Group Weights 与 Vertex Color 通道之间的双向转换，可读取或写出 RGB / R / G / B / A 数据，适合作为图片、权重和 Vertex Color 通道之间的数据中转工具。

---

## 使用指南

- 安装并启用 `YL VertexColForge`。
- 在 3D 视口中选择一个网格对象，按 `N` 打开侧边栏。
- 进入 `YL VertexColForge` 面板，开启通道预览后开始编辑。

---

## 许可协议

- 插件遵循 `GPL-3.0-or-later` 许可协议。
- 捆绑资源遵循对应资源文件声明的许可协议。
