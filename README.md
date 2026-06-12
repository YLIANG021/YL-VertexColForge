# YL VertexColForge

**一个面向 Blender 5.x 的全能顶点色 / 颜色属性工作站。**

YL VertexColForge 是一款全能顶点色工作站。它不仅是一个顶点色制作工具，更是专为游戏资产制作、风格化渲染和技术美术打造的“通道级”遮罩与颜色处理中心。

插件同时支持面拐（Face Corner）和顶点（Point）两种颜色属性模式。无论是单独控制任意通道、绘制渐变、打包 RGBA、烘焙 AO 与光照，还是在贴图、权重和物体之间传递数据，都可以在一个简单的面板中一站式完成。

---

## 🌐 多语言支持

原生支持 13 种界面语言：简体中文、繁体中文、英语、日语、韩语、德语、法语、西班牙语、意大利语、波兰语、葡萄牙语、俄语和越南语。

---

## ✨ 核心特性

### 1. 👁️ 所见即所得通道预览

突破默认视图限制，直接查看 RGB、Alpha 或任意单独通道，也可以快速切换不同的颜色层。当前预览通道可以和写入通道同步，让你真正做到“看什么通道，就写什么通道”。

<img width="640" height="480" alt="切换图层和预览单通道(1)" src="https://github.com/user-attachments/assets/053caf98-2367-4bef-9f75-2914ac807d0c" />


### 2. 🎨 笔刷、填充、吸管和调色板

画笔工具只影响当前选择区域，支持快速绘制、一键填充和直接从模型上拾取颜色。内置调色板最多可保存 40 个常用颜色，方便在多个工具之间快速复用。

<img width="640" height="480" alt="笔刷" src="https://github.com/user-attachments/assets/2f016293-0fe2-4bf1-8abb-1db6bb7f6ce0" />

### 3. 🌈 任意方向视口渐变

支持任意方向、任意颜色的实时渐变预览。使用 ColorRamp 渐变条，在 3D 视图中直接拖拽创建线性或圆形渐变。渐变写入同样遵循当前通道设置，可用于 RGB 着色，也可用于单通道遮罩制作。

<img width="426" height="320" alt="屏幕渐变" src="https://github.com/user-attachments/assets/6918da9a-8944-4a77-a5f1-61594bf87fc9" />

### 4. 🗺️ 实时 UV 渐变

直接在 UV 空间中沿 UV 岛方向创建渐变，适合贴图空间遮罩、风格化色带和需要贴合 UV 布局的工作流。UV 渐变也支持当前写入通道，便于制作可打包进 RGBA 的精确控制数据。

<img width="426" height="320" alt="uv渐变" src="https://github.com/user-attachments/assets/e4d2307c-9a4a-4d2e-96b1-abdfec75ffda" />

### 5. ⚡ 快速颜色选择

点击模型上的颜色并拖动鼠标，即可实时预览选择区域，高效隔离需要继续编辑的颜色范围。选择结果可以继续用于绘制、填充、调整和其他只作用于选区的操作。

<img width="426" height="320" alt="选择(1)" src="https://github.com/user-attachments/assets/b3172d9b-6d97-4e91-bab9-637afd6013df" />

### 6. 🪞 一键颜色镜像和通道混合

点击并拖动即可完成颜色镜像，系统会自动判断镜像方向，不再需要手动选择轴向或正负方向。通道工具支持将任意通道复制到另一任意通道，并可使用替换、相乘、相加、叠加等混合方式处理通道数据。

<img width="426" height="320" alt="镜像" src="https://github.com/user-attachments/assets/05fb3548-4673-4cbf-84d7-8cea1080d6f8" />

### 7. 💡 AO、方向光和曲率遮罩

一键烘焙 AO、方向光和曲率信息，并支持实时预览相关效果。生成的结果可以写入当前通道，也可以叠加到已有颜色中，为风格化贴图、材质遮罩和明暗层次奠定基础。

<img width="426" height="320" alt="Light AO" src="https://github.com/user-attachments/assets/5c140cbd-ff24-4856-a489-c9d62106ef16" />

### 8. 🧪 实时颜色调整

支持色阶、伽马、HSV、反转、平滑模糊和 Ramp 重映射等调整，并可实时预览结果。调整过程同样尊重当前通道和选择区域，确认满意后再应用，也可以取消并恢复原始颜色。

<img width="426" height="320" alt="ADJUST" src="https://github.com/user-attachments/assets/a6c2c6e3-1997-48da-850b-50b0c3d620e6" />

### 9. 🎲 结构化随机颜色

支持按连接网格、UV 岛、材质、锐边、角度、顶点组、面或顶点生成随机颜色，是快速制作 ID Map、资产区分和风格化变化的高效方式。随机结果可写入当前通道，适合生成 RGB 色块，也适合生成单通道遮罩数据。

<img width="426" height="320" alt="随机" src="https://github.com/user-attachments/assets/b017049a-6a03-4af9-b898-88f3c73cab7d" />

### 10. 🔁 贴图、权重和物体传递

轻松实现贴图与顶点色互转、权重与顶点色互转，以及不同网格对象之间的顶点色传递。物体传递支持相同拓扑、相似模型和不同拓扑模型之间的数据迁移，适合在高低模、LOD、换模、重拓扑模型或相近资产之间复用颜色与遮罩数据。

传递工具同样支持通道级数据处理，可以读取 RGB 或单独的 R、G、B、A 通道，并将结果写入目标颜色属性中，方便在贴图、权重、颜色属性和网格对象之间建立完整的数据流。

---

## 📦 安装指南

1. 确保使用的是 **Blender 5.0** 或更高版本。
2. 下载扩展包 `.zip`，或克隆此仓库。
3. 在 Blender 中打开 `编辑 (Edit) > 偏好设置 (Preferences) > 扩展 (Extensions)`。
4. 从磁盘安装该插件，并启用 `YL VertexColForge`。
5. 在 3D 视图中选中一个网格，按 `N` 打开侧边栏，即可在 `YL VertexColForge` 面板开始创作。

## 📄 许可证

- 插件 Python 代码采用 `GPL-3.0-or-later` 许可证。
- `assets/` 目录中的捆绑资源采用 `CC0-1.0` 许可证。
